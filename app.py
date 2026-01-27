import os
from dotenv import load_dotenv
from flask import Flask, redirect, url_for
from extensions import login_manager, csrf
from models import db, Usuario

def create_app():
    app = Flask(__name__)
    # Habilitar extensión 'do' para Jinja2 (útil para lógica en templates)
    app.jinja_env.add_extension('jinja2.ext.do')
    load_dotenv()

    # --- CONFIGURACIÓN ---
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    
    db_pass = os.getenv('MYSQL_PASSWORD')
    db_name = 'red_protege_db'  # ✅ BD Correcta
    
    # Conexión estándar cPanel/Local
    app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:{db_pass}@localhost/{db_name}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Límite de subida (Manteniendo tu estándar de 32MB)
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

    # Configuración de Pool para estabilidad (Recomendado cPanel)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 280
    }

    # --- INICIALIZACIÓN ---
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Acceso restringido al sistema RedProtege.'
    login_manager.login_message_category = 'warning'

    # --- REGISTRO DE BLUEPRINTS ---
    
    from blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from blueprints.admin import admin_bp
    app.register_blueprint(admin_bp)

    # Blueprint del negocio principal (casos)
    from blueprints.casos import casos_bp
    app.register_blueprint(casos_bp)

    # Blueprint Formulario Público
    from blueprints.publico import publico_bp
    app.register_blueprint(publico_bp)

    @app.route('/')
    def index():
        # Redirigir al login por ahora
        return redirect(url_for('auth.login')) 

    return app

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        # Esto crea las tablas según el modelo definido si no existen
        try:
            db.create_all()
            print("✅ Sistema RedProtege inicializado. Tablas verificadas.")
        except Exception as e:
            print(f"❌ Error al conectar con BD: {e}")
            
    app.run(debug=True)