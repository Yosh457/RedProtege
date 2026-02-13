from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Caso, CatalogoRecinto, CatalogoVulneracion, CatalogoCiclo, CatalogoInstitucion
from utils import registrar_log, es_rut_valido, enviar_aviso_nuevo_caso, safe_int
from datetime import datetime

# Blueprint de Solicitudes (Acceso restringido a usuarios logueados, especialmente Rol 'Solicitante')
solicitudes_bp = Blueprint('solicitudes', __name__, template_folder='../templates', url_prefix='/solicitudes')
    
def clean(value):
    """Convierte espacios vacios a None para guardar NULL en BD."""
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None

def clean_rut(value):
    """
    Normaliza RUT para persistencia: sin puntos y con guion.
    Retorna None si viene vacío.
    Ej: 12.345.678-9 -> 12345678-9
    """
    v = clean(value)
    if not v:
        return None
    v = v.replace(".", "").replace(" ", "").upper()
    # Si viene con guion, ok; si no, lo agregamos al final
    if "-" in v:
        cuerpo, dv = v.split("-", 1)
        cuerpo = "".join(ch for ch in cuerpo if ch.isdigit())
        dv = (dv[:1] or "").upper()
        return f"{cuerpo}-{dv}" if cuerpo and dv else None
    else:
        # último char es dv
        cuerpo = "".join(ch for ch in v[:-1] if ch.isdigit())
        dv = v[-1].upper()
        return f"{cuerpo}-{dv}" if cuerpo and dv else None
    
def rut_excede_largo(rut_normalizado):
    """
    Evita Data too long.
    Persistimos como 12345678-9 => largo máx 10 (8 + 1 + 1).
    Para 7 dígitos => 9.
    """
    if not rut_normalizado:
        return False
    return len(rut_normalizado) > 10

@solicitudes_bp.route('/ingreso', methods=['GET', 'POST'])
@login_required
def formulario():
    """
    Formulario de ingreso de casos.
    Disponible para roles: Solicitante (principal), Admin, Referente.
    """
    # Carga de catálogos para los selects
    recintos = CatalogoRecinto.query.filter_by(activo=True).order_by(CatalogoRecinto.nombre).all()
    vulneraciones = CatalogoVulneracion.query.filter_by(activo=True).order_by(CatalogoVulneracion.nombre).all()
    ciclos = CatalogoCiclo.query.all()
    instituciones = CatalogoInstitucion.query.filter_by(activo=True).order_by(CatalogoInstitucion.nombre).all()

    if request.method == 'POST':
        try:
            # 1. Anti-Spam (Honeypot)
            if request.form.get('website'): 
                return redirect(url_for('solicitudes.formulario'))

            f = request.form
            errores = []

            # 2. Normalización de IDs
            recinto_id_int = safe_int(f.get('recinto_id'))
            ciclo_id_int = safe_int(f.get('ciclo_id'))
            institucion_id_int = safe_int(f.get('institucion_id'))
            
            # Vulneraciones (lista de ints)
            vulneraciones_raw = f.getlist('vulneraciones')
            vulneraciones_ids_int = [safe_int(x) for x in vulneraciones_raw if safe_int(x) is not None]

            # 3. Validaciones de Campos Obligatorios
            # Nota: Nombres y Apellidos del paciente YA NO son obligatorios (pueden venir vacíos)
            
            if not f.get('fecha_atencion') or not f.get('folio_atencion'):
                errores.append("Faltan datos de fecha o folio de atención.")
            
            if not recinto_id_int:
                errores.append("Debe seleccionar un Recinto de Notificación.")
            
            if not ciclo_id_int:
                errores.append("Debe seleccionar un Ciclo Vital.")

            if not vulneraciones_ids_int:
                errores.append("Debe seleccionar al menos un Tipo de Vulneración.")

            # Relato obligatorio (usa clean => strip + None)
            relato = clean(f.get('relato_caso'))
            if not relato:
                errores.append("El relato del caso es obligatorio.")

            # --- RUT PACIENTE: validar SOLO si tipo=RUT y viene valor ---
            paciente_doc_tipo = f.get('paciente_doc_tipo')
            paciente_doc_num_raw = f.get('paciente_doc_numero')
            paciente_doc_num = clean_rut(paciente_doc_num_raw) if paciente_doc_tipo == 'RUT' else clean(paciente_doc_num_raw)

            if paciente_doc_tipo == 'RUT' and paciente_doc_num:
                if rut_excede_largo(paciente_doc_num):
                    errores.append("El RUT del paciente excede el largo permitido.")
                elif not es_rut_valido(paciente_doc_num):
                    errores.append("El RUT del paciente ingresado no es válido.")

            # --- RUT ACOMPAÑANTE: validar SOLO si tipo=RUT y viene valor ---
            acomp_doc_tipo = f.get('acomp_doc_tipo')
            acomp_doc_num_raw = f.get('acomp_doc_numero')
            acomp_doc_num = clean_rut(acomp_doc_num_raw) if acomp_doc_tipo == 'RUT' else clean(acomp_doc_num_raw)

            if acomp_doc_tipo == 'RUT' and acomp_doc_num:
                if rut_excede_largo(acomp_doc_num):
                    errores.append("El RUT del acompañante excede el largo permitido.")
                elif not es_rut_valido(acomp_doc_num):
                    errores.append("El RUT del acompañante ingresado no es válido.")

            # Si hay errores, devolver formulario con datos previos
            if errores:
                for e in errores: flash(e, 'danger')
                return render_template('solicitudes/formulario.html', 
                                       recintos=recintos, vulneraciones=vulneraciones, 
                                       ciclos=ciclos, instituciones=instituciones,
                                       datos=f)

            # --- NUEVA VALIDACIÓN: DENUNCIA OBLIGATORIA ---
            # Verificamos si el usuario marcó "Sí" en el formulario
            denuncia_flag_check = (f.get('denuncia_realizada') == '1')
            
            if denuncia_flag_check:
                # Validar Institución (institucion_id_int ya fue procesado con safe_int arriba)
                if not institucion_id_int:
                    errores.append("Si se realizó denuncia, debe seleccionar la Institución.")
                
                # Validar Nombre Profesional
                denuncia_nombre_check = clean(f.get('denuncia_nombre'))
                if not denuncia_nombre_check:
                    errores.append("Si se realizó denuncia, debe indicar el Nombre del Profesional.")

            # Si hay errores, devolver formulario con datos previos
            if errores:
                for e in errores: flash(e, 'danger')
                return render_template('solicitudes/formulario.html', 
                                       recintos=recintos, vulneraciones=vulneraciones, 
                                       ciclos=ciclos, instituciones=instituciones,
                                       datos=f)
            
            # 4. Lógica de Campos "Otro"
            # Recinto
            recinto_obj = CatalogoRecinto.query.get(recinto_id_int)
            recinto_texto = f.get('recinto_otro') if (recinto_obj and 'otro' in recinto_obj.nombre.lower()) else None

            # Vulneración
            objetos_vulneracion = []
            flag_vuln_otro = False
            for v_id in vulneraciones_ids_int:
                v_obj = CatalogoVulneracion.query.get(v_id)
                if v_obj:
                    objetos_vulneracion.append(v_obj)
                    if 'otro' in v_obj.nombre.lower():
                        flag_vuln_otro = True
            
            vulneracion_texto = clean(f.get('vulneracion_otro_txt')) if flag_vuln_otro else None

            # 5. Lógica Denuncia Institución (si hubo denuncia)
            # Si NO hubo denuncia, forzamos todos los campos relacionados a None (NULL en DB)
            denuncia_flag = (f.get('denuncia_realizada') == '1')
            
            denuncia_inst_id = None
            denuncia_inst_otro = None
            denuncia_prof_nombre = None
            denuncia_prof_cargo = None

            if denuncia_flag:
                # Solo procesamos datos si marcó Sí
                denuncia_inst_id = institucion_id_int
                # Revisar si es "Otra" institución
                if denuncia_inst_id:
                    inst_obj = CatalogoInstitucion.query.get(denuncia_inst_id)
                    if inst_obj and 'otro' in inst_obj.nombre.lower():
                        denuncia_inst_otro = clean(f.get('institucion_otro'))
                
                denuncia_prof_nombre = clean(f.get('denuncia_nombre'))
                denuncia_prof_cargo = clean(f.get('denuncia_cargo'))
            
            # --- NUEVA LÓGICA: ACOMPAÑANTE DINÁMICO ---
            acompanante_presente = (f.get('acompanante_presente') == '1')

            # Si NO viene acompañado, forzamos todos los campos del acompañante a None (NULL en DB)
            if not acompanante_presente:
                acomp_nombre = None
                acomp_parentesco = None
                acomp_telefono = None
                acomp_tel_tipo = None
                acomp_doc_tipo = None
                acomp_doc_num = None
                acomp_doc_otro_desc = None
                a_calle = None
                a_num = None
                a_dom = None
            else:
                # Si viene acompañado:
                # - Nombre y parentesco ya NO son obligatorios
                # - Teléfono SÍ es obligatorio
                acomp_nombre = clean(f.get('acomp_nombre'))
                acomp_parentesco = clean(f.get('acomp_parentesco'))

                acomp_telefono = clean(f.get('acomp_telefono'))
                if not acomp_telefono:
                    errores.append(
                        "Si el paciente viene acompañado, el teléfono del acompañante es obligatorio."
                    )

                acomp_tel_tipo = clean(f.get('acomp_tel_tipo'))

                # Documento acompañante (ya normalizado arriba: acomp_doc_tipo / acomp_doc_num)
                acomp_doc_otro_desc = (
                    clean(f.get('acomp_doc_otro_desc'))
                    if acomp_doc_tipo == 'OTRO'
                    else None
                )

                # Dirección acompañante
                a_calle = clean(f.get('acomp_calle'))
                a_num = clean(f.get('acomp_numero'))
                a_dom = f"{a_calle} #{a_num}".strip(" #") if (a_calle or a_num) else None

            # Si hubo error por teléfono obligatorio
            if errores:
                for e in errores:
                    flash(e, 'danger')
                return render_template(
                    'solicitudes/formulario.html',
                    recintos=recintos,
                    vulneraciones=vulneraciones,
                    ciclos=ciclos,
                    instituciones=instituciones,
                    datos=f
                )

            # 6. Preparar Fechas
            fecha_atencion_dt = datetime.strptime(f.get('fecha_atencion'), '%Y-%m-%d').date()
            hora_atencion_dt = datetime.strptime(f.get('hora_atencion'), '%H:%M').time() if f.get('hora_atencion') else None
            
            fecha_nac_dt = None
            if f.get('paciente_fecha_nac'):
                fecha_nac_dt = datetime.strptime(f.get('paciente_fecha_nac'), '%Y-%m-%d').date()

            # 7. Construcción de Direcciones (mismo flujp. érp cñean => NULL)
            # Paciente
            p_calle = clean(f.get('paciente_calle'))
            p_num = clean(f.get('paciente_numero'))
            p_dom = f"{p_calle} #{p_num}".strip(" #") if (p_calle or p_num) else None

            # 8. Creación del Objeto Caso
            nuevo_caso = Caso(
                # Antecedentes
                fecha_atencion=fecha_atencion_dt,
                hora_atencion=hora_atencion_dt,
                recinto_notifica_id=recinto_id_int,
                recinto_otro_texto=recinto_texto,
                folio_atencion=clean(f.get('folio_atencion')),
                ingresado_por_nombre=clean(f.get('funcionario_nombre')),
                ingresado_por_cargo=clean(f.get('funcionario_cargo')),
                ciclo_vital_id=ciclo_id_int,
                
                # Paciente (Permite Nulos)
                origen_nombres=clean(f.get('paciente_nombres')),
                origen_apellidos=clean(f.get('paciente_apellidos')),
                origen_rut=f.get('paciente_doc_numero') if f.get('paciente_doc_tipo') == 'RUT' else None, # Llenamos legacy
                origen_fecha_nacimiento=fecha_nac_dt, # Llenamos legacy

                # Asignación de Relato Obligatorio
                origen_relato=relato,
                
                paciente_doc_tipo=paciente_doc_tipo,
                paciente_doc_numero=paciente_doc_num, # normalizado si es RUT, clean si no
                paciente_doc_otro_descripcion=clean(f.get('paciente_doc_otro_desc')) if f.get('paciente_doc_tipo') == 'OTRO' else None,
                paciente_fecha_nacimiento=fecha_nac_dt,
                
                # Direcciones
                paciente_direccion_calle=p_calle,
                paciente_direccion_numero=p_num,
                paciente_domicilio=p_dom,

                # Acompañante
                acompanante_nombre=acomp_nombre,
                acompanante_parentesco=acomp_parentesco,
                acompanante_telefono=acomp_telefono,
                acompanante_telefono_tipo=acomp_tel_tipo,
                acompanante_doc_tipo=acomp_doc_tipo,
                acompanante_doc_numero=acomp_doc_num,
                acompanante_doc_otro_descripcion=acomp_doc_otro_desc,
                
                acompanante_direccion_calle=a_calle,
                acompanante_direccion_numero=a_num,
                acompanante_domicilio=a_dom,

                # Denuncia
                denuncia_realizada=denuncia_flag,
                denuncia_institucion_id=denuncia_inst_id,
                denuncia_institucion_otro=denuncia_inst_otro,
                denuncia_profesional_nombre=denuncia_prof_nombre,
                denuncia_profesional_cargo=denuncia_prof_cargo,
                
                vulneracion_otro_texto=vulneracion_texto,
                estado='PENDIENTE_RESCATAR'
            )

            # Asignar relaciones Many-to-Many
            for v_obj in objetos_vulneracion:
                nuevo_caso.vulneraciones.append(v_obj)

            # 9. Persistencia
            db.session.add(nuevo_caso)
            db.session.commit()

            # 10. Trazabilidad y Notificaciones
            registrar_log("Ingreso Caso", f"Caso #{nuevo_caso.folio_atencion} ingresado por {current_user.email}")
            
            # Enviar aviso a Referentes
            enviar_aviso_nuevo_caso(nuevo_caso, current_user)

            flash("Solicitud ingresada exitosamente. Se ha notificado al equipo.", "success")
            return redirect(url_for('solicitudes.formulario'))

        except Exception as e:
            db.session.rollback()
            print(f"Error ingreso caso: {e}")
            flash("Error al procesar la solicitud. Verifique los datos.", "danger")
            return render_template('solicitudes/formulario.html', 
                                   recintos=recintos, vulneraciones=vulneraciones, 
                                   ciclos=ciclos, instituciones=instituciones,
                                   datos=request.form)

    return render_template('solicitudes/formulario.html', 
                           recintos=recintos, vulneraciones=vulneraciones, 
                           ciclos=ciclos, instituciones=instituciones)