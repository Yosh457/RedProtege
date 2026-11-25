"""Pruebas de regresión de acceso para RedProtege (Fase 1.1).

No crea tablas ni consulta datos reales. Ejecutar desde la raíz:
    python -m unittest discover -s tests -v
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import create_app
from blueprints.auth import es_password_segura, obtener_ruta_redireccion

class TestAccesoAnonimo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # La factoría necesita configurar MySQL, pero estas pruebas nunca lo consultan.
        # Mantener SECRET_KEY propia para no depender del secreto del entorno real.
        with patch.dict(os.environ, {"SECRET_KEY": "test-solo-para-unittest-acceso-redprotege"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        self.client = self.app.test_client()

    def test_raiz_redirige_a_login(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_modulos_privados_exigen_autenticacion(self):
        for url in ("/admin/panel", "/admin/ver_logs", "/casos/", "/solicitudes/ingreso"):
            with self.subTest(ruta=url):
                response = self.client.get(url, follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.headers["Location"].startswith("/login"))

    def test_rutas_de_modificacion_no_admiten_get(self):
        # Comprueba solo el contrato HTTP registrado; no envía acciones ni usa BD.
        rutas = ("/admin/toggle_activo/1", "/casos/anular/1", "/casos/cerrar/1")
        for url in rutas:
            with self.subTest(ruta=url):
                response = self.client.get(url, follow_redirects=False)
                self.assertEqual(response.status_code, 405)

    def test_el_logout_actual_acepta_get(self):
        # Caracterización de comportamiento legado, NO una aprobación de seguridad.
        rule = next(r for r in self.app.url_map.iter_rules() if r.endpoint == "auth.logout")
        self.assertIn("GET", rule.methods)

class TestAutenticacionPura(unittest.TestCase):
    def test_validacion_actual_de_contrasenas(self):
        self.assertTrue(es_password_segura("ClaveSegura2026"))
        self.assertFalse(es_password_segura("corta1A"))
        self.assertFalse(es_password_segura("sinmayusculas123"))
        self.assertFalse(es_password_segura("SinNumeros"))

    def test_redireccion_inicial_por_rol(self):
        app = create_app_para_rutas()
        with app.test_request_context("/"):
            casos = {
                "Admin": "/admin/panel",
                "Solicitante": "/solicitudes/ingreso",
                "Referente": "/casos/",
                "Torre Control": "/casos/",
                "Visualizador": "/casos/",
            }
            for rol, destino in casos.items():
                with self.subTest(rol=rol):
                    usuario = SimpleNamespace(rol=SimpleNamespace(nombre=rol))
                    self.assertEqual(obtener_ruta_redireccion(usuario), destino)
            self.assertEqual(obtener_ruta_redireccion(SimpleNamespace(rol=None)), "/login")

def create_app_para_rutas():
    with patch.dict(os.environ, {"SECRET_KEY": "test-solo-para-unittest-acceso-redprotege"}):
        app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


if __name__ == "__main__":
    unittest.main()