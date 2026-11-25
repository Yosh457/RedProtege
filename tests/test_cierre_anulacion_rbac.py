"""Fase 1.3-C.5-D: autorizacion y efectos de cierre/anulacion.

Pruebas aisladas: no usan MySQL ni SMTP y sustituyen la generacion PDF.
Invocan vistas sin login_required; autenticacion real y CSRF se comprueban aparte.
"""
import os
import unittest
from unittest.mock import patch

from app import create_app
from tests import test_post_rbac_caracterizacion as fixtures_post


class TestCierreAnulacionRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'SECRET_KEY': 'rbac-c5d-pruebas-sin-db'}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    usuario = staticmethod(fixtures_post.TestPostRBACCaracterizacion.usuario)
    caso = staticmethod(fixtures_post.TestPostRBACCaracterizacion.caso)
    ejecutar = fixtures_post.TestPostRBACCaracterizacion.ejecutar
    sin_efectos = fixtures_post.TestPostRBACCaracterizacion.sin_efectos

    def test_01_admin_inactivo_no_cierra(self):
        r = self.ejecutar('cerrar_caso', '/casos/cerrar/1',
                          self.usuario('Admin', activo=False), self.caso())
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    def test_02_admin_inactivo_no_anula(self):
        r = self.ejecutar('anular_caso', '/casos/anular/1',
                          self.usuario('Admin', activo=False), self.caso(),
                          data={'motivo_anulacion': 'Prueba'})
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    def test_03_ts_ajeno_no_cierra(self):
        r = self.ejecutar('cerrar_caso', '/casos/cerrar/1',
                          self.usuario('Trabajador(a) Social', uid=10), self.caso(ts=99))
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    def test_04_ts_no_anula(self):
        r = self.ejecutar('anular_caso', '/casos/anular/1',
                          self.usuario('Trabajador(a) Social', uid=20), self.caso(ts=20),
                          data={'motivo_anulacion': 'Prueba'})
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    def test_05_admin_no_cierra_terminal(self):
        for estado in ('CERRADO', 'ANULADO'):
            with self.subTest(estado=estado):
                r = self.ejecutar('cerrar_caso', '/casos/cerrar/1',
                                  self.usuario('Admin'), self.caso(estado=estado))
                self.assertEqual(r.status, 403)
                self.sin_efectos(r, estado=estado)

    def test_06_torre_no_anula_terminal(self):
        for estado in ('CERRADO', 'ANULADO'):
            with self.subTest(estado=estado):
                r = self.ejecutar('anular_caso', '/casos/anular/1',
                                  self.usuario('Torre Control'), self.caso(estado=estado),
                                  data={'motivo_anulacion': 'Prueba'})
                self.assertEqual(r.status, 403)
                self.sin_efectos(r, estado=estado)

    def test_07_visualizador_no_cierra_ni_anula(self):
        for accion, ruta in (('cerrar_caso', '/casos/cerrar/1'),
                             ('anular_caso', '/casos/anular/1')):
            with self.subTest(accion=accion):
                r = self.ejecutar(accion, ruta, self.usuario('Visualizador'),
                                  self.caso(), data={'motivo_anulacion': 'Prueba'})
                self.assertEqual(r.status, 403)
                self.sin_efectos(r)

    def test_08_urgencia_no_cierra_ni_anula_su_recinto(self):
        for accion, ruta in (('cerrar_caso', '/casos/cerrar/1'),
                             ('anular_caso', '/casos/anular/1')):
            with self.subTest(accion=accion):
                r = self.ejecutar(accion, ruta,
                                  self.usuario('Coordinador(a) de Urgencia', recintos=[1]),
                                  self.caso(recinto=1), data={'motivo_anulacion': 'Prueba'})
                self.assertEqual(r.status, 403)
                self.sin_efectos(r)

    def test_09_ts_legacy_puede_cerrar(self):
        caso = self.caso(ts=99)
        caso.asignado_a_usuario_id = 10
        r = self.ejecutar('cerrar_caso', '/casos/cerrar/1',
                          self.usuario('Trabajador(a) Social', uid=10), caso)
        self.assertEqual(r.status, 302)
        self.assertEqual(caso.estado, 'CERRADO')
        self.assertEqual(caso.usuario_cierre_id, 10)
        self.assertEqual(r.sesion.commit.call_count, 2)
        r.pdf.assert_called_once()
        r.mail1.assert_called_once()
        r.sesion.rollback.assert_not_called()

    def test_10_admin_puede_cerrar_y_generar_acta(self):
        caso = self.caso()
        r = self.ejecutar('cerrar_caso', '/casos/cerrar/1', self.usuario('Admin'), caso)
        self.assertEqual(r.status, 302)
        self.assertEqual(caso.estado, 'CERRADO')
        self.assertEqual(caso.usuario_cierre_id, 10)
        self.assertEqual(r.sesion.commit.call_count, 2)
        r.sesion.add.assert_called_once()
        self.assertEqual(r.sesion.add.call_args.args[0].accion, 'CIERRE_CASO')
        r.pdf.assert_called_once()
        r.mail1.assert_called_once()
        r.sesion.rollback.assert_not_called()

    def test_11_torre_puede_anular_con_motivo(self):
        caso = self.caso()
        r = self.ejecutar('anular_caso', '/casos/anular/1',
                          self.usuario('Torre Control'), caso,
                          data={'motivo_anulacion': 'Duplicado de prueba'})
        self.assertEqual(r.status, 302)
        self.assertEqual(caso.estado, 'ANULADO')
        r.sesion.commit.assert_called_once()
        r.sesion.add.assert_called_once()
        auditoria = r.sesion.add.call_args.args[0]
        self.assertEqual(auditoria.accion, 'ANULACION_CASO')
        self.assertEqual(auditoria.motivo, 'Duplicado de prueba')
        r.pdf.assert_not_called()
        r.mail1.assert_not_called()
        r.sesion.rollback.assert_not_called()

    def test_12_admin_sin_motivo_no_anula(self):
        caso = self.caso()
        r = self.ejecutar('anular_caso', '/casos/anular/1',
                          self.usuario('Admin'), caso, data={})
        self.assertEqual(r.status, 302)
        self.sin_efectos(r)


if __name__ == '__main__':
    unittest.main()
