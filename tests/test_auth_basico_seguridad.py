"""Pruebas HTTP dirigidas para sesiones y métodos de Auth, sin MySQL."""
import os
import unittest
from unittest.mock import patch

from app import create_app


class TestAuthBasicoSeguridad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'SECRET_KEY': 'tests-auth-redprotege',
                                    'MYSQL_HOST': '127.0.0.1', 'MYSQL_PORT': '3306',
                                    'MYSQL_USER': 'root', 'MYSQL_PASSWORD': 'ficticia',
                                    'MYSQL_DB': 'red_protege_db'}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def test_logout_get_rechazado(self):
        with self.app.test_client() as cliente:
            self.assertEqual(cliente.get('/logout').status_code, 405)

    def test_estado_sesion_sin_login(self):
        with self.app.test_client() as cliente:
            r = cliente.get('/sesion/estado')
            self.assertEqual(r.status_code, 401)
            self.assertFalse(r.json['autenticado'])

    def test_renovar_sesion_sin_login(self):
        with self.app.test_client() as cliente:
            r = cliente.post('/sesion/renovar')
            self.assertEqual(r.status_code, 401)
            self.assertFalse(r.json['autenticado'])

    def test_login_sin_credenciales_no_consulta_mysql(self):
        with self.app.app_context():
            with patch('blueprints.auth.Usuario.query') as consulta:
                with self.app.test_client() as cliente:
                    respuesta = cliente.post(
                        '/login',
                        data={'email': '', 'password': ''}
                    )

                self.assertEqual(respuesta.status_code, 200)
                consulta.filter_by.assert_not_called()

    def test_recuperacion_formulario_get(self):
        with self.app.test_client() as cliente:
            self.assertEqual(cliente.get('/solicitar-reseteo').status_code, 200)

    def test_sesion_inactiva_no_renueva_por_get(self):
        with self.app.test_client() as cliente:
            self.assertEqual(cliente.get('/sesion/renovar').status_code, 405)


if __name__ == '__main__':
    unittest.main()
