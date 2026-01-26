from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user

def check_password_change(f):
    """Verifica si el usuario debe cambiar su contraseña obligatoriamente."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.cambio_clave_requerido:
            flash('Debes cambiar tu contraseña para continuar.', 'warning')
            return redirect(url_for('auth.cambiar_clave'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Solo permite acceso al Rol 'Admin'."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Validamos que esté logueado y que su rol sea Admin
        if not current_user.is_authenticated or not current_user.rol or current_user.rol.nombre != 'Admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def gestor_required(f):
    """Permite acceso a 'Admin' y 'Referente' (Gestores del sistema)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        roles_permitidos = ['Admin', 'Referente']
        if not current_user.is_authenticated or not current_user.rol or current_user.rol.nombre not in roles_permitidos:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function