"""Resolucion segura de rutas relativas de actas de RedProtege.

No accede a la base de datos ni abre archivos; el endpoint verifica existencia.
"""
from pathlib import Path, PurePosixPath
import ntpath

def resolver_ruta_acta(base_proyecto, ruta_almacenada):
    """Devuelve una ruta absoluta confinada a uploads/actas.

    Lanza ValueError ante rutas nulas, absolutas, escapes, extensiones
    incorrectas o enlaces simbolicos que salgan de la carpeta autorizada.
    """
    if not isinstance(ruta_almacenada, str) or not ruta_almacenada.strip():
        raise ValueError('Ruta de acta vacia o no valida')
    ruta = ruta_almacenada.replace('\\', '/')
    if '\x00' in ruta or ruta.startswith('/') or ntpath.isabs(ruta):
        raise ValueError('Ruta absoluta o invalida')
    partes = PurePosixPath(ruta).parts
    if (len(partes) < 3 or partes[:2] != ('uploads', 'actas')
            or '..' in partes or partes[-1] in ('', '.', '..')
            or PurePosixPath(partes[-1]).suffix.lower() != '.pdf'):
        raise ValueError('Ruta fuera de uploads/actas o no PDF')
    base = Path(base_proyecto).resolve()
    jaula = (base / 'uploads' / 'actas').resolve()
    destino = (base.joinpath(*partes)).resolve()
    try:
        destino.relative_to(jaula)
    except ValueError as exc:
        raise ValueError('Ruta fuera de la carpeta autorizada') from exc
    if destino == jaula:
        raise ValueError('La ruta apunta al directorio, no a un PDF')
    return str(destino)