import os
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Diccionario de Labels para "Humanizar" los ENUMs
LABELS = {
    'PENDIENTE_REVISION': 'Pendiente por Revisar',
    'CITACION_1': '1° Citación',
    'CITACION_2': '2° Citación',
    'CITACION_3': '3° Citación',
    'AL_DIA': 'Al Día',
    'PENDIENTE': 'Pendiente',
    'INGRESADO': 'Ingresado',
    'DERIVADO': 'Derivado',
    'NO_CORRESPONDE': 'No corresponde'
}

def pretty(valor):
    """Devuelve el texto bonito del ENUM o el valor original si no existe."""
    return LABELS.get(valor, valor or '-')

def generar_acta_cierre_pdf(caso, output_filename, usuario_cierre):
    """
    Genera un PDF con el Acta de Cierre del caso usando ReportLab.
    Guarda el archivo en la ruta especificada.
    """
    # 1. Asegurar que el directorio existe
    output_dir = os.path.dirname(output_filename)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 2. Configuración del Documento con MÁRGENES PERSONALIZADOS
    # El default es 72 puntos (1 pulgada). Lo bajamos a 30 para subir el contenido.
    doc = SimpleDocTemplate(
        output_filename, 
        pagesize=LETTER,
        rightMargin=50,
        leftMargin=50,
        topMargin=30,    # <--- ESTE ES EL CAMBIO CLAVE (Sube el contenido)
        bottomMargin=30
    )
    elements = []
    styles = getSampleStyleSheet()

    # --- LOGOS (CABECERA) ---
    # Calculamos ruta absoluta a static/img
    # Asumiendo estructura: /utils/pdf_actas.py -> subir -> /static/img
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    logo1_path = os.path.join(base_dir, 'static', 'img', 'Logo_Red_APS_2.png')
    logo2_path = os.path.join(base_dir, 'static', 'img', 'logoMaho.png')

    # Tabla invisible para logos
    if os.path.exists(logo1_path) and os.path.exists(logo2_path):
        img1 = Image(logo1_path, width=120, height=50) # Ajusta tamaño según necesidad
        img2 = Image(logo2_path, width=120, height=50)
        # Ratio de aspecto se mantiene si solo fijas width o height, aquí fuerzo ambos
        img1.hAlign = 'LEFT'
        img2.hAlign = 'RIGHT'
        
        data_logos = [[img1, '', img2]]
        t_logos = Table(data_logos, colWidths=[200, 140, 200])
        t_logos.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            # Eliminamos padding extra de la tabla de logos para que pegue bien arriba
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        elements.append(t_logos)
        elements.append(Spacer(1, 10))
    else:
        # Fallback texto si no hay logos
        elements.append(Paragraph("Red de Atención Primaria de Salud Municipal - Alto Hospicio", styles['Normal']))

    # Estilos Personalizados
    estilo_titulo = ParagraphStyle(
        'TituloActa', 
        parent=styles['Heading1'], 
        alignment=TA_CENTER, 
        fontSize=16, 
        spaceAfter=20,
        textColor=colors.HexColor('#275c80')
    )
    estilo_subtitulo = ParagraphStyle(
        'Subtitulo', 
        parent=styles['Heading2'], 
        fontSize=12, 
        spaceBefore=15, 
        spaceAfter=10,
        textColor=colors.HexColor('#444444')
    )
    estilo_normal = styles['Normal']
    
    # --- CONTENIDO DEL PDF ---

    # Encabezado
    elements.append(Paragraph(f"ACTA DE CIERRE DE CASO #{caso.folio_atencion}", estilo_titulo))

    # Tabla: Información General
    # Usamos la fecha real del objeto caso, formateada
    fecha_cierre_str = caso.fecha_cierre.strftime('%d/%m/%Y %H:%M') if caso.fecha_cierre else "N/A"

    data_general = [
        ['Folio Atención:', caso.folio_atencion],
        ['Fecha Ingreso:', caso.fecha_ingreso.strftime('%d/%m/%Y %H:%M')],
        ['Estado Final:', 'CERRADO'],
        ['Ingresado Por:', caso.ingresado_por_nombre or 'Sistema'],
        ['Cerrado Por:', usuario_cierre.nombre_completo],
        ['Fecha Cierre:', fecha_cierre_str]
    ]
    
    t_general = Table(data_general, colWidths=[120, 300])
    t_general.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0,0), (0,-1), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    elements.append(t_general)
    elements.append(Spacer(1, 15))

    # Sección: Paciente
    elements.append(Paragraph("1. Antecedentes del Paciente", estilo_subtitulo))
    nombre_paciente = f"{caso.origen_nombres or ''} {caso.origen_apellidos or ''}".strip() or "No registrado"
    doc_id = f"{caso.paciente_doc_tipo}: {caso.paciente_doc_numero}" if caso.paciente_doc_numero else "Sin ID"
    
    data_paciente = [
        ['Nombre:', nombre_paciente],
        ['Identificación:', doc_id],
        ['Fecha Nacimiento:', caso.paciente_fecha_nacimiento.strftime('%d/%m/%Y') if caso.paciente_fecha_nacimiento else '-'],
        ['Ciclo Vital:', caso.ciclo_vital.nombre if caso.ciclo_vital else '-'],
        ['Domicilio:', caso.paciente_domicilio or '-']
    ]
    t_paciente = Table(data_paciente, colWidths=[120, 300])
    t_paciente.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
    ]))
    elements.append(t_paciente)

    # Sección: Relato
    elements.append(Paragraph("2. Motivo de Consulta / Relato", estilo_subtitulo))
    elements.append(Paragraph(caso.origen_relato or "Sin relato.", estilo_normal))
    
    # Vulneraciones
    vuln_list = [v.nombre for v in caso.vulneraciones]
    if caso.vulneracion_otro_texto:
        vuln_list.append(f"Otro: {caso.vulneracion_otro_texto}")
    vuln_str = ", ".join(vuln_list) if vuln_list else "Ninguna registrada"
    
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"<b>Vulneraciones detectadas:</b> {vuln_str}", estilo_normal))

    # Sección: Gestión Clínica
    elements.append(Paragraph("3. Gestión y Seguimiento", estilo_subtitulo))

    recinto_txt = "-"
    if caso.recinto_inscrito:
        recinto_txt = caso.recinto_inscrito.nombre
        # Lógica para mostrar texto "Otro"
        if 'otro' in recinto_txt.lower() and caso.recinto_inscrito_otro_texto:
            recinto_txt = f"{recinto_txt} ({caso.recinto_inscrito_otro_texto})"
    elif caso.recinto_inscrito_otro_texto:
        recinto_txt = caso.recinto_inscrito_otro_texto
    
    data_gestion = [
        ['Recinto Inscrito:', recinto_txt],
        ['Controles Salud:', pretty(caso.control_sanitario) or '-'],
        ['Vacunas:', pretty(caso.gestion_vacunas) or '-'],
        ['Informe Judicial:', pretty(caso.gestion_judicial) or '-'],
        ['Salud Mental:', pretty(caso.gestion_salud_mental) or '-'],
        ['COSAM:', pretty(caso.gestion_cosam) or '-'],
    ]
    
    # Agregar info si falleció
    if caso.fallecido:
        fecha_def = caso.fecha_defuncion.strftime('%d/%m/%Y') if caso.fecha_defuncion else 'S/I'
        data_gestion.append(['ESTADO:', f'FALLECIDO (Fecha: {fecha_def})'])

    t_gestion = Table(data_gestion, colWidths=[120, 300])
    t_gestion.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
    ]))
    elements.append(t_gestion)

    # Sección: Observaciones Finales
    elements.append(Paragraph("4. Observaciones y Derivaciones Finales", estilo_subtitulo))
    obs = caso.observaciones_gestion or "Sin observaciones registradas al cierre."
    elements.append(Paragraph(obs, estilo_normal))

    # Footer
    #elements.append(Spacer(1, 40))
    #elements.append(Paragraph("_" * 40, styles['Normal']))
    #elements.append(Paragraph(f"Firma Responsable: {usuario_cierre.nombre_completo}", styles['Normal']))
    #elements.append(Paragraph(f"Cargo: {usuario_cierre.rol.nombre}", styles['Normal']))

    # 3. Generar PDF
    doc.build(elements)
    return True