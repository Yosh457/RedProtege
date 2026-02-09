from datetime import datetime
import pytz
from flask_login import current_user
import re
from itertools import cycle

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

def es_rut_valido(rut: str) -> bool:
    """
    Valida un RUT chileno usando el algoritmo Módulo 11.
    Acepta formatos: 12.345.678-9, 12345678-9, 123456789 (sin guion también).
    """
    if not rut:
        return False

    # 1) Limpieza
    rut = rut.replace(".", "").replace("-", "").upper().strip()

    # 2) Formato: 7 u 8 dígitos + DV (0-9 o K)
    if not re.match(r"^\d{7,8}[0-9K]$", rut):
        return False

    cuerpo = rut[:-1]
    dv_ingresado = rut[-1]

    try:
        revertido = map(int, reversed(cuerpo))
        factors = cycle(range(2, 8))
        s = sum(d * f for d, f in zip(revertido, factors))
        res = (-s) % 11  # 0..10

        if res == 10:
            dv_calculado = "K"
        else:
            dv_calculado = str(res)  # 0..9

        return dv_ingresado == dv_calculado

    except (ValueError, TypeError):
        return False
    
def safe_int(value):
    """Ayuda a convertir a int de forma segura, retornando None si falla o es vacío."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None