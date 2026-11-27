"""Pruebas HTTP del endpoint REAL GET /casos/ (Fase 1.3-C.2-C).

Aislamiento: instancia Flask exclusiva, SQLite en memoria, datos inventados.
NO importa create_app(), NO utiliza .env/MySQL y NO escribe en uploads/.
Solo se sustituye render_template para inspeccionar datos de la vista como JSON.
La autorización, las consultas, Flask-Login y la ruta index() son reales.
"""
import unittest
from datetime import timedelta
from unittest.mock import patch

from flask import Flask, jsonify
from flask_login import LoginManager
from sqlalchemy.pool import StaticPool

from blueprints import casos as modulo_casos
from models import (
    db, Usuario, Rol, Caso, CatalogoCiclo,
    CatalogoRecinto, CatalogoEstablecimiento, obtener_hora_chile,
)


class TestDashboardHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SECRET_KEY='solo-pruebas-dashboard-http',
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
        login_manager.login_view = 'login_test'

        @login_manager.user_loader
        def cargar_usuario(uid):
            return db.session.get(Usuario, int(uid))

        @cls.app.route('/login-prueba')
        def login_test():
            return 'LOGIN_PRUEBA', 200

        cls.app.register_blueprint(modulo_casos.casos_bp)

        with cls.app.app_context():
            db.create_all()
            roles = {
                nombre: Rol(id=i, nombre=nombre)
                for i, nombre in enumerate([
                    'Admin', 'Torre Control', 'Visualizador', 'Referente',
                    'Trabajador(a) Social', 'Coordinador Ciclo',
                    'Coordinador EPI', 'Coordinador(a) de Urgencia',
                    'Solicitante',
                ], start=1)
            }
            recintos = {
                i: CatalogoRecinto(id=i, nombre=f'Recinto Ficticio {i}', activo=True)
                for i in (1, 2, 3, 5)
            }
            ciclos = {
                i: CatalogoCiclo(id=i, nombre=f'Ciclo Ficticio {i}')
                for i in (1, 2, 3)
            }
            establecimientos = {
                i: CatalogoEstablecimiento(id=i, nombre=f'Establecimiento Ficticio {i}', activo=True)
                for i in (1, 2, 3)
            }
            db.session.add_all([
                *roles.values(), *recintos.values(), *ciclos.values(),
                *establecimientos.values(),
            ])

            def usuario(uid, rol, *, activo=True, recintos_ids=(), ciclos_ids=()):
                u = Usuario(
                    id=uid,
                    nombre_completo=f'Usuario Ficticio {uid}',
                    email=f'usuario{uid}@example.invalid',
                    password_hash='no-es-una-contrasena-real',
                    activo=activo,
                    cambio_clave_requerido=False,
                    rol=roles[rol],
                )
                u.recintos = [recintos[r] for r in recintos_ids]
                u.ciclos = [ciclos[c] for c in ciclos_ids]
                return u

            usuarios = [
                usuario(10, 'Trabajador(a) Social'),
                usuario(30, 'Coordinador Ciclo'),
                usuario(40, 'Referente', ciclos_ids=(1,)),
                usuario(41, 'Referente'),
                usuario(50, 'Coordinador EPI', recintos_ids=(1,)),
                usuario(51, 'Coordinador(a) de Urgencia', recintos_ids=(2, 5)),
                usuario(52, 'Coordinador(a) de Urgencia'),
                usuario(60, 'Visualizador', ciclos_ids=(1,)),
                usuario(70, 'Solicitante'),
                usuario(71, 'Admin', activo=False),
                usuario(80, 'Admin'),
                usuario(81, 'Torre Control'),
            ]
            db.session.add_all(usuarios)
            hoy = obtener_hora_chile().replace(tzinfo=None)

            # Ocho casos inventados. El recinto inscrito NO determina acceso.
            datos = [
                # id, notificador, inscrito, ciclo, estado, ts, legacy, coord, dias
                (1, 1, 2, 1, 'PENDIENTE_RESCATAR', 10, None, None, 0),
                (2, 2, 1, 2, 'EN_SEGUIMIENTO', None, 10, None, 0),
                (3, 2, 1, 1, 'CERRADO', None, None, 30, 0),
                (4, 3, 2, 3, 'ANULADO', None, None, None, 0),
                (5, 5, 3, 3, 'EN_SEGUIMIENTO', None, None, None, 0),
                (6, 1, 1, 2, 'CERRADO', None, None, None, 0),
                (7, 3, 2, 1, 'EN_SEGUIMIENTO', None, None, None, 0),
                (8, 5, 2, 2, 'CERRADO', None, None, None, 20),
            ]
            for (id_, notificador, inscrito, ciclo, estado, ts, legacy,
                 coord, dias) in datos:
                db.session.add(Caso(
                    id=id_, recinto_notifica_id=notificador,
                    recinto_inscrito_id=inscrito, ciclo_vital_id=ciclo,
                    estado=estado, asignado_ts_id=ts,
                    asignado_a_usuario_id=legacy, asignado_coord_id=coord,
                    origen_relato='Historia completamente ficticia',
                    folio_atencion=f'PRUEBA-{id_:03d}',
                    fecha_ingreso=hoy-timedelta(days=dias),
                ))
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    @staticmethod
    def _renderizar_resumen(template, **contexto):
        # NO se parchea la lógica del endpoint: solo HTML -> JSON observable.
        assert template == 'casos/index.html'
        pag = contexto['pagination']
        stats = contexto['stats']
        return jsonify({
            'ids': sorted(item.id for item in pag.items),
            'total_pagina': pag.total,
            'pagina': pag.page,
            'por_pagina': pag.per_page,
            'stats': {
                k: stats[k] for k in
                ('total', 'pendientes', 'seguimiento', 'cerrados',
                 'notif_total', 'notif_labels', 'notif_values',
                 'inscritos_labels', 'inscritos_values', 'bar_data')
            },
            'titulo': contexto['nombre_filtro'],
        })

    def _get(self, uid=None, ruta='/casos/'):
        with self.app.test_client() as cliente:
            if uid is not None:
                with cliente.session_transaction() as sesion:
                    sesion['_user_id'] = str(uid)
                    sesion['_fresh'] = True
            with patch.object(modulo_casos, 'render_template', self._renderizar_resumen):
                respuesta = cliente.get(ruta, follow_redirects=False)
            return respuesta

    def _comprobar(self, uid, ids, *, kpis=None, notificados=None):
        respuesta = self._get(uid)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos['ids'], sorted(ids))
        total_no_anulados = sum(i != 4 for i in ids)
        self.assertEqual(datos['stats']['total'], total_no_anulados if kpis is None else kpis)
        self.assertEqual(datos['stats']['notif_total'], datos['stats']['total'])
        self.assertEqual(sum(datos['stats']['notif_values']), datos['stats']['total'])
        if notificados is not None:
            self.assertEqual(set(datos['stats']['notif_labels']),
                             {f'Recinto Ficticio {i}' for i in notificados})
        # Para todos los casos con establecimiento de prueba, coincide el total.
        self.assertEqual(sum(datos['stats']['inscritos_values']), datos['stats']['total'])
        return datos

    def test_admin_global(self):
        self._comprobar(80, [1, 2, 3, 5, 6, 7, 8], kpis=7,
                        notificados=[1, 2, 3, 5])

    def test_torre_control_global(self):
        self._comprobar(81, [1, 2, 3, 5, 6, 7, 8], kpis=7)

    def test_visualizador_global_aunque_tenga_ciclo(self):
        self._comprobar(60, [1, 2, 3, 5, 6, 7, 8], kpis=7)

    def test_referente_limitado_a_ciclo(self):
        self._comprobar(40, [1, 3, 7], kpis=3)

    def test_referente_sin_ciclos_no_expone_kpis(self):
        datos = self._comprobar(41, [], kpis=0)
        self.assertEqual(datos['stats']['bar_data'], [0]*7)

    def test_trabajador_social_actual_y_legacy(self):
        self._comprobar(10, [1, 2], kpis=2)

    def test_coordinador_ciclo_solo_asignados(self):
        self._comprobar(30, [3], kpis=1)

    def test_epi_recinto_notificador(self):
        datos = self._comprobar(50, [1, 6], kpis=2, notificados=[1])
        # El recinto inscrito 1 tambien existe en casos ajenos; no concede acceso.
        self.assertEqual(datos['stats']['inscritos_values'], [1, 1])

    def test_urgencia_varios_recintos(self):
        self._comprobar(51, [2, 3, 5, 8], kpis=4, notificados=[2, 5])

    def test_urgencia_sin_recintos_no_expone_nada(self):
        self._comprobar(52, [], kpis=0)

    def test_solicitante_recibe_403(self):
        self.assertEqual(self._get(70).status_code, 403)

    def test_usuario_inactivo_redirige_login(self):
        respuesta = self._get(71)

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/login-prueba', respuesta.headers['Location'])

    def test_anonimo_requiere_login(self):
        respuesta = self._get()
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/login-prueba', respuesta.headers['Location'])

    def test_anulados_explicitos_solo_en_listado(self):
        respuesta = self._get(80, '/casos/?estado=ANULADO')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos['ids'], [4])
        self.assertEqual(datos['stats']['total'], 7)

    def test_busqueda_y_filtro_estado_no_exponen_ajenos(self):
        respuesta = self._get(50, '/casos/?search=PRUEBA-002&estado=EN_SEGUIMIENTO')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos['ids'], [])
        self.assertEqual(datos['stats']['total'], 2)

    def test_busqueda_autorizada_y_paginacion(self):
        respuesta = self._get(51, '/casos/?search=PRUEBA-005&page=2')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos['ids'], [])
        self.assertEqual(datos['total_pagina'], 1)
        self.assertEqual(datos['pagina'], 2)
        self.assertEqual(datos['por_pagina'], 15)
        self.assertEqual(datos['stats']['total'], 4)


if __name__ == '__main__':
    unittest.main()
