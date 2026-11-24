"""Pruebas de politica sobre asignaciones, sin MySQL ni SMTP.

Ejecutar: python -m unittest tests.test_asignaciones_rbac -v
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints import casos as modulo


class TestAsignacionesRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'SECRET_KEY': 'asignaciones-rbac-test-aislado'}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, *, activo=True, ciclos=(), recintos=()):
        return SimpleNamespace(
            id=10, activo=activo, is_authenticated=True,
            rol=SimpleNamespace(nombre=rol),
            ciclos=[SimpleNamespace(id=x) for x in ciclos],
            recintos=[SimpleNamespace(id=x) for x in recintos],
            subrogante_de=None,
        )

    @staticmethod
    def caso(*, estado='EN_SEGUIMIENTO'):
        return SimpleNamespace(
            id=1, estado=estado, ciclo_vital_id=2, recinto_notifica_id=5,
            asignado_ts_id=10, asignado_a_usuario_id=10, asignado_coord_id=10,
            acta_pdf_path=None,
        )

    def ejecutar(self, usuario, caso, *, metodo='POST'):
        """Aisla toda consulta y toda operacion de escritura/correo."""
        consulta = MagicMock()
        consulta.get_or_404.return_value = caso
        usuarios = MagicMock()
        usuarios.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
        sesion = MagicMock()
        with self.app.test_request_context('/casos/ver/1', method=metodo,
                                           data={'asignar_funcionario': '1', 'ts_id': '20'} if metodo == 'POST' else None):
            with patch.object(modulo, 'current_user', usuario), \
                 patch.object(modulo.Caso, 'query', consulta), \
                 patch.object(modulo.Usuario, 'query', usuarios), \
                 patch.object(modulo.db, 'session', sesion), \
                 patch.object(modulo, 'render_template', return_value='DETALLE') as plantilla, \
                 patch.object(modulo, 'enviar_aviso_asignacion') as correo, \
                 patch.object(modulo, 'registrar_log') as registro:
                try:
                    respuesta = modulo.ver_caso.__wrapped__(1)
                    status = getattr(respuesta, 'status_code', 200)
                except Exception as ex:
                    from werkzeug.exceptions import HTTPException
                    if not isinstance(ex, HTTPException):
                        raise
                    status = ex.code
                estado = (status, sesion.commit.call_count, sesion.add.call_count,
                          correo.call_count, registro.call_count,
                          plantilla.call_args.kwargs.get('puede_asignar') if plantilla.called else None,
                          usuarios.join.call_count)
                return estado

    def comprobar_denegado(self, usuario, caso):
        status, commits, adds, correos, logs, _, consultas = self.ejecutar(usuario, caso)
        self.assertEqual(status, 403)
        self.assertEqual((commits, adds, correos, logs, consultas), (0, 0, 0, 0, 0))

    def test_ts_asignado_no_puede_asignar(self):
        self.comprobar_denegado(self.usuario('Trabajador(a) Social'), self.caso())

    def test_coordinador_asignado_no_puede_asignar(self):
        self.comprobar_denegado(self.usuario('Coordinador Ciclo'), self.caso())

    def test_visualizador_no_puede_asignar(self):
        self.comprobar_denegado(self.usuario('Visualizador'), self.caso())

    def test_epi_del_recinto_no_puede_asignar(self):
        self.comprobar_denegado(self.usuario('Coordinador EPI', recintos=(5,)), self.caso())

    def test_urgencia_del_recinto_no_puede_asignar(self):
        self.comprobar_denegado(self.usuario('Coordinador(a) de Urgencia', recintos=(5,)), self.caso())

    def test_referente_fuera_del_ciclo_no_puede_asignar(self):
        self.comprobar_denegado(self.usuario('Referente', ciclos=(3,)), self.caso())

    def test_usuario_inactivo_no_puede_asignar(self):
        self.comprobar_denegado(self.usuario('Admin', activo=False), self.caso())

    def test_admin_no_asigna_caso_cerrado(self):
        self.comprobar_denegado(self.usuario('Admin'), self.caso(estado='CERRADO'))

    def test_admin_ve_formulario_en_caso_abierto(self):
        status, _, _, _, _, flag, consultas = self.ejecutar(self.usuario('Admin'), self.caso(), metodo='GET')
        self.assertEqual(status, 200)
        self.assertIs(flag, True)
        self.assertGreater(consultas, 0)

    def test_referente_del_ciclo_ve_formulario(self):
        status, _, _, _, _, flag, consultas = self.ejecutar(
            self.usuario('Referente', ciclos=(2,)), self.caso(), metodo='GET'
        )
        self.assertEqual(status, 200)
        self.assertIs(flag, True)
        self.assertGreater(consultas, 0)


if __name__ == '__main__':
    unittest.main()
