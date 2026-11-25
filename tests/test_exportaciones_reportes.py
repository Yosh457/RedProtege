"""Fase 1.2-A: caracterizacion de exportaciones y reportes de RedProtege.

Sin conexiones MySQL, sin datos reales y sin correos enviados.
Las reglas actuales no equivalen a los permisos futuros validados con la unidad.
Ejecutar: python -m unittest tests.test_exportaciones_reportes -v
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import Forbidden

from app import create_app
from blueprints import casos as modulo_casos


class TestExportacionesReportes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "test-exportaciones-sin-datos-reales"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, *, ciclos=None, subrogante_de=None):
        return SimpleNamespace(
            id=10, activo=True, is_authenticated=True,
            recintos=[SimpleNamespace(id=1)] if rol == "Coordinador EPI" else [],
            rol=SimpleNamespace(nombre=rol),
            ciclos=[] if ciclos is None else ciclos,
            subrogante_de=subrogante_de,
            email="pruebas@example.invalid",
        )

    def test_solicitante_no_puede_exportar(self):
        self._comprobar_exportacion_denegada("Solicitante")

    def test_rol_desconocido_no_puede_exportar(self):
        self._comprobar_exportacion_denegada("Perfil inexistente")

    def _comprobar_exportacion_denegada(self, rol):
        consulta = MagicMock(side_effect=AssertionError("No debe consultar MySQL"))
        with self.app.test_request_context("/casos/exportar"):
            with patch.object(modulo_casos, "current_user", self.usuario(rol)), \
                 patch.object(modulo_casos.Caso, "query", consulta), \
                 patch.object(modulo_casos, "send_file") as archivo:
                with self.assertRaises(Forbidden):
                    modulo_casos.exportar_excel.__wrapped__()
        consulta.assert_not_called()
        archivo.assert_not_called()

    def test_admin_exporta_reporte_vacio_simulado(self):
        self._comprobar_exportacion_permitida("Admin")

    def test_torre_control_exporta_reporte_vacio_simulado(self):
        self._comprobar_exportacion_permitida("Torre Control")

    def test_coordinador_epi_exporta_con_recinto_autorizado(self):
        # Comportamiento heredado: debe limitarse por recinto en futura fase.
        self._comprobar_exportacion_permitida("Coordinador EPI")

    def _comprobar_exportacion_permitida(self, rol):
        consulta = MagicMock()
        consulta.filter.return_value = consulta
        consulta.order_by.return_value = consulta
        consulta.all.return_value = []

        with self.app.test_request_context("/casos/exportar"):
            with patch.object(modulo_casos, "current_user", self.usuario(rol)), \
                 patch.object(modulo_casos.Caso, "query", consulta):
                respuesta = modulo_casos.exportar_excel.__wrapped__()

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      respuesta.mimetype)
        self.assertIn("attachment", respuesta.headers["Content-Disposition"])
        consulta.filter.assert_called()
        consulta.all.assert_called_once_with()

    def test_visualizador_no_puede_enviar_reporte_masivo(self):
        self._comprobar_envio_masivo_denegado("Visualizador")

    def test_coordinador_epi_no_puede_enviar_reporte_masivo(self):
        self._comprobar_envio_masivo_denegado("Coordinador EPI")

    def test_solicitante_no_puede_enviar_reporte_masivo(self):
        self._comprobar_envio_masivo_denegado("Solicitante")

    def _comprobar_envio_masivo_denegado(self, rol):
        with self.app.test_request_context("/casos/enviar_reporte_masivo", method="POST"):
            with patch.object(modulo_casos, "current_user", self.usuario(rol)), \
                 patch.object(modulo_casos, "enviar_reporte_estadistico_masivo") as enviar, \
                 patch.object(modulo_casos, "registrar_log") as log, \
                 patch.object(modulo_casos.db.session, "query") as query_bd, \
                 patch.object(modulo_casos.Usuario, "query", MagicMock()) as consulta_usuario:
                respuesta = modulo_casos.enviar_reporte_masivo.__wrapped__()

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.headers["Location"].endswith("/casos/"))
        enviar.assert_not_called()
        log.assert_not_called()
        query_bd.assert_not_called()
        consulta_usuario.filter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
