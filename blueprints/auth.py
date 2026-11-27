# blueprints/auth.py
import time

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    session, jsonify, current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from models import db, Usuario
from utils import registrar_log, enviar_correo_reseteo
from utils.security import (
    generar_token, hash_token, ahora_utc, password_valida,
    RECUPERACION_HORAS,
)

# Definimos el Blueprint
auth_bp = Blueprint('auth', __name__, template_folder='../templates')

# --- VALIDACIONES LOCALES ---

def obtener_ruta_redireccion(usuario):
    """
    Define el destino tras login según el Rol en RedProtege.
    """
    if not usuario.rol:
        return url_for('auth.login')

    # 1. Admin -> Panel Global
    if usuario.rol.nombre == 'Admin':
        return url_for('admin.panel')

    # 2. Solicitante -> Formulario de Ingreso
    if usuario.rol.nombre == 'Solicitante':
        return url_for('solicitudes.formulario')

    # 3. Referente, Torre Control, Coordinador EPI, Trabajador(a) Social,
    # Coordinador Ciclo, Visualizador -> Bandeja de Casos
    return url_for('casos.index')

# --- RUTAS DE AUTENTICACIÓN ---

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(obtener_ruta_redireccion(current_user))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Validación básica de credenciales ingresadas.
        if not email or not password:
            flash('Debes ingresar correo y contraseña.', 'danger')
            return render_template('auth/login.html')

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and usuario.check_password(password):

            # La contraseña es correcta, pero la cuenta fue desactivada.
            if not usuario.activo:
                registrar_log(
                    "Login Rechazado",
                    "Intento de acceso mediante una cuenta desactivada."
                )

                flash(
                    'Tu cuenta ha sido desactivada. Contacta al administrador.',
                    'warning'
                )
                return redirect(url_for('auth.login'))

            # Una cuenta pendiente debe completar su activación por correo.
            if usuario.activacion_pendiente:
                registrar_log(
                    "Login Rechazado",
                    "Intento de acceso mediante una cuenta pendiente de activación."
                )

                flash(
                    'Tu cuenta está pendiente de activación. '
                    'Revisa el enlace enviado a tu correo electrónico.',
                    'warning'
                )
                return redirect(url_for('auth.login'))

            # Comprobación final del estado de la cuenta.
            if not usuario.is_active:
                flash('Correo o contraseña incorrectos.', 'danger')
                return redirect(url_for('auth.login'))

            # Limpiar cualquier dato anterior antes de autenticar.
            session.clear()

            if not login_user(usuario):
                flash('No fue posible iniciar sesión.', 'danger')
                return redirect(url_for('auth.login'))

            # Control de actividad y versión de sesión.
            session['ultima_actividad'] = time.time()
            session['sesion_version'] = usuario.sesion_version

            registrar_log(
                "Inicio de Sesión",
                f"Acceso exitoso a RedProtege. Rol: {usuario.rol.nombre}"
            )

            # Bloqueo obligatorio hasta establecer una nueva contraseña.
            if usuario.cambio_clave_requerido:
                flash(
                    'Por seguridad, debes cambiar tu contraseña inicial.',
                    'warning'
                )
                return redirect(url_for('auth.cambiar_clave'))

            flash(
                f'Bienvenido, {usuario.nombre_completo}',
                'success'
            )
            return redirect(obtener_ruta_redireccion(usuario))

        # Respuesta genérica para cuentas inexistentes o claves incorrectas.
        registrar_log(
            "Login Fallido",
            "Credenciales incorrectas o cuenta no registrada."
        )

        flash('Correo o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')

# --- CONTROL DE SESIÓN E INACTIVIDAD ---

@auth_bp.route('/sesion/estado', methods=['GET'])
def estado_sesion():
    """Consulta la vigencia y el tiempo restante de la sesión sin renovarla."""
    if not current_user.is_authenticated:
        return jsonify(autenticado=False), 401

    ultima = session.get('ultima_actividad')
    limite = current_app.config['SESION_INACTIVIDAD_SEGUNDOS']

    # Una sesión válida debe contar con una referencia de actividad.
    if not isinstance(ultima, (int, float)):
        return jsonify(autenticado=False), 401

    # Calcular el tiempo restante según la última actividad registrada.
    restante = max(0, int(limite - (time.time() - ultima)))

    return jsonify(
        autenticado=True,
        restante_segundos=restante
    )

# Solo se permite renovar mediante una solicitud POST autenticada y con CSRF.
@auth_bp.route('/sesion/renovar', methods=['POST'])
def renovar_sesion():
    """Renueva el tiempo de actividad de una sesión vigente."""
    if not current_user.is_authenticated:
        return jsonify(autenticado=False), 401

    # La comprobación de expiración se realiza previamente en before_request.
    session['ultima_actividad'] = time.time()

    return jsonify(
        autenticado=True,
        restante_segundos=current_app.config['SESION_INACTIVIDAD_SEGUNDOS']
    )

# --- CIERRE DE SESIÓN ---

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    motivo = request.form.get('reason', '')
    ultima_actividad = session.get('ultima_actividad')

    ahora = time.time()
    tiempo_maximo = current_app.config.get(
        'SESION_INACTIVIDAD_SEGUNDOS',
        600
    )

    # Una pequeña tolerancia permite clasificar el cierre
    # cuando el navegador envía el POST justo antes del límite.
    cierre_por_inactividad = (
        motivo == 'timeout'
        and isinstance(ultima_actividad, (int, float))
        and ultima_actividad <= ahora
        and ahora - ultima_actividad >= max(0, tiempo_maximo - 2)
    )

    if cierre_por_inactividad:
        registrar_log(
            "Cierre de Sesión Automático",
            "Sesión cerrada por inactividad del usuario."
        )

        mensaje = (
            'Tu sesión ha expirado por inactividad. '
            'Por favor, inicia sesión nuevamente.'
        )
        categoria = 'warning'

    else:
        registrar_log(
            "Cierre de Sesión",
            "Usuario salió del sistema manualmente."
        )

        mensaje = 'Has cerrado sesión correctamente.'
        categoria = 'success'

    # Cerrar la sesión de Flask-Login y eliminar los datos de sesión.
    logout_user()
    session.clear()

    flash(mensaje, categoria)

    return redirect(url_for('auth.login'))

# --- CAMBIO OBLIGATORIO DE CONTRASEÑA ---

@auth_bp.route('/cambiar_clave', methods=['GET', 'POST'])
@login_required
def cambiar_clave():
    # Si el usuario ya la cambió, no debería estar aquí, lo sacamos
    if not current_user.cambio_clave_requerido:
        return redirect(obtener_ruta_redireccion(current_user))

    if request.method == 'POST':
        nueva_password = request.form.get('nueva_password')
        confirmar = request.form.get('confirmar_password')

        # Validar los requisitos de seguridad y la confirmación de contraseña.
        if not password_valida(nueva_password, confirmar):
            flash('Error: La contraseña debe tener 8 caracteres, una mayúscula y un número.', 'danger')

        else:
            current_user.set_password(nueva_password)
            current_user.cambio_clave_requerido = False

            try:
                # Confirmar el cambio de contraseña y su auditoría en una misma transacción.
                registrar_log(
                    "Cambio de Clave",
                    "Usuario actualizó su contraseña obligatoria.",
                    commit=False
                )

                db.session.commit()

            except SQLAlchemyError:
                db.session.rollback()

                current_app.logger.exception(
                    'Fallo al actualizar contraseña obligatoria'
                )

                flash('No fue posible actualizar la contraseña.', 'danger')
                return render_template('auth/cambiar_clave.html')

            # Obligar al usuario a iniciar sesión con su nueva contraseña.
            logout_user()
            session.clear()

            flash('Contraseña actualizada correctamente. Ingresa nuevamente.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/cambiar_clave.html')

# --- ACTIVACIÓN DE CUENTAS ---

@auth_bp.route('/activar-cuenta/<token>', methods=['GET', 'POST'])
def activar_cuenta(token):
    """Permite activar una cuenta estableciendo su contraseña inicial."""
    if current_user.is_authenticated:
        return redirect(obtener_ruta_redireccion(current_user))

    # Buscar la cuenta mediante el hash del token recibido.
    usuario = Usuario.query.filter_by(
        activacion_token_hash=hash_token(token)
    ).first()

    # Validar el estado de la cuenta, la vigencia del token y la activación pendiente.
    if (
        not usuario
        or not usuario.activo
        or not usuario.activacion_pendiente
        or not usuario.activacion_token_expiracion
        or usuario.activacion_token_expiracion <= ahora_utc()
    ):
        flash(
            'El enlace de activación es inválido o ha expirado. '
            'Solicita uno nuevo al administrador.',
            'warning'
        )
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        nueva_password = request.form.get('nueva_password')
        confirmar = request.form.get('confirmar_password')

        # Validar los requisitos de seguridad y la confirmación de contraseña.
        if not password_valida(nueva_password, confirmar):
            flash('Verifica la contraseña, su confirmación y los requisitos indicados.', 'danger')

        else:
            try:
                # Establecer la contraseña inicial y completar la activación.
                usuario.set_password(nueva_password)
                usuario.activacion_pendiente = False

                # Invalidar el token para impedir que vuelva a utilizarse.
                usuario.activacion_token_hash = None
                usuario.activacion_token_expiracion = None

                # El usuario ya estableció su propia contraseña.
                usuario.cambio_clave_requerido = False

                # Registrar la activación dentro de la misma transacción.
                registrar_log(
                    'Activación Cuenta',
                    f'Cuenta activada: {usuario.id}',
                    commit=False
                )

                db.session.commit()

                flash('Cuenta activada. Ya puedes iniciar sesión.', 'success')
                return redirect(url_for('auth.login'))

            except SQLAlchemyError:
                db.session.rollback()

                current_app.logger.exception(
                    'Fallo de base de datos en operación de autenticación'
                )

                flash('No fue posible activar la cuenta. Intenta nuevamente.', 'danger')

    return render_template('auth/activar_cuenta.html')

# --- RECUPERACIÓN DE CONTRASEÑA ---

@auth_bp.route('/solicitar-reseteo', methods=['GET', 'POST'])
def solicitar_reseteo():
    if current_user.is_authenticated:
        return redirect(obtener_ruta_redireccion(current_user))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        usuario = Usuario.query.filter_by(email=email).first()

        # Solo las cuentas habilitadas y previamente activadas pueden recuperar su clave.
        if (
            usuario
            and usuario.is_active
            and not usuario.activacion_pendiente
            and usuario.password_hash is not None
        ):
            # Generar un token seguro, su hash y su fecha de expiración.
            token, digest, expiracion = generar_token(RECUPERACION_HORAS)

            try:
                # Almacenar únicamente el hash e invalidar cualquier token anterior.
                usuario.reset_token = digest
                usuario.reset_token_expiracion = expiracion

                registrar_log(
                    'Solicitud Reseteo',
                    f'Solicitud recibida para ID {usuario.id}',
                    commit=False
                )

                db.session.commit()

                # Función importada de utils/email.py.
                # Enviar el token original por correo y registrar posibles fallos.
                if not enviar_correo_reseteo(usuario, token):
                    registrar_log(
                        'Error Correo Reseteo',
                        f'Fallo al enviar recuperación para ID {usuario.id}'
                    )

            except SQLAlchemyError:
                db.session.rollback()

                current_app.logger.exception(
                    'Fallo de base de datos en operación de autenticación'
                )

        # No revelamos si el correo existe o no por seguridad.
        # Misma respuesta para cuentas existentes, inexistentes, inactivas o pendientes.
        flash(
            'Si la cuenta existe y está habilitada, recibirás un enlace de recuperación.',
            'info'
        )

        return redirect(url_for('auth.login'))

    return render_template('auth/solicitar_reseteo.html')

@auth_bp.route('/resetear-clave/<token>', methods=['GET', 'POST'])
def resetear_clave(token):
    if current_user.is_authenticated:
        return redirect(obtener_ruta_redireccion(current_user))

    # Buscar la cuenta mediante el hash del token de recuperación.
    usuario = Usuario.query.filter_by(
        reset_token=hash_token(token)
    ).first()

    # Validar el estado de la cuenta y la vigencia del token.
    if (
        not usuario
        or not usuario.is_active
        or usuario.activacion_pendiente
        or usuario.password_hash is None
        or not usuario.reset_token_expiracion
        or usuario.reset_token_expiracion <= ahora_utc()
    ):
        flash('El enlace es inválido o ha expirado.', 'danger')
        return redirect(url_for('auth.solicitar_reseteo'))

    if request.method == 'POST':
        nueva_password = request.form.get('nueva_password')
        confirmar = request.form.get('confirmar_password')

        # Validar los requisitos de seguridad y la confirmación de contraseña.
        if not password_valida(nueva_password, confirmar):
            flash('Verifica la contraseña, su confirmación y los requisitos indicados.', 'danger')

        else:
            try:
                # Actualizar la contraseña e invalidar las sesiones anteriores.
                usuario.set_password(nueva_password)

                # Invalidar el token de recuperación después de su utilización.
                usuario.reset_token = None
                usuario.reset_token_expiracion = None

                # La nueva contraseña ya fue establecida por el usuario.
                usuario.cambio_clave_requerido = False

                # Confirmar la recuperación y su auditoría en una misma transacción.
                registrar_log(
                    'Recuperación Clave',
                    f'Clave recuperada para ID {usuario.id}',
                    commit=False
                )

                db.session.commit()

                flash('Contraseña restablecida. Inicia sesión nuevamente.', 'success')
                return redirect(url_for('auth.login'))

            except SQLAlchemyError:
                db.session.rollback()

                current_app.logger.exception(
                    'Fallo de base de datos en operación de autenticación'
                )

                flash('No fue posible completar la operación.', 'danger')

    return render_template('auth/resetear_clave.html')