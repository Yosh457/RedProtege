from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Caso, CatalogoRecinto, CatalogoVulneracion, CatalogoCiclo, CatalogoInstitucion
from utils import registrar_log, es_rut_valido
from datetime import datetime

# Blueprint PÚBLICO (Sin @login_required)
publico_bp = Blueprint('publico', __name__, template_folder='../templates')

def safe_int(value):
    """Ayuda a convertir a int de forma segura, retornando None si falla."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

@publico_bp.route('/formulario', methods=['GET', 'POST'])
def formulario():
    # 1. Carga de catálogos para renderizar el form
    recintos = CatalogoRecinto.query.filter_by(activo=True).order_by(CatalogoRecinto.nombre).all()
    vulneraciones = CatalogoVulneracion.query.filter_by(activo=True).order_by(CatalogoVulneracion.nombre).all()
    ciclos = CatalogoCiclo.query.all()
    instituciones = CatalogoInstitucion.query.filter_by(activo=True).order_by(CatalogoInstitucion.nombre).all()

    if request.method == 'POST':
        try:
            # 2. ANTI-SPAM (Honeypot)
            if request.form.get('website'):
                return redirect(url_for('publico.formulario'))

            errores = []
            f = request.form # Alias corto

            # --- A) NORMALIZACIÓN DE IDs (String -> Int) ---
            recinto_id_int = safe_int(f.get('recinto_id'))
            ciclo_id_int = safe_int(f.get('ciclo_id'))
            institucion_id_int = safe_int(f.get('institucion_id'))
            
            # Vulneraciones: Lista de ints
            vulneraciones_raw = f.getlist('vulneraciones')
            vulneraciones_ids_int = [safe_int(x) for x in vulneraciones_raw if safe_int(x) is not None]

            # --- B) VALIDACIÓN DE CAMPOS OBLIGATORIOS ---
            campos_obligatorios = [
                ('fecha_atencion', 'Fecha de Atención'),
                ('hora_atencion', 'Hora de Atención'),
                ('folio_atencion', 'Folio de Atención'),
                ('funcionario_nombre', 'Nombre Funcionario'),
                ('funcionario_cargo', 'Cargo Funcionario'),
                ('paciente_nombres', 'Nombres Paciente'),
                ('paciente_apellidos', 'Apellidos Paciente'),
                ('paciente_fecha_nac', 'Fecha Nacimiento Paciente'),
                ('paciente_domicilio', 'Domicilio Paciente'),
                ('relato_caso', 'Relato del Caso'),
                ('acomp_nombre', 'Nombre Acompañante'),
                ('acomp_parentesco', 'Parentesco Acompañante'),
                ('acomp_telefono', 'Teléfono Acompañante')
            ]

            for campo, label in campos_obligatorios:
                if not f.get(campo):
                    errores.append(f"El campo '{label}' es obligatorio.")

            if not recinto_id_int:
                errores.append("Debe seleccionar un Recinto de Notificación.")
            
            if not ciclo_id_int:
                errores.append("Debe seleccionar un Ciclo Vital.")

            if not vulneraciones_ids_int:
                errores.append("Debe seleccionar al menos un Tipo de Vulneración.")

            # --- C) VALIDACIONES DE LÓGICA DE NEGOCIO ---

            # 1. Validación RUT Paciente
            if f.get('paciente_doc_tipo') == 'RUT':
                rut = f.get('paciente_doc_numero')
                if not rut or not es_rut_valido(rut):
                    errores.append("El RUT del paciente ingresado no es válido.")

            # 2. Validación "Otro Recinto"
            recinto_obj = CatalogoRecinto.query.get(recinto_id_int) if recinto_id_int else None
            recinto_otro_valido = None # Variable final para guardar
            
            if recinto_obj and 'otro' in recinto_obj.nombre.lower():
                texto_otro = f.get('recinto_otro')
                if not texto_otro or not texto_otro.strip():
                    errores.append("Especificó 'Otro' recinto pero no ingresó el nombre.")
                else:
                    recinto_otro_valido = texto_otro

            # 3. Validación Vulneración "Otro"
            # Recuperamos los objetos seleccionados para ver si alguno es "otro"
            objetos_vulneracion = []
            flag_vuln_otro = False
            
            for v_id in vulneraciones_ids_int:
                v_obj = CatalogoVulneracion.query.get(v_id)
                if v_obj:
                    objetos_vulneracion.append(v_obj)
                    if 'otro' in v_obj.nombre.lower():
                        flag_vuln_otro = True
            
            vulneracion_otro_valido = None
            if flag_vuln_otro:
                texto_vuln_otro = f.get('vulneracion_otro_txt')
                if not texto_vuln_otro or not texto_vuln_otro.strip():
                    errores.append("Seleccionó vulneración 'Otro' pero no especificó cuál.")
                else:
                    vulneracion_otro_valido = texto_vuln_otro

            # 4. Validación y Limpieza Denuncia
            denuncia_flag = (f.get('denuncia_realizada') == '1')
            
            institucion_final_id = None
            institucion_otro_valido = None
            profesional_nombre_valido = None
            profesional_cargo_valido = None

            if denuncia_flag:
                # Si hubo denuncia, validar campos extra
                if not institucion_id_int:
                    errores.append("Si hubo denuncia, debe seleccionar la Institución.")
                else:
                    institucion_final_id = institucion_id_int
                    inst_obj = CatalogoInstitucion.query.get(institucion_id_int)
                    
                    # Validar "Otra" institución
                    if inst_obj and 'otro' in inst_obj.nombre.lower():
                        texto_inst_otro = f.get('institucion_otro')
                        if not texto_inst_otro or not texto_inst_otro.strip():
                            errores.append("Especificó 'Otra' institución pero no ingresó el nombre.")
                        else:
                            institucion_otro_valido = texto_inst_otro
                
                # Campos de profesional (opcionales u obligatorios según criterio, aquí los guardamos si existen)
                profesional_nombre_valido = f.get('denuncia_nombre')
                profesional_cargo_valido = f.get('denuncia_cargo')
            
            # Si NO hubo denuncia, las variables se quedan en None (limpieza)

            # --- D) MANEJO DE ERRORES ---
            if errores:
                for error in errores:
                    flash(error, 'danger')
                return render_template('publico/formulario.html', 
                                       recintos=recintos, vulneraciones=vulneraciones, 
                                       ciclos=ciclos, instituciones=instituciones,
                                       datos=request.form)

            # --- E) CREACIÓN DEL CASO (Datos Limpios) ---
            nuevo_caso = Caso(
                # ANTECEDENTES
                fecha_atencion=datetime.strptime(f.get('fecha_atencion'), '%Y-%m-%d').date(),
                hora_atencion=datetime.strptime(f.get('hora_atencion'), '%H:%M').time(),
                recinto_notifica_id=recinto_id_int,
                recinto_otro_texto=recinto_otro_valido, # Solo si aplica
                folio_atencion=f.get('folio_atencion'),
                ingresado_por_nombre=f.get('funcionario_nombre'),
                ingresado_por_cargo=f.get('funcionario_cargo'),
                ciclo_vital_id=ciclo_id_int,
                
                # PACIENTE
                paciente_doc_tipo=f.get('paciente_doc_tipo'),
                paciente_doc_numero=f.get('paciente_doc_numero'),
                paciente_doc_otro_descripcion=f.get('paciente_doc_otro_desc') if f.get('paciente_doc_tipo') == 'OTRO' else None,
                paciente_fecha_nacimiento=datetime.strptime(f.get('paciente_fecha_nac'), '%Y-%m-%d').date(),
                paciente_domicilio=f.get('paciente_domicilio'),
                
                # LEGACY / COMPATIBILIDAD (Llenado automático)
                origen_nombres=f.get('paciente_nombres'),
                origen_apellidos=f.get('paciente_apellidos'),
                origen_relato=f.get('relato_caso'),
                origen_rut=f.get('paciente_doc_numero') if f.get('paciente_doc_tipo') == 'RUT' else None,
                origen_fecha_nacimiento=datetime.strptime(f.get('paciente_fecha_nac'), '%Y-%m-%d').date(),
                
                # ACOMPAÑANTE
                acompanante_nombre=f.get('acomp_nombre'),
                acompanante_parentesco=f.get('acomp_parentesco'),
                acompanante_telefono=f.get('acomp_telefono'),
                acompanante_telefono_tipo=f.get('acomp_tel_tipo'),
                acompanante_doc_tipo=f.get('acomp_doc_tipo'),
                acompanante_doc_numero=f.get('acomp_doc_numero'),
                acompanante_doc_otro_descripcion=f.get('acomp_doc_otro_desc') if f.get('acomp_doc_tipo') == 'OTRO' else None,
                acompanante_domicilio=f.get('acomp_domicilio'),

                # DENUNCIA (Datos limpios y consistentes)
                denuncia_realizada=denuncia_flag,
                denuncia_institucion_id=institucion_final_id,
                denuncia_institucion_otro=institucion_otro_valido,
                denuncia_profesional_nombre=profesional_nombre_valido,
                denuncia_profesional_cargo=profesional_cargo_valido,
                
                # VULNERACIÓN TEXTO
                vulneracion_otro_texto=vulneracion_otro_valido, # Solo si aplica

                # ESTADO INICIAL
                estado='PENDIENTE_RESCATAR'
            )

            # Agregar relaciones Many-to-Many
            for v_obj in objetos_vulneracion:
                nuevo_caso.vulneraciones.append(v_obj)

            # Guardar
            db.session.add(nuevo_caso)
            db.session.commit()

            # Log
            registrar_log("Ingreso Caso Público", f"Nuevo caso folio: {nuevo_caso.folio_atencion}")
            
            flash("Solicitud ingresada correctamente. Muchas gracias.", "success")
            return redirect(url_for('publico.formulario'))

        except Exception as e:
            db.session.rollback()
            print(f"Error crítico form público: {e}")
            flash("Error interno al procesar la solicitud. Intente nuevamente.", "danger")
            # En caso de error crítico, también devolvemos los datos para no frustrar al usuario
            return render_template('publico/formulario.html', 
                                   recintos=recintos, vulneraciones=vulneraciones, 
                                   ciclos=ciclos, instituciones=instituciones,
                                   datos=request.form)

    # Render GET inicial
    return render_template('publico/formulario.html', 
                           recintos=recintos, vulneraciones=vulneraciones, 
                           ciclos=ciclos, instituciones=instituciones)