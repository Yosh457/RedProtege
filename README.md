# 🏥 RedProtege - Sistema de Gestión de Casos APS

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)
![Database](https://img.shields.io/badge/Database-MySQL-blue.svg)
![ORM](https://img.shields.io/badge/ORM-SQLAlchemy-red.svg)

Plataforma web integral desarrollada para la **Red de Atención Primaria de Salud Municipal de Alto Hospicio**. Su objetivo es digitalizar, centralizar y optimizar el flujo de derivación, seguimiento y gestión clínica de casos vulnerables, asegurando la trazabilidad y la seguridad de la información del paciente.

## 🚀 Características Principales

* **Gestión de Casos y Derivaciones:**
    * **Ingreso Digital:** Formulario público estandarizado con validación de RUT y detección automática de ciclo vital.
    * **Asignación Dual:** Modelo de responsabilidad compartida entre **Trabajador(a) Social** (Gestión) y **Coordinador de Ciclo** (Supervisión).
    * **Bandeja Inteligente:** Filtros por estado, búsqueda avanzada y alertas visuales.

* **Seguridad y Roles (RBAC):**
    * **Admin / Torre de Control:** Visión global y métricas.
    * **Referente:** Gestión por ciclo vital y sistema de **Subrogancia** (delegación temporal).
    * **Trabajador Social:** Gestión clínica operativa y cierre de casos.
    * **Coordinador EPI:** Visión global de solo lectura sin acciones operativas.

* **Herramientas Clínicas:**
    * **Bitácora de Movimientos:** Historial cronológico inmutable de observaciones y cambios de estado.
    * **Gestión Dinámica:** Soporte para acompañantes, denuncias y seguimiento de hitos (vacunas, salud mental).
    * **Cierre Formal:** Generación automática de **Actas de Cierre en PDF** y notificación por correo.

* **Reportabilidad:**
    * **Dashboard:** KPIs en tiempo real y gráficos interactivos (Chart.js).
    * **Reportes Masivos:** Envío de resumen ejecutivo por correo a los funcionarios.
    * **Excel:** Exportación de data completa para análisis.

## 🛠️ Tecnologías Utilizadas

* **Backend:** Python 3, Flask (Blueprints).
* **Base de Datos:** MySQL (SQLAlchemy ORM).
* **Frontend:** HTML5, Jinja2, TailwindCSS, JavaScript.
* **Librerías Clave:** `Flask-Login` (Auth), `ReportLab` (PDF), `OpenPyXL` (Excel), `Chart.js` (Gráficos).

## 📂 Estructura del Proyecto

El proyecto sigue una arquitectura modular basada en **Blueprints**:

```text
REDPROTEGE/
├── blueprints/          # Lógica de rutas y controladores
│   ├── admin.py         # Gestión de usuarios y logs
│   ├── auth.py          # Autenticación y recuperación de clave
│   ├── casos.py         # Bandeja, gestión, asignación y reportes
│   └── solicitudes.py   # Formulario de ingreso
├── static/              # Archivos estáticos
│   ├── css/             # Estilos personalizados (style.css)
│   ├── docs/            # Documentación
│   ├── img/             # Assets gráficos (logos, favicon)
│   └── js/              # Scripts (modales, validaciones, flash messages)
├── templates/           # Vistas HTML (Jinja2)
│   ├── admin/           # Vistas de panel y usuarios
│   ├── auth/            # Vistas de login y contraseña
│   ├── casos/           # Bandeja, ver detalle, gestión
│   ├── errors/          # Páginas de error (403, 404, 500)
│   └── solicitudes/     # Formulario de ingreso y macros
├── uploads/actas/       # Almacenamiento de PDFs generados
├── utils/               # Módulos transversales
│   ├── email.py         # Lógica de envío de correos
│   ├── pdf_actas.py     # Generador de reportes PDF
│   ├── decorators.py    # Decoradores de permisos
│   └── helpers.py       # Funciones auxiliares
├── venv/                # Entorno virtual
├── app.py               # Punto de entrada de la aplicación
├── models.py            # Modelos de Base de Datos (SQLAlchemy)
├── extensions.py        # Inicialización de extensiones
└── requirements.txt     # Dependencias del proyecto
```
## ⚙️ Instalación y Despliegue Local

1. Clonar el repositorio:

```bash
git clone https://github.com/Yosh457/redprotege.git
cd redprotege
```
2. Crear entorno virtual:

```bash
python -m venv venv
# En Windows:
venv\Scripts\activate
# En Mac/Linux:
source venv/bin/activate
```
3. Instalar dependencias:

```bash
pip install -r requirements.txt
```
4. Configurar variables de entorno (.env):

```env
SECRET_KEY=tu_clave_secreta_segura
MYSQL_PASSWORD=tu_password_de_base_de_datos
FLASK_DEBUG=True
EMAIL_USUARIO=tu_correo_notificaciones@gmail.com
EMAIL_CONTRASENA=tu_contraseña_de_aplicacion
```
5. Inicializar Base de Datos (Primera vez):

**Paso A: Crear la base de datos en MySQL.**

Ingresa a tu cliente MySQL (Workbench o consola) y ejecuta:

```sql
CREATE DATABASE redprotege_db;
-- (Asegúrate de que el nombre coincida con el configurado en tu config.py)
```
**Paso B: Crear las tablas.**

```bash
flask shell
```
Dentro de la shell interactiva de Flask ejecuta línea por línea lo siguiente:

```python
from models import db
db.create_all()
exit()
```
**Paso C: Crear usuario administrador inicial.**

```bash
python crear_superadmin.py
```
6. Ejecutar la aplicación:

```bash
python app.py
# O alternativamente: flask run
```

Accede en tu navegador a: http://localhost:5000

## 🛡️ Matriz de Permisos (Resumen)

| Rol              | Ingreso | Bandeja   | Asignar | Gestionar | Reportes |
|------------------|----------|------------|----------|------------|-----------|
| Admin            | ✅       | Global     | ✅       | ✅         | ✅        |
| Torre Control    | ✅       | Global     | ❌       | ❌         | ✅        |
| Referente        | ❌       | Ciclo      | ✅       | ❌         | ❌        |
| Trabajador Soc.  | ❌       | Asignados  | ❌       | ✅         | ✅        |
| Coord. Ciclo     | ❌       | Asignados  | ❌       | ❌         | ✅        |
| Solicitante      | ✅       | ❌         | ❌       | ❌         | ❌        |
---
Desarrollado por **Josting Silva**  
Analista Programador – Unidad de TICs  
Departamento de Salud, Municipalidad de Alto Hospicio
