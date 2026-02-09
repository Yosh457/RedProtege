import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formataddr
from flask import url_for

# --- PLANTILLA BASE HTML PARA CORREOS (DISEÑO UNIFICADO) ---
def get_email_template(titulo, contenido):
    return f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #333; max-width: 600px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; margin: 0 auto;">
        <div style="background-color: #275c80; padding: 20px; text-align: center;">
            <h2 style="color: white; margin: 0; font-size: 20px;">{titulo}</h2>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
            {contenido}
        </div>
        <div style="background-color: #f1f1f1; padding: 15px; text-align: center; font-size: 11px; color: #888; border-top: 1px solid #eee;">
            <p style="margin: 0;">Red de Atención Primaria de Salud Municipal - Alto Hospicio</p>
            <p style="margin: 5px 0 0;">Este es un mensaje automático, por favor no responder.</p>
        </div>
    </div>
    """

def enviar_correo_generico(destinatarios, asunto, cuerpo_html, adjunto_path=None):
    remitente = os.getenv("EMAIL_USUARIO")
    contrasena = os.getenv("EMAIL_CONTRASENA")
    
    if not remitente or not contrasena or not destinatarios:
        print("ERROR: Faltan credenciales o destinatarios.")
        return False

    if isinstance(destinatarios, str):
        destinatarios = [destinatarios]

    msg = MIMEMultipart()
    msg['Subject'] = asunto
    msg['From'] = formataddr(('RedProtege Notificaciones', remitente))
    msg['To'] = ", ".join(destinatarios)

    msg.attach(MIMEText(cuerpo_html, 'html'))

    # Adjuntar archivo si existe (para el PDF de cierre)
    if adjunto_path and os.path.exists(adjunto_path):
        try:
            with open(adjunto_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(adjunto_path))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(adjunto_path)}"'
                msg.attach(part)
        except Exception as e:
            print(f"Error adjuntando archivo: {e}")

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(remitente, contrasena)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error enviando correo '{asunto}': {e}")
        return False

# --- FUNCIONES ESPECÍFICAS DE NOTIFICACIÓN ---

def enviar_correo_reseteo(usuario, token):
    url = url_for('auth.resetear_clave', token=token, _external=True)
    contenido = f"""
        <p>Hola <strong>{usuario.nombre_completo}</strong>,</p>
        <p>Hemos recibido una solicitud para restablecer tu contraseña.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{url}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Restablecer Contraseña
            </a>
        </div>
        <p style="font-size: 13px; color: #666;">El enlace expirará en 1 hora.</p>
    """
    html = get_email_template("Recuperación de Contraseña", contenido)
    enviar_correo_generico(usuario.email, 'Restablecimiento de Contraseña - RedProtege', html)

def enviar_aviso_asignacion(funcionario, caso, asignador):
    url = url_for('casos.ver_caso', id=caso.id, _external=True)
    recinto = caso.recinto_notifica.nombre if caso.recinto_notifica else "No especificado"
    if caso.recinto_otro_texto: recinto += f" ({caso.recinto_otro_texto})"
    
    fecha_fmt = caso.fecha_atencion.strftime('%d/%m/%Y') if caso.fecha_atencion else "S/I"
    
    contenido = f"""
        <p>Hola <strong>{funcionario.nombre_completo}</strong>,</p>
        <p>El referente <strong>{asignador.nombre_completo}</strong> te ha asignado un nuevo caso.</p>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #275c80; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 5px 0;"><strong>Folio:</strong> {caso.folio_atencion}</p>
            <p style="margin: 5px 0;"><strong>Paciente:</strong> {caso.origen_nombres} {caso.origen_apellidos}</p>
            <p style="margin: 5px 0;"><strong>Fecha Atención:</strong> {fecha_fmt}</p>
            <p style="margin: 5px 0;"><strong>Recinto:</strong> {recinto}</p>
        </div>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{url}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Ver Detalle del Caso
            </a>
        </div>
    """
    html = get_email_template(f"Nuevo Caso Asignado #{caso.folio_atencion}", contenido)
    return enviar_correo_generico(funcionario.email, f"Nuevo Caso Asignado #{caso.folio_atencion}", html)

def enviar_aviso_nuevo_caso(caso, usuario_ingreso):
    # Lazy Import para evitar ciclos
    from models import Usuario, Rol
    
    referentes = Usuario.query.join(Rol).filter(Rol.nombre == 'Referente', Usuario.activo == True).filter(
        (Usuario.ciclo_asignado_id == caso.ciclo_vital_id) | (Usuario.ciclo_asignado_id == None)
    ).all()
    
    destinatarios = list(set([u.email for u in referentes if u.email]))
    if not destinatarios: return

    url = url_for('casos.ver_caso', id=caso.id, _external=True)
    fecha_fmt = caso.fecha_atencion.strftime('%d/%m/%Y') if caso.fecha_atencion else "S/I"
    
    contenido = f"""
        <p>Se ha ingresado una nueva solicitud al sistema que requiere revisión.</p>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #d9534f; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 5px 0;"><strong>Folio:</strong> {caso.folio_atencion}</p>
            <p style="margin: 5px 0;"><strong>Ciclo Vital:</strong> {caso.ciclo_vital.nombre}</p>
            <p style="margin: 5px 0;"><strong>Fecha Atención:</strong> {fecha_fmt}</p>
            <p style="margin: 5px 0;"><strong>Ingresado por:</strong> {usuario_ingreso.nombre_completo}</p>
        </div>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{url}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Ir a Bandeja de Casos
            </a>
        </div>
    """
    html = get_email_template(f"Nuevo Caso Ingresado #{caso.folio_atencion}", contenido)
    enviar_correo_generico(destinatarios, f"Alerta: Nuevo Caso #{caso.folio_atencion}", html)

def enviar_aviso_cierre(caso, funcionario_cierre, pdf_path=None):
    """
    Notifica cierre al referente y al funcionario. Adjunta PDF si existe.
    """
    from models import Usuario, Rol
    
    # Destinatarios: Funcionario que cierra + Referentes del ciclo
    destinatarios = []
    if funcionario_cierre.email:
        destinatarios.append(funcionario_cierre.email)
    
    referentes = Usuario.query.join(Rol).filter(Rol.nombre == 'Referente', Usuario.activo == True).filter(
        (Usuario.ciclo_asignado_id == caso.ciclo_vital_id) | (Usuario.ciclo_asignado_id == None)
    ).all()
    
    for r in referentes:
        if r.email: destinatarios.append(r.email)
    
    destinatarios = list(set(destinatarios)) # Únicos

    url = url_for('casos.ver_caso', id=caso.id, _external=True)

    contenido = f"""
        <p>El caso <strong>#{caso.folio_atencion}</strong> ha sido cerrado exitosamente.</p>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #28a745; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 5px 0;"><strong>Paciente:</strong> {caso.origen_nombres} {caso.origen_apellidos}</p>
            <p style="margin: 5px 0;"><strong>Cerrado por:</strong> {funcionario_cierre.nombre_completo}</p>
            <p style="margin: 5px 0;"><strong>Fecha Cierre:</strong> {caso.fecha_cierre.strftime('%d/%m/%Y %H:%M')}</p>
        </div>
        
        <p>Se adjunta el Acta de Cierre en formato PDF con el detalle de la gestión.</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{url}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Ver Caso en Sistema
            </a>
        </div>
    """
    html = get_email_template(f"Caso Cerrado #{caso.folio_atencion}", contenido)
    return enviar_correo_generico(destinatarios, f"Caso Cerrado #{caso.folio_atencion}", html, adjunto_path=pdf_path)

def enviar_credenciales_nuevo_usuario(usuario, password_texto_plano):
    """
    Envía correo de bienvenida con credenciales al nuevo usuario.
    """
    url_login = url_for('auth.login', _external=True)
    
    contenido = f"""
        <p>Hola <strong>{usuario.nombre_completo}</strong>,</p>
        <p>Bienvenido al Sistema <strong>RedProtege</strong>. Se ha creado tu cuenta de acceso.</p>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #275c80; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 5px 0;"><strong>Usuario (Email):</strong> {usuario.email}</p>
            <p style="margin: 5px 0;"><strong>Contraseña Temporal:</strong> {password_texto_plano}</p>
        </div>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{url_login}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Ingresar al Sistema
            </a>
        </div>
        
        <p style="color: #d9534f; font-size: 13px;"><strong>Importante:</strong> Por seguridad, el sistema te solicitará cambiar esta contraseña al iniciar sesión por primera vez.</p>
    """
    
    html = get_email_template("Bienvenido a RedProtege", contenido)
    return enviar_correo_generico(usuario.email, "Bienvenido - Credenciales de Acceso", html)