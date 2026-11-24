"""Fase 1.3-C.5-A: caracterizacion aislada de operaciones POST.

No abre MySQL, no escribe PDFs y no envia correos. Se invocan las vistas bajo
request_context, omitiendo exclusivamente @login_required. NO comprueba sesiones
reales, CSRF ni middleware before_request; esas superficies requieren pruebas
HTTP integradas posteriores.

Las pruebas *_OBJETIVO documentan diferencias de seguridad del codigo legado.
Se eliminara @expectedFailure cuando se implemente cada politica POST.
"""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import HTTPException
from app import create_app
from blueprints import casos as modulo


class TestPostRBACCaracterizacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "redprotege-fase-1-3-c5a-sin-db"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol, *, uid=10, activo=True, ciclos=None, recintos=None):
        return SimpleNamespace(
            id=uid, activo=activo, is_authenticated=True,
            rol=SimpleNamespace(nombre=rol),
            ciclos=[SimpleNamespace(id=x) for x in (ciclos or [])],
            recintos=[SimpleNamespace(id=x) for x in (recintos or [])],
            subrogante_de=None,
            email="usuario@example.invalid",
            nombre_completo="Usuario de prueba",
        )

    @staticmethod
    def caso(*, estado="EN_SEGUIMIENTO", ts=20, coord=30,
             ciclo=2, recinto=1):
        return SimpleNamespace(
            id=1, folio_atencion="FICT-001", estado=estado,
            ciclo_vital_id=ciclo, recinto_notifica_id=recinto,
            asignado_ts_id=ts, asignado_a_usuario_id=ts,
            asignado_coord_id=coord, usuario_cierre_id=None,
            acta_pdf_path=None, asignado_at=None,
            asignado_por_usuario_id=None,
        )

    def ejecutar(self, nombre, ruta, usuario, caso, *, data=None):
        """Ejecuta la vista con dependencias sustituidas y registra efectos.

        Las operaciones simuladas sobre db.session no persisten nada; los
        cambios sobre el caso ficticio se detectan comparando su estado.
        """
        with self.app.test_request_context(ruta, method="POST", data=data or {}):
            with ExitStack() as stack:
                stack.enter_context(patch.object(modulo, "current_user", usuario))
                cq = MagicMock(name="consulta_casos_simulada")
                cq.get_or_404.return_value = caso
                stack.enter_context(patch.object(modulo.Caso, "query", cq))
                uq = MagicMock(name="consulta_usuarios_simulada")
                stack.enter_context(patch.object(modulo.Usuario, "query", uq))
                sesion = MagicMock(name="sesion_simulada")
                stack.enter_context(patch.object(modulo.db, "session", sesion))
                log = stack.enter_context(patch.object(modulo, "registrar_log"))
                pdf = stack.enter_context(patch.object(modulo, "generar_acta_cierre_pdf"))
                mail1 = stack.enter_context(patch.object(modulo, "enviar_aviso_cierre"))
                mail2 = stack.enter_context(patch.object(modulo, "enviar_aviso_asignacion"))
                stack.enter_context(patch.object(modulo, "obtener_hora_chile", return_value=None))
                stack.enter_context(patch.object(modulo, "render_template", return_value="VISTA_SIMULADA"))
                try:
                    resultado = getattr(modulo, nombre).__wrapped__(1)
                    status = resultado.status_code if hasattr(resultado, "status_code") else 200
                except HTTPException as exc:
                    status = exc.code
                return SimpleNamespace(status=status, sesion=sesion, log=log,
                                       pdf=pdf, mail1=mail1, mail2=mail2,
                                       caso=caso, usuarios=uq)

    def sin_efectos(self, r, *, estado="EN_SEGUIMIENTO"):
        self.assertEqual(r.caso.estado, estado)
        r.sesion.add.assert_not_called()
        r.sesion.commit.assert_not_called()
        r.sesion.delete.assert_not_called()
        r.sesion.flush.assert_not_called()
        r.pdf.assert_not_called()
        r.mail1.assert_not_called()
        r.mail2.assert_not_called()
        r.log.assert_not_called()

    # --- Comportamientos existentes que no deben deteriorarse ---
    def test_01_visualizador_no_gestiona_actualmente(self):
        r = self.ejecutar("gestionar_caso", "/casos/gestionar/1",
                          self.usuario("Visualizador"), self.caso())
        self.assertEqual(r.status, 302)
        self.sin_efectos(r)

    def test_02_ts_ajeno_no_cierra_actualmente(self):
        r = self.ejecutar("cerrar_caso", "/casos/cerrar/1",
                          self.usuario("Trabajador(a) Social", uid=10), self.caso(ts=99))
        self.assertEqual(r.status, 302)
        self.sin_efectos(r)

    def test_03_admin_no_cierra_estado_terminal(self):
        r = self.ejecutar("cerrar_caso", "/casos/cerrar/1",
                          self.usuario("Admin"), self.caso(estado="CERRADO"))
        self.assertEqual(r.status, 302)
        self.sin_efectos(r, estado="CERRADO")

    def test_04_torre_no_cierra_anulado(self):
        r = self.ejecutar("cerrar_caso", "/casos/cerrar/1",
                          self.usuario("Torre Control"), self.caso(estado="ANULADO"))
        self.assertEqual(r.status, 302)
        self.sin_efectos(r, estado="ANULADO")

    def test_05_ts_no_anula_actualmente(self):
        r = self.ejecutar("anular_caso", "/casos/anular/1",
                          self.usuario("Trabajador(a) Social", uid=20), self.caso(),
                          data={"motivo_anulacion": "Motivo ficticio"})
        self.assertEqual(r.status, 302)
        self.sin_efectos(r)

    def test_06_admin_no_anula_sin_motivo(self):
        r = self.ejecutar("anular_caso", "/casos/anular/1",
                          self.usuario("Admin"), self.caso(), data={})
        self.assertEqual(r.status, 302)
        self.sin_efectos(r)

    def test_07_referente_fuera_ciclo_no_asigna_ya_por_lectura(self):
        r = self.ejecutar("ver_caso", "/casos/ver/1",
                          self.usuario("Referente", ciclos=[77]), self.caso(ciclo=2),
                          data={"asignar_funcionario": "1", "ts_id": "20"})
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    def test_08_admin_inactivo_no_asigna_ya_por_lectura(self):
        r = self.ejecutar("ver_caso", "/casos/ver/1",
                          self.usuario("Admin", activo=False), self.caso(),
                          data={"asignar_funcionario": "1", "ts_id": "20"})
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    # --- Objetivos pendientes: se activan al modernizar endpoints ---
    @unittest.expectedFailure
    def test_09_OBJETIVO_visualizador_gestion_rechazada_403(self):
        r = self.ejecutar("gestionar_caso", "/casos/gestionar/1",
                          self.usuario("Visualizador"), self.caso())
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    @unittest.expectedFailure
    def test_10_OBJETIVO_urgencia_gestiona_su_recinto(self):
        r = self.ejecutar("gestionar_caso", "/casos/gestionar/1",
                          self.usuario("Coordinador(a) de Urgencia", recintos=[1]),
                          self.caso(recinto=1))
        self.assertEqual(r.status, 200)

    @unittest.expectedFailure
    def test_11_OBJETIVO_urgencia_ajeno_denegado_403(self):
        r = self.ejecutar("gestionar_caso", "/casos/gestionar/1",
                          self.usuario("Coordinador(a) de Urgencia", recintos=[3]),
                          self.caso(recinto=1))
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    @unittest.expectedFailure
    def test_12_OBJETIVO_admin_inactivo_no_cierra(self):
        r = self.ejecutar("cerrar_caso", "/casos/cerrar/1",
                          self.usuario("Admin", activo=False), self.caso())
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    @unittest.expectedFailure
    def test_13_OBJETIVO_admin_inactivo_no_anula(self):
        r = self.ejecutar("anular_caso", "/casos/anular/1",
                          self.usuario("Admin", activo=False), self.caso(),
                          data={"motivo_anulacion": "Caso ficticio duplicado"})
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    @unittest.expectedFailure
    def test_14_OBJETIVO_ts_ajeno_no_cierra_403(self):
        r = self.ejecutar("cerrar_caso", "/casos/cerrar/1",
                          self.usuario("Trabajador(a) Social", uid=10), self.caso(ts=99))
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)

    @unittest.expectedFailure
    def test_15_OBJETIVO_ts_no_anula_403(self):
        r = self.ejecutar("anular_caso", "/casos/anular/1",
                          self.usuario("Trabajador(a) Social", uid=20), self.caso(),
                          data={"motivo_anulacion": "Motivo ficticio"})
        self.assertEqual(r.status, 403)
        self.sin_efectos(r)


if __name__ == "__main__":
    unittest.main()
