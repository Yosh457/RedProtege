from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

db = SQLAlchemy()

def obtener_hora_chile():
    cl_tz = pytz.timezone('America/Santiago')
    return datetime.now(cl_tz)

# --- CATÁLOGOS ---

class Rol(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    usuarios = db.relationship('Usuario', back_populates='rol')

class CatalogoCiclo(db.Model):
    __tablename__ = 'catalogo_ciclos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    rango_descripcion = db.Column(db.String(100))
    usuarios = db.relationship('Usuario', back_populates='ciclo_asignado')
    casos = db.relationship('Caso', back_populates='ciclo_vital')

# --- USUARIOS & SISTEMA ---

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre_completo = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_chile)
    
    cambio_clave_requerido = db.Column(db.Boolean, default=False, nullable=False)
    reset_token = db.Column(db.String(32), nullable=True)
    reset_token_expiracion = db.Column(db.DateTime, nullable=True)

    # Relaciones e Índices
    rol_id = db.Column(db.Integer, db.ForeignKey('roles.id'), index=True)
    rol = db.relationship('Rol', back_populates='usuarios')
    
    ciclo_asignado_id = db.Column(db.Integer, db.ForeignKey('catalogo_ciclos.id'), index=True, nullable=True)
    ciclo_asignado = db.relationship('CatalogoCiclo', back_populates='usuarios')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Log(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=obtener_hora_chile, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    usuario_nombre = db.Column(db.String(255))
    accion = db.Column(db.String(255), nullable=False)
    detalles = db.Column(db.Text)

# --- NEGOCIO: CASOS ---

class Caso(db.Model):
    __tablename__ = 'casos'
    id = db.Column(db.Integer, primary_key=True)
    
    # Origen (Inmutable)
    origen_nombres = db.Column(db.String(100), nullable=False)
    origen_apellidos = db.Column(db.String(100), nullable=False)
    origen_rut = db.Column(db.String(20), nullable=False, index=True)
    origen_telefono = db.Column(db.String(20))
    origen_fecha_nacimiento = db.Column(db.Date)
    origen_relato = db.Column(db.Text, nullable=False)
    
    # Trazabilidad
    fecha_ingreso = db.Column(db.DateTime, default=obtener_hora_chile)
    updated_at = db.Column(db.DateTime, default=obtener_hora_chile, onupdate=obtener_hora_chile)

    # Clasificación
    ciclo_vital_id = db.Column(db.Integer, db.ForeignKey('catalogo_ciclos.id'), nullable=False)
    ciclo_vital = db.relationship('CatalogoCiclo', back_populates='casos')

    # Gestión
    observaciones_gestion = db.Column(db.Text)
    acciones_realizadas = db.Column(db.Text)

    # Estados
    estado = db.Column(db.Enum('PENDIENTE_RESCATAR', 'EN_SEGUIMIENTO', 'CERRADO'), 
                       default='PENDIENTE_RESCATAR', nullable=False)
    
    # Bloqueo
    bloqueado = db.Column(db.Boolean, default=False)
    bloqueado_at = db.Column(db.DateTime)
    bloqueado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    
    fecha_cierre = db.Column(db.DateTime)
    usuario_cierre_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))

    auditorias = db.relationship('AuditoriaCaso', back_populates='caso', cascade="all, delete-orphan")

class AuditoriaCaso(db.Model):
    __tablename__ = 'auditoria_casos'
    id = db.Column(db.Integer, primary_key=True)
    caso_id = db.Column(db.Integer, db.ForeignKey('casos.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    fecha_movimiento = db.Column(db.DateTime, default=obtener_hora_chile)
    
    accion = db.Column(db.String(50), nullable=False)
    motivo = db.Column(db.Text)
    detalles_cambio = db.Column(db.JSON)
    
    caso = db.relationship('Caso', back_populates='auditorias')
    usuario = db.relationship('Usuario')