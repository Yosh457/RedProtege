# blueprints/casos.py
from flask import Blueprint, render_template, abort, request
from flask_login import login_required, current_user
from models import db, Caso, CatalogoCiclo
from utils import check_password_change

casos_bp = Blueprint('casos', __name__, template_folder='../templates', url_prefix='/casos')

@casos_bp.before_request
@login_required
@check_password_change
def before_request():
    pass

@casos_bp.route('/')
def index():
    """
    Bandeja de Entrada de Casos.
    Muestra SOLO los casos del ciclo vital asignado al usuario (o todos si es Admin).
    """
    page = request.args.get('page', 1, type=int)
    
    query = Caso.query

    # LOGICA DE FILTRO POR ALCANCE (Ciclo Vital)
    nombre_filtro = "Vista Global"
    
    # Si el usuario tiene un ciclo asignado (ej: Referente Infantil), filtramos.
    if current_user.ciclo_asignado_id:
        query = query.filter(Caso.ciclo_vital_id == current_user.ciclo_asignado_id)
        if current_user.ciclo_asignado:
            nombre_filtro = f"Ciclo {current_user.ciclo_asignado.nombre}"
    
    # Ordenar por fecha de ingreso descendente
    pagination = query.order_by(Caso.fecha_ingreso.desc()).paginate(page=page, per_page=15)

    return render_template('casos/index.html', pagination=pagination, nombre_filtro=nombre_filtro)

@casos_bp.route('/ver/<int:id>')
def ver_caso(id):
    caso = Caso.query.get_or_404(id)

    # SEGURIDAD: Verificar alcance
    # Si el usuario tiene ciclo asignado Y el caso no es de ese ciclo -> 403 Forbidden
    if current_user.ciclo_asignado_id and caso.ciclo_vital_id != current_user.ciclo_asignado_id:
        abort(403)

    return render_template('casos/ver.html', caso=caso)