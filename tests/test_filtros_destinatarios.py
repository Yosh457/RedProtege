"""Fase 1.2-A (bloque 2): filtros de exportación y destinatarios actuales.

Caracteriza reglas VIGENTES, no la política futura aprobada.
Sin consultas reales a MySQL ni envíos de correo. Ejecutar:
    python -m unittest tests.test_filtros_destinatarios -v
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints import casos as modulo_casos


class ConsultaFicticia:
    """Recoge los filtros SQLAlchemy sin ejecutar una consulta."""

    def __init__(self):
        self.condiciones = []
        self.consultas_all = 0

    def filter(self, *condiciones):
        self.condiciones.extend(condiciones)
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        self.consultas_all += 1
        return []

    def parametros(self):
        """Obtiene parámetros enlazados por los filtros, sin usar MySQL."""
        valores = []
        for condicion in self.condiciones:
            compilada = condicion.compile()
            valores.extend(compilada.params.values())
        return valores

    def texto_sql(self):
        return " ".join(str(condicion).lower() for condicion in self.condiciones)


class TestFiltrosExportacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "test-exportacion-filtros-sin-bd"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, *, ciclos=None, subrogante_de=None, id=10):
        return SimpleNamespace(
            id=id,
            rol=SimpleNamespace(nombre=rol),
            ciclos=[] if ciclos is None else ciclos,
            subrogante_de=subrogante_de,
            email="usuario@example.invalid",
        )

    def exportar_simulado(self, usuario):
        consulta = ConsultaFicticia()
        with self.app.test_request_context('/casos/exportar'):
            with patch.object(modulo_casos, 'current_user', usuario), \
                 patch.object(modulo_casos.Caso, 'query', consulta):
                respuesta = modulo_casos.exportar_excel.__wrapped__()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(consulta.consultas_all, 1)
        return consulta

    def test_referente_filtra_por_su_ciclo(self):
        consulta = self.exportar_simulado(
            self.usuario('Referente', ciclos=[SimpleNamespace(id=2)])
        )
        self.assertIn('ciclo_vital_id', consulta.texto_sql())
        self.assertIn([2], consulta.parametros())

    def test_referente_incluye_ciclo_subrogado(self):
        titular = SimpleNamespace(ciclos=[SimpleNamespace(id=3)])
        consulta = self.exportar_simulado(self.usuario(
            'Referente', ciclos=[SimpleNamespace(id=2)], subrogante_de=titular
        ))
        self.assertIn('ciclo_vital_id', consulta.texto_sql())
        # SQLAlchemy representa IN como una lista enlazada.
        self.assertTrue(any(isinstance(v, (tuple, list)) and set(v) == {2, 3}
                            for v in consulta.parametros()))

    def test_visualizador_con_ciclo_restringe_exportacion_actualmente(self):
        consulta = self.exportar_simulado(
            self.usuario('Visualizador', ciclos=[SimpleNamespace(id=2)])
        )
        self.assertIn('ciclo_vital_id', consulta.texto_sql())
        self.assertIn([2], consulta.parametros())

    def test_visualizador_sin_ciclos_exporta_globalmente_actualmente(self):
        consulta = self.exportar_simulado(self.usuario('Visualizador'))
        self.assertNotIn('ciclo_vital_id', consulta.texto_sql())

    def test_referente_sin_ciclos_exporta_globalmente_actualmente(self):
        consulta = self.exportar_simulado(self.usuario('Referente'))
        self.assertNotIn('ciclo_vital_id', consulta.texto_sql())

    def test_trabajador_social_filtra_por_asignacion_actual_y_heredada(self):
        consulta = self.exportar_simulado(self.usuario('Trabajador(a) Social'))
        sql = consulta.texto_sql()
        self.assertIn('asignado_ts_id', sql)
        self.assertIn('asignado_a_usuario_id', sql)
        self.assertGreaterEqual(consulta.parametros().count(10), 2)

    def test_coordinador_epi_no_filtra_por_recinto_actualmente(self):
        consulta = self.exportar_simulado(self.usuario('Coordinador EPI'))
        self.assertNotIn('recinto_notifica_id', consulta.texto_sql())
        self.assertNotIn('ciclo_vital_id', consulta.texto_sql())

    def test_exportacion_omite_anulados_por_defecto(self):
        consulta = self.exportar_simulado(self.usuario('Admin'))
        self.assertIn('estado', consulta.texto_sql())
        self.assertIn('ANULADO', consulta.parametros())


class TestDestinatariosReporte(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "test-envio-reportes-sin-bd"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol):
        return SimpleNamespace(
            id=10, email='administrador@example.invalid',
            rol=SimpleNamespace(nombre=rol),
        )

    def enviar_simulado(self, rol):
        # Las tres consultas de estadísticas usan únicamente respuestas ficticias.
        stats_globales = MagicMock()
        stats_globales.filter.return_value = stats_globales
        stats_globales.first.return_value = SimpleNamespace(
            total=7, pendientes=2, seguimiento=3, cerrados=2
        )
        inscritos = MagicMock()
        inscritos.outerjoin.return_value = inscritos
        inscritos.group_by.return_value = inscritos
        inscritos.order_by.return_value = inscritos
        inscritos.all.return_value = [SimpleNamespace(
            nombre='Recinto ficticio', total=7,
            pendientes=2, seguimiento=3, cerrados=2
        )]
        notificaciones = MagicMock()
        notificaciones.outerjoin.return_value = notificaciones
        notificaciones.group_by.return_value = notificaciones
        notificaciones.order_by.return_value = notificaciones
        notificaciones.all.return_value = [SimpleNamespace(
            nombre='Urgencia ficticia', total=7
        )]
        consulta_usuarios = MagicMock()
        consulta_usuarios.filter.return_value = consulta_usuarios
        consulta_usuarios.all.return_value = [
            SimpleNamespace(email=' UNO@example.invalid ', rol=SimpleNamespace(nombre='Solicitante')),
            SimpleNamespace(email='uno@example.invalid', rol=SimpleNamespace(nombre='Visualizador')),
            SimpleNamespace(email='dos@example.invalid', rol=SimpleNamespace(nombre='Torre Control')),
        ]
        consulta_estadisticas = MagicMock(side_effect=[
            stats_globales, inscritos, notificaciones
        ])
        with self.app.test_request_context('/casos/enviar_reporte_masivo', method='POST'):
            with patch.object(modulo_casos, 'current_user', self.usuario(rol)), \
                 patch.object(modulo_casos.db.session, 'query', consulta_estadisticas), \
                 patch.object(modulo_casos.Usuario, 'query', consulta_usuarios), \
                 patch.object(modulo_casos, 'enviar_reporte_estadistico_masivo', return_value=True) as enviar, \
                 patch.object(modulo_casos, 'registrar_log') as registrar:
                respuesta = modulo_casos.enviar_reporte_masivo.__wrapped__()
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.headers['Location'].endswith('/casos/'))
        self.assertEqual(consulta_estadisticas.call_count, 3)
        enviar.assert_called_once()
        registrar.assert_called_once()
        return enviar.call_args.args

    def test_admin_envia_a_todos_los_activos_incluso_solicitante_actualmente(self):
        destinatarios, datos = self.enviar_simulado('Admin')
        self.assertEqual(destinatarios, ['uno@example.invalid', 'dos@example.invalid'])
        self.assertIn('global', datos)
        self.assertIn('inscritos', datos)
        self.assertIn('notificacion', datos)
        self.assertEqual(datos['global']['total'], 7)

    def test_torre_control_puede_solicitar_envio_masivo(self):
        destinatarios, datos = self.enviar_simulado('Torre Control')
        self.assertEqual(len(destinatarios), 2)
        self.assertEqual(datos['notificacion'][0]['pct'], 100.0)


if __name__ == '__main__':
    unittest.main()
