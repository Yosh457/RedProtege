"""Caracterización de consistencia de asignaciones de RedProtege.

Pruebas con mocks: no conectan MySQL ni envían correos.
Ejecutar: python -m unittest tests.test_consistencia_asignaciones -v
"""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints import casos as modulo


class TestConsistenciaAsignaciones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "pruebas-consistencia-asignaciones-sin-db"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol="Admin", identificador=10):
        return SimpleNamespace(
            id=identificador, nombre_completo="Usuario de prueba",
            rol=SimpleNamespace(nombre=rol), ciclos=[], subrogante_de=None,
            activo=True, is_authenticated=True,
            email="prueba@example.invalid",
        )

    @staticmethod
    def caso(ts=None, coord=None, estado="EN_SEGUIMIENTO"):
        return SimpleNamespace(
            id=1, folio_atencion="FICT-001", ciclo_vital_id=2,
            estado=estado, asignado_ts_id=ts,
            asignado_a_usuario_id=ts, asignado_coord_id=coord,
            asignado_por_usuario_id=None, asignado_at=None,
        )

    def ejecutar(self, *, caso, ts_id=None, coord_id=None,
                email_resultado=True, email_error=None,
                error_segundo_commit=False):
        datos = {"asignar_funcionario": "1"}
        if ts_id is not None:
            datos["ts_id"] = str(ts_id)
        if coord_id is not None:
            datos["coord_id"] = str(coord_id)
        profesionales = {
            20: self.usuario("Trabajador(a) Social", 20),
            21: self.usuario("Trabajador(a) Social", 21),
            30: self.usuario("Coordinador Ciclo", 30),
        }
        with self.app.test_request_context("/casos/ver/1", method="POST", data=datos):
            with ExitStack() as stack:
                stack.enter_context(patch.object(modulo, "current_user", self.usuario()))
                cq = MagicMock()
                cq.get_or_404.return_value = caso
                stack.enter_context(patch.object(modulo.Caso, "query", cq))
                uq = MagicMock()
                uq.get.side_effect = lambda user_id: profesionales.get(user_id)
                uq.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
                stack.enter_context(patch.object(modulo.Usuario, "query", uq))
                sesion = MagicMock()
                if error_segundo_commit:
                    sesion.commit.side_effect = [None, RuntimeError("Segundo commit simulado")]
                stack.enter_context(patch.object(modulo.db, "session", sesion))
                stack.enter_context(patch.object(modulo, "obtener_hora_chile", return_value=None))
                registro = stack.enter_context(patch.object(modulo, "registrar_log"))
                opciones_email = {"return_value": email_resultado}
                if email_error is not None:
                    opciones_email = {"side_effect": RuntimeError(email_error)}
                correo = stack.enter_context(patch.object(modulo, "enviar_aviso_asignacion", **opciones_email))
                render = stack.enter_context(patch.object(modulo, "render_template", return_value="VISTA_SIMULADA"))
                respuesta = modulo.ver_caso.__wrapped__(1)
                return respuesta, caso, sesion, registro, correo, render

    def test_repetir_mismo_trabajador_social_no_escribe_ni_notifica(self):
        caso = self.caso(ts=20)
        respuesta, caso, sesion, registro, correo, render = self.ejecutar(caso=caso, ts_id=20)
        self.assertEqual(respuesta, "VISTA_SIMULADA")
        self.assertEqual(caso.asignado_ts_id, 20)
        self.assertIsNone(caso.asignado_por_usuario_id)
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()
        registro.assert_not_called()
        correo.assert_not_called()
        render.assert_called_once()

    def test_repetir_mismo_coordinador_no_escribe_ni_notifica(self):
        caso = self.caso(coord=30)
        respuesta, caso, sesion, registro, correo, render = self.ejecutar(caso=caso, coord_id=30)
        self.assertEqual(respuesta, "VISTA_SIMULADA")
        self.assertEqual(caso.asignado_coord_id, 30)
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()
        registro.assert_not_called()
        correo.assert_not_called()
        render.assert_called_once()

    def test_fallo_segundo_commit_sucede_despues_de_asignar_y_notificar(self):
        respuesta, caso, sesion, registro, correo, render = self.ejecutar(
            caso=self.caso(), ts_id=21, error_segundo_commit=True,
        )
        self.assertEqual(respuesta, "VISTA_SIMULADA")
        self.assertEqual(caso.asignado_ts_id, 21)
        self.assertEqual(caso.asignado_a_usuario_id, 21)
        self.assertEqual(sesion.commit.call_count, 2)
        sesion.rollback.assert_called_once()
        acciones = [call.args[0].accion for call in sesion.add.call_args_list]
        self.assertEqual(acciones, ["ASIGNACION_TS", "EMAIL_ASIGNACION"])
        correo.assert_called_once()
        registro.assert_called_once()
        render.assert_called_once()

    def test_correo_rechazado_registra_error_envio_y_no_revierte_asignacion(self):
        respuesta, caso, sesion, registro, correo, render = self.ejecutar(
            caso=self.caso(), ts_id=21, email_resultado=False,
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(caso.asignado_ts_id, 21)
        self.assertEqual(sesion.commit.call_count, 2)
        sesion.rollback.assert_not_called()
        acciones = [call.args[0].accion for call in sesion.add.call_args_list]
        self.assertEqual(acciones, ["ASIGNACION_TS", "EMAIL_ASIGNACION"])
        auditoria_email = sesion.add.call_args_list[1].args[0]
        self.assertEqual(auditoria_email.detalles_cambio["status"], "ERROR_ENVIO")
        correo.assert_called_once()
        render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
