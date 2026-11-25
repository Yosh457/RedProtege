"""Política objetivo de autorización de RedProtege (Fase 1.3-B).

Módulo independiente: NO está conectado aún a los blueprints.
No consulta BD, no escribe, no registra auditoría ni envía correos.

Reglas:
* Denegación por defecto ante usuarios, roles, acciones o ámbitos desconocidos.
* Una acción sobre un caso exige permiso del rol y coincidencia de ámbito.
* La validación de estados impide modificar casos cerrados o anulados.
* Las excepciones y permisos aún no acordados se deniegan hasta su definición.
* Usuario.recintos será la futura relación SQLAlchemy M:N usuario_recintos.
  Hasta la migración, la ausencia de dicha relación equivale a cero recintos.

No sustituye autenticación, CSRF, transacciones ni pruebas HTTP.
"""

from __future__ import annotations

from sqlalchemy import false, or_

# Valores exactos del catálogo actual y del rol nuevo previsto.
ADMIN = 'Admin'
TORRE = 'Torre Control'
TS = 'Trabajador(a) Social'
COORD = 'Coordinador Ciclo'
EPI = 'Coordinador EPI'
REFERENTE = 'Referente'
VISUALIZADOR = 'Visualizador'
SOLICITANTE = 'Solicitante'
URGENCIA = 'Coordinador(a) de Urgencia'

LISTAR = 'casos.listar'
VER = 'casos.ver'
GESTIONAR = 'casos.gestionar'
ASIGNAR_TS = 'casos.asignar_ts'
ASIGNAR_COORD = 'casos.asignar_coord'
CERRAR = 'casos.cerrar'
ANULAR = 'casos.anular'
EXPORTAR = 'casos.exportar'
DESCARGAR_ACTA = 'casos.descargar_acta'
REPORTE_MASIVO = 'casos.reporte_masivo'
GESTIONAR_SUBROGANCIAS = 'subrogancias.gestionar'
ADMINISTRAR_USUARIOS = 'usuarios.administrar'
INGRESAR_SOLICITUD = 'solicitudes.ingresar'

# Matriz objetivo: acciones no incluidas son prohibidas.
# La exportación se limita al ámbito. La descarga histórica se trata abajo.
# No habilitamos subrogancias de Admin/Torre ni exportaciones de Coordinador
# Ciclo hasta contar con una decisión funcional explícita.
_PERMISOS = {
    ADMIN: frozenset({LISTAR, VER, GESTIONAR, ASIGNAR_TS, ASIGNAR_COORD,
                      CERRAR, ANULAR, EXPORTAR, DESCARGAR_ACTA,
                      REPORTE_MASIVO, ADMINISTRAR_USUARIOS}),
    TORRE: frozenset({LISTAR, VER, GESTIONAR, ASIGNAR_TS, ASIGNAR_COORD,
                      CERRAR, ANULAR, EXPORTAR, DESCARGAR_ACTA,
                      REPORTE_MASIVO}),
    TS: frozenset({LISTAR, VER, GESTIONAR, CERRAR, EXPORTAR,
                   DESCARGAR_ACTA}),
    COORD: frozenset({LISTAR, VER, DESCARGAR_ACTA}),
    EPI: frozenset({LISTAR, VER, EXPORTAR, DESCARGAR_ACTA}),
    REFERENTE: frozenset({LISTAR, VER, ASIGNAR_TS, ASIGNAR_COORD,
                          EXPORTAR, DESCARGAR_ACTA, GESTIONAR_SUBROGANCIAS}),
    VISUALIZADOR: frozenset({LISTAR, VER, EXPORTAR, DESCARGAR_ACTA}),
    SOLICITANTE: frozenset({INGRESAR_SOLICITUD}),
    URGENCIA: frozenset({LISTAR, VER, GESTIONAR, EXPORTAR, DESCARGAR_ACTA}),
}

_ACCIONES_DE_CASO = frozenset({LISTAR, VER, GESTIONAR, ASIGNAR_TS,
                               ASIGNAR_COORD, CERRAR, ANULAR, EXPORTAR,
                               DESCARGAR_ACTA})
_MUTACIONES = frozenset({GESTIONAR, ASIGNAR_TS, ASIGNAR_COORD, CERRAR, ANULAR})

def _id_positivo(valor):
    """Acepta identificadores enteros positivos; nunca convierte valores arbitrarios."""
    return valor if type(valor) is int and valor > 0 else None

def _ids_relacion(elementos):
    """Extrae IDs de objetos de relación SQLAlchemy o dobles de prueba."""
    ids = set()
    if elementos is None:
        return ids
    for objeto in elementos:
        identificador = _id_positivo(getattr(objeto, 'id', None))
        if identificador is not None:
            ids.add(identificador)
    return ids

def _rol(usuario):
    rol = getattr(usuario, 'rol', None)
    return getattr(rol, 'nombre', None)

def _usuario_habilitado(usuario):
    """Solo usuarios con sesión autenticada y activo explícitamente True."""
    return (usuario is not None
            and getattr(usuario, 'is_authenticated', False) is True
            and getattr(usuario, 'activo', None) is True
            and _id_positivo(getattr(usuario, 'id', None)) is not None)

def puede_exportar_ambito(usuario):
    """Admite exportacion solo con permiso y ambito asignado cuando aplica.

    TS conserva exportacion vacia cuando no tiene casos; Referente y perfiles
    territoriales deben tener una asignacion de alcance explicita.
    """
    if not puede_realizar(usuario, EXPORTAR):
        return False
    rol = _rol(usuario)
    if rol == REFERENTE:
        return bool(_ciclos_autorizados(usuario))
    if rol in (EPI, URGENCIA):
        return bool(_recintos_autorizados(usuario))
    return True

def puede_realizar(usuario, accion):
    """Permiso basado exclusivamente en el rol (no evalúa un caso ni estado)."""
    return _usuario_habilitado(usuario) and accion in _PERMISOS.get(_rol(usuario), ())

def _ciclos_autorizados(usuario):
    ids = _ids_relacion(getattr(usuario, 'ciclos', None))
    # Compatibilidad con el ciclo legado explícitamente asignado.
    legado = _id_positivo(getattr(usuario, 'ciclo_asignado_id', None))
    if legado is not None:
        ids.add(legado)
    titular = getattr(usuario, 'subrogante_de', None)
    if (_rol(usuario) == REFERENTE and titular is not None
            and getattr(titular, 'activo', None) is True
            and _rol(titular) == REFERENTE):
        ids.update(_ids_relacion(getattr(titular, 'ciclos', None)))
        legado_titular = _id_positivo(getattr(titular, 'ciclo_asignado_id', None))
        if legado_titular is not None:
            ids.add(legado_titular)
    return ids

def _recintos_autorizados(usuario):
    # La futura relación 'recintos' no existe todavía en models.py.
    # Ausencia, None o colección vacía no otorgan acceso.
    return _ids_relacion(getattr(usuario, 'recintos', None))


def _ambito_permitido(usuario, caso):
    rol = _rol(usuario)
    usuario_id = _id_positivo(getattr(usuario, 'id', None))
    if rol in (ADMIN, TORRE, VISUALIZADOR):
        return True
    if rol == TS:
        return usuario_id in {
            _id_positivo(getattr(caso, 'asignado_ts_id', None)),
            _id_positivo(getattr(caso, 'asignado_a_usuario_id', None)),
        }
    if rol == COORD:
        return usuario_id == _id_positivo(getattr(caso, 'asignado_coord_id', None))
    if rol == REFERENTE:
        return _id_positivo(getattr(caso, 'ciclo_vital_id', None)) in _ciclos_autorizados(usuario)
    if rol in (EPI, URGENCIA):
        return _id_positivo(getattr(caso, 'recinto_notifica_id', None)) in _recintos_autorizados(usuario)
    return False

def puede_acceder_caso(usuario, caso, accion=VER):
    """Política objetivo para un caso concreto. No muta ningún objeto."""
    if caso is None or accion not in _ACCIONES_DE_CASO:
        return False
    if not puede_realizar(usuario, accion):
        return False
    if not _ambito_permitido(usuario, caso):
        return False
    if accion in _MUTACIONES:
        estado = getattr(caso, 'estado', None)
        if estado not in ('PENDIENTE_RESCATAR', 'EN_SEGUIMIENTO'):
            return False
    if accion == DESCARGAR_ACTA:
        return bool(getattr(caso, 'acta_pdf_path', None))
    return True

def puede_descargar_acta_historica(usuario, caso):
    """Excepción explícita: TS que cerró el caso, aun tras su reasignación.

    Solo aplica a actas existentes de casos cerrados; no concede vista del
    detalle, listado ni exportación. Requiere el permiso de descarga del rol.
    """
    if not puede_realizar(usuario, DESCARGAR_ACTA) or _rol(usuario) != TS:
        return False
    return (caso is not None
            and getattr(caso, 'estado', None) == 'CERRADO'
            and bool(getattr(caso, 'acta_pdf_path', None))
            and _id_positivo(getattr(caso, 'usuario_cierre_id', None))
                == _id_positivo(getattr(usuario, 'id', None)))

def aplicar_filtro_casos(usuario, consulta, accion=LISTAR, modelo=None):
    """Aplica filtros SQLAlchemy con política equivalente al acceso individual.

    Se requiere explícitamente `modelo` (p.ej. models.Caso), para facilitar
    pruebas aisladas sin importar los blueprints ni acceder a la BD.
    No aplica filtros de estado de interfaz ni obtiene resultados.
    """
    if modelo is None:
        raise ValueError('Se requiere el modelo Caso')
    if accion not in (LISTAR, VER, EXPORTAR, DESCARGAR_ACTA):
        return consulta.filter(false())
    if not puede_realizar(usuario, accion):
        return consulta.filter(false())
    rol = _rol(usuario)
    if rol in (ADMIN, TORRE, VISUALIZADOR):
        resultado = consulta
    elif rol == TS:
        uid = usuario.id
        resultado = consulta.filter(or_(modelo.asignado_ts_id == uid,
                                        modelo.asignado_a_usuario_id == uid))
    elif rol == COORD:
        resultado = consulta.filter(modelo.asignado_coord_id == usuario.id)
    elif rol == REFERENTE:
        ids = _ciclos_autorizados(usuario)
        resultado = (consulta.filter(modelo.ciclo_vital_id.in_(sorted(ids)))
                     if ids else consulta.filter(false()))
    elif rol in (EPI, URGENCIA):
        ids = _recintos_autorizados(usuario)
        resultado = (consulta.filter(modelo.recinto_notifica_id.in_(sorted(ids)))
                     if ids else consulta.filter(false()))
    else:
        resultado = consulta.filter(false())
    if accion == DESCARGAR_ACTA:
        resultado = resultado.filter(modelo.acta_pdf_path.isnot(None), modelo.acta_pdf_path != '')
    return resultado