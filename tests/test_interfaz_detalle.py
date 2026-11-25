"""Pruebas aisladas de los controles Jinja del detalle; no usan MySQL.
Se ejecutan despues de aplicar templates/casos/ver.html.candidate.
"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader, StrictUndefined


class CasoFicticio:
    id = 1
    folio_atencion = 'FICTICIO-001'
    estado = 'EN_SEGUIMIENTO'
    fecha_ingreso = None
    vulneraciones = []
    gestiones = []
    auditorias = []

    def __getattr__(self, nombre):
        return None


class TestInterfazDetalle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raiz = Path(__file__).resolve().parents[1]
        cls.entorno = Environment(
            loader=FileSystemLoader(str(raiz / 'templates')),
            autoescape=True,
        )
        cls.entorno.globals.update(
            url_for=lambda endpoint, **kw: '/' + endpoint.replace('.', '/') + '/' + str(kw.get('id', '')),
            csrf_token=lambda: 'TOKEN-PRUEBA',
        )
        # Plantilla base propia en memoria para evitar dependencias de la app.
        from jinja2 import ChoiceLoader, DictLoader
        cls.entorno.loader = ChoiceLoader([
            DictLoader({'base.html': '{% block content %}{% endblock %}'}),
            cls.entorno.loader,
        ])

    def renderizar(self, *, rol='Visualizador', estado='EN_SEGUIMIENTO',
                   asignar=False, gestionar=False, anular=False, acta=False):
        caso = CasoFicticio()
        caso.estado = estado
        caso.acta_pdf_path = 'uploads/actas/ficticio.pdf' if acta else None
        usuario = SimpleNamespace(id=12, rol=SimpleNamespace(nombre=rol))
        return self.entorno.get_template('casos/ver.html').render(
            caso=caso,
            current_user=usuario,
            puede_asignar=asignar,
            puede_gestionar_vista=gestionar,
            puede_anular_vista=anular,
            puede_descargar_acta_vista=acta,
            funcionarios_ts=[], funcionarios_coord=[],
        )

    def test_visualizador_no_tiene_acciones(self):
        html = self.renderizar()
        for texto in ('Guardar Asignaciones', 'Ingresar Gestión',
                      'Anular Ingreso', 'Descargar Acta de Cierre'):
            self.assertNotIn(texto, html)
        self.assertIn('solo lectura', html)

    def test_asignaciones_muestran_formulario_solo_si_permitido(self):
        self.assertIn('Guardar Asignaciones', self.renderizar(rol='Admin', asignar=True))
        self.assertNotIn('Guardar Asignaciones', self.renderizar(rol='Admin', asignar=False))

    def test_gestion_muestra_enlace_solo_si_permitido(self):
        self.assertIn('Ingresar Gestión', self.renderizar(rol='Admin', gestionar=True))
        self.assertNotIn('Ingresar Gestión', self.renderizar(rol='Admin', gestionar=False))

    def test_urgencia_no_muestra_gestion_antes_de_actualizar_endpoint(self):
        self.assertNotIn('Ingresar Gestión', self.renderizar(rol='Coordinador(a) de Urgencia'))

    def test_anulacion_muestra_modal_solo_si_permitido(self):
        self.assertIn('Confirmar Anulación', self.renderizar(rol='Admin', anular=True))
        self.assertNotIn('Confirmar Anulación', self.renderizar(rol='Admin', anular=False))

    def test_descarga_solo_si_permitida(self):
        self.assertIn('Descargar Acta de Cierre', self.renderizar(rol='Admin', estado='CERRADO', acta=True))
        self.assertNotIn('Descargar Acta de Cierre', self.renderizar(rol='Visualizador', estado='CERRADO', acta=False))

    def test_estados_terminales_ocultan_mutaciones(self):
        # El servidor debera enviar flags False para estados terminales;
        # la plantilla protege adicionalmente el formulario de asignacion.
        for estado in ('CERRADO', 'ANULADO'):
            html = self.renderizar(rol='Admin', estado=estado, asignar=True)
            self.assertNotIn('Guardar Asignaciones', html)
            self.assertNotIn('Ingresar Gestión', html)


if __name__ == '__main__':
    unittest.main()
