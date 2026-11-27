"""Limitación de solicitudes usando contadores MySQL por ventana fija.

La IP proviene de REMOTE_ADDR. No confiar en X-Forwarded-For sin
configurar explícitamente el proxy confiable en el despliegue.
"""
import hashlib
import hmac
import time
from datetime import datetime, timezone
from flask import current_app, request
from sqlalchemy import text

from models import db

def _clave(politica, identificador):
    secreto = current_app.config['SECRET_KEY'].encode('utf-8')
    contenido = f'{politica}\x1f{identificador}'.encode('utf-8')
    return hmac.new(secreto, contenido, hashlib.sha256).hexdigest()


def _ip():
    return request.remote_addr or 'desconocida'

def consumir_limite(politica, identificador, max_intentos, ventana_segundos):
    """Cuenta el intento; devuelve (permitido, segundos_hasta_fin_de_ventana).

    El incremento es atómico en MySQL y se confirma antes de ejecutar la acción.
    El límite se aplica a TODOS los intentos, no solo a contraseñas erróneas.
    """
    actual = int(time.time())
    ventana = actual // ventana_segundos
    espera = max(1, (ventana + 1) * ventana_segundos - actual)
    clave = _clave(politica, identificador)
    vence = datetime.fromtimestamp((ventana + 1) * ventana_segundos, timezone.utc).replace(tzinfo=None)
    try:
        db.session.execute(text('''
            INSERT INTO limites_solicitudes (clave, ventana, intentos, expira_en)
            VALUES (:clave, :ventana, 1, :vence)
            ON DUPLICATE KEY UPDATE intentos = intentos + 1
        '''), {'clave': clave, 'ventana': ventana, 'vence': vence})
        cantidad = db.session.execute(text('''
            SELECT intentos FROM limites_solicitudes
            WHERE clave = :clave AND ventana = :ventana FOR UPDATE
        '''), {'clave': clave, 'ventana': ventana}).scalar_one()
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('No se pudo consultar el límite de solicitudes')
        from werkzeug.exceptions import ServiceUnavailable
        raise ServiceUnavailable(description="Validación temporalmente no disponible")
    return cantidad <= max_intentos, espera

def validar_limite(politica, identificador, max_intentos, ventana_segundos):
    """Abortar con HTTP 429 y cabecera Retry-After cuando corresponde."""
    from werkzeug.exceptions import TooManyRequests
    permitido, espera = consumir_limite(politica, identificador, max_intentos, ventana_segundos)
    if not permitido:
        raise TooManyRequests(description='Demasiadas solicitudes. Intenta nuevamente más tarde.', retry_after=espera)

def limitar_autenticacion():
    """Límite general y particular para POST de rutas de autenticación."""
    # Aislar los tests HTTP unitarios de la infraestructura MySQL. Las
    # pruebas específicas de limitación deben usar RATELIMIT_TEST_BYPASS=False.
    if current_app.config.get('TESTING') and current_app.config.get('RATELIMIT_TEST_BYPASS', True):
        return
    if request.method != 'POST' or request.endpoint is None:
        return
    if request.endpoint.startswith('auth.'):
        validar_limite('auth_general_ip', _ip(), 60, 60)
    if request.endpoint == 'auth.login':
        email = request.form.get('email', '').strip().lower()
        # Un mismo email desde dos equipos no se bloquea conjuntamente.
        validar_limite('login_cuenta_ip', f'{_ip()}\x1f{email}', 5, 60)
    elif request.endpoint == 'auth.solicitar_reseteo':
        email = request.form.get('email', '').strip().lower()
        validar_limite('recuperar_cuenta_ip', f'{_ip()}\x1f{email}', 3, 15 * 60)