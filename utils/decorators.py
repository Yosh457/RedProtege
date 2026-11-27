# utils/decorators.py
import time
from functools import wraps
from flask import abort, redirect, url_for, flash, request, current_app, session, jsonify
from flask_login import current_user, logout_user
from .helpers import registrar_log

def verificar_restricciones_sesion():
    """Protege todas las rutas con un único control de sesión.

    Se registra mediante app.before_request en la fábrica Flask.
    Devuelve una respuesta para bloquear la solicitud, o None si puede continuar.
    """
    # Los archivos estáticos no necesitan esta comprobación.
    if request.endpoint == 'static':
        return None

    if not current_user.is_authenticated:
        return None

    # Una cuenta desactivada pierde acceso en su siguiente solicitud.
    if not current_user.is_active:
        logout_user()
        session.clear()
        if request.endpoint in ('auth.estado_sesion', 'auth.renovar_sesion'):
            return jsonify(autenticado=False), 401
        flash('Tu cuenta ha sido desactivada. Contacta al administrador.', 'warning')
        return redirect(url_for('auth.login'))

    # Rechazar cookies de sesión antiguas, incluidas las restauradas
    # por remember-me de Flask-Login: requieren un marcador vigente
    # guardado en la cookie de sesión firmada por Flask.
    version_sesion = session.get('sesion_version')
    version_actual = current_user.sesion_version
    if (
        type(version_sesion) is not int
        or version_sesion != version_actual
    ):
        logout_user()
        session.clear()
        if request.endpoint in ('auth.estado_sesion', 'auth.renovar_sesion'):
            return jsonify(autenticado=False), 401
        flash(
            'Tu sesión ya no es válida. Inicia sesión nuevamente.',
            'warning'
        )
        return redirect(url_for('auth.login'))

    # Control de inactividad desde Flask.
    ahora = time.time()
    ultima_actividad = session.get('ultima_actividad')

    tiempo_maximo = current_app.config.get(
        'SESION_INACTIVIDAD_SEGUNDOS',
        600
    )

    if (
        not isinstance(ultima_actividad, (int, float))
        or ultima_actividad > ahora
        or ahora - ultima_actividad >= tiempo_maximo
    ):
        # Registrar el cierre automático únicamente cuando se confirme que expiró el tiempo de inactividad.
        if (
            isinstance(ultima_actividad, (int, float))
            and ultima_actividad <= ahora
            and ahora - ultima_actividad >= tiempo_maximo
        ):
            registrar_log(
                "Cierre de Sesión Automático",
                "Sesión cerrada por inactividad del usuario."
            )
        logout_user()
        session.clear()

        flash(
            "Tu sesión ha expirado por inactividad. "
            "Por favor, inicia sesión nuevamente.",
            "warning"
        )

        if request.endpoint in ('auth.estado_sesion', 'auth.renovar_sesion'):
            return jsonify(autenticado=False), 401

        return redirect(url_for('auth.login'))

    # No renovar la sesión con solicitudes GET ni peticiones automáticas.
    # Solo auth.renovar_sesion actualiza ultima_actividad tras validar la sesión.

    if current_user.cambio_clave_requerido and request.endpoint == 'auth.renovar_sesion':
        return jsonify(autenticado=False), 403

    # Permitir únicamente actualizar la clave o cerrar sesión durante
    # el cambio inicial obligatorio; aplica tanto a Admin como Funcionario.
    if current_user.cambio_clave_requerido:
        if request.endpoint not in ('auth.cambiar_clave', 'auth.logout', 'auth.estado_sesion', 'auth.renovar_sesion'):
            return redirect(url_for('auth.cambiar_clave'))

    return None

def check_password_change(f):
    """Verifica si el usuario debe cambiar su contraseña obligatoriamente."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.cambio_clave_requerido:
            if request.endpoint not in ['auth.cambiar_clave', 'auth.logout']:
                flash('Debes cambiar tu contraseña para continuar.', 'warning')
                return redirect(url_for('auth.cambiar_clave'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Solo permite acceso al Rol 'Admin'."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_active or not current_user.rol or current_user.rol.nombre != 'Admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def gestor_required(f):
    """Solo permite acceso a los roles Admin o Referente."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_active or not current_user.rol or current_user.rol.nombre not in ('Admin', 'Referente'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def roles_required(*roles_permitidos):
    """Permite acceso a uno o más roles específicos."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_active or not current_user.rol:
                abort(403)
            if current_user.rol.nombre not in roles_permitidos:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator