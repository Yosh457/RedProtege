"""Fase 1.3-C.5-C: reglas de gestion clinica sin MySQL, SMTP ni PDFs.

Invoca la vista sin el decorador login_required. La autenticacion HTTP/CSRF
se cubre por separado; estas pruebas verifican la autorizacion interna.
"""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from werkzeug.exceptions import Forbidden

from app import create_app
from blueprints import casos as modulo


class TestGestionRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'SECRET_KEY': 'test-c5c-gestion-sin-db'}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, *, uid=10, activo=True, recintos=None):
        return SimpleNamespace(
            id=uid, activo=activo, is_authenticated=True,
            rol=SimpleNamespace(nombre=rol),
            recintos=[SimpleNamespace(id=i) for i in (recintos or [])],
            ciclos=[], subrogante_de=None,
        )

    @staticmethod
    def caso(*, estado='EN_SEGUIMIENTO', ts=20, ts_legacy=None, recinto=1):
        return SimpleNamespace(
            id=1, estado=estado, recinto_notifica_id=recinto,
            asignado_ts_id=ts, asignado_a_usuario_id=ts_legacy,
            asignado_coord_id=30, ciclo_vital_id=2,
        )

    def ejecutar(self, usuario, caso, *, metodo='GET'):
        with self.app.test_request_context('/casos/gestionar/1', method=metodo):
            with ExitStack() as stack:
                stack.enter_context(patch.object(modulo, 'current_user', usuario))
                cq = MagicMock()
                cq.get_or_404.return_value = caso
                stack.enter_context(patch.object(modulo.Caso, 'query', cq))
                establecimientos = MagicMock()
                instituciones = MagicMock()
                stack.enter_context(patch.object(modulo.CatalogoEstablecimiento, 'query', establecimientos))
                stack.enter_context(patch.object(modulo.CatalogoInstitucion, 'query', instituciones))
                sesion = MagicMock()
                stack.enter_context(patch.object(modulo.db, 'session', sesion))
                render = stack.enter_context(patch.object(modulo, 'render_template', return_value='FORMULARIO'))
                try:
                    resultado = modulo.gestionar_caso.__wrapped__(1)
                    codigo = getattr(resultado, 'status_code', 200)
                except Forbidden:
                    codigo = 403
                return codigo, sesion, render, establecimientos, instituciones

    def denegado(self, usuario, caso, *, metodo='POST'):
        codigo, sesion, render, establecimientos, instituciones = self.ejecutar(
            usuario, caso, metodo=metodo)
        self.assertEqual(codigo, 403)
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()
        sesion.rollback.assert_not_called()
        render.assert_not_called()
        establecimientos.filter_by.assert_not_called()
        instituciones.filter_by.assert_not_called()

    def permitido_get(self, usuario, caso):
        codigo, sesion, render, establecimientos, instituciones = self.ejecutar(usuario, caso)
        self.assertEqual(codigo, 200)
        render.assert_called_once()
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()
        establecimientos.filter_by.assert_called_once_with(activo=True)
        instituciones.filter_by.assert_called_once_with(activo=True)

    def test_admin_get_permitido(self):
        self.permitido_get(self.usuario('Admin'), self.caso())

    def test_torre_get_permitido(self):
        self.permitido_get(self.usuario('Torre Control'), self.caso())

    def test_ts_asignado_get_permitido(self):
        self.permitido_get(self.usuario('Trabajador(a) Social', uid=20), self.caso())

    def test_ts_legacy_get_permitido(self):
        self.permitido_get(self.usuario('Trabajador(a) Social', uid=21), self.caso(ts=99, ts_legacy=21))

    def test_urgencia_recinto_notificador_get_permitido(self):
        self.permitido_get(self.usuario('Coordinador(a) de Urgencia', recintos=[1]), self.caso())

    def test_urgencia_recinto_ajeno_post_denegado(self):
        self.denegado(self.usuario('Coordinador(a) de Urgencia', recintos=[3]), self.caso())

    def test_urgencia_sin_recintos_post_denegado(self):
        self.denegado(self.usuario('Coordinador(a) de Urgencia'), self.caso())

    def test_epi_del_mismo_recinto_post_denegado(self):
        self.denegado(self.usuario('Coordinador EPI', recintos=[1]), self.caso())

    def test_visualizador_post_denegado(self):
        self.denegado(self.usuario('Visualizador'), self.caso())

    def test_referente_post_denegado(self):
        self.denegado(self.usuario('Referente'), self.caso())

    def test_coordinador_ciclo_post_denegado(self):
        self.denegado(self.usuario('Coordinador Ciclo', uid=30), self.caso())

    def test_ts_ajeno_post_denegado(self):
        self.denegado(self.usuario('Trabajador(a) Social', uid=50), self.caso())

    def test_admin_inactivo_post_denegado(self):
        self.denegado(self.usuario('Admin', activo=False), self.caso())

    def test_admin_cerrado_post_denegado(self):
        self.denegado(self.usuario('Admin'), self.caso(estado='CERRADO'))

    def test_urgencia_anulado_post_denegado(self):
        self.denegado(self.usuario('Coordinador(a) de Urgencia', recintos=[1]), self.caso(estado='ANULADO'))


if __name__ == '__main__':
    unittest.main()
