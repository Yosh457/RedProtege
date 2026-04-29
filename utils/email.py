import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formataddr
from flask import url_for, current_app

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

def enviar_correo_generico(destinatarios, asunto, cuerpo_html, adjunto_path=None, bcc=None):
    """
    Envía un correo utilizando SMTP (Gmail) de forma segura y consistente.

    - 'destinatarios' (To): lista o string. Visible en el correo.
    - 'bcc' (BCC): lista o string. NO visible en el correo (privacidad).
    - Importante: usamos server.send_message(..., to_addrs=...) para controlar
      el "envelope" SMTP y NO depender de headers Bcc.

    Esto evita:
    - exponer correos en envíos masivos
    - depender de que 'send_message' elimine headers Bcc
    """
    remitente = os.getenv("EMAIL_USUARIO")
    contrasena = os.getenv("EMAIL_CONTRASENA")

    # Validación mínima de credenciales
    if not remitente or not contrasena:
        print("ERROR: Faltan credenciales EMAIL_USUARIO / EMAIL_CONTRASENA en .env")
        return False

    # -----------------------------
    # 1) Normalizar inputs a listas
    # -----------------------------
    if destinatarios is None:
        destinatarios = []
    if isinstance(destinatarios, str):
        destinatarios = [destinatarios]

    if bcc is None:
        bcc = []
    if isinstance(bcc, str):
        bcc = [bcc]

    # -------------------------------------------------
    # 2) Limpiar vacíos/None y quitar duplicados (orden)
    # -------------------------------------------------
    destinatarios = [d.strip() for d in destinatarios if d and str(d).strip()]
    bcc = [d.strip() for d in bcc if d and str(d).strip()]

    # Deduplicar manteniendo el orden
    destinatarios = list(dict.fromkeys(destinatarios))
    bcc = list(dict.fromkeys(bcc))

    # Si no hay nadie en To ni Bcc, no tiene sentido enviar
    if not destinatarios and not bcc:
        print("ERROR: Faltan destinatarios (To/Bcc).")
        return False

    # -------------------------------------------------------------
    # 3) Construir el mensaje (headers visibles)
    # -------------------------------------------------------------
    msg = MIMEMultipart()
    msg["Subject"] = asunto
    msg["From"] = formataddr(("RedProtege Notificaciones", remitente))

    # "To" visible: si no hay destinatarios, ponemos el remitente
    # (así el correo no queda con To vacío)
    msg["To"] = ", ".join(destinatarios) if destinatarios else remitente

    # OJO: NO seteamos msg["Bcc"] a propósito.
    # La privacidad la manejamos con "to_addrs" en send_message.

    # Cuerpo HTML
    msg.attach(MIMEText(cuerpo_html, "html"))

    # Adjuntar archivo si corresponde
    if adjunto_path and os.path.exists(adjunto_path):
        try:
            with open(adjunto_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(adjunto_path))
                part["Content-Disposition"] = f'attachment; filename="{os.path.basename(adjunto_path)}"'
                msg.attach(part)
        except Exception as e:
            print(f"Error adjuntando archivo: {e}")

    # -------------------------------------------------------------
    # 4) Enviar: definimos explícitamente el "sobre" (envelope SMTP)
    # -------------------------------------------------------------
    # Los receptores reales son: To visibles + BCC ocultos
    # Si To estaba vacío, el header To quedó como remitente, pero igual
    # garantizamos que el remitente esté en recipients para que el envío tenga
    # un destinatario visible coherente.
    recipients = []
    if destinatarios:
        recipients.extend(destinatarios)
    else:
        recipients.append(remitente)

    if bcc:
        recipients.extend(bcc)

    # Deduplicar recipients por si se repiten
    recipients = list(dict.fromkeys([r for r in recipients if r]))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(remitente, contrasena)

            # MODERNO + CONTROL:
            # - send_message es moderno
            # - to_addrs controla a quién se envía realmente (incluye BCC)
            # - No dependemos del header Bcc (ni lo exponemos)
            server.send_message(
                msg,
                from_addr=remitente,
                to_addrs=recipients
            )

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
    from sqlalchemy import or_
    
    # ✅ FASE 2: Notificar a los Referentes cuyos ciclos incluyan el del caso (M:N)
    # Y a TODOS los usuarios con rol 'Torre Control' globalmente.
    destinatarios_query = Usuario.query.join(Rol).filter(
        Usuario.activo == True,
        Usuario.email.isnot(None),
        Usuario.email != '',
        or_(
            (Rol.nombre == 'Referente') & (Usuario.ciclos.any(id=caso.ciclo_vital_id)),
            Rol.nombre == 'Torre Control'
        )
    ).all()
    
    destinatarios = list(set([u.email.strip() for u in destinatarios_query if u.email and u.email.strip()]))
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

def enviar_aviso_cierre(caso, funcionario_cierre):
    """
    Notifica cierre al referente y al funcionario
    """
    from models import Usuario, Rol
    from sqlalchemy import or_
    
    # Destinatarios: Funcionario que cierra + Referentes del ciclo
    destinatarios = []

    # 1. El funcionario que cerró
    if funcionario_cierre.email:
        destinatarios.append(funcionario_cierre.email.strip())
    
    # 2. 🔥 ARQUITECTURA CORREGIDA: Referentes del ciclo + Torre Control
    # ✅ FASE 2: Referentes del ciclo (M:N) + Torre Control
    monitores = Usuario.query.join(Rol).filter(
        Usuario.activo == True,
        Usuario.email.isnot(None),
        Usuario.email != '',
        or_(
            (Rol.nombre == 'Referente') & (Usuario.ciclos.any(id=caso.ciclo_vital_id)),
            Rol.nombre == 'Torre Control'
        )
    ).all()
    
    for m in monitores:
        if m.email and m.email.strip():
            destinatarios.append(m.email.strip())
    
    destinatarios = list(set(destinatarios)) # Únicos

    url = url_for('casos.ver_caso', id=caso.id, _external=True)

    contenido = f"""
        <p>El caso <strong>#{caso.folio_atencion}</strong> ha sido cerrado exitosamente.</p>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #28a745; margin: 20px 0; border-radius: 4px;">
            <p style="margin: 5px 0;"><strong>Paciente:</strong> {caso.origen_nombres} {caso.origen_apellidos}</p>
            <p style="margin: 5px 0;"><strong>Cerrado por:</strong> {funcionario_cierre.nombre_completo}</p>
            <p style="margin: 5px 0;"><strong>Fecha Cierre:</strong> {caso.fecha_cierre.strftime('%d/%m/%Y %H:%M')}</p>
        </div>
        
        <p>El Acta de Cierre está disponible para su descarga dentro del sistema.</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{url}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Ver Caso en Sistema
            </a>
        </div>
    """
    html = get_email_template(f"Caso Cerrado #{caso.folio_atencion}", contenido)
    return enviar_correo_generico(destinatarios, f"Caso Cerrado #{caso.folio_atencion}", html)

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

def enviar_reporte_estadistico_masivo(destinatarios_bcc, data):
    """
    Genera el reporte HTML y lo envía de forma masiva y PRIVADA:

    - To (visible): el remitente/sistema (EMAIL_USUARIO)
    - Receptores reales: van en BCC, pero controlados por to_addrs (envelope SMTP)
      para no depender del header Bcc.

    'destinatarios_bcc' debe ser lista de emails (o string, pero ideal lista).
    'data' debe traer:
      - data['global'] = {total, pendientes, seguimiento, cerrados}
      - data['inscritos'] = [{nombre,total,pendientes,seguimiento,cerrados}, ...]
      - data['notificacion'] = [{nombre,total,pct}, ...]
    """
    remitente = os.getenv("EMAIL_USUARIO")
    if not remitente:
        print("ERROR: EMAIL_USUARIO no está configurado en .env")
        return False

    stats = data.get('global', {}) or {}
    inscritos = data.get('inscritos', []) or []
    notificacion = data.get('notificacion', []) or []

    # Fecha en español sin locale del sistema
    meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }
    now = datetime.now()
    fecha_larga = f"{now.day:02d} de {meses[now.month]}, {now.year}"
    fecha_corta = now.strftime("%d/%m/%Y")

    # Helper % seguro
    def pct(val, total):
        return round((val / total * 100), 1) if total and total > 0 else 0
    # Datos
    total = int(stats.get("total", 0) or 0)
    pendientes = int(stats.get("pendientes", 0) or 0)
    seguimiento = int(stats.get("seguimiento", 0) or 0)
    cerrados = int(stats.get("cerrados", 0) or 0)

    pct_p = pct(pendientes, total)
    pct_s = pct(seguimiento, total)
    pct_c = pct(cerrados, total)

    # -------------------------
    # Construcción tabla inscritos
    # -------------------------
    rows_inscritos = ""
    for item in inscritos:
        rows_inscritos += f"""
        <tr>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; color:#374151;">{item.get('nombre','')}</td>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; text-align:center; font-weight:700;">{int(item.get('total',0) or 0)}</td>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; text-align:center; color:#D97706; font-weight:700;">{int(item.get('pendientes',0) or 0)}</td>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; text-align:center; color:#2563EB; font-weight:700;">{int(item.get('seguimiento',0) or 0)}</td>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; text-align:center; color:#059669; font-weight:700;">{int(item.get('cerrados',0) or 0)}</td>
        </tr>
        """

    # -------------------------
    # Construcción tabla notificación
    # -------------------------
    rows_notif = ""
    total_notif = sum(int(x.get('total', 0) or 0) for x in notificacion) or 0
    for item in notificacion:
        rows_notif += f"""
        <tr>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; color:#374151;">{item.get('nombre','')}</td>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; text-align:right; font-weight:700;">{int(item.get('total',0) or 0)}</td>
            <td style="padding:10px; border-bottom:1px solid #E5E7EB; text-align:right; color:#6B7280;">{float(item.get('pct',0) or 0)}%</td>
        </tr>
        """

    rows_notif += f"""
        <tr style="background-color:#F9FAFB; font-weight:800;">
            <td style="padding:10px; text-align:right; color:#111827;">Total Notificaciones Registradas</td>
            <td style="padding:10px; text-align:right; color:#111827;">{total_notif}</td>
            <td style="padding:10px; text-align:right; color:#111827;">100%</td>
        </tr>
    """

    contenido = f"""
    <div style="font-family: 'Segoe UI', Helvetica, Arial, sans-serif; color:#111827; line-height:1.6;">

        <p style="margin:0 0 14px; font-size:15px;">Estimado equipo,</p>
        <p style="margin:0 0 22px; font-size:15px; color:#374151;">
            Compartimos el <strong>Resumen de Gestión</strong> actualizado al día de la fecha
            (<strong>{fecha_larga}</strong>).
            A continuación se detallan las métricas clave y el estado actual de los casos.
        </p>

        <h3 style="margin:0 0 14px; font-size:16px; border-bottom:2px solid #E5E7EB; padding-bottom:8px;">
            📊 Resumen Global
        </h3>

        <!-- KPIs -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 26px;">
            <tr>
                <td width="25%" style="padding-right:8px;">
                    <div style="background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:14px; text-align:center;">
                        <div style="font-size:28px; font-weight:800; color:#111827; line-height:1;">{total}</div>
                        <div style="font-size:11px; font-weight:700; color:#6B7280; text-transform:uppercase; letter-spacing:.6px; margin-top:6px;">Total</div>
                    </div>
                </td>
                <td width="25%" style="padding:0 8px;">
                    <div style="background:#FFFBEB; border:1px solid #FEF3C7; border-radius:10px; padding:14px; text-align:center;">
                        <div style="font-size:28px; font-weight:800; color:#D97706; line-height:1;">{pendientes}</div>
                        <div style="font-size:11px; font-weight:700; color:#D97706; text-transform:uppercase; letter-spacing:.6px; margin-top:6px;">Pendientes</div>
                    </div>
                </td>
                <td width="25%" style="padding:0 8px;">
                    <div style="background:#EFF6FF; border:1px solid #DBEAFE; border-radius:10px; padding:14px; text-align:center;">
                        <div style="font-size:28px; font-weight:800; color:#2563EB; line-height:1;">{seguimiento}</div>
                        <div style="font-size:11px; font-weight:700; color:#2563EB; text-transform:uppercase; letter-spacing:.6px; margin-top:6px;">Seguimiento</div>
                    </div>
                </td>
                <td width="25%" style="padding-left:8px;">
                    <div style="background:#ECFDF5; border:1px solid #D1FAE5; border-radius:10px; padding:14px; text-align:center;">
                        <div style="font-size:28px; font-weight:800; color:#059669; line-height:1;">{cerrados}</div>
                        <div style="font-size:11px; font-weight:700; color:#059669; text-transform:uppercase; letter-spacing:.6px; margin-top:6px;">Cerrados</div>
                    </div>
                </td>
            </tr>
        </table>

        <h3 style="margin:0 0 14px; font-size:16px; border-bottom:2px solid #E5E7EB; padding-bottom:8px;">
            🕒 Distribución de Casos
        </h3>

        <!-- Pendiente -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 14px;">
            <tr>
                <td style="padding:0 0 6px;">
                    <div style="font-size:14px; font-weight:700; color:#374151;">Pendiente Rescatar</div>
                    <div style="font-size:12px; color:#6B7280;">Acción requerida inmediata</div>
                </td>
                <td align="right" style="padding:0 0 6px;">
                    <div style="font-size:14px; font-weight:800; color:#D97706;">{pendientes} Casos</div>
                    <div style="font-size:11px; color:#9CA3AF;">{pct_p}% del total</div>
                </td>
            </tr>
            <tr>
                <td colspan="2">
                    <div style="background:#F3F4F6; height:10px; border-radius:999px; overflow:hidden;">
                        <div style="background:#F59E0B; width:{pct_p}%; height:10px; border-radius:999px;"></div>
                    </div>
                </td>
            </tr>
        </table>

        <!-- Seguimiento -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 14px;">
            <tr>
                <td style="padding:0 0 6px;">
                    <div style="font-size:14px; font-weight:700; color:#374151;">En Seguimiento</div>
                    <div style="font-size:12px; color:#6B7280;">En proceso de gestión</div>
                </td>
                <td align="right" style="padding:0 0 6px;">
                    <div style="font-size:14px; font-weight:800; color:#2563EB;">{seguimiento} Casos</div>
                    <div style="font-size:11px; color:#9CA3AF;">{pct_s}% del total</div>
                </td>
            </tr>
            <tr>
                <td colspan="2">
                    <div style="background:#F3F4F6; height:10px; border-radius:999px; overflow:hidden;">
                        <div style="background:#3B82F6; width:{pct_s}%; height:10px; border-radius:999px;"></div>
                    </div>
                </td>
            </tr>
        </table>

        <!-- Cerrados -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 22px;">
            <tr>
                <td style="padding:0 0 6px;">
                    <div style="font-size:14px; font-weight:700; color:#374151;">Cerrados</div>
                    <div style="font-size:12px; color:#6B7280;">Gestión completada exitosamente</div>
                </td>
                <td align="right" style="padding:0 0 6px;">
                    <div style="font-size:14px; font-weight:800; color:#059669;">{cerrados} Casos</div>
                    <div style="font-size:11px; color:#9CA3AF;">{pct_c}% del total</div>
                </td>
            </tr>
            <tr>
                <td colspan="2">
                    <div style="background:#F3F4F6; height:10px; border-radius:999px; overflow:hidden;">
                        <div style="background:#10B981; width:{pct_c}%; height:10px; border-radius:999px;"></div>
                    </div>
                </td>
            </tr>
        </table>

        <!-- TABLA INSCRITOS -->
        <h3 style="margin:0 0 12px; font-size:16px; border-bottom:2px solid #E5E7EB; padding-bottom:8px; text-align:center;">
            Resumen por Recinto (Inscritos)
        </h3>

        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E5E7EB; border-radius:10px; overflow:hidden; font-size:12px; margin-bottom:22px;">
            <tr style="background:#EFF6FF; color:#1D4ED8;">
                <th style="padding:10px; text-align:left;">Recinto</th>
                <th style="padding:10px; text-align:center;">Total Casos</th>
                <th style="padding:10px; text-align:center;">Pendientes</th>
                <th style="padding:10px; text-align:center;">En Seguimiento</th>
                <th style="padding:10px; text-align:center;">Cerrados</th>
            </tr>
            {rows_inscritos}
        </table>

        <!-- TABLA NOTIFICACIÓN -->
        <h3 style="margin:0 0 12px; font-size:16px; border-bottom:2px solid #E5E7EB; padding-bottom:8px; text-align:center;">
            Resumen de Notificaciones (Origen)
        </h3>

        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E5E7EB; border-radius:10px; overflow:hidden; font-size:12px; margin-bottom:22px;">
            <tr style="background:#EFF6FF; color:#1D4ED8;">
                <th style="padding:10px; text-align:left;">Origen de Notificación</th>
                <th style="padding:10px; text-align:right;">Total Notificaciones</th>
                <th style="padding:10px; text-align:right;">Porcentaje</th>
            </tr>
            {rows_notif}
        </table>

        <!-- CTA -->
        <div style="text-align: center; margin-top: 26px; padding-top: 18px; border-top: 1px solid #E5E7EB;">
            <a href="{url_for('auth.login', _external=True)}"
               style="display: inline-block; background-color: #275C80; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: 600;">
                Ir al Dashboard →
            </a>
        </div>

    </div>
    """

    html = get_email_template(f"Reporte de Gestión - {fecha_corta}", contenido)

    # Envío masivo PRIVADO:
    # - To: el sistema (remitente)
    # - BCC: todos los usuarios
    return enviar_correo_generico(
        destinatarios=[remitente],  # visible en To
        asunto=f"Reporte de Gestión RedProtege - {fecha_corta}",
        cuerpo_html=html,
        bcc=destinatarios_bcc
    )

def enviar_aviso_subrogancia(titular, subrogante, es_activacion=True):
    """
    Notifica al SUBROGANTE por correo cuando:
    - es_activacion=True: fue designado como subrogante del TITULAR
    - es_activacion=False: se revoca/finaliza la subrogancia

    Requisitos:
    - titular y subrogante: objetos Usuario (con nombre_completo, email, ciclo_asignado opcional)
    """
    # Validación mínima
    if not subrogante or not getattr(subrogante, "email", None):
        print("ERROR: Subrogante sin email. No se puede notificar.")
        return False

    # Títulos / textos dinámicos
    tipo = "Activación" if es_activacion else "Finalización"
    color = "#275C80" if es_activacion else "#6B7280"  # azul institucional vs gris

    nombre_titular = getattr(titular, "nombre_completo", "Titular")
    nombre_subrogante = getattr(subrogante, "nombre_completo", "Usuario")

    # ✅ FASE 2: Listar todos los nombres de los ciclos del titular
    ciclo_titular = ", ".join([c.nombre for c in titular.ciclos]) if titular.ciclos else "Global/Sin asignar"

    # Link a la bandeja
    url_bandeja = url_for("casos.index", _external=True)

    # Mensajes
    if es_activacion:
        intro = f"""
            <p>Hola <strong>{nombre_subrogante}</strong>,</p>
            <p>
                Se te informa que el referente <strong>{nombre_titular}</strong> te ha designado como su
                <strong>Subrogante</strong>.
            </p>
        """
        detalle = """
            <p>
                A partir de ahora, tendrás acceso para visualizar y gestionar los casos del ciclo del titular
                desde tu bandeja.
            </p>
        """
    else:
        intro = f"""
            <p>Hola <strong>{nombre_subrogante}</strong>,</p>
            <p>
                Se te informa que la subrogancia del referente <strong>{nombre_titular}</strong> ha finalizado.
            </p>
        """
        detalle = """
            <p>
                Desde este momento, ya no tendrás acceso a los casos del ciclo del titular.
            </p>
        """

    contenido = f"""
        {intro}

        <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid {color}; margin: 20px 0; border-radius: 6px;">
            <p style="margin: 6px 0;"><strong>Acción:</strong> {tipo} de Subrogancia</p>
            <p style="margin: 6px 0;"><strong>Titular:</strong> {nombre_titular}</p>
            <p style="margin: 6px 0;"><strong>Ciclo del titular:</strong> {ciclo_titular}</p>
            <p style="margin: 6px 0;"><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        </div>

        {detalle}

        <div style="text-align: center; margin: 30px 0;">
            <a href="{url_bandeja}" style="background-color: #275c80; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                Ir a Bandeja de Casos
            </a>
        </div>
    """

    html = get_email_template(f"Aviso de Subrogancia - {tipo}", contenido)
    asunto = f"RedProtege: {tipo} de Subrogancia"

    # Enviar al subrogante (To visible)
    return enviar_correo_generico(subrogante.email, asunto, html)