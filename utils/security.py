"""Tokens de enlace y validación centralizada (instantes UTC sin tz para MySQL DATETIME)."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

ACTIVACION_HORAS = 24
RECUPERACION_HORAS = 1

def ahora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def generar_token(horas):
    token = secrets.token_urlsafe(32)
    return token, hash_token(token), ahora_utc() + timedelta(hours=horas)

def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def password_valida(password, confirmar):
    if not isinstance(password, str) or not isinstance(confirmar, str):
        return False
    return (password == confirmar and len(password) >= 8
            and bool(re.search(r'[A-Z]', password))
            and bool(re.search(r'[0-9]', password)))