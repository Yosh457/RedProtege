# app.py
import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, redirect, url_for, flash, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy.engine import URL

# Extensiones y modelos
from extensions import login_manager, csrf
from models import db, Usuario

def create_app():
    """Crea y configura la aplicacion Flask de RedProtege."""

    # -------------------------------------------------------------------------
    # INICIALIZACION DE FLASK
    # -------------------------------------------------------------------------
    load_dotenv()

    app = Flask(__name__)
    app.jinja_env.add_extension('jinja2.ext.do')

    # -------------------------------------------------------------------------
    # CONFIGURACION DE ENTORNO
    # -------------------------------------------------------------------------
    app_env = os.getenv('APP_ENV', 'development').strip().lower()

    if app_env not in ('development', 'testing', 'production'):
        raise RuntimeError(
            "APP_ENV debe ser development, testing o production."
        )

    debug_solicitado = os.getenv('FLASK_DEBUG', '0') == '1'
    debug_habilitado = (
        app_env == 'development' and debug_solicitado
    )

    app.config['DEBUG'] = debug_habilitado

    # -------------------------------------------------------------------------
    # SEGURIDAD DE FLASK Y SESIONES
    # -------------------------------------------------------------------------
    secret_key = os.getenv('SECRET_KEY')

    if not secret_key:
        raise RuntimeError(
            "Error critico: SECRET_KEY no esta configurada en .env."
        )

    app.config['SECRET_KEY'] = secret_key

    # Impedir el acceso a la cookie de sesion desde JavaScript.
    app.config['SESSION_COOKIE_HTTPONLY'] = True

    # Reducir el envio de cookies en solicitudes entre sitios.
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # En produccion, la cookie solo se envia mediante HTTPS.
    app.config['SESSION_COOKIE_SECURE'] = (
        app_env == 'production'
    )

    # Duracion maxima para sesiones marcadas como permanentes.
    # No convierte automaticamente todas las sesiones en permanentes.
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

    # CSRF global: Flask-WTF protege las solicitudes aplicables.
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600

    # -------------------------------------------------------------------------
    # CONEXION A BASE DE DATOS MYSQL
    # -------------------------------------------------------------------------
    db_host = os.getenv('MYSQL_HOST')
    db_port = os.getenv('MYSQL_PORT')
    db_user = os.getenv('MYSQL_USER')
    db_pass = os.getenv('MYSQL_PASSWORD')
    db_name = os.getenv('MYSQL_DB')

    configuracion_mysql = {
        'MYSQL_HOST': db_host,
        'MYSQL_PORT': db_port,
        'MYSQL_USER': db_user,
        'MYSQL_PASSWORD': db_pass,
        'MYSQL_DB': db_name,
    }

    faltantes = [
        nombre
        for nombre, valor in configuracion_mysql.items()
        if not valor
    ]

    if faltantes:
        raise RuntimeError(
            "Configuracion MySQL incompleta. "
            "Revise estas variables en .env: "
            + ', '.join(faltantes)
        )

    try:
        puerto_mysql = int(db_port)
    except ValueError as exc:
        raise RuntimeError(
            "MYSQL_PORT debe ser un numero entero."
        ) from exc

    if not 1 <= puerto_mysql <= 65535:
        raise RuntimeError(
            "MYSQL_PORT debe estar entre 1 y 65535."
        )

    app.config['SQLALCHEMY_DATABASE_URI'] = URL.create(
        drivername='mysql+pymysql',
        username=db_user,
        password=db_pass,
        host=db_host,
        port=puerto_mysql,
        database=db_name,
    )

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Limite de subida de archivos: 32 MB.
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

    # Mantener conexiones saludables y reciclarlas periodicamente.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }

    # -------------------------------------------------------------------------
    # CONFIGURACION DE URL BASE
    # -------------------------------------------------------------------------
    app.config['REDPROTEGE_BASE_URL'] = (
        os.getenv(
            'REDPROTEGE_BASE_URL',
            'http://127.0.0.1:5000'
        ).rstrip('/')
    )

    app.config['PREFERRED_URL_SCHEME'] = (
        'https' if app_env == 'production' else 'http'
    )

    # -------------------------------------------------------------------------
    # INICIALIZACION DE EXTENSIONES
    # -------------------------------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # -------------------------------------------------------------------------
    # CONFIGURACION DE FLASK-LOGIN
    # -------------------------------------------------------------------------
    login_manager.session_protection = 'strong'
    login_manager.login_view = 'auth.login'
    login_manager.login_message = (
        'Acceso restringido al sistema RedProtege.'
    )
    login_manager.login_message_category = 'warning'

    # -------------------------------------------------------------------------
    # REGISTRO DE BLUEPRINTS
    # -------------------------------------------------------------------------
    from blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from blueprints.admin import admin_bp
    app.register_blueprint(admin_bp)

    from blueprints.casos import casos_bp
    app.register_blueprint(casos_bp)

    from blueprints.solicitudes import solicitudes_bp
    app.register_blueprint(solicitudes_bp)

    # -------------------------------------------------------------------------
    # RUTA PRINCIPAL
    # -------------------------------------------------------------------------
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # -------------------------------------------------------------------------
    # MANEJO DE ERRORES CSRF
    # -------------------------------------------------------------------------
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        app.logger.warning(
            'Solicitud rechazada por CSRF: %s %s',
            request.method,
            request.path,
        )

        flash(
            'La solicitud no se pudo validar. '
            'Actualice la pagina y vuelva a intentarlo.',
            'warning',
        )
        return redirect(url_for('auth.login'))

    # -------------------------------------------------------------------------
    # CABECERAS HTTP Y CACHE
    # -------------------------------------------------------------------------
    @app.after_request
    def add_header(response):
        """Diferencia recursos estaticos de respuestas sensibles."""

        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'

        if response.status_code >= 400:
            response.headers['Cache-Control'] = 'no-store'

        elif request.endpoint == 'static':
            response.headers['Cache-Control'] = (
                'public, max-age=3600'
            )

        else:
            # Autenticacion, administracion, casos, solicitudes,
            # reportes, documentos y redirecciones.
            response.headers['Cache-Control'] = (
                'private, no-store'
            )

        response.headers.pop('Pragma', None)
        response.headers.pop('Expires', None)

        return response

    # -------------------------------------------------------------------------
    # MANEJO DE ERRORES PERSONALIZADOS
    # -------------------------------------------------------------------------
    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def access_denied(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_server_error(error):
        db.session.rollback()

        app.logger.error(
            'Error interno no controlado: %s',
            type(error).__name__,
        )

        return render_template('errors/500.html'), 500

    return app

# -----------------------------------------------------------------------------
# RECUPERACION DE USUARIOS PARA FLASK-LOGIN
# -----------------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    try:
        identificador = int(user_id)
    except (TypeError, ValueError):
        return None

    if identificador <= 0:
        return None

    usuario = db.session.get(Usuario, identificador)

    # Una cuenta desactivada no debe conservar acceso por una sesion previa.
    if usuario is None or usuario.activo is not True:
        return None

    return usuario

# -----------------------------------------------------------------------------
# EJECUCION DIRECTA - DESARROLLO LOCAL
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    app = create_app()

    app.run(
        debug=app.config['DEBUG'],
        host='127.0.0.1',
        port=5000,
    )