"""Fase 1.2-B: caracterización de gestión clínica autorizada sin MySQL.

Ejecutar: python -m unittest tests.test_gestion_autorizada -v
Solo invoca la vista sin el decorador login_required. No cubre CSRF ni HTTP real.
"""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints import casos as modulo


class TestGestionAutorizada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "test-gestion-redprotege-sin-base"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol="Admin", identificador=10):
        return SimpleNamespace(id=identificador, rol=SimpleNamespace(nombre=rol))

    @staticmethod
    def caso(ts=20, legacy_ts=None):
        # Datos ficticios suficientes para completar un POST sin campos opcionales.
        return SimpleNamespace(
            id=1, estado="EN_SEGUIMIENTO", asignado_ts_id=ts,
            asignado_a_usuario_id=legacy_ts,
            origen_nombres="Paciente", origen_apellidos="Ficticio",
            paciente_doc_tipo="RUT", paciente_doc_numero=None,
            paciente_fecha_nacimiento=None,
            paciente_direccion_calle=None, paciente_direccion_numero=None,
            paciente_domicilio=None,
            denuncia_realizada=False, denuncia_institucion_id=None,
            denuncia_institucion_otro=None, denuncia_profesional_nombre=None,
            denuncia_profesional_cargo=None,
            acompanante_presente=False, acompanante_telefono=None,
            acompanante_nombre=None, acompanante_parentesco=None,
            acompanante_telefono_tipo=None, acompanante_doc_tipo=None,
            acompanante_doc_numero=None, acompanante_doc_otro_descripcion=None,
            acompanante_direccion_calle=None, acompanante_direccion_numero=None,
            acompanante_domicilio=None,
            recinto_inscrito_id=None, recinto_inscrito_otro_texto=None,
            ingreso_lain=False, fallecido=False, fecha_defuncion=None,
            control_sanitario=None, gestion_vacunas=None,
            gestion_judicial=None, gestion_salud_mental=None, gestion_cosam=None,
            observaciones_gestion=None,
        )

    def ejecutar(self, usuario, caso, *, datos=None, error_commit=False):
        if datos is None:
            datos = {"nueva_observacion": "Seguimiento ficticio de prueba",
                     "control_sanitario": "AL_DIA"}
        with self.app.test_request_context("/casos/gestionar/1", method="POST", data=datos):
            with ExitStack() as stack:
                stack.enter_context(patch.object(modulo, "current_user", usuario))
                q_casos = MagicMock()
                q_casos.get_or_404.return_value = caso
                stack.enter_context(patch.object(modulo.Caso, "query", q_casos))
                # Son consultas de catálogos, nunca deben llegar a MySQL.
                q_est = MagicMock()
                q_est.filter_by.return_value.order_by.return_value.all.return_value = []
                stack.enter_context(patch.object(modulo.CatalogoEstablecimiento, "query", q_est))
                q_inst = MagicMock()
                q_inst.filter_by.return_value.order_by.return_value.all.return_value = []
                stack.enter_context(patch.object(modulo.CatalogoInstitucion, "query", q_inst))
                sesion = MagicMock()
                stack.enter_context(patch.object(modulo.db, "session", sesion))
                stack.enter_context(patch.object(modulo, "obtener_hora_chile", return_value=None))
                render = stack.enter_context(patch.object(modulo, "render_template", return_value="FORMULARIO_SIMULADO"))
                if error_commit:
                    sesion.commit.side_effect = RuntimeError("Error ficticio de persistencia")
                respuesta = modulo.gestionar_caso.__wrapped__(1)
                return respuesta, sesion, render

    def test_admin_registra_gestion_y_auditoria(self):
        caso = self.caso()
        respuesta, sesion, render = self.ejecutar(self.usuario(), caso)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.location.endswith("/casos/ver/1"))
        self.assertEqual(caso.observaciones_gestion, "Seguimiento ficticio de prueba")
        self.assertEqual(caso.control_sanitario, "AL_DIA")
        registros = [call.args[0] for call in sesion.add.call_args_list]
        self.assertEqual(len(registros), 2)
        self.assertEqual({type(r).__name__ for r in registros}, {"CasoGestion", "AuditoriaCaso"})
        gestion = next(r for r in registros if type(r).__name__ == "CasoGestion")
        auditoria = next(r for r in registros if type(r).__name__ == "AuditoriaCaso")
        self.assertEqual((gestion.caso_id, gestion.usuario_id), (1, 10))
        self.assertEqual(gestion.observacion, "Seguimiento ficticio de prueba")
        self.assertEqual(auditoria.accion, "GESTION_CLINICA")
        self.assertEqual((auditoria.caso_id, auditoria.usuario_id), (1, 10))
        sesion.commit.assert_called_once()
        sesion.rollback.assert_not_called()
        render.assert_not_called()

    def test_torre_control_registra_gestion(self):
        respuesta, sesion, _ = self.ejecutar(self.usuario("Torre Control"), self.caso(), datos={})
        self.assertEqual(respuesta.status_code, 302)
        sesion.commit.assert_called_once()
        self.assertEqual(sesion.add.call_count, 1)  # solo auditoría, sin observación

    def test_trabajador_social_asignado_registra_gestion(self):
        respuesta, sesion, _ = self.ejecutar(self.usuario("Trabajador(a) Social", 20), self.caso())
        self.assertEqual(respuesta.status_code, 302)
        sesion.commit.assert_called_once()

    def test_trabajador_social_legacy_registra_gestion(self):
        respuesta, sesion, _ = self.ejecutar(self.usuario("Trabajador(a) Social", 10), self.caso(ts=99, legacy_ts=10))
        self.assertEqual(respuesta.status_code, 302)
        sesion.commit.assert_called_once()

    def test_fallo_commit_invoca_rollback_y_no_devuelve_exito(self):
        respuesta, sesion, render = self.ejecutar(self.usuario(), self.caso(), error_commit=True)
        self.assertEqual(respuesta, "FORMULARIO_SIMULADO")
        sesion.commit.assert_called_once()
        sesion.rollback.assert_called_once()
        render.assert_called_once()


if __name__ == "__main__":
    unittest.main()
