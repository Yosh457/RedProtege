# crear_superadmin.py
from app import create_app
from models import db, Usuario, Rol

app = create_app()

def crear_admin():
    with app.app_context():
        print("\n--- CREACIÓN DE SUPER ADMINISTRADOR ---")
        
        # 1. Verificar que los roles existan (por si acaso falló el SQL)
        rol_admin = Rol.query.filter_by(nombre='Admin').first()
        if not rol_admin:
            print("Error: El rol 'Admin' no existe en la base de datos.")
            print("Asegúrate de haber ejecutado el script SQL inicial en Workbench.")
            return

        email = input("Ingresa el email del nuevo Admin: ")
        
        # 2. Verificar si el usuario ya existe
        if Usuario.query.filter_by(email=email).first():
            print(f"Error: El email {email} ya está registrado.")
            return
        
        password = input("Ingresa la contraseña: ")

        # 3. Crear el usuario
        nuevo_admin = Usuario(
            nombre_completo="Super Administrador",
            email=email,
            rol_id=rol_admin.id,
            activo=True,
            cambio_clave_requerido=False, # Al ser superadmin creado por consola, asumimos que es seguro
            ciclo_asignado_id=None # Admin ve todo (no está restringido a un ciclo)
        )
        nuevo_admin.set_password(password)
        
        try:
            db.session.add(nuevo_admin)
            db.session.commit()
            print(f"¡Éxito! Usuario {email} creado correctamente con rol de Administrador.")
        except Exception as e:
            print(f"Error al guardar en base de datos: {e}")
            db.session.rollback()

if __name__ == '__main__':
    crear_admin()