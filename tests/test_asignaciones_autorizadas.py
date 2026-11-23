"""Caracterizacion de asignaciones autorizadas de RedProtege (Fase 1.2-B).

Pruebas aisladas: no usan MySQL, SMTP ni generan documentos.
Ejecutar: python -m unittest tests.test_asignaciones_autorizadas -v
"""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints import casos as modulo


class TestAsignacionesAutorizadas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "pruebas-asignaciones-redprotege-sin-db"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol="Admin", identificador=10, ciclos=None):
        return SimpleNamespace(
            id=identificador,
            nombre_completo="Usuario de prueba",
            rol=SimpleNamespace(nombre=rol),
            ciclos=list(ciclos or []),
            subrogante_de=None,
            activo=True,
            is_authenticated=True,
            email="profesional@example.invalid",
        )

    @staticmethod
    def caso(*, ts=None, coordinador=None, estado="PENDIENTE_RESCATAR"):
        return SimpleNamespace(
            id=1, folio_atencion="FICT-001", ciclo_vital_id=2,
            estado=estado, asignado_ts_id=ts,
            asignado_a_usuario_id=ts, asignado_coord_id=coordinador,
            asignado_por_usuario_id=None, asignado_at=None,
        )

    def ejecutar(self, *, rol="Admin", caso=None, ts_id=None, coord_id=None,
                profesionales=None, error_commit=False):
        caso = caso or self.caso()
        profesionales = profesionales or {}
        datos = {"asignar_funcionario": "1"}
        if ts_id is not None:
            datos["ts_id"] = str(ts_id)
        if coord_id is not None:
            datos["coord_id"] = str(coord_id)
        # El Referente de prueba debe pertenecer al ciclo del caso.
        ciclos_usuario = (
            [SimpleNamespace(id=caso.ciclo_vital_id)]
            if rol == "Referente"
            else None
        )

        usuario = self.usuario(
            rol=rol,
            ciclos=ciclos_usuario
        )
        with self.app.test_request_context("/casos/ver/1", method="POST", data=datos):
            with ExitStack() as stack:
                stack.enter_context(patch.object(modulo, "current_user", usuario))
                caso_query = MagicMock()
                caso_query.get_or_404.return_value = caso
                stack.enter_context(patch.object(modulo.Caso, "query", caso_query))
                usuarios_query = MagicMock()
                usuarios_query.get.side_effect = lambda identificador: profesionales.get(identificador)
                usuarios_query.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
                stack.enter_context(patch.object(modulo.Usuario, "query", usuarios_query))
                sesion = MagicMock()
                if error_commit:
                    sesion.commit.side_effect = RuntimeError("Fallo simulado en commit")
                stack.enter_context(patch.object(modulo.db, "session", sesion))
                stack.enter_context(patch.object(modulo, "obtener_hora_chile", return_value=None))
                log = stack.enter_context(patch.object(modulo, "registrar_log"))
                email = stack.enter_context(patch.object(modulo, "enviar_aviso_asignacion", return_value=True))
                render = stack.enter_context(patch.object(modulo, "render_template", return_value="VISTA_SIMULADA"))
                respuesta = modulo.ver_caso.__wrapped__(1)
                return respuesta, caso, sesion, log, email, render

    def test_admin_asigna_trabajador_social_y_avanza_estado(self):
        profesional = self.usuario("Trabajador(a) Social", identificador=20)
        respuesta, caso, sesion, log, email, render = self.ejecutar(
            ts_id=20, profesionales={20: profesional}
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.location.endswith("/casos/ver/1"))
        self.assertEqual(caso.asignado_ts_id, 20)
        self.assertEqual(caso.asignado_a_usuario_id, 20)  # compatibilidad legacy
        self.assertEqual(caso.asignado_por_usuario_id, 10)
        self.assertEqual(caso.estado, "EN_SEGUIMIENTO")
        acciones = [llamada.args[0].accion for llamada in sesion.add.call_args_list]
        self.assertEqual(acciones, ["ASIGNACION_TS", "EMAIL_ASIGNACION"])
        self.assertEqual(sesion.commit.call_count, 2)
        email.assert_called_once()
        log.assert_called_once()
        render.assert_not_called()

    def test_torre_control_reasigna_trabajador_social_y_audita_anterior(self):
        profesional = self.usuario("Trabajador(a) Social", identificador=21)
        _, caso, sesion, _, _, _ = self.ejecutar(
            rol="Torre Control", caso=self.caso(ts=20, estado="EN_SEGUIMIENTO"),
            ts_id=21, profesionales={21: profesional}
        )
        self.assertEqual(caso.asignado_ts_id, 21)
        self.assertEqual(caso.asignado_a_usuario_id, 21)
        auditoria = sesion.add.call_args_list[0].args[0]
        self.assertEqual(auditoria.accion, "REASIGNACION_TS")
        self.assertEqual(auditoria.detalles_cambio["previo_id"], 20)
        self.assertEqual(auditoria.detalles_cambio["nuevo_id"], 21)

    def test_referente_asigna_coordinador_del_ciclo_correspondiente(self):
        profesional = self.usuario("Coordinador Ciclo", identificador=30,
                                    ciclos=[SimpleNamespace(id=2)])
        respuesta, caso, sesion, _, email, _ = self.ejecutar(
            rol="Referente", coord_id=30, profesionales={30: profesional}
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(caso.asignado_coord_id, 30)
        self.assertEqual(sesion.add.call_args_list[0].args[0].accion, "ASIGNACION_COORD")
        self.assertEqual(sesion.commit.call_count, 2)
        email.assert_called_once()

    def test_profesional_inactivo_no_se_asigna_y_no_hay_escrituras(self):
        profesional = self.usuario("Trabajador(a) Social", identificador=20)
        profesional.activo = False
        respuesta, caso, sesion, log, email, _ = self.ejecutar(
            ts_id=20, profesionales={20: profesional}
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertIsNone(caso.asignado_ts_id)
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()
        log.assert_not_called()
        email.assert_not_called()

    def test_fallo_primer_commit_provoca_rollback_y_no_envia_correo(self):
        profesional = self.usuario("Trabajador(a) Social", identificador=20)
        respuesta, _, sesion, log, email, render = self.ejecutar(
            ts_id=20, profesionales={20: profesional}, error_commit=True
        )
        self.assertEqual(respuesta, "VISTA_SIMULADA")
        sesion.commit.assert_called_once()
        sesion.rollback.assert_called_once()
        log.assert_not_called()
        email.assert_not_called()
        render.assert_called_once()


if __name__ == "__main__":
    unittest.main()
