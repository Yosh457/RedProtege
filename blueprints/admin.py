# blueprints/admin.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_

# Modelos
from models import db, Usuario, Rol, Log, CatalogoCiclo, Caso
# Utilidades
from utils import registrar_log, admin_required, enviar_credenciales_nuevo_usuario

admin_bp = Blueprint('admin', __name__, template_folder='../templates', url_prefix='/admin')

@admin_bp.before_request
@login_required
@admin_required
def before_request():
    """Protege todo el blueprint para solo Admins"""
    pass

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

@admin_bp.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    roles = Rol.query.order_by(Rol.nombre).all()
    ciclos = CatalogoCiclo.query.order_by(CatalogoCiclo.id).all()

    if request.method == 'POST':
        nombre = request.form.get('nombre_completo')
        email = request.form.get('email')
        password = request.form.get('password')
        rol_id = request.form.get('rol_id')
        ciclo_id = request.form.get('ciclo_id') # Puede venir vacío
        forzar_cambio = request.form.get('forzar_cambio_clave') == '1'

        # Validación básica
        if Usuario.query.filter_by(email=email).first():
            flash('Error: El correo ya está registrado.', 'danger')
            return render_template('admin/crear_usuario.html', roles=roles, ciclos=ciclos, datos_previos=request.form)

        # Convertir ciclo_id vacío a None para la DB
        ciclo_final = int(ciclo_id) if ciclo_id else None

        nuevo_usuario = Usuario(
            nombre_completo=nombre, 
            email=email, 
            rol_id=rol_id,
            ciclo_asignado_id=ciclo_final,
            cambio_clave_requerido=forzar_cambio, 
            activo=True
        )
        nuevo_usuario.set_password(password)
        
        try:
            db.session.add(nuevo_usuario)
            db.session.commit()

            # --- Log + Envío de Credenciales ---
            registrar_log("Creación Usuario", f"Admin creó a {nombre} ({email}) - Ciclo ID: {ciclo_final}")
            
            if enviar_credenciales_nuevo_usuario(nuevo_usuario, password):
                flash(f'Usuario creado con éxito. Credenciales enviadas a {email}.', 'success')
            else:
                # Si falla el correo, avisamos al admin para que entregue la clave manual
                flash(f'Usuario creado, pero FALLÓ el envío del correo. Entregue la clave manualmente: {password}', 'warning')
            
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear usuario: {str(e)}', 'danger')

    return render_template('admin/crear_usuario.html', roles=roles, ciclos=ciclos)

@admin_bp.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
def editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    roles = Rol.query.order_by(Rol.nombre).all()
    ciclos = CatalogoCiclo.query.order_by(CatalogoCiclo.id).all()

    if request.method == 'POST':
        email_nuevo = request.form.get('email')
        
        # Validar duplicidad si cambia el email
        usuario_existente = Usuario.query.filter_by(email=email_nuevo).first()
        if usuario_existente and usuario_existente.id != id:
            flash('Error: Ese correo ya pertenece a otro usuario.', 'danger')
            return render_template('admin/editar_usuario.html', usuario=usuario, roles=roles, ciclos=ciclos)

        usuario.nombre_completo = request.form.get('nombre_completo')
        usuario.email = email_nuevo
        usuario.rol_id = request.form.get('rol_id')
        
        ciclo_id = request.form.get('ciclo_id')
        usuario.ciclo_asignado_id = int(ciclo_id) if ciclo_id else None
        
        usuario.cambio_clave_requerido = request.form.get('forzar_cambio_clave') == '1'

        password = request.form.get('password')
        if password and password.strip():
            usuario.set_password(password)
            flash('Contraseña actualizada.', 'info')

        try:
            db.session.commit()
            registrar_log("Edición Usuario", f"Admin editó a {usuario.nombre_completo}")
            flash('Usuario actualizado con éxito.', 'success')
            return redirect(url_for('admin.panel'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')

    return render_template('admin/editar_usuario.html', usuario=usuario, roles=roles, ciclos=ciclos)

@admin_bp.route('/toggle_activo/<int:id>', methods=['POST'])
def toggle_activo(id):
    usuario = Usuario.query.get_or_404(id)
    if usuario.id == current_user.id:
        flash('No puedes desactivar tu propia cuenta.', 'danger')
        return redirect(url_for('admin.panel'))
        
    usuario.activo = not usuario.activo
    db.session.commit()
    estado = "activado" if usuario.activo else "desactivado"
    registrar_log("Cambio Estado", f"Usuario {usuario.nombre_completo} fue {estado}.")
    flash(f'Usuario {usuario.nombre_completo} {estado}.', 'success')
    return redirect(url_for('admin.panel'))

@admin_bp.route('/ver_logs')
def ver_logs():
    page = request.args.get('page', 1, type=int)
    usuario_filtro = request.args.get('usuario_id')
    accion_filtro = request.args.get('accion')

    query = Log.query.order_by(Log.timestamp.desc())

    if usuario_filtro and usuario_filtro.isdigit():
        query = query.filter(Log.usuario_id == int(usuario_filtro))
    if accion_filtro:
        query = query.filter(Log.accion == accion_filtro)

    pagination = query.paginate(page=page, per_page=15, error_out=False)
    todos_los_usuarios = Usuario.query.order_by(Usuario.nombre_completo).all()
    # Acciones comunes en RedProtege
    acciones_posibles = ["Inicio de Sesión", "Cierre de Sesión", "Cierre de Sesión Automático", 
                         "Creación Usuario", "Edición Usuario", "Cambio Estado", 
                         "Cambio de Clave", "Ingreso Caso", "Bloqueo Caso", 
                         "Desbloqueo Caso", "Login Fallido", "Solicitud Reseteo", 
                         "Solicitud Reseteo Fallida", "Recuperación Clave", "Asignación Dual", 
                         "Cierre Caso", "Email Asignación", "Error Email", 
                         "Error Archivo", "Seguridad", "Error Archivo", 
                         "Descargar Acta", "Reporte Masivo", "Subrogancia", 
                         "Seguridad", "Descarga Acta"]

    return render_template('admin/ver_logs.html', pagination=pagination,
                           todos_los_usuarios=todos_los_usuarios,
                           acciones_posibles=acciones_posibles,
                           filtros={'usuario_id': usuario_filtro, 'accion': accion_filtro})