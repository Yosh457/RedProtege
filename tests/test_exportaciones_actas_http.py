"""Fase 1.3-C.4-A: caracterizacion HTTP de Excel y actas.

SQLite en memoria, identidades/casos ficticios y actas simuladas. Las marcas
expectedFailure registran brechas de la politica objetivo; NO son exitos de
seguridad. No modifica la app, el esquema ni archivos de produccion.
"""
import io
import unittest
from unittest.mock import patch

from flask import Flask, Response
from flask_login import LoginManager
from openpyxl import load_workbook
from sqlalchemy.pool import StaticPool

from blueprints import casos as modulo
from models import db, Usuario, Rol, Caso, CatalogoCiclo, CatalogoRecinto


class TestExportacionesActasHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SECRET_KEY='solo-tests-exportaciones-actas',
            SQLALCHEMY_DATABASE_URI='sqlite+pysqlite:///:memory:',
            SQLALCHEMY_ENGINE_OPTIONS={
                'connect_args': {'check_same_thread': False},
                'poolclass': StaticPool,
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)
        login = LoginManager()
        login.login_view = 'login_test_exportaciones'
        login.init_app(cls.app)

        @login.user_loader
        def cargar_usuario(uid):
            return db.session.get(Usuario, int(uid))

        @cls.app.route('/login-test-exportaciones')
        def login_test_exportaciones():
            return 'LOGIN_PRUEBA'

        cls.app.register_blueprint(modulo.casos_bp)
        with cls.app.app_context():
            db.create_all()
            nombres = [
                'Admin', 'Torre Control', 'Visualizador', 'Referente',
                'Trabajador(a) Social', 'Coordinador Ciclo', 'Coordinador EPI',
                'Coordinador(a) de Urgencia', 'Solicitante',
            ]
            roles = {nombre: Rol(id=i, nombre=nombre)
                     for i, nombre in enumerate(nombres, 1)}
            ciclos = {i: CatalogoCiclo(id=i, nombre=f'Ciclo Ficticio {i}')
                      for i in (1, 2)}
            recintos = {i: CatalogoRecinto(id=i, nombre=f'Recinto Ficticio {i}', activo=True)
                        for i in (1, 2)}
            db.session.add_all([*roles.values(), *ciclos.values(), *recintos.values()])

            def usuario(uid, rol, *, ciclo_ids=(), recinto_ids=(), activo=True):
                u = Usuario(
                    id=uid, nombre_completo=f'Profesional Ficticio {uid}',
                    email=f'exportacion{uid}@example.invalid',
                    password_hash='hash-ficticio', activo=activo,
                    cambio_clave_requerido=False, rol=roles[rol],
                )
                u.ciclos = [ciclos[c] for c in ciclo_ids]
                u.recintos = [recintos[r] for r in recinto_ids]
                return u

            usuarios = [
                usuario(10, 'Admin'),
                usuario(11, 'Torre Control'),
                usuario(12, 'Visualizador', ciclo_ids=(1,)),
                usuario(13, 'Referente', ciclo_ids=(1,)),
                usuario(14, 'Referente'),
                usuario(15, 'Trabajador(a) Social'),
                usuario(16, 'Coordinador Ciclo'),
                usuario(17, 'Coordinador EPI', recinto_ids=(1,)),
                usuario(18, 'Coordinador(a) de Urgencia', recinto_ids=(2,)),
                usuario(19, 'Solicitante'),
                usuario(20, 'Admin', activo=False),
                usuario(21, 'Trabajador(a) Social'),
            ]
            db.session.add_all(usuarios)
            for pk, ciclo, recinto, estado, ts, legado, coord, cierre in [
                (1, 1, 1, 'EN_SEGUIMIENTO', 15, None, 16, None),
                (2, 2, 2, 'CERRADO', None, 15, None, 21),
                (3, 1, 2, 'ANULADO', None, None, None, None),
            ]:
                db.session.add(Caso(
                    id=pk, ciclo_vital_id=ciclo, recinto_notifica_id=recinto,
                    estado=estado, asignado_ts_id=ts,
                    asignado_a_usuario_id=legado, asignado_coord_id=coord,
                    usuario_cierre_id=cierre,
                    folio_atencion=f'FIC-{pk:03d}',
                    origen_relato='Relato totalmente ficticio',
                    acta_pdf_path=(f'uploads/actas/ficticia_{pk}.pdf' if pk != 3 else None),
                ))
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def peticion(self, ruta, uid=None, *, simular_pdf=False):
        with self.app.test_client() as cliente:
            if uid is not None:
                with cliente.session_transaction() as sesion:
                    sesion['_user_id'] = str(uid)
                    sesion['_fresh'] = True
            if simular_pdf:
                # No se consulta ni abre un archivo PDF real.
                with patch.object(modulo.os.path, 'exists', return_value=True), \
                     patch.object(modulo, 'send_file', return_value=Response(
                         b'PDF_FICTICIO', mimetype='application/pdf')) as servir, \
                     patch.object(modulo, 'registrar_log'):
                    respuesta = cliente.get(ruta, follow_redirects=False)
                    return respuesta, servir.called
            return cliente.get(ruta, follow_redirects=False), False

    def folios_excel(self, uid, parametros=''):
        respuesta, _ = self.peticion('/casos/exportar' + parametros, uid)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('spreadsheetml', respuesta.mimetype)
        libro = load_workbook(io.BytesIO(respuesta.data), read_only=True, data_only=True)
        try:
            filas = list(libro.active.iter_rows(values_only=True))
            self.assertEqual(filas[0][1], 'Folio')
            return {fila[1] for fila in filas[1:]}
        finally:
            libro.close()

    def test_01_exportacion_anonima_redirige_login(self):
        r, _ = self.peticion('/casos/exportar')
        self.assertEqual(r.status_code, 302)
        self.assertIn('login-test-exportaciones', r.headers['Location'])

    def test_02_admin_exporta_no_anulados_por_defecto(self):
        self.assertEqual(self.folios_excel(10), {'FIC-001', 'FIC-002'})

    def test_03_torre_control_exporta_global(self):
        self.assertEqual(self.folios_excel(11), {'FIC-001', 'FIC-002'})

    def test_04_estado_anulado_explicito_es_exportable(self):
        self.assertEqual(self.folios_excel(10, '?estado=ANULADO'), {'FIC-003'})

    def test_05_referente_con_ciclo_filtra_exportacion(self):
        self.assertEqual(self.folios_excel(13), {'FIC-001'})

    def test_06_ts_incluye_asignacion_legacy(self):
        self.assertEqual(self.folios_excel(15), {'FIC-001', 'FIC-002'})

    def test_07_solicitante_no_exporta(self):
        r, _ = self.peticion('/casos/exportar', 19)
        self.assertEqual(r.status_code, 403)

    def test_08_descarga_anonima_redirige_login(self):
        r, _ = self.peticion('/casos/acta/1')
        self.assertEqual(r.status_code, 302)
        self.assertIn('login-test-exportaciones', r.headers['Location'])

    def test_09_admin_descarga_acta_simulada(self):
        r, servido = self.peticion('/casos/acta/1', 10, simular_pdf=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(servido)
        self.assertEqual(r.data, b'PDF_FICTICIO')

    def test_10_ts_que_cerro_conserva_descarga_historica(self):
        # El TS 21 cerró el caso 2 y no es su TS asignado actualmente.
        r, servido = self.peticion('/casos/acta/2', 21, simular_pdf=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(servido)

    def test_11_ts_ajeno_no_descarga(self):
        r, servido = self.peticion('/casos/acta/1', 21, simular_pdf=True)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(servido)

    # Politica OBJETIVO: estas discrepancias deben desaparecer en 1.3-C.4-B/C.
    def test_12_OBJETIVO_epi_exporta_solo_recinto_notificador(self):
        self.assertEqual(self.folios_excel(17), {'FIC-001'})

    def test_13_OBJETIVO_referente_sin_ciclos_no_exporta(self):
        r, _ = self.peticion('/casos/exportar', 14)
        self.assertEqual(r.status_code, 403)

    def test_14_OBJETIVO_visualizador_exporta_global(self):
        self.assertEqual(self.folios_excel(12), {'FIC-001', 'FIC-002'})

    def test_15_OBJETIVO_usuario_inactivo_no_exporta(self):
        r, _ = self.peticion('/casos/exportar', 20)
        self.assertEqual(r.status_code, 403)

    def test_16_OBJETIVO_epi_no_descarga_acta_de_recinto_ajeno(self):
        r, servido = self.peticion('/casos/acta/2', 17, simular_pdf=True)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(servido)

    def test_17_OBJETIVO_urgencia_descarga_acta_de_su_recinto(self):
        r, servido = self.peticion('/casos/acta/2', 18, simular_pdf=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(servido)

    def test_18_OBJETIVO_referente_sin_ciclos_no_descarga_acta(self):
        r, servido = self.peticion('/casos/acta/1', 14, simular_pdf=True)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(servido)


if __name__ == '__main__':
    unittest.main()
