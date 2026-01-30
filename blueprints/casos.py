from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import case
from models import db, Caso, Usuario, Rol, AuditoriaCaso, CatalogoEstablecimiento, obtener_hora_chile
from utils import check_password_change, registrar_log, enviar_aviso_asignacion
from datetime import datetime

casos_bp = Blueprint('casos', __name__, template_folder='../templates', url_prefix='/casos')

def safe_int(value):
    """Ayuda a convertir a int de forma segura, retornando None si falla o es vacío."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

@casos_bp.before_request
@login_required
@check_password_change
def before_request():
    pass

@casos_bp.route('/')
def index():
    """
    Bandeja de Entrada de Casos.
    Aplica filtros de seguridad según el Rol del usuario.
    """
    page = request.args.get('page', 1, type=int)
    query = Caso.query
    
    rol_nombre = current_user.rol.nombre
    titulo_vista = "Vista Global"

    # --- 1. REGLAS DE VISIBILIDAD (FILTROS) ---
    
    if rol_nombre == 'Admin':
        # Ve todo sin filtro
        pass

    elif rol_nombre in ['Referente', 'Visualizador']:
        # Si tiene ciclo asignado, filtra. Si es NULL, ve todo (Global).
        if current_user.ciclo_asignado_id:
            query = query.filter(Caso.ciclo_vital_id == current_user.ciclo_asignado_id)
            titulo_vista = f"Ciclo {current_user.ciclo_asignado.nombre}"
        else:
            titulo_vista = "Vista Global (Todos los Ciclos)"

    elif rol_nombre == 'Funcionario':
        # Solo ve lo que le asignaron explícitamente a él
        query = query.filter(Caso.asignado_a_usuario_id == current_user.id)
        titulo_vista = "Mis Casos Asignados"
    
    else:
        # Rol desconocido o sin permiso base
        abort(403)

    # --- 2. ORDENAMIENTO POR PRIORIDAD ---
    # Prioridad: PENDIENTE_RESCATAR (0) -> EN_SEGUIMIENTO (1) -> CERRADO (2)
    orden_estado = case(
        (Caso.estado == 'PENDIENTE_RESCATAR', 0),
        (Caso.estado == 'EN_SEGUIMIENTO', 1),
        (Caso.estado == 'CERRADO', 2),
        else_=3
    )

    # Aplicamos orden: Estado Prioritario -> Fecha más reciente
    pagination = query.order_by(
        orden_estado, 
        Caso.fecha_ingreso.desc()
    ).paginate(page=page, per_page=15, error_out=False)

    return render_template('casos/index.html', pagination=pagination, nombre_filtro=titulo_vista)

@casos_bp.route('/ver/<int:id>', methods=['GET', 'POST'])
def ver_caso(id):
    caso = Caso.query.get_or_404(id)
    rol_nombre = current_user.rol.nombre

    # --- 1. SEGURIDAD DE ACCESO (Permisos) ---
    permitido = False
    
    if rol_nombre == 'Admin':
        permitido = True
        
    elif rol_nombre in ['Referente', 'Visualizador']:
        # Permiso si es Referente/Visualizador Global (None) O del ciclo del caso
        if current_user.ciclo_asignado_id is None or caso.ciclo_vital_id == current_user.ciclo_asignado_id:
            permitido = True
            
    elif rol_nombre == 'Funcionario':
        # Solo si está asignado a él
        if caso.asignado_a_usuario_id == current_user.id:
            permitido = True
    
    if not permitido:
        abort(403) # Acceso Denegado

    # --- 2. LÓGICA DE ASIGNACIÓN (Solo Admin/Referente) ---
    funcionarios_disponibles = []
    
    # Solo Admin y Referente pueden asignar. Visualizador solo mira.
    if rol_nombre in ['Admin', 'Referente']:
        
        # Cargar lista de funcionarios para el select
        q_func = Usuario.query.join(Rol).filter(Rol.nombre == 'Funcionario').filter(Usuario.activo == True)
        
        # Si es Referente de ciclo específico, solo listar funcionarios de ESE ciclo
        if rol_nombre == 'Referente' and current_user.ciclo_asignado_id:
            q_func = q_func.filter(Usuario.ciclo_asignado_id == current_user.ciclo_asignado_id)
            
        funcionarios_disponibles = q_func.all()

        # Procesar Formulario de Asignación
        if request.method == 'POST' and 'asignar_funcionario' in request.form:
            nuevo_asignado_id = request.form.get('funcionario_id')
            
            if nuevo_asignado_id:
                try:
                    nuevo_asignado_id = int(nuevo_asignado_id)
                    funcionario_nuevo = Usuario.query.get(nuevo_asignado_id)

                    # Validaciones extra de seguridad
                    if not funcionario_nuevo or not funcionario_nuevo.activo:
                        flash('El funcionario seleccionado no es válido o está inactivo.', 'danger')
                        return redirect(url_for('casos.ver_caso', id=caso.id))

                    if rol_nombre == 'Referente' and current_user.ciclo_asignado_id:
                        if funcionario_nuevo.ciclo_asignado_id != current_user.ciclo_asignado_id:
                            flash('No puedes asignar a un funcionario de otro ciclo.', 'danger')
                            return redirect(url_for('casos.ver_caso', id=caso.id))
                    
                    # Datos previos para auditoría
                    anterior_asignado_id = caso.asignado_a_usuario_id
                    accion_tipo = 'REASIGNACION' if anterior_asignado_id else 'ASIGNACION'
                    
                    # --- A) ACTUALIZAR CASO Y DB (PRIMERO) ---
                    caso.asignado_a_usuario_id = nuevo_asignado_id
                    caso.asignado_por_usuario_id = current_user.id
                    caso.asignado_at = obtener_hora_chile() # Hora Local
                    
                    # Avanzar estado automáticamente si estaba pendiente
                    if caso.estado == 'PENDIENTE_RESCATAR':
                        caso.estado = 'EN_SEGUIMIENTO'
                    
                    # Auditoría de la Asignación
                    detalles = {
                        'folio': caso.folio_atencion,
                        'previo_id': anterior_asignado_id,
                        'nuevo_id': nuevo_asignado_id,
                        'nombre_asignado': funcionario_nuevo.nombre_completo,
                        'asignado_por': current_user.nombre_completo
                    }
                    
                    nueva_auditoria = AuditoriaCaso(
                        caso_id=caso.id,
                        usuario_id=current_user.id,
                        fecha_movimiento=obtener_hora_chile(),
                        accion=accion_tipo,
                        detalles_cambio=detalles
                    )
                    db.session.add(nueva_auditoria)
                    
                    # COMMIT DE LA ASIGNACIÓN (Esto asegura que el cambio persista sí o sí)
                    db.session.commit()
                    
                    # Log General
                    registrar_log("Asignación Caso", f"Caso #{caso.folio_atencion} asignado a {funcionario_nuevo.nombre_completo}")
                    flash(f'Caso asignado correctamente a {funcionario_nuevo.nombre_completo}', 'success')
                    
                    # --- B) ENVÍO DE CORREO (BEST EFFORT) ---
                    # Lo hacemos DESPUÉS del commit. Si falla, no rompe la asignación.
                    try:
                        email_enviado = enviar_aviso_asignacion(funcionario_nuevo, caso, current_user)
                        
                        if email_enviado:
                            # Log éxito email
                            registrar_log("Email Asignación", f"Enviado a {funcionario_nuevo.email} (Folio: {caso.folio_atencion})")
                            
                            # Auditoría opcional recomendada
                            audit_email = AuditoriaCaso(
                                caso_id=caso.id,
                                usuario_id=current_user.id,
                                fecha_movimiento=obtener_hora_chile(),
                                accion='EMAIL_ASIGNACION',
                                detalles_cambio={'status': 'OK', 'destino': funcionario_nuevo.email}
                            )
                            db.session.add(audit_email)
                            db.session.commit()
                        else:
                            # Log fallo email
                            registrar_log("Error Email", f"Fallo al enviar a {funcionario_nuevo.email}")
                            flash("Aviso: El caso fue asignado, pero no se pudo enviar el correo de notificación.", "warning")
                            
                            audit_email_fail = AuditoriaCaso(
                                caso_id=caso.id,
                                usuario_id=current_user.id,
                                fecha_movimiento=obtener_hora_chile(),
                                accion='EMAIL_ASIGNACION',
                                detalles_cambio={'status': 'ERROR_ENVIO', 'destino': funcionario_nuevo.email}
                            )
                            db.session.add(audit_email_fail)
                            db.session.commit()

                    except Exception as e_mail:
                        print(f"Excepción crítica enviando correo: {e_mail}")
                        registrar_log("Error Crítico Email", str(e_mail))
                    
                    return redirect(url_for('casos.ver_caso', id=caso.id))
                    
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error al asignar caso: {str(e)}', 'danger')

    return render_template('casos/ver.html', 
                           caso=caso, 
                           funcionarios=funcionarios_disponibles)

# --- NUEVA RUTA: GESTIÓN CLÍNICA (FASE 4 P2) ---
@casos_bp.route('/gestionar/<int:id>', methods=['GET', 'POST'])
@login_required
def gestionar_caso(id):
    """
    Formulario para que el Funcionario (o Admin) ingrese la gestión clínica y cierre el caso.
    """
    caso = Caso.query.get_or_404(id)
    rol_nombre = current_user.rol.nombre

    # 1. Validar Permisos para GESTIONAR (Más estricto que ver)
    puede_gestionar = False
    if rol_nombre == 'Admin':
        puede_gestionar = True
    elif rol_nombre == 'Funcionario' and caso.asignado_a_usuario_id == current_user.id:
        puede_gestionar = True
    
    if not puede_gestionar:
        flash('No tienes permisos para gestionar este caso.', 'danger')
        return redirect(url_for('casos.ver_caso', id=caso.id))

    # Cargar catálogos necesarios para el formulario de gestión
    establecimientos = CatalogoEstablecimiento.query.filter_by(activo=True).order_by(CatalogoEstablecimiento.nombre).all()

    if request.method == 'POST':
        try:
            # 2. PROCESAR GESTIÓN
            
            # A) Completar Nombres (Solo si venían vacíos del origen)
            # Esto evita sobrescribir si ya tenían datos
            if not caso.origen_nombres:
                caso.origen_nombres = request.form.get('nombres_edit')
            if not caso.origen_apellidos:
                caso.origen_apellidos = request.form.get('apellidos_edit')

            # B) Datos Clínicos (CORRECCIÓN SAFE INT + OTRO)
            recinto_inscrito_id_raw = request.form.get('recinto_inscrito_id')
            recinto_inscrito_id_int = safe_int(recinto_inscrito_id_raw) # Convierte '' a None
            
            caso.recinto_inscrito_id = recinto_inscrito_id_int
            
            # Lógica "Otro Recinto Inscrito"
            caso.recinto_inscrito_otro_texto = None # Reset por defecto
            if recinto_inscrito_id_int:
                est_obj = CatalogoEstablecimiento.query.get(recinto_inscrito_id_int)
                if est_obj and 'otro' in est_obj.nombre.lower():
                    texto_otro = request.form.get('recinto_inscrito_otro')
                    if texto_otro and texto_otro.strip():
                        caso.recinto_inscrito_otro_texto = texto_otro.strip()
                    else:
                        flash("Seleccionó 'Otro' recinto pero no especificó cuál.", "warning")
                        # No bloqueamos, pero avisamos.

            caso.ingreso_lain = (request.form.get('ingreso_lain') == '1')
            
            # C) Lógica Fallecido
            es_fallecido = (request.form.get('fallecido') == '1')
            caso.fallecido = es_fallecido
            if es_fallecido and request.form.get('fecha_defuncion'):
                caso.fecha_defuncion = datetime.strptime(request.form.get('fecha_defuncion'), '%Y-%m-%d').date()
            else:
                caso.fecha_defuncion = None # Limpiar si desmarcan

            # D) Seguimiento (Los valores vienen exactamente como los códigos ENUM del select)
            caso.control_sanitario = request.form.get('control_sanitario')
            caso.gestion_vacunas = request.form.get('gestion_vacunas')
            caso.gestion_judicial = request.form.get('gestion_judicial')
            caso.gestion_salud_mental = request.form.get('gestion_salud_mental')
            caso.gestion_cosam = request.form.get('gestion_cosam')

            # E) Observaciones Finales
            caso.observaciones_gestion = request.form.get('observaciones_gestion')
            
            # F) Auditoría del movimiento
            audit = AuditoriaCaso(
                caso_id=caso.id,
                usuario_id=current_user.id,
                fecha_movimiento=obtener_hora_chile(),
                accion='GESTION_CLINICA',
                detalles_cambio={'tipo': 'actualizacion_seguimiento'}
            )
            db.session.add(audit)
            
            db.session.commit()
            
            flash('Gestión guardada exitosamente.', 'success')
            return redirect(url_for('casos.ver_caso', id=caso.id))

        except Exception as e:
            db.session.rollback()
            print(f"Error gestionando caso: {e}")
            flash('Ocurrió un error al guardar la gestión.', 'danger')

    return render_template('casos/gestion.html', caso=caso, establecimientos=establecimientos)