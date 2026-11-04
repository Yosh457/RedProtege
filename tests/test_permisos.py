"""Pruebas de caracterización de permisos actuales de RedProtege (Fase 1.2).

No crea tablas, no modifica casos ni consulta la base de datos.
Ejecutar: python -m unittest discover -s tests -v

IMPORTANTE: documenta el comportamiento existente, no el diseño futuro del
rol Coordinador(a) de Urgencia. Las diferencias detectadas requieren revisión.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from werkzeug.exceptions import Forbidden

from app import create_app
from blueprints import casos as modulo_casos

class TestPermisosCasos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "test-redprotege-permisos-sin-base-de-datos"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, *, id=10, ciclos=None, subrogante_de=None):
        return SimpleNamespace(
            id=id,
            rol=SimpleNamespace(nombre=rol),
            ciclos=[] if ciclos is None else ciclos,
            subrogante_de=subrogante_de,
        )

    @staticmethod
    def caso(*, ciclo=2, ts=20, legacy_ts=None, coordinador=30,
             cierre=None, estado='EN_SEGUIMIENTO'):
        return SimpleNamespace(
            id=1,
            ciclo_vital_id=ciclo,
            asignado_ts_id=ts,
            asignado_a_usuario_id=legacy_ts,
            asignado_coord_id=coordinador,
            usuario_cierre_id=cierre,
            estado=estado,
            acta_pdf_path=None,
        )

    def probar_detalle_denegado(self, usuario, caso):
        with self.app.test_request_context('/casos/ver/1'):
            with patch.object(modulo_casos, 'current_user', usuario), \
                 patch.object(modulo_casos.Caso, 'query',
                              SimpleNamespace(get_or_404=lambda _id: caso)), \
                 patch.object(modulo_casos, 'render_template', return_value='ACCESO_PERMITIDO'):
                # Evitamos que Jinja2 interfiera en la prueba. Si la ruta llega
                # a renderizar, significa que NO rechazó el acceso como se esperaba.
                # Saltamos únicamente @login_required. La regla de acceso real
                # dentro de ver_caso permanece intacta y es la que se comprueba.
                with self.assertRaises(Forbidden):
                    modulo_casos.ver_caso.__wrapped__(1)

    def test_trabajador_social_no_ve_caso_ajeno(self):
        self.probar_detalle_denegado(
            self.usuario('Trabajador(a) Social'), self.caso(ts=99)
        )

    def test_coordinador_ciclo_no_ve_caso_ajeno(self):
        self.probar_detalle_denegado(
            self.usuario('Coordinador Ciclo'), self.caso(coordinador=99)
        )

    def test_referente_no_ve_caso_fuera_de_sus_ciclos(self):
        self.probar_detalle_denegado(
            self.usuario('Referente', ciclos=[SimpleNamespace(id=1)]),
            self.caso(ciclo=2),
        )

    def test_visualizador_no_ve_caso_fuera_de_sus_ciclos(self):
        self.probar_detalle_denegado(
            self.usuario('Visualizador', ciclos=[SimpleNamespace(id=1)]),
            self.caso(ciclo=2),
        )

    def test_solicitante_no_puede_abrir_detalle_de_caso(self):
        self.probar_detalle_denegado(
            self.usuario('Solicitante'), self.caso()
        )

    def test_coordinador_epi_no_puede_abrir_detalle_actualmente(self):
        # Caracteriza la diferencia actual: su bandeja/exportación admiten
        # acceso global, pero la ruta ver_caso no lo incluye explícitamente.
        self.probar_detalle_denegado(
            self.usuario('Coordinador EPI'), self.caso()
        )

    def test_trabajador_social_ajeno_no_descarga_acta(self):
        with self.app.test_request_context('/casos/acta/1'):
            with patch.object(modulo_casos, 'current_user',
                              self.usuario('Trabajador(a) Social')), \
                 patch.object(modulo_casos.Caso, 'query',
                              SimpleNamespace(get_or_404=lambda _id: self.caso(ts=99))):
                respuesta = modulo_casos.descargar_acta.__wrapped__(1)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.headers['Location'].endswith('/casos/'))

    def test_coordinador_ciclo_no_gestiona_caso(self):
        with self.app.test_request_context('/casos/gestionar/1'):
            with patch.object(modulo_casos, 'current_user',
                              self.usuario('Coordinador Ciclo', id=30)), \
                 patch.object(modulo_casos.Caso, 'query',
                              SimpleNamespace(get_or_404=lambda _id: self.caso(coordinador=30))):
                respuesta = modulo_casos.gestionar_caso.__wrapped__(1)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.headers['Location'].endswith('/casos/ver/1'))

if __name__ == '__main__':
    unittest.main()