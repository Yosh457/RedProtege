from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

db = SQLAlchemy()

def obtener_hora_chile():
    cl_tz = pytz.timezone('America/Santiago')
    return datetime.now(cl_tz)

# --- TABLA DE ASOCIACIÓN (MANY-TO-MANY) ---
# Tabla puente para relacionar Casos con múltiples Vulneraciones
caso_vulneraciones = db.Table('caso_vulneraciones',
    db.Column('caso_id', db.Integer, db.ForeignKey('casos.id'), primary_key=True),
    db.Column('vulneracion_id', db.Integer, db.ForeignKey('catalogo_vulneraciones.id'), primary_key=True)
)

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

class CatalogoRecinto(db.Model):
    __tablename__ = 'catalogo_recintos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)
    casos = db.relationship('Caso', back_populates='recinto_notifica')

class CatalogoVulneracion(db.Model):
    __tablename__ = 'catalogo_vulneraciones'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)
    casos = db.relationship('Caso', secondary=caso_vulneraciones, back_populates='vulneraciones')

class CatalogoInstitucion(db.Model):
    __tablename__ = 'catalogo_instituciones'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)
    casos = db.relationship('Caso', back_populates='denuncia_institucion')

class CatalogoEstablecimiento(db.Model):
    __tablename__ = 'catalogo_establecimientos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)
    casos = db.relationship('Caso', back_populates='recinto_inscrito')

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
    
    # --- A) ANTECEDENTES / ATENCIÓN ---
    fecha_atencion = db.Column(db.Date, index=True)
    hora_atencion = db.Column(db.Time)
    
    recinto_notifica_id = db.Column(db.Integer, db.ForeignKey('catalogo_recintos.id'), index=True)
    recinto_notifica = db.relationship('CatalogoRecinto', back_populates='casos')
    recinto_otro_texto = db.Column(db.String(255))
    
    vulneraciones = db.relationship('CatalogoVulneracion', secondary=caso_vulneraciones, back_populates='casos')
    vulneracion_otro_texto = db.Column(db.Text)
    
    folio_atencion = db.Column(db.String(50), index=True)
    ingresado_por_nombre = db.Column(db.String(100))
    ingresado_por_cargo = db.Column(db.String(100))

    # --- B) DATOS PACIENTE ---
    # Nota: origen_rut ahora es nullable, se mantiene por compatibilidad legacy si es necesario
    origen_rut = db.Column(db.String(20), nullable=True, index=True) 
    
    # RELAJADO: Ahora pueden ser NULL si el solicitante no los tiene
    origen_nombres = db.Column(db.String(100), nullable=True)
    origen_apellidos = db.Column(db.String(100), nullable=True, index=True)

    # Los campos 'origen_' obligatorios se llenarán con los datos del form para cumplir el NOT NULL
    origen_telefono = db.Column(db.String(20))
    origen_fecha_nacimiento = db.Column(db.Date) # Legacy
    origen_relato = db.Column(db.Text, nullable=False)
    
    # Campos Nuevos Específicos
    paciente_doc_tipo = db.Column(db.Enum('RUT','DNI','NIP','OTRO'), default='RUT')
    paciente_doc_numero = db.Column(db.String(50), index=True) 
    paciente_doc_otro_descripcion = db.Column(db.String(100))
    paciente_fecha_nacimiento = db.Column(db.Date) # Nueva columna principal
    paciente_domicilio = db.Column(db.Text)

    # --- C) DATOS ACOMPAÑANTE ---
    acompanante_nombre = db.Column(db.String(100))
    acompanante_parentesco = db.Column(db.String(50))
    acompanante_telefono = db.Column(db.String(20))
    acompanante_telefono_tipo = db.Column(db.Enum('CELULAR','FIJO','OTRO'))
    acompanante_doc_tipo = db.Column(db.Enum('RUT','DNI','NIP','OTRO'))
    acompanante_doc_numero = db.Column(db.String(50))
    acompanante_doc_otro_descripcion = db.Column(db.String(100))
    acompanante_domicilio = db.Column(db.Text)

    # --- D) DENUNCIA ---
    denuncia_realizada = db.Column(db.Boolean, default=False)
    denuncia_institucion_id = db.Column(db.Integer, db.ForeignKey('catalogo_instituciones.id'))
    denuncia_institucion = db.relationship('CatalogoInstitucion', back_populates='casos')
    denuncia_institucion_otro = db.Column(db.String(100))
    denuncia_profesional_nombre = db.Column(db.String(100))
    denuncia_profesional_cargo = db.Column(db.String(100))

    # --- E) ASIGNACIÓN ---
    asignado_a_usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), index=True)
    asignado_por_usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    asignado_at = db.Column(db.DateTime)

    # Relaciones explícitas con foreign_keys definidos para evitar ambigüedad
    asignado_a = db.relationship('Usuario', foreign_keys=[asignado_a_usuario_id], backref='casos_asignados')
    asignado_por = db.relationship('Usuario', foreign_keys=[asignado_por_usuario_id], backref='casos_distribuidos')

    # --- F) GESTIÓN CLÍNICA / SEGUIMIENTO (FASE 4 P2 - CÓDIGOS LIMPIOS) ---
    recinto_inscrito_id = db.Column(db.Integer, db.ForeignKey('catalogo_establecimientos.id'))
    recinto_inscrito = db.relationship('CatalogoEstablecimiento', back_populates='casos')

    # NUEVO: Texto para "Otro" recinto inscrito
    recinto_inscrito_otro_texto = db.Column(db.String(255))
    
    ingreso_lain = db.Column(db.Boolean, default=False)
    fallecido = db.Column(db.Boolean, default=False)
    fecha_defuncion = db.Column(db.Date)
    
    # Seguimiento Sanitario (ENUMs codificados)
    control_sanitario = db.Column(db.Enum('PENDIENTE_REVISION', 'CITACION_1', 'CITACION_2', 'CITACION_3', 'AL_DIA'), default='PENDIENTE_REVISION')
    gestion_vacunas = db.Column(db.Enum('PENDIENTE_REVISION', 'CITACION_1', 'CITACION_2', 'CITACION_3', 'AL_DIA'), default='PENDIENTE_REVISION')
    
    # Seguimiento Salud Mental / COSAM
    gestion_salud_mental = db.Column(db.Enum('PENDIENTE_REVISION', 'INGRESADO', 'NO_CORRESPONDE'), default='PENDIENTE_REVISION')
    gestion_cosam = db.Column(db.Enum('PENDIENTE_REVISION', 'DERIVADO', 'INGRESADO', 'NO_CORRESPONDE'), default='PENDIENTE_REVISION')
    
    # Seguimiento Judicial
    gestion_judicial = db.Column(db.Enum('PENDIENTE_REVISION', 'PENDIENTE', 'AL_DIA'), default='PENDIENTE_REVISION')

    observaciones_gestion = db.Column(db.Text)

    # --- DIRECCIONES DESGLOSADAS (NUEVO) ---
    paciente_direccion_calle = db.Column(db.String(200))
    paciente_direccion_numero = db.Column(db.String(50))
    acompanante_direccion_calle = db.Column(db.String(200))
    acompanante_direccion_numero = db.Column(db.String(50))

    # --- TRAZABILIDAD & GESTIÓN ---
    fecha_ingreso = db.Column(db.DateTime, default=obtener_hora_chile, index=True)
    updated_at = db.Column(db.DateTime, default=obtener_hora_chile, onupdate=obtener_hora_chile)

    ciclo_vital_id = db.Column(db.Integer, db.ForeignKey('catalogo_ciclos.id'), nullable=False, index=True) # Índice ya existe via FK o explícito
    ciclo_vital = db.relationship('CatalogoCiclo', back_populates='casos')

    acciones_realizadas = db.Column(db.Text)

    estado = db.Column(db.Enum('PENDIENTE_RESCATAR', 'EN_SEGUIMIENTO', 'CERRADO'), 
                       default='PENDIENTE_RESCATAR', nullable=False, index=True)
    
    bloqueado = db.Column(db.Boolean, default=False)
    bloqueado_at = db.Column(db.DateTime)
    bloqueado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    
    fecha_cierre = db.Column(db.DateTime)
    usuario_cierre_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))

    # Ruta al archivo PDF del acta de cierre
    acta_pdf_path = db.Column(db.String(255))

    auditorias = db.relationship('AuditoriaCaso', back_populates='caso', cascade="all, delete-orphan")

    # Índice compuesto para dashboard (Solicitado)
    __table_args__ = (
        db.Index('idx_casos_ciclo_estado', 'ciclo_vital_id', 'estado'),
    )

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

    # --- NUEVO: Propiedad para dar formato visual en el Frontend ---
    @property
    def estilo_visual(self):
        """
        Retorna configuración de colores e íconos según el tipo de acción.
        """
        config = {
            'color_bg': 'bg-gray-100',
            'color_text': 'text-gray-600',
            'icono': 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z', # Info (default)
            'titulo': self.accion.replace('_', ' ').title()
        }

        if self.accion in ['ASIGNACION', 'REASIGNACION']:
            config = {
                'color_bg': 'bg-green-100',
                'color_text': 'text-green-600',
                'icono': 'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z', # User Add
                'titulo': 'Asignación de Profesional'
            }
        elif self.accion == 'GESTION_CLINICA':
            config = {
                'color_bg': 'bg-blue-100',
                'color_text': 'text-blue-600',
                'icono': 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2', # Clipboard
                'titulo': 'Gestión Clínica Realizada'
            }
        elif self.accion == 'CIERRE_CASO':
            config = {
                'color_bg': 'bg-red-100',
                'color_text': 'text-red-600',
                'icono': 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z', # Lock
                'titulo': 'Cierre del Caso'
            }
        elif 'EMAIL' in self.accion:
            config = {
                'color_bg': 'bg-yellow-100',
                'color_text': 'text-yellow-600',
                'icono': 'M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z', # Mail
                'titulo': 'Notificación por Correo'
            }
        elif 'INGRESO' in self.accion or 'CREACION' in self.accion:
             config = {
                'color_bg': 'bg-purple-100',
                'color_text': 'text-purple-600',
                'icono': 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z', # Edit/Create
                'titulo': 'Ingreso del Caso'
            }

        return config