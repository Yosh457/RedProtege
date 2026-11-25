"""Caracterizacion de accesos permitidos actuales de RedProtege (Fase 1.2).

No representa aun los permisos futuros acordados para EPI, Visualizador o
Coordinador(a) de Urgencia. No utiliza registros reales ni conexiones MySQL.
Ejecutar: python -m unittest tests.test_permisos_positivos -v
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import Forbidden

from app import create_app
from blueprints import casos as modulo_casos


class TestPermisosPositivos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "test-redprotege-permisos-positivos"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, *, usuario_id=10, ciclos=None, subrogante_de=None):
        return SimpleNamespace(
            id=usuario_id,
            activo=True,
            is_authenticated=True,
            rol=SimpleNamespace(nombre=rol),
            ciclos=[] if ciclos is None else ciclos,
            subrogante_de=subrogante_de,
        )

    @staticmethod
    def caso(*, ciclo=2, ts=20, ts_anterior=None, coordinador=30):
        return SimpleNamespace(
            id=1,
            ciclo_vital_id=ciclo,
            asignado_ts_id=ts,
            asignado_a_usuario_id=ts_anterior,
            asignado_coord_id=coordinador,
            estado='EN_SEGUIMIENTO',
            acta_pdf_path=None,
        )

    def comprobar_detalle_permitido(self, usuario, caso):
        """Ejecuta la regla real, aislando las consultas posteriores al permiso.

        Se utiliza la funcion sin @login_required para caracterizar la
        autorizacion interna; las pruebas de acceso anonimo cubren el decorador.
        """
        consulta_caso = MagicMock()
        consulta_caso.get_or_404.return_value = caso
        consulta_usuarios = MagicMock()

        with self.app.test_request_context('/casos/ver/1', method='GET'):
            with patch.object(modulo_casos, 'current_user', usuario), \
                 patch.object(modulo_casos.Caso, 'query', consulta_caso), \
                 patch.object(modulo_casos.Usuario, 'query', consulta_usuarios), \
                 patch.object(modulo_casos, 'render_template', return_value='DETALLE_AUTORIZADO') as plantilla:
                resultado = modulo_casos.ver_caso.__wrapped__(1)

        self.assertEqual(resultado, 'DETALLE_AUTORIZADO')
        consulta_caso.get_or_404.assert_called_once_with(1)
        plantilla.assert_called_once()
        args, kwargs = plantilla.call_args
        self.assertEqual(args[0], 'casos/ver.html')
        self.assertIs(kwargs['caso'], caso)

    def test_admin_puede_abrir_detalle(self):
        self.comprobar_detalle_permitido(self.usuario('Admin'), self.caso())

    def test_torre_control_puede_abrir_detalle(self):
        self.comprobar_detalle_permitido(self.usuario('Torre Control'), self.caso())

    def test_trabajador_social_asignado_puede_abrir_detalle(self):
        self.comprobar_detalle_permitido(
            self.usuario('Trabajador(a) Social', usuario_id=10), self.caso(ts=10)
        )

    def test_trabajador_social_asignacion_heredada_puede_abrir_detalle(self):
        self.comprobar_detalle_permitido(
            self.usuario('Trabajador(a) Social', usuario_id=10),
            self.caso(ts=99, ts_anterior=10),
        )

    def test_coordinador_ciclo_asignado_puede_abrir_detalle(self):
        self.comprobar_detalle_permitido(
            self.usuario('Coordinador Ciclo', usuario_id=10), self.caso(coordinador=10)
        )

    def test_referente_de_ciclo_puede_abrir_detalle(self):
        self.comprobar_detalle_permitido(
            self.usuario('Referente', ciclos=[SimpleNamespace(id=2)]),
            self.caso(ciclo=2),
        )

    def test_referente_subrogante_puede_abrir_ciclo_subrogado(self):
        titular = SimpleNamespace(activo=True, rol=SimpleNamespace(nombre='Referente'), ciclos=[SimpleNamespace(id=2)])
        self.comprobar_detalle_permitido(
            self.usuario('Referente', ciclos=[SimpleNamespace(id=1)], subrogante_de=titular),
            self.caso(ciclo=2),
        )

    def test_referente_sin_ciclos_no_tiene_acceso_global(self):
        usuario = self.usuario('Referente')
        caso = self.caso(ciclo=2)
        consulta_caso = MagicMock()
        consulta_caso.get_or_404.return_value = caso
        with self.app.test_request_context('/casos/ver/1', method='GET'):
            with patch.object(modulo_casos, 'current_user', usuario), \
                 patch.object(modulo_casos.Caso, 'query', consulta_caso):
                with self.assertRaises(Forbidden):
                    modulo_casos.ver_caso.__wrapped__(1)

    def test_visualizador_sin_ciclos_tiene_acceso_global_actualmente(self):
        # Comportamiento heredado; posteriormente debe validarse la regla global.
        self.comprobar_detalle_permitido(self.usuario('Visualizador'), self.caso(ciclo=2))

    def test_visualizador_con_ciclo_accede_a_otro_por_politica_global(self):
        usuario = self.usuario('Visualizador', ciclos=[SimpleNamespace(id=1)])
        self.comprobar_detalle_permitido(usuario, self.caso(ciclo=2))


if __name__ == '__main__':
    unittest.main()
