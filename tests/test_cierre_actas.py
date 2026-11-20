"""Fase 1.2-B / bloque 2C: cierre de casos y actas (caracterizacion).

Pruebas unitarias con datos ficticios: SIN consultas MySQL, PDFs ni SMTP reales.
Ejecutar: python -m unittest tests.test_cierre_actas -v
No cubren sesiones HTTP/CSRF ni demuestran atomicidad real de MySQL.
"""
import os
import unittest
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints import casos as modulo


class TestCierreActas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "redprotege-prueba-cierre-aislada"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol="Admin", identificador=10):
        return SimpleNamespace(
            id=identificador,
            rol=SimpleNamespace(nombre=rol),
            nombre_completo="Profesional Ficticio",
            email="profesional@example.invalid",
        )

    @staticmethod
    def caso(ts=99, legacy_ts=None):
        return SimpleNamespace(
            id=1,
            folio_atencion="FICTICIO-001",
            estado="EN_SEGUIMIENTO",
            asignado_ts_id=ts,
            asignado_a_usuario_id=legacy_ts,
            fecha_cierre=None,
            usuario_cierre_id=None,
            acta_pdf_path=None,
        )

    def ejecutar(self, usuario, caso, *, error_en=None):
        """Ejecuta la funcion real con dependencias externas aisladas.

        error_en: 'primer_commit', 'pdf', 'segundo_commit' o 'correo'.
        """
        fecha = datetime(2026, 11, 20, 10, 30)
        eventos = []

        with self.app.test_request_context("/casos/cerrar/1", method="POST"):
            with ExitStack() as stack:
                stack.enter_context(patch.object(modulo, "current_user", usuario))
                consulta = MagicMock()
                consulta.get_or_404.return_value = caso
                stack.enter_context(patch.object(modulo.Caso, "query", consulta))
                session = MagicMock()
                stack.enter_context(patch.object(modulo.db, "session", session))
                stack.enter_context(patch.object(modulo, "obtener_hora_chile", return_value=fecha))
                pdf = stack.enter_context(patch.object(modulo, "generar_acta_cierre_pdf"))
                aviso = stack.enter_context(patch.object(modulo, "enviar_aviso_cierre"))
                log = stack.enter_context(patch.object(modulo, "registrar_log"))
                mensajes = stack.enter_context(patch.object(modulo, "flash"))

                def confirmar():
                    eventos.append(("commit", caso.estado, caso.acta_pdf_path))
                    if error_en == "primer_commit" and len([e for e in eventos if e[0] == "commit"]) == 1:
                        raise RuntimeError("Commit inicial simulado")
                    if error_en == "segundo_commit" and len([e for e in eventos if e[0] == "commit"]) == 2:
                        raise RuntimeError("Commit de ruta simulado")

                def generar(caso_arg, ruta, usuario_arg):
                    self.assertIs(caso_arg, caso)
                    self.assertIs(usuario_arg, usuario)
                    self.assertTrue(ruta.endswith("acta_1_FICTICIO-001.pdf"))
                    self.assertIn(os.path.join("uploads", "actas"), ruta)
                    eventos.append(("pdf", caso.estado, caso.acta_pdf_path))
                    if error_en == "pdf":
                        raise RuntimeError("Generacion PDF simulada")

                session.commit.side_effect = confirmar
                pdf.side_effect = generar
                if error_en == "correo":
                    aviso.side_effect = RuntimeError("SMTP simulado")

                respuesta = modulo.cerrar_caso.__wrapped__(1)

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.headers["Location"].endswith("/casos/ver/1"))
        consulta.get_or_404.assert_called_once_with(1)
        return SimpleNamespace(
            caso=caso, sesion=session, pdf=pdf, aviso=aviso,
            log=log, mensajes=mensajes, eventos=eventos,
            fecha=fecha, usuario=usuario,
        )

    def comprobar_exito(self, rol, identificador=10, ts=99, legacy_ts=None):
        caso = self.caso(ts=ts, legacy_ts=legacy_ts)
        result = self.ejecutar(self.usuario(rol, identificador), caso)
        self.assertEqual(caso.estado, "CERRADO")
        self.assertEqual(caso.fecha_cierre, result.fecha)
        self.assertEqual(caso.usuario_cierre_id, identificador)
        self.assertEqual(caso.acta_pdf_path, "uploads/actas/acta_1_FICTICIO-001.pdf")
        self.assertEqual(result.sesion.commit.call_count, 2)
        result.sesion.rollback.assert_not_called()
        self.assertEqual([e[0] for e in result.eventos], ["commit", "pdf", "commit"])
        self.assertIsNone(result.eventos[0][2])
        self.assertIsNone(result.eventos[1][2])
        self.assertEqual(result.eventos[2][2], caso.acta_pdf_path)
        self.assertEqual(result.sesion.add.call_count, 1)
        auditoria = result.sesion.add.call_args.args[0]
        self.assertEqual(type(auditoria).__name__, "AuditoriaCaso")
        self.assertEqual(auditoria.accion, "CIERRE_CASO")
        self.assertEqual((auditoria.caso_id, auditoria.usuario_id), (1, identificador))
        result.pdf.assert_called_once()
        result.aviso.assert_called_once_with(caso, result.usuario)
        result.log.assert_called_once()
        return result

    def test_admin_cierra_y_asocia_acta(self):
        self.comprobar_exito("Admin")

    def test_torre_control_cierra_y_asocia_acta(self):
        self.comprobar_exito("Torre Control")

    def test_trabajador_social_asignado_cierra(self):
        self.comprobar_exito("Trabajador(a) Social", identificador=20, ts=20)

    def test_trabajador_social_legacy_cierra(self):
        self.comprobar_exito("Trabajador(a) Social", identificador=20, ts=99, legacy_ts=20)

    def test_fallo_primer_commit_impide_pdf_y_correo(self):
        result = self.ejecutar(self.usuario(), self.caso(), error_en="primer_commit")
        self.assertEqual(result.sesion.commit.call_count, 1)
        result.sesion.rollback.assert_called_once()
        result.pdf.assert_not_called()
        result.aviso.assert_not_called()
        result.log.assert_not_called()
        self.assertIsNone(result.caso.acta_pdf_path)
        self.assertTrue(any(call.args[1] == "danger" for call in result.mensajes.call_args_list))

    def test_fallo_pdf_ocurre_despues_del_primer_commit_actualmente(self):
        result = self.ejecutar(self.usuario(), self.caso(), error_en="pdf")
        self.assertEqual([e[0] for e in result.eventos], ["commit", "pdf"])
        self.assertEqual(result.sesion.commit.call_count, 1)
        result.sesion.rollback.assert_called_once()
        result.aviso.assert_not_called()
        result.log.assert_not_called()
        self.assertIsNone(result.caso.acta_pdf_path)
        # Caracteriza el riesgo: el primer commit ya habia sido solicitado.
        self.assertEqual(result.eventos[0][1], "CERRADO")

    def test_fallo_segundo_commit_ya_ocurre_despues_de_generar_pdf(self):
        result = self.ejecutar(self.usuario(), self.caso(), error_en="segundo_commit")
        self.assertEqual([e[0] for e in result.eventos], ["commit", "pdf", "commit"])
        self.assertEqual(result.sesion.commit.call_count, 2)
        result.sesion.rollback.assert_called_once()
        result.pdf.assert_called_once()
        result.aviso.assert_not_called()
        result.log.assert_not_called()
        # La ruta se asigno en memoria, pero su persistencia no esta garantizada.
        self.assertEqual(result.caso.acta_pdf_path, "uploads/actas/acta_1_FICTICIO-001.pdf")

    def test_fallo_correo_no_revierte_cierre_ni_acta(self):
        result = self.ejecutar(self.usuario(), self.caso(), error_en="correo")
        self.assertEqual(result.sesion.commit.call_count, 2)
        result.sesion.rollback.assert_not_called()
        result.pdf.assert_called_once()
        result.aviso.assert_called_once()
        result.log.assert_called_once()
        self.assertTrue(any(call.args[1] == "warning" for call in result.mensajes.call_args_list))


if __name__ == "__main__":
    unittest.main()
