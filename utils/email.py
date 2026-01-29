import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from flask import url_for

def enviar_correo_reseteo(usuario, token):
    """Envía correo de recuperación de contraseña."""
    remitente = os.getenv("EMAIL_USUARIO")
    contrasena = os.getenv("EMAIL_CONTRASENA")
    
    if not remitente or not contrasena:
        print("ERROR: Credenciales de correo faltantes en .env")
        return

    msg = MIMEMultipart()
    msg['Subject'] = 'Restablecimiento de Contraseña - RedProtege'
    msg['From'] = formataddr(('RedProtege Salud', remitente))
    msg['To'] = usuario.email

    url_reseteo = url_for('auth.resetear_clave', token=token, _external=True)

    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #275c80;">Recuperación de Contraseña</h2>
        <p>Hola <strong>{usuario.nombre_completo}</strong>,</p>
        <p>Hemos recibido una solicitud para restablecer tu contraseña en el sistema <strong>RedProtege</strong>.</p>
        <p style="margin: 20px 0;">
            <a href="{url_reseteo}" style="background-color: #275c80; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Restablecer mi contraseña
            </a>
        </p>
        <p>Si no solicitaste esto, puedes ignorar este correo. El enlace expirará en 1 hora.</p>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <p style="font-size: 12px; color: #888;">Unidad de TICs - Departamento de Salud</p>
    </div>
    """
    msg.attach(MIMEText(cuerpo_html, 'html'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(remitente, contrasena)
            server.send_message(msg)
    except Exception as e:
        print(f"Error enviando correo: {e}")

def enviar_aviso_asignacion(funcionario, caso, asignador):
    """
    Envía notificación de asignación de caso a un funcionario.
    Retorna True si fue exitoso, False si falló (Best Effort).
    """
    remitente = os.getenv("EMAIL_USUARIO")
    contrasena = os.getenv("EMAIL_CONTRASENA")
    
    if not remitente or not contrasena or not funcionario.email:
        print("ERROR: Faltan credenciales o el funcionario no tiene email.")
        return False

    msg = MIMEMultipart()
    msg['Subject'] = f'Nuevo Caso Asignado #{caso.folio_atencion or caso.id} - RedProtege'
    msg['From'] = formataddr(('RedProtege Notificaciones', remitente))
    msg['To'] = funcionario.email

    # Link al caso (External para que funcione desde correo)
    url_caso = url_for('casos.ver_caso', id=caso.id, _external=True)

    # Lógica de Recinto (Mostrar nombre catálogo o texto "Otro")
    recinto_texto = caso.recinto_notifica.nombre if caso.recinto_notifica else "No especificado"
    if caso.recinto_otro_texto:
        recinto_texto = f"{recinto_texto} ({caso.recinto_otro_texto})"

    # Formateo de fechas para el correo
    fecha_fmt = caso.fecha_atencion.strftime('%d/%m/%Y') if caso.fecha_atencion else "S/I"
    hora_fmt = caso.hora_atencion.strftime('%H:%M') if caso.hora_atencion else "S/I"

    cuerpo_html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #333; max-width: 600px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #275c80; padding: 20px; text-align: center;">
            <h2 style="color: white; margin: 0;">Nuevo Caso Asignado</h2>
        </div>
        <div style="padding: 20px;">
            <p>Hola <strong>{funcionario.nombre_completo}</strong>,</p>
            <p>El referente <strong>{asignador.nombre_completo}</strong> te ha asignado un nuevo caso para gestión.</p>
            
            <div style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid #275c80; margin: 20px 0;">
                <p style="margin: 5px 0;"><strong>Folio Atención:</strong> {caso.folio_atencion or 'S/I'}</p>
                <p style="margin: 5px 0;"><strong>Paciente:</strong> {caso.origen_nombres} {caso.origen_apellidos}</p>
                <p style="margin: 5px 0;"><strong>Ciclo Vital:</strong> {caso.ciclo_vital.nombre}</p>
                <p style="margin: 5px 0;"><strong>Recinto Origen:</strong> {recinto_texto}</p>
                <p style="margin: 5px 0;"><strong>Fecha Atención:</strong> {fecha_fmt} a las {hora_fmt}</p>
            </div>

            <p style="text-align: center; margin-top: 30px;">
                <a href="{url_caso}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Ver Detalle del Caso
                </a>
            </p>
            <p style="font-size: 13px; color: #666; margin-top: 30px;">
                Por favor, ingresa a la plataforma para gestionar y realizar el seguimiento correspondiente.
            </p>
        </div>
        <div style="background-color: #f1f1f1; padding: 10px; text-align: center; font-size: 11px; color: #888;">
            Red de Atención Primaria de Salud Municipal - Alto Hospicio
        </div>
    </div>
    """
    msg.attach(MIMEText(cuerpo_html, 'html'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(remitente, contrasena)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error enviando notificación asignación: {e}")
        return False
    
def enviar_aviso_nuevo_caso(caso, usuario_ingreso):
    """
    Envía aviso a los Referentes del ciclo correspondiente Y a los Globales.
    Usa Lazy Import para evitar ciclos.
    """
    from models import Usuario, Rol # ✅ Lazy Import Correcto

    remitente = os.getenv("EMAIL_USUARIO")
    contrasena = os.getenv("EMAIL_CONTRASENA")
    
    if not remitente or not contrasena: return

    # Buscar referentes:
    # 1. Que sean del ciclo del caso
    # 2. O que sean Globales (ciclo_asignado_id IS NULL)
    referentes = Usuario.query.join(Rol).filter(
        Rol.nombre == 'Referente',
        Usuario.activo == True
    ).filter(
        (Usuario.ciclo_asignado_id == caso.ciclo_vital_id) | (Usuario.ciclo_asignado_id == None)
    ).all()

    if not referentes: return

    destinatarios = [u.email for u in referentes if u.email]
    if not destinatarios: return

    # Armar lista única de emails (set) para no duplicar si hubiera lógica compleja
    destinatarios = list(set(destinatarios))

    # Link al caso
    url_caso = url_for('casos.ver_caso', id=caso.id, _external=True)

    msg = MIMEMultipart()
    msg['Subject'] = f'Nuevo Caso Ingresado #{caso.folio_atencion} - RedProtege'
    msg['From'] = formataddr(('RedProtege Alertas', remitente))
    msg['To'] = ", ".join(destinatarios)

    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; color: #333; border: 1px solid #ddd; padding: 20px; max-width: 600px;">
        <h2 style="color: #275c80; margin-top: 0;">Nuevo Caso Disponible</h2>
        <p>Se ha ingresado una nueva solicitud que requiere revisión.</p>
        
        <ul style="background: #f9f9f9; padding: 15px 20px; list-style: none;">
            <li><strong>Folio Atención:</strong> {caso.folio_atencion}</li>
            <li><strong>Ciclo Vital:</strong> {caso.ciclo_vital.nombre}</li>
            <li><strong>Fecha Atención:</strong> {caso.fecha_atencion.strftime('%d/%m/%Y')}</li>
            <li><strong>Ingresado por:</strong> {caso.ingresado_por_nombre} ({usuario_ingreso.nombre_completo})</li>
        </ul>

        <p style="text-align: center; margin-top: 25px;">
            <a href="{url_caso}" style="background-color: #275c80; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Ir a Bandeja de Casos
            </a>
        </p>
    </div>
    """
    msg.attach(MIMEText(cuerpo_html, 'html'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(remitente, contrasena)
            server.send_message(msg)
            print(f"Aviso enviado a {len(destinatarios)} referentes.")
    except Exception as e:
        print(f"Error enviando aviso referente: {e}")