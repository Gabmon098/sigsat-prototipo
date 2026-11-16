"""
Validación de archivos adjuntos (puro: no depende de la interfaz ni de `datos`).

Un adjunto es opcional y solo sirve de apoyo a una solicitud (una captura de
pantalla, un registro de error, un documento). Por seguridad:

* solo se aceptan unas pocas extensiones de documentos e imágenes (nada ejecutable
  ni comprimido, que podrían esconder programas);
* el contenido tiene que corresponder a la extensión (se revisan los primeros
  bytes del archivo), no basta con renombrarlo;
* hay un tamaño máximo por archivo y un máximo de archivos por solicitud;
* el nombre se limpia: nunca se usa una ruta del usuario ni caracteres de control.
"""

import os
import re

MAX_ADJUNTOS_POR_SOLICITUD = 5
MAX_TAMANO_ADJUNTO = 5 * 1024 * 1024          # 5 MB
LIM_NOMBRE_ARCHIVO = 100

# extensión -> (tipo MIME, firma esperada al inicio del archivo; None = texto)
_TIPOS = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b"PK\x03\x04",)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b"PK\x03\x04",)),
    ".txt": ("text/plain", None),
    ".log": ("text/plain", None),
    ".csv": ("text/csv", None),
}
EXTENSIONES_PERMITIDAS = tuple(sorted(_TIPOS))

_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_RE_PROHIBIDOS = re.compile(r'[<>:"/\\|?*]')


def formato_tamano(n_bytes: int) -> str:
    """Tamaño legible: '850 B', '12.4 KB', '3.2 MB'."""
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / (1024 * 1024):.1f} MB"


def limpiar_nombre(nombre: str) -> str:
    """Solo el nombre del archivo (sin carpetas), sin caracteres de control ni prohibidos."""
    nombre = (nombre or "").replace("\\", "/").split("/")[-1]
    nombre = _RE_PROHIBIDOS.sub("_", _RE_CONTROL.sub("", nombre)).strip(" .")
    return nombre


def validar_adjunto(nombre: str, contenido: bytes) -> dict:
    """Devuelve {'nombre', 'tipo', 'tamano'} o lanza ValueError con un mensaje listo para mostrar."""
    if not isinstance(contenido, (bytes, bytearray)):
        raise ValueError("No se pudo leer el archivo.")
    limpio = limpiar_nombre(nombre)
    if not limpio:
        raise ValueError("El archivo no tiene un nombre válido.")
    if len(limpio) > LIM_NOMBRE_ARCHIVO:
        raise ValueError(f"El nombre del archivo es demasiado largo (máximo {LIM_NOMBRE_ARCHIVO} caracteres).")

    extension = os.path.splitext(limpio)[1].lower()
    if extension not in _TIPOS:
        raise ValueError(f"No se aceptan archivos «{extension or 'sin extensión'}». "
                         f"Permitidos: {', '.join(EXTENSIONES_PERMITIDAS)}.")
    if len(contenido) == 0:
        raise ValueError(f"El archivo «{limpio}» está vacío.")
    if len(contenido) > MAX_TAMANO_ADJUNTO:
        raise ValueError(f"El archivo «{limpio}» pesa {formato_tamano(len(contenido))}; "
                         f"el máximo es {formato_tamano(MAX_TAMANO_ADJUNTO)}.")

    tipo, firmas = _TIPOS[extension]
    if firmas is None:                                    # texto plano: sin bytes nulos y legible
        if b"\x00" in contenido[:4096]:
            raise ValueError(f"El contenido de «{limpio}» no corresponde a un archivo de texto.")
    elif not any(bytes(contenido[:len(f)]) == f for f in firmas):
        raise ValueError(f"El contenido de «{limpio}» no corresponde a su extensión ({extension}).")
    return {"nombre": limpio, "tipo": tipo, "tamano": len(contenido)}
