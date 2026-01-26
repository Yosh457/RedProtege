import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from flask import url_for

def enviar_correo_reseteo(usuario, token):
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