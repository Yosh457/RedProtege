"""Pruebas de política objetivo (Fase 1.3-B) sin Flask, MySQL ni SMTP.

Ejecutar: python -m unittest tests.test_autorizacion -v
"""
import unittest
from types import SimpleNamespace as NS

from sqlalchemy import select
from sqlalchemy.dialects import mysql

from models import Caso
from utils.autorizacion import (
    ADMIN, TORRE, TS, COORD, EPI, REFERENTE, VISUALIZADOR,
    SOLICITANTE, URGENCIA, LISTAR, VER, GESTIONAR, ASIGNAR_TS,
    ASIGNAR_COORD, CERRAR, ANULAR, EXPORTAR, DESCARGAR_ACTA,
    REPORTE_MASIVO, GESTIONAR_SUBROGANCIAS, ADMINISTRAR_USUARIOS,
    INGRESAR_SOLICITUD, puede_realizar, puede_acceder_caso,
    puede_descargar_acta_historica, aplicar_filtro_casos,
)


def usuario(rol, uid=10, *, ciclos=(), recintos=None, activo=True,
            autenticado=True, titular=None, ciclo_legado=None):
    return NS(id=uid, rol=NS(nombre=rol) if rol is not None else None,
              activo=activo, is_authenticated=autenticado,
              ciclos=[NS(id=c) for c in ciclos],
              recintos=None if recintos is None else [NS(id=r) for r in recintos],
              subrogante_de=titular, ciclo_asignado_id=ciclo_legado)


def caso(*, ciclo=2, recinto=3, ts=20, ts_legacy=None, coord=30,
         estado='EN_SEGUIMIENTO', cierre=None, acta='uploads/actas/acta_prueba.pdf'):
    return NS(ciclo_vital_id=ciclo, recinto_notifica_id=recinto,
              recinto_inscrito_id=99, asignado_ts_id=ts,
              asignado_a_usuario_id=ts_legacy, asignado_coord_id=coord,
              estado=estado, usuario_cierre_id=cierre, acta_pdf_path=acta)


def sql_consulta(usuario_obj, accion=LISTAR):
    stmt = aplicar_filtro_casos(usuario_obj, select(Caso.id), accion, Caso)
    return str(stmt.compile(dialect=mysql.dialect(), compile_kwargs={'literal_binds': True}))


class TestAutorizacionObjetivo(unittest.TestCase):
    def test_admin_tiene_operaciones_principales(self):
        u = usuario(ADMIN)
        for accion in (LISTAR, VER, GESTIONAR, ASIGNAR_TS, ASIGNAR_COORD,
                       CERRAR, ANULAR, EXPORTAR, REPORTE_MASIVO,
                       ADMINISTRAR_USUARIOS):
            with self.subTest(accion=accion):
                self.assertTrue(puede_realizar(u, accion))

    def test_solicitante_solo_ingresa(self):
        u = usuario(SOLICITANTE)
        self.assertTrue(puede_realizar(u, INGRESAR_SOLICITUD))
        for accion in (VER, LISTAR, EXPORTAR, GESTIONAR, CERRAR):
            self.assertFalse(puede_realizar(u, accion))

    def test_desconocido_inactivo_anonimo_denegados(self):
        for u in (None, usuario('Rol inexistente'), usuario(ADMIN, activo=False),
                  usuario(ADMIN, autenticado=False), usuario(None), usuario(ADMIN, uid=None)):
            with self.subTest(usuario=u):
                self.assertFalse(puede_realizar(u, VER))
                self.assertFalse(puede_acceder_caso(u, caso(), VER))

    def test_accion_desconocida_denegada(self):
        self.assertFalse(puede_realizar(usuario(ADMIN), 'casos.borrar'))
        self.assertFalse(puede_acceder_caso(usuario(ADMIN), caso(), 'casos.borrar'))

    def test_visualizador_global_aunque_tenga_ciclos(self):
        u = usuario(VISUALIZADOR, ciclos=(1,))
        self.assertTrue(puede_acceder_caso(u, caso(ciclo=2, recinto=100), VER))
        self.assertFalse(puede_acceder_caso(u, caso(), GESTIONAR))
        self.assertFalse(puede_realizar(u, REPORTE_MASIVO))

    def test_torre_global_sin_administracion_usuarios(self):
        u = usuario(TORRE)
        self.assertTrue(puede_acceder_caso(u, caso(), CERRAR))
        self.assertFalse(puede_realizar(u, ADMINISTRAR_USUARIOS))

    def test_ts_asignacion_actual(self):
        self.assertTrue(puede_acceder_caso(usuario(TS), caso(ts=10), GESTIONAR))

    def test_ts_asignacion_heredada(self):
        self.assertTrue(puede_acceder_caso(usuario(TS), caso(ts=20, ts_legacy=10), CERRAR))

    def test_ts_no_puede_caso_ajeno(self):
        self.assertFalse(puede_acceder_caso(usuario(TS), caso(ts=20, ts_legacy=30), VER))

    def test_coordinador_ciclo_solo_lectura_asignada(self):
        u = usuario(COORD)
        self.assertTrue(puede_acceder_caso(u, caso(coord=10), VER))
        self.assertFalse(puede_acceder_caso(u, caso(coord=11), VER))
        self.assertFalse(puede_acceder_caso(u, caso(coord=10), GESTIONAR))

    def test_referente_ciclo_propio(self):
        u = usuario(REFERENTE, ciclos=(2,))
        self.assertTrue(puede_acceder_caso(u, caso(ciclo=2), ASIGNAR_TS))
        self.assertFalse(puede_acceder_caso(u, caso(ciclo=3), ASIGNAR_TS))
        self.assertFalse(puede_realizar(u, GESTIONAR))

    def test_referente_sin_ciclos_ya_no_es_global(self):
        self.assertFalse(puede_acceder_caso(usuario(REFERENTE), caso(), VER))

    def test_referente_ciclo_legacy_explicito(self):
        self.assertTrue(puede_acceder_caso(usuario(REFERENTE, ciclo_legado=2), caso(ciclo=2), VER))

    def test_subrogancia_referente_valida_amplia_ciclos(self):
        titular = usuario(REFERENTE, uid=11, ciclos=(3,))
        u = usuario(REFERENTE, ciclos=(2,), titular=titular)
        self.assertTrue(puede_acceder_caso(u, caso(ciclo=3), ASIGNAR_COORD))
        self.assertFalse(puede_acceder_caso(u, caso(ciclo=4), VER))

    def test_subrogancia_titular_inactivo_o_rol_invalido_no_amplia(self):
        for titular in (usuario(REFERENTE, uid=11, ciclos=(3,), activo=False),
                        usuario(EPI, uid=11, ciclos=(3,))):
            self.assertFalse(puede_acceder_caso(
                usuario(REFERENTE, ciclos=(2,), titular=titular), caso(ciclo=3), VER))

    def test_subrogancia_solo_referentes(self):
        self.assertFalse(puede_realizar(usuario(VISUALIZADOR), GESTIONAR_SUBROGANCIAS))
        self.assertTrue(puede_realizar(usuario(REFERENTE), GESTIONAR_SUBROGANCIAS))

    def test_epi_dentro_y_fuera_recinto(self):
        u = usuario(EPI, recintos=(1, 3))
        self.assertTrue(puede_acceder_caso(u, caso(recinto=3), VER))
        self.assertFalse(puede_acceder_caso(u, caso(recinto=2), VER))
        self.assertFalse(puede_acceder_caso(u, caso(recinto=3), GESTIONAR))

    def test_urgencia_puede_gestionar_en_su_recinto(self):
        u = usuario(URGENCIA, recintos=(1, 3))
        self.assertTrue(puede_acceder_caso(u, caso(recinto=3), GESTIONAR))
        self.assertFalse(puede_acceder_caso(u, caso(recinto=2), GESTIONAR))
        self.assertFalse(puede_acceder_caso(u, caso(recinto=3), CERRAR))
        self.assertFalse(puede_acceder_caso(u, caso(recinto=3), ANULAR))

    def test_recinto_no_asignado_o_nulo_denegado(self):
        self.assertFalse(puede_acceder_caso(usuario(URGENCIA), caso(recinto=1), VER))
        self.assertFalse(puede_acceder_caso(usuario(EPI, recintos=(1,)), caso(recinto=None), VER))

    def test_recinto_inscrito_no_concede_permiso(self):
        c = caso(recinto=2)
        c.recinto_inscrito_id = 1
        self.assertFalse(puede_acceder_caso(usuario(URGENCIA, recintos=(1,)), c, VER))

    def test_estados_terminales_denegacion_de_mutaciones(self):
        u = usuario(ADMIN)
        for estado in ('CERRADO', 'ANULADO', None, 'DESCONOCIDO'):
            with self.subTest(estado=estado):
                self.assertFalse(puede_acceder_caso(u, caso(estado=estado), GESTIONAR))
                self.assertFalse(puede_acceder_caso(u, caso(estado=estado), CERRAR))
                self.assertTrue(puede_acceder_caso(u, caso(estado=estado), VER))

    def test_acta_requiere_ruta(self):
        self.assertFalse(puede_acceder_caso(usuario(ADMIN), caso(acta=None), DESCARGAR_ACTA))
        self.assertTrue(puede_acceder_caso(usuario(ADMIN), caso(), DESCARGAR_ACTA))

    def test_excepcion_historica_ts_que_cerro(self):
        u = usuario(TS)
        c = caso(ts=99, ts_legacy=98, estado='CERRADO', cierre=10)
        self.assertFalse(puede_acceder_caso(u, c, VER))
        self.assertTrue(puede_descargar_acta_historica(u, c))
        self.assertFalse(puede_descargar_acta_historica(usuario(TS, uid=11), c))
        self.assertFalse(puede_descargar_acta_historica(u, caso(cierre=10),))

    def test_consulta_global_no_agrega_filtros(self):
        sql = sql_consulta(usuario(VISUALIZADOR, ciclos=(1,)))
        self.assertNotIn('WHERE', sql)

    def test_consulta_referente_incluye_subrogado(self):
        u = usuario(REFERENTE, ciclos=(1,), titular=usuario(REFERENTE, uid=2, ciclos=(2,)))
        sql = sql_consulta(u)
        self.assertIn('casos.ciclo_vital_id IN (1, 2)', sql)

    def test_consulta_referente_sin_ciclos_no_deja_consulta_global(self):
        self.assertIn('WHERE false', sql_consulta(usuario(REFERENTE)).lower().replace('where false', 'WHERE false'))

    def test_consulta_urgencia_filtra_recinto_notificador(self):
        sql = sql_consulta(usuario(URGENCIA, recintos=(1, 3)), EXPORTAR)
        self.assertIn('casos.recinto_notifica_id IN (1, 3)', sql)
        self.assertNotIn('recinto_inscrito_id', sql)

    def test_consulta_urgencia_sin_recintos_denegada(self):
        self.assertIn('WHERE false', sql_consulta(usuario(URGENCIA)).lower().replace('where false', 'WHERE false'))

    def test_consulta_ts_incluye_asignacion_legacy(self):
        sql = sql_consulta(usuario(TS))
        self.assertIn('casos.asignado_ts_id = 10', sql)
        self.assertIn('casos.asignado_a_usuario_id = 10', sql)

    def test_consulta_coordinador_solo_sus_asignaciones(self):
        self.assertIn('casos.asignado_coord_id = 10', sql_consulta(usuario(COORD)))

    def test_consulta_solicitante_denegada(self):
        self.assertIn('WHERE false', sql_consulta(usuario(SOLICITANTE)).lower().replace('where false', 'WHERE false'))

    def test_consulta_accion_de_modificacion_no_exponible(self):
        self.assertIn('WHERE false', sql_consulta(usuario(ADMIN), CERRAR).lower().replace('where false', 'WHERE false'))

    def test_consulta_actas_filtra_ruta_no_nula(self):
        sql = sql_consulta(usuario(ADMIN), DESCARGAR_ACTA)
        self.assertIn('acta_pdf_path IS NOT NULL', sql)


if __name__ == '__main__':
    unittest.main()
