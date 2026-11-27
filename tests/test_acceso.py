"""Pruebas de regresión de acceso para RedProtege (Fase 1.1).

No crea tablas ni consulta datos reales. Ejecutar desde la raíz:
    python -m unittest discover -s tests -v
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import create_app
from blueprints.auth import obtener_ruta_redireccion
from utils.security import password_valida

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

    def test_logout_solo_admite_post(self):
        rule = next(
            r for r in self.app.url_map.iter_rules()
            if r.endpoint == "auth.logout"
        )

        self.assertIn("POST", rule.methods)
        self.assertNotIn("GET", rule.methods)

class TestAutenticacionPura(unittest.TestCase):
    def test_validacion_actual_de_contrasenas(self):
        self.assertTrue(password_valida("ClaveSegura2026", "ClaveSegura2026"))
        self.assertFalse(password_valida("corta1A", "corta1A"))
        self.assertFalse(password_valida("sinmayusculas123", "sinmayusculas123"))
        self.assertFalse(password_valida("SinNumeros", "SinNumeros"))
        self.assertFalse(password_valida("ClaveSegura2026", "OtraClave2026"))

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