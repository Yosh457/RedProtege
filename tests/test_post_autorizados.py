"""RedProtege Fase 1.2-B / bloque 2A: POST autorizados (caracterización).

No utiliza MySQL, SMTP ni archivos reales. Los objetos son ficticios.
La ejecución directa omite @login_required; NO es una prueba HTTP/CSRF.
"""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints import casos as modulo


class TestPostAutorizados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SECRET_KEY": "redprotege-post-autorizados-test-only"}):
            cls.app = create_app()
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    @staticmethod
    def usuario(rol="Admin", identificador=10):
        return SimpleNamespace(
            id=identificador,
            rol=SimpleNamespace(nombre=rol),
            email="ficticio@example.invalid",
            nombre_completo="Usuario Ficticio",
            subrogantes_activos=[],
            activo=True,
            is_authenticated=True,
        )

    @staticmethod
    def caso(estado="EN_SEGUIMIENTO"):
        return SimpleNamespace(id=1, estado=estado, folio_atencion="FICTICIO-001")

    def entorno(self, stack, usuario, caso=None):
        """Sustituye TODA Caso.query y Usuario.query, además de db.session."""
        stack.enter_context(patch.object(modulo, "current_user", usuario))
        consulta_casos = MagicMock()
        if caso is not None:
            consulta_casos.get_or_404.return_value = caso
        stack.enter_context(patch.object(modulo.Caso, "query", consulta_casos))
        consulta_usuarios = MagicMock()
        stack.enter_context(patch.object(modulo.Usuario, "query", consulta_usuarios))
        sesion = MagicMock()
        stack.enter_context(patch.object(modulo.db, "session", sesion))
        log = stack.enter_context(patch.object(modulo, "registrar_log"))
        correo = stack.enter_context(patch.object(modulo, "enviar_aviso_subrogancia"))
        stack.enter_context(patch.object(modulo, "obtener_hora_chile", return_value=None))
        return consulta_casos, consulta_usuarios, sesion, log, correo

    def test_admin_anula_caso_y_registra_auditoria(self):
        usuario = self.usuario("Admin")
        caso = self.caso()
        with self.app.test_request_context(
            "/casos/anular/1", method="POST",
            data={"motivo_anulacion": "Ingreso duplicado ficticio"}
        ):
            with ExitStack() as stack:
                _, _, sesion, log, _ = self.entorno(stack, usuario, caso)
                respuesta = modulo.anular_caso.__wrapped__(1)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.location.endswith("/casos/"))
        self.assertEqual(caso.estado, "ANULADO")
        sesion.add.assert_called_once()
        sesion.commit.assert_called_once()
        auditoria = sesion.add.call_args.args[0]
        self.assertEqual(auditoria.accion, "ANULACION_CASO")
        self.assertEqual(auditoria.motivo, "Ingreso duplicado ficticio")
        self.assertEqual(auditoria.detalles_cambio["estado_anterior"], "EN_SEGUIMIENTO")
        self.assertEqual(auditoria.detalles_cambio["estado_nuevo"], "ANULADO")
        log.assert_called_once()

    def test_torre_control_puede_anular(self):
        usuario = self.usuario("Torre Control")
        caso = self.caso()
        with self.app.test_request_context(
            "/casos/anular/1", method="POST", data={"motivo_anulacion": "Error ficticio"}
        ):
            with ExitStack() as stack:
                _, _, sesion, _, _ = self.entorno(stack, usuario, caso)
                respuesta = modulo.anular_caso.__wrapped__(1)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(caso.estado, "ANULADO")
        sesion.commit.assert_called_once()

    def test_referente_activa_subrogancia_valida(self):
        titular = self.usuario("Referente", 10)
        candidato = self.usuario("Referente", 20)
        candidato.activo = True
        candidato.subrogante_de_usuario_id = None
        with self.app.test_request_context(
            "/casos/subrogancia/gestionar", method="POST",
            data={"accion": "activar", "subrogante_id": "20"}
        ):
            with ExitStack() as stack:
                _, usuarios, sesion, log, correo = self.entorno(stack, titular)
                usuarios.get.return_value = candidato
                respuesta = modulo.gestionar_subrogancia.__wrapped__()
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(candidato.subrogante_de_usuario_id, 10)
        usuarios.get.assert_called_once_with(20)
        sesion.commit.assert_called_once()
        correo.assert_called_once_with(titular, candidato, es_activacion=True)
        log.assert_called_once()

    def test_referente_desactiva_subrogancia(self):
        titular = self.usuario("Referente", 10)
        subrogante = self.usuario("Referente", 20)
        subrogante.subrogante_de_usuario_id = 10
        titular.subrogantes_activos = [subrogante]
        with self.app.test_request_context(
            "/casos/subrogancia/gestionar", method="POST", data={"accion": "desactivar"}
        ):
            with ExitStack() as stack:
                _, usuarios, sesion, log, correo = self.entorno(stack, titular)
                respuesta = modulo.gestionar_subrogancia.__wrapped__()
        self.assertEqual(respuesta.status_code, 302)
        self.assertIsNone(subrogante.subrogante_de_usuario_id)
        usuarios.get.assert_not_called()
        sesion.commit.assert_called_once()
        correo.assert_called_once_with(titular, subrogante, es_activacion=False)
        log.assert_called_once()

    def test_fallo_de_correo_no_revierte_subrogancia_actualmente(self):
        titular = self.usuario("Referente", 10)
        candidato = self.usuario("Referente", 20)
        candidato.activo = True
        candidato.subrogante_de_usuario_id = None
        with self.app.test_request_context(
            "/casos/subrogancia/gestionar", method="POST",
            data={"accion": "activar", "subrogante_id": "20"}
        ):
            with ExitStack() as stack:
                _, usuarios, sesion, log, correo = self.entorno(stack, titular)
                usuarios.get.return_value = candidato
                correo.side_effect = RuntimeError("SMTP de prueba no disponible")
                respuesta = modulo.gestionar_subrogancia.__wrapped__()
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(candidato.subrogante_de_usuario_id, 10)
        sesion.commit.assert_called_once()
        sesion.rollback.assert_not_called()
        log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
