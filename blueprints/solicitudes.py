from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Caso, CatalogoRecinto, CatalogoVulneracion, CatalogoCiclo, CatalogoInstitucion
from utils import registrar_log, es_rut_valido, enviar_aviso_nuevo_caso
from datetime import datetime

# Blueprint de Solicitudes (Acceso restringido a usuarios logueados, especialmente Rol 'Solicitante')
solicitudes_bp = Blueprint('solicitudes', __name__, template_folder='../templates', url_prefix='/solicitudes')

def safe_int(value):
    """Ayuda a convertir a int de forma segura, retornando None si falla."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

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

            # CORRECCIÓN: Validación de Relato Obligatorio
            relato = (f.get('relato_caso') or '').strip()
            if not relato:
                errores.append("El relato del caso es obligatorio.")

            # Validar RUT solo si el tipo es RUT
            if f.get('paciente_doc_tipo') == 'RUT':
                rut = f.get('paciente_doc_numero')
                if not rut or not es_rut_valido(rut):
                    errores.append("El RUT del paciente ingresado no es válido.")

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
            
            vulneracion_texto = f.get('vulneracion_otro_txt') if flag_vuln_otro else None

            # Institución (si hubo denuncia)
            denuncia_flag = (f.get('denuncia_realizada') == '1')
            inst_texto = None
            inst_final_id = None
            
            if denuncia_flag and institucion_id_int:
                inst_final_id = institucion_id_int
                inst_obj = CatalogoInstitucion.query.get(institucion_id_int)
                if inst_obj and 'otro' in inst_obj.nombre.lower():
                    inst_texto = f.get('institucion_otro')

            # 5. Construcción de Direcciones (Legacy + Nuevas)
            # Paciente
            p_calle = (f.get('paciente_calle') or '').strip()
            p_num = (f.get('paciente_numero') or '').strip()
            p_dom = f"{p_calle} #{p_num}".strip(" #") if (p_calle or p_num) else None

            # Acompañante
            a_calle = (f.get('acomp_calle') or '').strip()
            a_num = (f.get('acomp_numero') or '').strip()
            a_dom = f"{a_calle} #{a_num}".strip(" #") if (a_calle or a_num) else None

            # 6. Creación del Objeto Caso
            nuevo_caso = Caso(
                # Antecedentes
                fecha_atencion=datetime.strptime(f.get('fecha_atencion'), '%Y-%m-%d').date(),
                hora_atencion=datetime.strptime(f.get('hora_atencion'), '%H:%M').time() if f.get('hora_atencion') else None,
                recinto_notifica_id=recinto_id_int,
                recinto_otro_texto=recinto_texto,
                folio_atencion=f.get('folio_atencion'),
                ingresado_por_nombre=f.get('funcionario_nombre'),
                ingresado_por_cargo=f.get('funcionario_cargo'),
                ciclo_vital_id=ciclo_id_int,
                
                # Paciente (Permite Nulos)
                origen_nombres=f.get('paciente_nombres') or None,
                origen_apellidos=f.get('paciente_apellidos') or None,

                # CORRECCIÓN: Asignación de Relato Obligatorio
                origen_relato=relato,
                
                paciente_doc_tipo=f.get('paciente_doc_tipo'),
                paciente_doc_numero=f.get('paciente_doc_numero'),
                paciente_doc_otro_descripcion=f.get('paciente_doc_otro_desc') if f.get('paciente_doc_tipo') == 'OTRO' else None,
                paciente_fecha_nacimiento=datetime.strptime(f.get('paciente_fecha_nac'), '%Y-%m-%d').date() if f.get('paciente_fecha_nac') else None,
                
                # Direcciones
                paciente_direccion_calle=p_calle,
                paciente_direccion_numero=p_num,
                paciente_domicilio=p_dom,

                # Acompañante
                acompanante_nombre=f.get('acomp_nombre'),
                acompanante_parentesco=f.get('acomp_parentesco'),
                acompanante_telefono=f.get('acomp_telefono'),
                acompanante_telefono_tipo=f.get('acomp_tel_tipo'),
                acompanante_doc_tipo=f.get('acomp_doc_tipo'),
                acompanante_doc_numero=f.get('acomp_doc_numero'),
                acompanante_doc_otro_descripcion=f.get('acomp_doc_otro_desc') if f.get('acomp_doc_tipo') == 'OTRO' else None,
                
                acompanante_direccion_calle=a_calle,
                acompanante_direccion_numero=a_num,
                acompanante_domicilio=a_dom,

                # Denuncia
                denuncia_realizada=denuncia_flag,
                denuncia_institucion_id=inst_final_id,
                denuncia_institucion_otro=inst_texto,
                denuncia_profesional_nombre=f.get('denuncia_nombre'),
                denuncia_profesional_cargo=f.get('denuncia_cargo'),
                
                vulneracion_otro_texto=vulneracion_texto,
                estado='PENDIENTE_RESCATAR'
            )

            # Asignar relaciones Many-to-Many
            for v_obj in objetos_vulneracion:
                nuevo_caso.vulneraciones.append(v_obj)

            # 7. Persistencia
            db.session.add(nuevo_caso)
            db.session.commit()

            # 8. Trazabilidad y Notificaciones
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