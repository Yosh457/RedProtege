"""Fase 1.3-C.2: contratos de alcance para consultas del dashboard.

Pruebas aisladas con SQLite en memoria. NO ejecutan app.create_app(), no
consultan MySQL, no envian correo y no escriben en uploads/. Las consultas
simulan las cinco superficies de index(); la integracion HTTP se probara al
modificar blueprints/casos.py en la siguiente entrega.
"""
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from utils.autorizacion import aplicar_filtro_casos

Base = declarative_base()


class Recinto(Base):
    __tablename__ = 'recintos_ficticios_dashboard'
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)


class Establecimiento(Base):
    __tablename__ = 'establecimientos_ficticios_dashboard'
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)


class Caso(Base):
    __tablename__ = 'casos_ficticios_dashboard'
    id = Column(Integer, primary_key=True)
    recinto_notifica_id = Column(Integer, ForeignKey(Recinto.id))
    recinto_inscrito_id = Column(Integer, ForeignKey(Establecimiento.id))
    ciclo_vital_id = Column(Integer)
    asignado_ts_id = Column(Integer)
    asignado_a_usuario_id = Column(Integer)
    asignado_coord_id = Column(Integer)
    estado = Column(String(30), nullable=False)
    fecha_ingreso = Column(DateTime, nullable=False)
    acta_pdf_path = Column(String(255))


def usuario(rol, uid=99, *, recintos=(), ciclos=(), ciclo_legacy=None,
            subrogante_de=None, activo=True):
    return SimpleNamespace(
        id=uid, is_authenticated=True, activo=activo,
        rol=SimpleNamespace(nombre=rol),
        recintos=[SimpleNamespace(id=i) for i in recintos],
        ciclos=[SimpleNamespace(id=i) for i in ciclos],
        ciclo_asignado_id=ciclo_legacy, subrogante_de=subrogante_de,
    )


class TestDashboardAmbitos(unittest.TestCase):
    """Los cinco tipos de consulta deben respetar la misma politica RBAC."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            'sqlite+pysqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)
        with cls.Session.begin() as sesion:
            sesion.add_all([
                Recinto(id=1, nombre='Recinto A'),
                Recinto(id=2, nombre='Recinto B'),
                Recinto(id=3, nombre='Recinto C'),
                Recinto(id=5, nombre='Recinto D'),
                Establecimiento(id=1, nombre='Establecimiento X'),
                Establecimiento(id=2, nombre='Establecimiento Y'),
                Establecimiento(id=5, nombre='Establecimiento Z'),
                Establecimiento(id=999, nombre='Establecimiento Otro'),
            ])
            hoy = datetime.combine(date.today(), datetime.min.time())
            sesion.add_all([
                Caso(id=1, recinto_notifica_id=1, recinto_inscrito_id=999,
                     ciclo_vital_id=1, asignado_ts_id=10, estado='PENDIENTE_RESCATAR', fecha_ingreso=hoy),
                Caso(id=2, recinto_notifica_id=2, recinto_inscrito_id=1,
                     ciclo_vital_id=2, asignado_a_usuario_id=10, estado='EN_SEGUIMIENTO', fecha_ingreso=hoy),
                Caso(id=3, recinto_notifica_id=2, recinto_inscrito_id=1,
                     ciclo_vital_id=1, asignado_coord_id=30, estado='CERRADO', fecha_ingreso=hoy),
                Caso(id=4, recinto_notifica_id=3, recinto_inscrito_id=2,
                     ciclo_vital_id=3, estado='ANULADO', fecha_ingreso=hoy),
                Caso(id=5, recinto_notifica_id=5, recinto_inscrito_id=2,
                     ciclo_vital_id=4, estado='CERRADO', fecha_ingreso=hoy),
                Caso(id=6, recinto_notifica_id=None, recinto_inscrito_id=1,
                     ciclo_vital_id=1, estado='EN_SEGUIMIENTO', fecha_ingreso=hoy),
                Caso(id=7, recinto_notifica_id=3, recinto_inscrito_id=5,
                     ciclo_vital_id=2, estado='PENDIENTE_RESCATAR', fecha_ingreso=hoy),
            ])

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.sesion = self.Session()

    def tearDown(self):
        self.sesion.close()

    def filtrada(self, persona, consulta):
        return aplicar_filtro_casos(persona, consulta, 'casos.listar', modelo=Caso)

    def ids(self, persona, estado=None):
        consulta = self.filtrada(persona, self.sesion.query(Caso.id))
        if estado is None:
            consulta = consulta.filter(Caso.estado != 'ANULADO')
        else:
            consulta = consulta.filter(Caso.estado == estado)
        return {fila[0] for fila in consulta.all()}

    def kpis(self, persona):
        # El conteo de KPIs usa la misma politica y excluye anulados.
        return self.filtrada(persona, self.sesion.query(func.count(Caso.id))).filter(
            Caso.estado != 'ANULADO'
        ).scalar()

    def semanal(self, persona):
        limite = datetime.combine(date.today() - timedelta(days=6), datetime.min.time())
        consulta = self.sesion.query(Caso.fecha_ingreso).filter(
            Caso.fecha_ingreso >= limite, Caso.estado != 'ANULADO'
        )
        return len(self.filtrada(persona, consulta).all())

    def notificacion(self, persona):
        consulta = self.sesion.query(
            Recinto.nombre, func.count(Caso.id)
        ).join(Recinto, Caso.recinto_notifica_id == Recinto.id).filter(
            Caso.estado != 'ANULADO'
        ).group_by(Recinto.nombre)
        return dict(self.filtrada(persona, consulta).all())

    def inscritos(self, persona):
        consulta = self.sesion.query(
            Establecimiento.nombre, func.count(Caso.id)
        ).join(Establecimiento, Caso.recinto_inscrito_id == Establecimiento.id).filter(
            Caso.estado != 'ANULADO'
        ).group_by(Establecimiento.nombre)
        return dict(self.filtrada(persona, consulta).all())

    def comprobar_cinco_superficies(self, persona, esperados):
        self.assertEqual(self.ids(persona), esperados)
        self.assertEqual(self.kpis(persona), len(esperados))
        self.assertEqual(self.semanal(persona), len(esperados))
        self.assertLessEqual(sum(self.notificacion(persona).values()), len(esperados))
        self.assertLessEqual(sum(self.inscritos(persona).values()), len(esperados))

    def test_admin_global_en_cinco_superficies(self):
        self.comprobar_cinco_superficies(usuario('Admin'), {1, 2, 3, 5, 6, 7})

    def test_torre_control_global_en_cinco_superficies(self):
        self.comprobar_cinco_superficies(usuario('Torre Control'), {1, 2, 3, 5, 6, 7})

    def test_visualizador_global_aunque_tenga_ciclos(self):
        self.comprobar_cinco_superficies(usuario('Visualizador', ciclos=(1,)), {1, 2, 3, 5, 6, 7})

    def test_referente_con_ciclo_solo_casos_de_su_ciclo(self):
        self.comprobar_cinco_superficies(usuario('Referente', ciclos=(1,)), {1, 3, 6})

    def test_referente_sin_ciclos_no_expone_indicadores(self):
        self.comprobar_cinco_superficies(usuario('Referente'), set())

    def test_trabajador_social_asignacion_actual_y_heredada(self):
        self.comprobar_cinco_superficies(usuario('Trabajador(a) Social', uid=10), {1, 2})

    def test_coordinador_ciclo_solo_asignacion(self):
        self.comprobar_cinco_superficies(usuario('Coordinador Ciclo', uid=30), {3})

    def test_epi_ve_solo_recinto_autorizado(self):
        self.comprobar_cinco_superficies(usuario('Coordinador EPI', recintos=(2,)), {2, 3})

    def test_urgencia_ve_varios_recintos_autorizados(self):
        self.comprobar_cinco_superficies(usuario('Coordinador(a) de Urgencia', recintos=(1, 5)), {1, 5})

    def test_usuario_territorial_sin_recintos_no_expone_nada(self):
        self.comprobar_cinco_superficies(usuario('Coordinador(a) de Urgencia'), set())

    def test_solicitante_no_expone_listado_ni_indicadores(self):
        self.comprobar_cinco_superficies(usuario('Solicitante'), set())

    def test_recinto_inscrito_no_concede_acceso_territorial(self):
        # Caso 6 tiene establecimiento inscrito 1, pero recinto notificador NULL.
        persona = usuario('Coordinador EPI', recintos=(1,))
        self.assertEqual(self.ids(persona), {1})
        self.assertEqual(self.inscritos(persona), {'Establecimiento Otro': 1})
        self.assertEqual(self.notificacion(persona), {'Recinto A': 1})

    def test_anulados_no_entran_a_kpis_pero_si_filtro_explicito_de_estado(self):
        persona = usuario('Coordinador EPI', recintos=(3,))
        self.assertEqual(self.ids(persona), {7})
        self.assertEqual(self.ids(persona, estado='ANULADO'), {4})
        self.assertEqual(self.kpis(persona), 1)
        self.assertEqual(self.semanal(persona), 1)

    def test_usuario_inactivo_no_recibe_casos(self):
        self.comprobar_cinco_superficies(usuario('Admin', activo=False), set())


if __name__ == '__main__':
    unittest.main()
