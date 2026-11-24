"""Fase 1.2-B: caracterizacion de rechazos de operaciones POST.

No usa MySQL, no envia correo, no genera PDF y no modifica datos reales.
Caracteriza las reglas VIGENTES, no los permisos futuros por recinto.
Ejecutar: python -m unittest tests.test_post_denegaciones -v
"""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import Forbidden

from app import create_app
from blueprints import casos as modulo_casos


class TestPostDenegaciones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "redprotege-pruebas-post-sin-bd"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, usuario_id=10):
        return SimpleNamespace(
            id=usuario_id,
            rol=SimpleNamespace(nombre=rol),
            email="usuario@example.invalid",
            nombre_completo="Usuario Ficticio",
        )

    @staticmethod
    def caso(estado="EN_SEGUIMIENTO", ts_id=99, legacy_id=None):
        return SimpleNamespace(
            id=1,
            estado=estado,
            asignado_ts_id=ts_id,
            asignado_a_usuario_id=legacy_id,
            folio_atencion="FICTICIO-001",
        )

    def comprobar_rechazo(self, funcion, ruta, usuario, caso=None, data=None, destino="/casos/ver/1"):
        """Aisla consultas/efectos externos y exige que el rechazo sea sin escritura."""
        consulta_caso = MagicMock()
        consulta_caso.get_or_404.return_value = caso
        sesion = MagicMock()
        # Si la ruta intenta escribir, la prueba falla inmediatamente.
        for operacion in ("add", "commit", "delete", "flush", "rollback"):
            getattr(sesion, operacion).side_effect = AssertionError(
                "Operacion de BD inesperada: " + operacion
            )

        with self.app.test_request_context(ruta, method="POST", data=data or {}):
            with ExitStack() as stack:
                stack.enter_context(patch.object(modulo_casos, "current_user", usuario))
                stack.enter_context(patch.object(modulo_casos.Caso, "query", consulta_caso))
                stack.enter_context(patch.object(modulo_casos.Usuario, "query", MagicMock(side_effect=AssertionError("Consulta de usuarios inesperada"))))
                stack.enter_context(patch.object(modulo_casos.db, "session", sesion))
                log = stack.enter_context(patch.object(modulo_casos, "registrar_log"))
                pdf = stack.enter_context(patch.object(modulo_casos, "generar_acta_cierre_pdf"))
                aviso_cierre = stack.enter_context(patch.object(modulo_casos, "enviar_aviso_cierre"))
                aviso_asignacion = stack.enter_context(patch.object(modulo_casos, "enviar_aviso_asignacion"))
                aviso_subrogancia = stack.enter_context(patch.object(modulo_casos, "enviar_aviso_subrogancia"))
                # Se salta unicamente @login_required: se prueba la politica
                # de la funcion, no una sesion HTTP real (cubierta aparte).
                # Gestion clinica ahora deniega mediante 403. Las otras rutas
                # conservan temporalmente sus redirecciones heredadas.
                if funcion is modulo_casos.gestionar_caso:
                    with self.assertRaises(Forbidden):
                        funcion.__wrapped__(1)
                else:
                    respuesta = funcion.__wrapped__(1) if caso is not None else funcion.__wrapped__()
                    self.assertEqual(respuesta.status_code, 302)
                    self.assertTrue(
                        respuesta.headers["Location"].endswith(destino),
                        respuesta.headers["Location"],
                    )
        if caso is not None:
            consulta_caso.get_or_404.assert_called_once_with(1)
        else:
            consulta_caso.get_or_404.assert_not_called()
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()
        sesion.delete.assert_not_called()
        sesion.flush.assert_not_called()
        sesion.rollback.assert_not_called()
        log.assert_not_called()
        pdf.assert_not_called()
        aviso_cierre.assert_not_called()
        aviso_asignacion.assert_not_called()
        aviso_subrogancia.assert_not_called()

    def test_visualizador_no_puede_gestionar_por_post(self):
        caso = self.caso()
        self.comprobar_rechazo(modulo_casos.gestionar_caso, "/casos/gestionar/1",
                              self.usuario("Visualizador"), caso)
        self.assertEqual(caso.estado, "EN_SEGUIMIENTO")

    def test_trabajador_social_ajeno_no_puede_gestionar_por_post(self):
        self.comprobar_rechazo(modulo_casos.gestionar_caso, "/casos/gestionar/1",
                              self.usuario("Trabajador(a) Social"), self.caso(ts_id=99))

    def test_coordinador_ciclo_no_puede_gestionar_por_post(self):
        self.comprobar_rechazo(modulo_casos.gestionar_caso, "/casos/gestionar/1",
                              self.usuario("Coordinador Ciclo"), self.caso())

    def test_admin_no_gestiona_caso_cerrado(self):
        self.comprobar_rechazo(modulo_casos.gestionar_caso, "/casos/gestionar/1",
                              self.usuario("Admin"), self.caso(estado="CERRADO"))

    def test_torre_control_no_gestiona_caso_anulado(self):
        self.comprobar_rechazo(modulo_casos.gestionar_caso, "/casos/gestionar/1",
                              self.usuario("Torre Control"), self.caso(estado="ANULADO"))

    def test_coordinador_ciclo_no_cierra_por_post(self):
        caso = self.caso()
        self.comprobar_rechazo(modulo_casos.cerrar_caso, "/casos/cerrar/1",
                              self.usuario("Coordinador Ciclo"), caso)
        self.assertEqual(caso.estado, "EN_SEGUIMIENTO")

    def test_trabajador_social_ajeno_no_cierra_por_post(self):
        self.comprobar_rechazo(modulo_casos.cerrar_caso, "/casos/cerrar/1",
                              self.usuario("Trabajador(a) Social"), self.caso(ts_id=99))

    def test_admin_no_cierra_caso_ya_cerrado(self):
        self.comprobar_rechazo(modulo_casos.cerrar_caso, "/casos/cerrar/1",
                              self.usuario("Admin"), self.caso(estado="CERRADO"))

    def test_torre_control_no_cierra_caso_anulado(self):
        self.comprobar_rechazo(modulo_casos.cerrar_caso, "/casos/cerrar/1",
                              self.usuario("Torre Control"), self.caso(estado="ANULADO"))

    def test_trabajador_social_no_anula_por_post(self):
        caso = self.caso(ts_id=10)
        self.comprobar_rechazo(modulo_casos.anular_caso, "/casos/anular/1",
                              self.usuario("Trabajador(a) Social"), caso,
                              data={"motivo_anulacion": "Ejemplo ficticio"})
        self.assertEqual(caso.estado, "EN_SEGUIMIENTO")

    def test_admin_no_anula_caso_cerrado(self):
        self.comprobar_rechazo(modulo_casos.anular_caso, "/casos/anular/1",
                              self.usuario("Admin"), self.caso(estado="CERRADO"),
                              data={"motivo_anulacion": "Ejemplo ficticio"})

    def test_admin_no_anula_sin_motivo(self):
        self.comprobar_rechazo(modulo_casos.anular_caso, "/casos/anular/1",
                              self.usuario("Admin"), self.caso(), data={})

    def test_visualizador_no_gestiona_subrogancia(self):
        self.comprobar_rechazo(modulo_casos.gestionar_subrogancia,
                              "/casos/subrogancia/gestionar",
                              self.usuario("Visualizador"), destino="/casos/")


if __name__ == "__main__":
    unittest.main()
