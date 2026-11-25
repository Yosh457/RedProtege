"""Fase 1.3-C.3-A: caracterizacion HTTP de GET /casos/ver/<id>.

Usa el blueprint real, Flask-Login y SQLite temporal en memoria.
No importa create_app(), no usa .env ni la base MySQL local.
La plantilla se reemplaza por JSON para comprobar la autorizacion sin depender
ni del HTML ni de formularios de asignacion.

Los @expectedFailure reflejan reglas objetivo NO integradas aun en ver_caso().
Cuando se integre la politica, quitar esos decoradores y exigir que pasen.
"""
import unittest
from unittest.mock import patch

from flask import Flask, jsonify
from flask_login import LoginManager
from sqlalchemy.pool import StaticPool

from blueprints import casos as modulo_casos
from models import db, Usuario, Rol, Caso, CatalogoCiclo, CatalogoRecinto


class TestDetalleHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SECRET_KEY='solo-pruebas-detalle-http',
            SQLALCHEMY_DATABASE_URI='sqlite+pysqlite:///:memory:',
            SQLALCHEMY_ENGINE_OPTIONS={
                'connect_args': {'check_same_thread': False},
                'poolclass': StaticPool,
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)
        login_manager = LoginManager()
        login_manager.init_app(cls.app)
        login_manager.login_view = 'login_detalle_prueba'

        @login_manager.user_loader
        def cargar_usuario(uid):
            return db.session.get(Usuario, int(uid))

        @cls.app.route('/login-detalle-prueba')
        def login_detalle_prueba():
            return 'LOGIN_PRUEBA', 200

        cls.app.register_blueprint(modulo_casos.casos_bp)

        with cls.app.app_context():
            db.create_all()
            nombres_roles = [
                'Admin', 'Torre Control', 'Visualizador', 'Referente',
                'Trabajador(a) Social', 'Coordinador Ciclo', 'Coordinador EPI',
                'Coordinador(a) de Urgencia', 'Solicitante',
            ]
            roles = {nombre: Rol(id=i, nombre=nombre)
                     for i, nombre in enumerate(nombres_roles, start=1)}
            ciclos = {i: CatalogoCiclo(id=i, nombre=f'Ciclo Ficticio {i}')
                      for i in (1, 2)}
            recintos = {i: CatalogoRecinto(id=i, nombre=f'Recinto Ficticio {i}', activo=True)
                        for i in (1, 2)}
            db.session.add_all([*roles.values(), *ciclos.values(), *recintos.values()])

            def usuario(uid, rol, *, activo=True, ciclo_ids=(), recinto_ids=()):
                u = Usuario(
                    id=uid,
                    nombre_completo=f'Usuario Ficticio {uid}',
                    email=f'detalle{uid}@example.invalid',
                    password_hash='hash-no-real',
                    activo=activo,
                    cambio_clave_requerido=False,
                    rol=roles[rol],
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
                usuario(21, 'Coordinador EPI'),
                usuario(22, 'Referente', ciclo_ids=(2,)),
            ]
            # La subrogancia del usuario 22 extiende su ambito al ciclo 1.
            usuarios[-1].subrogante_de = usuarios[3]
            db.session.add_all(usuarios)
            for id_, ciclo, recinto, ts, legado, coord in [
                (1, 1, 1, 15, None, 16),
                (2, 2, 2, None, 15, None),
                (3, 1, 2, None, None, None),
            ]:
                db.session.add(Caso(
                    id=id_, ciclo_vital_id=ciclo,
                    recinto_notifica_id=recinto,
                    asignado_ts_id=ts, asignado_a_usuario_id=legado,
                    asignado_coord_id=coord,
                    estado='EN_SEGUIMIENTO',
                    folio_atencion=f'DET-{id_:03d}',
                    origen_relato='Caso totalmente inventado',
                ))
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    @staticmethod
    def _renderizar_detalle(template, **contexto):
        assert template == 'casos/ver.html'
        return jsonify({
            'caso_id': contexto['caso'].id,
            'puede_asignar_interfaz': bool(contexto['puede_asignar']),
            'total_ts_disponibles': len(contexto['funcionarios_ts']),
            'total_coord_disponibles': len(contexto['funcionarios_coord']),
        })

    def _get(self, usuario_id=None, caso_id=1):
        with self.app.test_client() as cliente:
            if usuario_id is not None:
                with cliente.session_transaction() as sesion:
                    sesion['_user_id'] = str(usuario_id)
                    sesion['_fresh'] = True
            with patch.object(modulo_casos, 'render_template', self._renderizar_detalle):
                return cliente.get(f'/casos/ver/{caso_id}', follow_redirects=False)

    def _permitido(self, usuario_id, caso_id, *, puede_asignar=None):
        respuesta = self._get(usuario_id, caso_id)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos['caso_id'], caso_id)
        if puede_asignar is not None:
            self.assertEqual(datos['puede_asignar_interfaz'], puede_asignar)

    def _denegado(self, usuario_id, caso_id):
        self.assertEqual(self._get(usuario_id, caso_id).status_code, 403)

    # Comportamientos actuales que deben preservarse.
    def test_01_anonimo_redirige_login(self):
        r = self._get()
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login-detalle-prueba', r.headers['Location'])

    def test_02_admin_accede_detalle(self):
        self._permitido(10, 2, puede_asignar=True)

    def test_03_torre_control_accede_detalle(self):
        self._permitido(11, 1, puede_asignar=True)

    def test_04_visualizador_en_su_ciclo_solo_lectura(self):
        self._permitido(12, 1, puede_asignar=False)

    def test_05_referente_accede_su_ciclo(self):
        self._permitido(13, 1, puede_asignar=True)

    def test_06_referente_no_accede_ajeno(self):
        self._denegado(13, 2)

    def test_07_trabajador_social_asignado(self):
        self._permitido(15, 1, puede_asignar=False)

    def test_08_trabajador_social_heredado(self):
        self._permitido(15, 2, puede_asignar=False)

    def test_09_trabajador_social_ajeno_denegado(self):
        self._denegado(15, 3)

    def test_10_coordinador_asignado_solo_lectura(self):
        self._permitido(16, 1, puede_asignar=False)

    def test_11_coordinador_no_asignado_denegado(self):
        self._denegado(16, 2)

    def test_12_solicitante_denegado(self):
        self._denegado(19, 1)

    def test_13_referente_subrogante_accede_ciclo_titular(self):
        self._permitido(22, 1, puede_asignar=True)

    # Diferencias conocidas contra la politica OBJETIVO; no ocultarlas.
    def test_14_OBJETIVO_epi_puede_ver_su_recinto(self):
        self._permitido(17, 1, puede_asignar=False)

    def test_15_OBJETIVO_urgencia_puede_ver_su_recinto(self):
        self._permitido(18, 2, puede_asignar=False)

    def test_16_OBJETIVO_visualizador_global_con_ciclo(self):
        self._permitido(12, 2, puede_asignar=False)

    def test_17_OBJETIVO_referente_sin_ciclos_no_es_global(self):
        self._denegado(14, 1)

    def test_18_OBJETIVO_usuario_inactivo_denegado(self):
        self._denegado(20, 1)

    def test_19_epi_sin_recintos_no_puede_ver_actualmente(self):
        self._denegado(21, 1)


if __name__ == '__main__':
    unittest.main()
