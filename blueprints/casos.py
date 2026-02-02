import os
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from sqlalchemy import case
from models import db, Caso, Usuario, Rol, AuditoriaCaso, CatalogoEstablecimiento, obtener_hora_chile
from utils import check_password_change, registrar_log, enviar_aviso_asignacion, generar_acta_cierre_pdf, enviar_aviso_cierre
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
    
    # Solo Admin y Referente pueden asignar. Visualizador solo mira. Si el caso está cerrado, no se procesa asignación.
    if rol_nombre in ['Admin', 'Referente'] and caso.estado != 'CERRADO':
        
        # Cargar lista de funcionarios para el select
        q_func = Usuario.query.join(Rol).filter(Rol.nombre == 'Funcionario').filter(Usuario.activo == True)
        
        # Si es Referente de ciclo específico, solo listar funcionarios de ESE ciclo
        if rol_nombre == 'Referente' and current_user.ciclo_asignado_id:
            q_func = q_func.filter(Usuario.ciclo_asignado_id == current_user.ciclo_asignado_id)
            
        funcionarios_disponibles = q_func.all()

        # Procesar Formulario de Asignación
        if request.method == 'POST' and 'asignar_funcionario' in request.form:
            # Doble check por si forzaron el POST
            if caso.estado == 'CERRADO':
                flash('El caso está cerrado. No se puede asignar', 'danger')
                return redirect(url_for('casos.ver_caso', id=caso.id))
            
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

    #Si el caso está cerrado, se expulsa inmediatamente
    if caso.estado == 'CERRADO':
        flash('El caso ya está cerrado. No es posible editar la gestión.', 'danger')
        return redirect(url_for('casos.ver_caso', id=caso.id))

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

# --- RUTA CIERRE DE CASO (FINAL) ---
@casos_bp.route('/cerrar/<int:id>', methods=['POST'])
@login_required
def cerrar_caso(id):
    caso = Caso.query.get_or_404(id)
    rol_nombre = current_user.rol.nombre

    # 1. Validar Permisos (Admin o Funcionario Asignado)
    puede_cerrar = False
    if rol_nombre == 'Admin':
        puede_cerrar = True
    elif rol_nombre == 'Funcionario' and caso.asignado_a_usuario_id == current_user.id:
        puede_cerrar = True
    
    if not puede_cerrar:
        flash('No tienes permisos para cerrar este caso.', 'danger')
        return redirect(url_for('casos.ver_caso', id=caso.id))

    if caso.estado == 'CERRADO':
        flash('El caso ya se encuentra cerrado.', 'warning')
        return redirect(url_for('casos.ver_caso', id=caso.id))

    try:
        # 2. Actualizar Estado en BD (Primer Commit)
        caso.estado = 'CERRADO'
        caso.fecha_cierre = obtener_hora_chile() # Fecha oficial
        caso.usuario_cierre_id = current_user.id
        
        # Auditoría
        audit = AuditoriaCaso(
            caso_id=caso.id,
            usuario_id=current_user.id,
            fecha_movimiento=obtener_hora_chile(),
            accion='CIERRE_CASO',
            detalles_cambio={'motivo': 'Cierre manual por gestión finalizada'}
        )
        db.session.add(audit)
        db.session.commit() # Guardamos para que la fecha_cierre esté firme en DB

        # 3. Generar PDF de Acta (Path Estable y Multiplataforma)
        filename = f"acta_{caso.id}_{caso.folio_atencion}.pdf"
        
        # Calculamos la raíz del proyecto subiendo un nivel desde 'blueprints/'
        # Esto funciona en Windows y Linux/cPanel por igual
        BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        uploads_actas_dir = os.path.join(BASE_DIR, 'uploads', 'actas')
        
        # Ruta absoluta completa para guardar el archivo
        output_path_abs = os.path.join(uploads_actas_dir, filename)

        # Ruta relativa para guardar en BD (portable)
        output_path_rel = f"uploads/actas/{filename}"

        # Generar el PDF
        generar_acta_cierre_pdf(caso, output_path_abs, current_user)

        # 4. Guardar ruta relativa en BD
        caso.acta_pdf_path = output_path_rel
        db.session.commit()

        # 5. Enviar Correo con Adjunto (Best Effort)
        try:
            enviar_aviso_cierre(caso, current_user, output_path_abs)
            flash('Caso cerrado exitosamente. Acta generada y notificaciones enviadas.', 'success')
        except Exception as e_mail:
            print(f"Error enviando correo cierre: {e_mail}")
            flash('Caso cerrado y acta generada, pero falló el envío del correo.', 'warning')

        registrar_log("Cierre Caso", f"Caso #{caso.folio_atencion} cerrado por {current_user.nombre_completo}")

    except Exception as e:
        db.session.rollback()
        print(f"Error cerrando caso: {e}")
        flash(f'Error crítico al cerrar el caso: {str(e)}', 'danger')

    return redirect(url_for('casos.ver_caso', id=caso.id))

# --- RUTA DESCARGA SEGURA DE ACTA (PRODUCCIÓN) ---
@casos_bp.route('/acta/<int:id>', methods=['GET'])
@login_required
def descargar_acta(id):
    """
    Endpoint protegido para descargar el PDF del acta.
    Incluye protección robusta contra Path Traversal, auditoría de descarga
    y validación de permisos extendida (asignado o cerrador).
    """
    caso = Caso.query.get_or_404(id)
    rol_nombre = current_user.rol.nombre

    # 1. VALIDACIÓN DE PERMISOS
    permitido = False
    
    if rol_nombre == 'Admin':
        permitido = True
        
    elif rol_nombre in ['Referente', 'Visualizador']:
        # Permiso si es Global o del ciclo del caso
        if current_user.ciclo_asignado_id is None or caso.ciclo_vital_id == current_user.ciclo_asignado_id:
            permitido = True
            
    elif rol_nombre == 'Funcionario':
        # AJUSTE PERMISOS: Permitido si es el asignado actual O quien cerró el caso
        es_asignado = (caso.asignado_a_usuario_id == current_user.id)
        es_quien_cerro = (caso.usuario_cierre_id == current_user.id)
        
        if es_asignado or es_quien_cerro:
            permitido = True
            
    if not permitido:
        flash("No tienes permisos para descargar este documento.", "danger")
        return redirect(url_for('casos.index'))

    # 2. VALIDAR EXISTENCIA EN BD
    if not caso.acta_pdf_path:
        flash('El caso no tiene un acta generada.', 'warning')
        return redirect(url_for('casos.ver_caso', id=caso.id))

    try:
        # 3. CONSTRUCCIÓN Y SEGURIDAD DE RUTA (PATH TRAVERSAL ROBUSTO)
        
        # Base del proyecto (un nivel arriba de blueprints/)
        BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        # Limpiamos la ruta relativa de BD
        ruta_relativa = caso.acta_pdf_path.replace('\\', '/').lstrip('/')
        
        # Resolvemos la ruta absoluta final del archivo solicitado
        path_absoluto = os.path.abspath(os.path.join(BASE_DIR, ruta_relativa))
        
        # Definimos la "jaula" autorizada (carpeta actas)
        carpeta_actas = os.path.abspath(os.path.join(BASE_DIR, 'uploads', 'actas'))

        # AJUSTE 1: Validación estricta con os.sep para evitar falsos positivos
        # Aseguramos que la ruta comience con "carpeta_actas/" (o "\" en Windows)
        # Esto evita que 'uploads/actas_secretas' pase el filtro de 'uploads/actas'
        carpeta_con_sep = os.path.join(carpeta_actas, '') # Agrega el separador al final (/ o \)
        
        if not path_absoluto.startswith(carpeta_con_sep):
            registrar_log("Seguridad", f"ALERTA: Intento de Path Traversal por {current_user.email}. Path: {path_absoluto}")
            abort(403) # Acceso Prohibido

        # 4. VERIFICAR ARCHIVO FÍSICO
        if not os.path.exists(path_absoluto):
            registrar_log("Error Archivo", f"Acta no encontrada en disco: {path_absoluto}")
            flash('El archivo físico del acta no se encuentra en el servidor.', 'danger')
            return redirect(url_for('casos.ver_caso', id=caso.id))

        # AJUSTE 2: Auditoría de la descarga (Trazabilidad)
        # Registramos quién descargó el archivo y de qué caso antes de enviarlo
        registrar_log(
            "Descarga Acta", 
            f"Usuario={current_user.email} descargó el acta del Caso={caso.id} - Folio={caso.folio_atencion}"
        )

        # AJUSTE 3: Nombre de archivo amigable para el usuario
        # Genera "Acta_Cierre_FOLIO.pdf" en lugar de "acta_1_FOLIO.pdf" (interno)
        nombre_descarga = f"Acta_Cierre_{caso.folio_atencion or caso.id}.pdf"

        # 5. SERVIR ARCHIVO
        return send_file(
            path_absoluto,
            as_attachment=True,
            download_name=nombre_descarga
        )

    except Exception as e:
        print(f"Error sirviendo archivo: {e}")
        flash('Error interno al intentar descargar el archivo.', 'danger')
        return redirect(url_for('casos.ver_caso', id=caso.id))