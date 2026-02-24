# blueprints/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import pytz
import secrets
import re

from models import db, Usuario
from utils import registrar_log, enviar_correo_reseteo

# Definimos el Blueprint
auth_bp = Blueprint('auth', __name__, template_folder='../templates')

# --- VALIDACIONES LOCALES ---
def es_password_segura(password):
    """Mismas reglas: 8 caracteres, mayúscula y número."""
    if len(password) < 8: return False
    if not re.search(r"[A-Z]", password): return False
    if not re.search(r"[0-9]", password): return False
    return True

def obtener_ruta_redireccion(usuario):
    """
    Define el destino tras login según el Rol en RedProtege.
    """
    if not usuario.rol:
        return url_for('auth.login')
    
    # 1. Admin -> Panel Global
    if usuario.rol.nombre == 'Admin':
        return url_for('admin.panel')
    
    # 2. NUEVO: Solicitante -> Formulario de Ingreso
    if usuario.rol.nombre == 'Solicitante':
        return url_for('solicitudes.formulario')
    
    # 3. Referente, Torre Control, Coordinador EPI, Trabajador(a) Social, Coordinador Ciclo, Visualizador -> Bandeja de Casos
    return url_for('casos.index')

# --- RUTAS DE AUTENTICACIÓN ---

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(obtener_ruta_redireccion(current_user))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        usuario = Usuario.query.filter_by(email=email).first()

        if usuario:
            if not usuario.activo:
                flash('Tu cuenta está desactivada. Contacta al administrador.', 'danger')
                return redirect(url_for('auth.login'))
            
            if usuario.check_password(password):
                login_user(usuario)
                registrar_log("Inicio de Sesión", f"Acceso exitoso: {usuario.rol.nombre}")

                # Bloqueo forzoso si requiere cambio de clave
                if usuario.cambio_clave_requerido:
                    flash('Por seguridad, debes cambiar tu contraseña inicial.', 'warning')
                    return redirect(url_for('auth.cambiar_clave'))
                
                flash(f'Bienvenido, {usuario.nombre_completo}', 'success')
                return redirect(obtener_ruta_redireccion(usuario))
            else:
                # Log de contraseña incorrecta
                registrar_log("Login Fallido", f"Contraseña incorrecta para: {email}")
        else:
            # Log de usuario no encontrado
            registrar_log("Login Fallido", f"Email no registrado: {email}")
        
        flash('Correo o contraseña incorrectos.', 'danger')
    
    return render_template('auth/login.html')

from flask import request, redirect, url_for, flash
from flask_login import logout_user, login_required

@auth_bp.route('/logout')
@login_required
def logout():
    reason = request.args.get('reason')

    if reason == 'timeout':
        registrar_log(
            "Cierre de Sesión Automático",
            "Sesión cerrada por inactividad del usuario."
        )
        mensaje = 'Su sesión ha expirado por inactividad. Por favor, ingrese nuevamente.'
        categoria = 'warning'
    else:
        registrar_log(
            "Cierre de Sesión",
            "Usuario salió del sistema manualmente."
        )
        mensaje = 'Has cerrado sesión correctamente.'
        categoria = 'success'

    logout_user()
    flash(mensaje, categoria)

    return redirect(url_for('auth.login'))

@auth_bp.route('/cambiar_clave', methods=['GET', 'POST'])
@login_required
def cambiar_clave():
    # Si el usuario ya la cambió, no debería estar aquí, lo sacamos
    if not current_user.cambio_clave_requerido:
        return redirect(obtener_ruta_redireccion(current_user))
        
    if request.method == 'POST':
        nueva_password = request.form.get('nueva_password')

        if not es_password_segura(nueva_password):
            flash('Error: La contraseña debe tener 8 caracteres, mayúscula y número.', 'danger')
        else:
            current_user.set_password(nueva_password)
            current_user.cambio_clave_requerido = False
            db.session.commit()
            
            registrar_log("Cambio de Clave", "Usuario actualizó su contraseña obligatoria.")
            logout_user()
            flash('Contraseña actualizada correctamente. Ingresa nuevamente.', 'success')
            return redirect(url_for('auth.login'))
            
    return render_template('auth/cambiar_clave.html')

@auth_bp.route('/solicitar-reseteo', methods=['GET', 'POST'])
def solicitar_reseteo():
    if current_user.is_authenticated:
        return redirect(obtener_ruta_redireccion(current_user))

    if request.method == 'POST':
        email = request.form.get('email')
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario:
            token = secrets.token_hex(16)
            cl_tz = pytz.timezone('America/Santiago')
            # Expiración en 1 hora
            expiracion = datetime.now(cl_tz).replace(tzinfo=None) + timedelta(hours=1)
            
            usuario.reset_token = token
            usuario.reset_token_expiracion = expiracion
            db.session.commit()
            
            # Función importada de utils/email.py
            enviar_correo_reseteo(usuario, token)
            registrar_log("Solicitud Reseteo", f"Enviado a {email}")
            flash(f'Se ha enviado un enlace a {email}.', 'success')
        else:
            # No revelamos si el correo existe o no por seguridad, pero logueamos el intento
            registrar_log("Solicitud Reseteo Fallida", f"Email no existe: {email}")
            flash(f'El correo electrónico no se encuentra registado en el sistema.', 'danger')
            
        return redirect(url_for('auth.login'))
        
    return render_template('auth/solicitar_reseteo.html')

@auth_bp.route('/resetear-clave/<token>', methods=['GET', 'POST'])
def resetear_clave(token):
    if current_user.is_authenticated:
        return redirect(obtener_ruta_redireccion(current_user))

    usuario = Usuario.query.filter_by(reset_token=token).first()
    cl_tz = pytz.timezone('America/Santiago')
    ahora = datetime.now(cl_tz).replace(tzinfo=None)
    
    if not usuario or not usuario.reset_token_expiracion or usuario.reset_token_expiracion < ahora:
        flash('El enlace es inválido o ha expirado.', 'danger')
        return redirect(url_for('auth.solicitar_reseteo'))
        
    if request.method == 'POST':
        nueva_password = request.form.get('nueva_password')

        if not es_password_segura(nueva_password):
            flash('Error: Requisitos de seguridad no cumplidos.', 'danger')
        else:
            usuario.set_password(nueva_password)
            usuario.reset_token = None
            usuario.reset_token_expiracion = None
            db.session.commit()
            
            registrar_log("Recuperación Clave", f"Usuario {usuario.email} recuperó su clave exitosamente.")
            flash('Tu contraseña ha sido restablecida. Inicia sesión.', 'success')
            return redirect(url_for('auth.login'))
        
    return render_template('auth/resetear_clave.html')