# blueprints/admin.py
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, current_app,
)
from flask_login import login_required, current_user
from sqlalchemy import or_

# Modelos
from models import db, Usuario, Rol, Log, CatalogoCiclo, Caso

# Utilidades
from utils import registrar_log, admin_required, enviar_activacion_usuario
from utils.security import generar_token, ACTIVACION_HORAS
from utils.rate_limit import validar_limite

admin_bp = Blueprint('admin', __name__, template_folder='../templates', url_prefix='/admin')

# --- PROTECCIÓN DEL BLUEPRINT ---

@admin_bp.before_request
@login_required
@admin_required
def before_request():
    """Protege todo el blueprint para solo Admins"""
    pass

# --- PANEL DE ADMINISTRACIÓN ---

@admin_bp.route('/panel')
def panel():
    # --- Filtros ---
    page = request.args.get('page', 1, type=int)
    busqueda = request.args.get('busqueda', '')
    rol_filtro = request.args.get('rol_filtro', '')

    query = Usuario.query

    if busqueda:
        query = query.filter(
            or_(Usuario.nombre_completo.ilike(f'%{busqueda}%'),
                Usuario.email.ilike(f'%{busqueda}%'))
        )

    if rol_filtro:
        query = query.filter(Usuario.rol_id == rol_filtro)

    # Paginación de usuarios
    pagination = query.order_by(Usuario.id).paginate(page=page, per_page=10, error_out=False)

    roles_para_filtro = Rol.query.order_by(Rol.nombre).all()

    # Estadísticas Rápidas
    stats = {
        'total_usuarios': Usuario.query.count(),
        'total_casos': Caso.query.count(),
        'casos_pendientes': Caso.query.filter_by(estado='PENDIENTE_RESCATAR').count()
    }

    return render_template('admin/panel.html',
                           pagination=pagination,
                           roles_para_filtro=roles_para_filtro,
                           busqueda=busqueda,
                           rol_filtro=rol_filtro,
                           stats=stats)

# --- CREACIÓN DE USUARIOS ---

@admin_bp.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    roles = Rol.query.order_by(Rol.nombre).all()
    ciclos_disponibles = CatalogoCiclo.query.order_by(CatalogoCiclo.id).all()

    if request.method == 'POST':
        nombre = request.form.get('nombre_completo', '').strip()
        email = request.form.get('email', '').strip().lower()
        rol_id = request.form.get('rol_id', type=int)
        raw_ciclos = request.form.getlist('ciclos')

        # Conservar los datos ingresados si falla alguna validación.
        datos = dict(
            roles=roles,
            ciclos=ciclos_disponibles,
            datos_previos=request.form
        )

        # Validación básica del nombre, correo electrónico y rol.
        if (
            not nombre
            or not email
            or len(nombre) > 255
            or len(email) > 255
            or '@' not in email
            or rol_id is None
            or Rol.query.get(rol_id) is None
        ):
            flash('Revisa el nombre, correo y rol del usuario.', 'danger')
            return render_template('admin/crear_usuario.html', **datos)

        # Convertir a INT correctamente y evitar ciclos duplicados.
        try:
            ciclos_ids = {int(c) for c in raw_ciclos}

        except (TypeError, ValueError):
            flash('Los ciclos seleccionados no son válidos.', 'danger')
            return render_template('admin/crear_usuario.html', **datos)

        # Validar que el correo no pertenezca a otro usuario.
        if Usuario.query.filter_by(email=email).first():
            flash('El correo ya está registrado.', 'danger')
            return render_template('admin/crear_usuario.html', **datos)

        try:
            # Obtener los objetos correspondientes a los ciclos seleccionados.
            objetos_ciclos = CatalogoCiclo.query.filter(
                CatalogoCiclo.id.in_(ciclos_ids)
            ).all()

            # Verificar que todos los ciclos seleccionados existan en BD.
            if len(objetos_ciclos) != len(ciclos_ids):
                flash('Se seleccionó un ciclo inexistente.', 'danger')
                return render_template('admin/crear_usuario.html', **datos)

            # Generar el token de activación, su hash y fecha de expiración.
            token, digest, expiracion = generar_token(ACTIVACION_HORAS)

            # Crear la cuenta sin contraseña, pendiente de activación.
            # El usuario establecerá su propia contraseña mediante el enlace.
            nuevo_usuario = Usuario(
                nombre_completo=nombre,
                email=email,
                rol_id=rol_id,
                activo=True,
                cambio_clave_requerido=False,
                password_hash=None,
                activacion_pendiente=True,
                activacion_token_hash=digest,
                activacion_token_expiracion=expiracion,
                sesion_version=1,
            )

            # Asignación de múltiples ciclos vitales (M:N).
            nuevo_usuario.ciclos = objetos_ciclos

            # 🔴 SAFE legacy
            if objetos_ciclos:
                nuevo_usuario.ciclo_asignado_id = objetos_ciclos[0].id

            db.session.add(nuevo_usuario)

            # Obtener el ID generado antes de registrar la auditoría.
            db.session.flush()

            # Registrar la creación dentro de la misma transacción.
            registrar_log(
                'Creación Usuario',
                f'Cuenta ID {nuevo_usuario.id} creada, pendiente de activación.',
                commit=False
            )

            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                'No fue posible crear usuario'
            )

            flash('No fue posible crear el usuario.', 'danger')
            return render_template('admin/crear_usuario.html', **datos)

        # --- Envío del enlace de activación ---
        # Enviar el correo después de confirmar la creación de la cuenta.
        if enviar_activacion_usuario(nuevo_usuario, token):
            flash(
                'Usuario creado. Se envió un enlace para establecer su contraseña.',
                'success'
            )

        else:
            # Si falla el correo, conservar la cuenta y permitir un nuevo envío.
            flash(
                'Usuario creado, pero falló el envío. Utiliza Reenviar activación.',
                'warning'
            )

        return redirect(url_for('admin.panel'))

    return render_template('admin/crear_usuario.html',
                           roles=roles,
                           ciclos=ciclos_disponibles,
                           datos_previos=None)

# --- EDICIÓN DE USUARIOS ---

@admin_bp.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
def editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    roles = Rol.query.order_by(Rol.nombre).all()
    ciclos_disponibles = CatalogoCiclo.query.order_by(CatalogoCiclo.id).all()

    if request.method == 'POST':
        email_nuevo = request.form.get('email')

        # Validar duplicidad si cambia el email
        usuario_existente = Usuario.query.filter_by(email=email_nuevo).first()

        if usuario_existente and usuario_existente.id != id:
            flash('Error: Ese correo ya pertenece a otro usuario.', 'danger')
            return render_template('admin/editar_usuario.html',
                                   usuario=usuario,
                                   roles=roles,
                                   ciclos=ciclos_disponibles,
                                   datos_previos=request.form)

        # Actualizar los datos generales y permisos del usuario.
        usuario.nombre_completo = request.form.get('nombre_completo')
        usuario.email = email_nuevo
        usuario.rol_id = request.form.get('rol_id')
        usuario.cambio_clave_requerido = request.form.get('forzar_cambio_clave') == '1'

        # ✅ Convertir a INT
        ciclos_ids = [int(c) for c in request.form.getlist('ciclos')]

        try:
            objetos_ciclos = CatalogoCiclo.query.filter(
                CatalogoCiclo.id.in_(ciclos_ids)
            ).all()

            # Actualizar la asignación de múltiples ciclos vitales (M:N).
            usuario.ciclos = objetos_ciclos

            # 🔴 SAFE legacy
            if objetos_ciclos:
                usuario.ciclo_asignado_id = objetos_ciclos[0].id

            # La contraseña pertenece al usuario. Para cambiarla debe usar
            # su propio flujo de recuperación, nunca se envía en correo.
            if usuario.activacion_pendiente:
                usuario.cambio_clave_requerido = False

            db.session.commit()

            # 🔧 LOG MEJORADO
            nombres_ciclos = ', '.join([c.nombre for c in objetos_ciclos])

            registrar_log(
                "Edición Usuario",
                f"Admin editó a {usuario.nombre_completo}. Ciclos: {nombres_ciclos}"
            )

            flash('Usuario actualizado con éxito.', 'success')
            return redirect(url_for('admin.panel'))

        except Exception as e:
            db.session.rollback()

            flash(f'Error al actualizar: {str(e)}', 'danger')

            return render_template('admin/editar_usuario.html',
                                   usuario=usuario,
                                   roles=roles,
                                   ciclos=ciclos_disponibles,
                                   datos_previos=request.form)

    return render_template('admin/editar_usuario.html',
                           usuario=usuario,
                           roles=roles,
                           ciclos=ciclos_disponibles,
                           datos_previos=None)

# --- ACTIVACIÓN Y BLOQUEO DE CUENTAS ---

@admin_bp.route('/toggle_activo/<int:id>', methods=['POST'])
def toggle_activo(id):
    usuario = Usuario.query.get_or_404(id)

    # Impedir que un administrador desactive su propia cuenta.
    if usuario.id == current_user.id:
        flash('No puedes desactivar tu propia cuenta.', 'danger')
        return redirect(url_for('admin.panel'))

    # Alternar el estado administrativo de la cuenta.
    usuario.activo = not usuario.activo

    # Incrementar la versión para invalidar las sesiones anteriores.
    usuario.sesion_version = (usuario.sesion_version or 1) + 1

    db.session.commit()

    estado = "activado" if usuario.activo else "desactivado"

    registrar_log(
        "Cambio Estado",
        f"Usuario {usuario.nombre_completo} fue {estado}."
    )

    flash(f'Usuario {usuario.nombre_completo} {estado}.', 'success')
    return redirect(url_for('admin.panel'))

# --- REENVÍO DE ACTIVACIÓN ---

@admin_bp.route('/reenviar_activacion/<int:id>', methods=['POST'])
def reenviar_activacion(id):
    usuario = Usuario.query.get_or_404(id)

    # Solo las cuentas habilitadas y pendientes pueden recibir un nuevo enlace.
    if not usuario.activo or not usuario.activacion_pendiente:
        flash(
            'La cuenta no está pendiente de activación o fue desactivada.',
            'warning'
        )
        return redirect(url_for('admin.panel'))

    # Limitar el reenvío a 3 solicitudes por hora para cada cuenta.
    validar_limite(
        'reenviar_activacion_cuenta',
        str(usuario.id),
        3,
        60 * 60
    )

    # Generar un nuevo token de activación.
    token, digest, expiracion = generar_token(ACTIVACION_HORAS)

    try:
        # Reemplazar el hash anterior e invalidar el enlace previo.
        usuario.activacion_token_hash = digest
        usuario.activacion_token_expiracion = expiracion

        # Confirmar la renovación y su auditoría en una misma transacción.
        registrar_log(
            'Reenvío Activación',
            f'Enlace renovado para cuenta ID {usuario.id}',
            commit=False
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            'Error de reenvío de activación ID %s',
            id
        )

        flash('No fue posible renovar el enlace.', 'danger')
        return redirect(url_for('admin.panel'))

    # Enviar el nuevo enlace después de confirmar la renovación.
    if enviar_activacion_usuario(usuario, token):
        flash('Se envió un nuevo enlace de activación.', 'success')

    else:
        flash(
            'El enlace se renovó, pero el envío falló. Intenta reenviar más tarde.',
            'warning'
        )

    return redirect(url_for('admin.panel'))

# --- REGISTROS DE AUDITORÍA ---

@admin_bp.route('/ver_logs')
def ver_logs():
    # Página actual de la paginación
    page = request.args.get('page', 1, type=int)

    # Filtros opcionales enviados por GET
    usuario_filtro = request.args.get('usuario_id')
    accion_filtro = request.args.get('accion')

    # Query base: logs ordenados del más reciente al más antiguo
    query = Log.query.order_by(Log.timestamp.desc())

    # --- FILTRO POR USUARIO ---

    # Validamos que venga un ID numérico antes de filtrar
    if usuario_filtro and usuario_filtro.isdigit():
        query = query.filter(Log.usuario_id == int(usuario_filtro))

    # --- FILTRO POR ACCIÓN ---

    if accion_filtro:
        query = query.filter(Log.accion == accion_filtro)

    # --- PAGINACIÓN ---

    pagination = query.paginate(page=page, per_page=15, error_out=False)

    # Lista de usuarios para poblar el select del filtro
    todos_los_usuarios = Usuario.query.order_by(Usuario.nombre_completo).all()

    # --- ACCIONES POSIBLES ---

    acciones_posibles = [
        "Inicio de Sesión",
        "Cierre de Sesión",
        "Cierre de Sesión Automático",
        "Login Fallido",
        "Cambio de Clave",
        "Solicitud Reseteo",
        "Solicitud Reseteo Fallida",
        "Recuperación Clave",
        "Creación Usuario",
        "Edición Usuario",
        "Cambio Estado",
        "Ingreso Caso",
        "Asignación Dual",
        "Cierre Caso",
        "Anulación Caso",
        "Descarga Acta",
        "Reporte Masivo",
        "Subrogancia",
        "Error Email",
        "Error Archivo",
        "Seguridad"
    ]

    return render_template('admin/ver_logs.html',
                           pagination=pagination,
                           todos_los_usuarios=todos_los_usuarios,
                           acciones_posibles=acciones_posibles,
                           filtros={
                               'usuario_id': usuario_filtro,
                               'accion': accion_filtro
                           })