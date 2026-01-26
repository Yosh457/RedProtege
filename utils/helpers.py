from datetime import datetime
import pytz
from flask_login import current_user

def obtener_hora_chile():
    """Retorna la fecha y hora actual en Santiago de Chile."""
    cl_tz = pytz.timezone('America/Santiago')
    return datetime.now(cl_tz)

def registrar_log(accion, detalles, usuario=None):
    """
    Registra un evento en la tabla 'logs' del sistema.
    Usa Lazy Import para evitar ciclos con models.py
    """
    from models import db, Log  # ✅ Importación diferida para evitar ciclos

    try:
        user_id = None
        user_nombre = "Sistema/Anónimo"

        # Si pasamos un usuario explícito (ej: login exitoso)
        if usuario:
            user_id = usuario.id
            user_nombre = usuario.nombre_completo
        # Si no, intentamos sacar del current_user
        elif current_user and current_user.is_authenticated:
            user_id = current_user.id
            user_nombre = current_user.nombre_completo

        nuevo_log = Log(
            usuario_id=user_id,
            usuario_nombre=user_nombre,
            accion=accion,
            detalles=detalles,
            timestamp=obtener_hora_chile()
        )
        db.session.add(nuevo_log)
        db.session.commit()
    except Exception as e:
        # En caso de error de DB, lo imprimimos en consola para no romper el flujo
        print(f"Error al registrar log: {e}")

def es_rut_valido(rut):
    """
    Validación básica de RUT chileno.
    Elimina puntos y guiones y verifica longitud mínima.
    """
    if not rut: return False
    rut = rut.replace(".", "").replace("-", "").upper()
    if len(rut) < 8: return False
    return True