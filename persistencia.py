"""
Persistencia en disco y respaldos (RNF-09). Hace que los datos sobrevivan al cerrar la
aplicación y que el administrador pueda respaldarlos y restaurarlos.

Carpeta de datos (por defecto ``datos_sigsat/`` junto al programa; cámbiala con la variable de
entorno ``SIGSAT_DATOS``)::

    datos_sigsat/
    ├── estado.json        todo el estado (cuentas con hash, solicitudes, bitácora, catálogos…)
    ├── adjuntos/          un archivo por adjunto (1.bin, 2.bin…)
    ├── respaldos/         copias .zip: una automática por día (se conservan 14) y las manuales
    └── correos_salida/    correos en modo desarrollo (.eml)

* El guardado es **atómico**: se escribe un archivo temporal y se reemplaza el anterior, así un
  corte de luz a media escritura no deja el archivo a medias.
* Antes de aplicar cualquier dato leído (al abrir o al restaurar) se valida la estructura y que la
  cadena de hashes de la bitácora esté íntegra; si algo no cuadra no se toca el estado actual.
* Restaurar crea primero un respaldo de seguridad del estado actual (``antes_de_restaurar``).

Limitaciones (prototipo): los archivos no están cifrados (las contraseñas sí van con hash) y los
bloqueos por intentos fallidos viven solo en memoria. En el entorno real el cifrado en reposo y los
respaldos programados fuera del equipo corresponden a la base de datos del servidor.
"""

import json
import logging
import os
import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import correo
import datos

log = logging.getLogger("sigsat.persistencia")

NOMBRE_ESTADO = "estado.json"
RETENCION_AUTOMATICOS = 14       # días de respaldos automáticos que se conservan
RETENCION_MANUALES = 30          # respaldos manuales / de seguridad que se conservan
_MAX_ESTADO_BYTES = 100 * 1024 * 1024
_MAX_ADJUNTO_BYTES = 10 * 1024 * 1024
_RE_ADJUNTO = re.compile(r"^adjuntos/(\d{1,9})\.bin$")
_RE_RESPALDO = re.compile(r"^sigsat_(auto|manual|antes_de_restaurar|antes_de_reiniciar|antes_de_actualizar)_(\d{8})(?:_(\d{6}))?\.zip$")

_estado = {"carpeta": None, "ultimo_guardado": None, "ultimo_error": None}


class ErrorPersistencia(Exception):
    """No se pudo leer o restaurar un archivo de datos (mensaje listo para mostrar)."""


class DatosDeOtraVersion(ErrorPersistencia):
    """Los datos guardados son de una versión anterior de la aplicación y no se pueden cargar."""


# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------

def carpeta_por_defecto() -> Path:
    return Path(os.environ.get("SIGSAT_DATOS") or Path(__file__).resolve().parent / "datos_sigsat")


def activa() -> bool:
    return _estado["carpeta"] is not None


def carpeta() -> Path:
    return _estado["carpeta"]


def _ruta_estado() -> Path:
    return _estado["carpeta"] / NOMBRE_ESTADO


def _dir_adjuntos() -> Path:
    return _estado["carpeta"] / "adjuntos"


def _dir_respaldos() -> Path:
    return _estado["carpeta"] / "respaldos"


def carpeta_respaldos() -> Path:
    return _dir_respaldos()


def informacion() -> dict:
    """Datos para mostrar en pantalla: dónde se guarda y cuándo fue el último guardado."""
    return dict(_estado)


def _privado(ruta: Path) -> None:
    try:
        os.chmod(ruta, 0o700 if ruta.is_dir() else 0o600)
    except OSError:                                              # Windows: los permisos los da la carpeta
        pass


def _escribir_atomico(destino: Path, contenido: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=destino.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)
        _privado(destino)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# Activar, guardar y cargar
# --------------------------------------------------------------------------

def activar(ruta=None, reiniciar: bool = False) -> str:
    """Activa la persistencia en `ruta`. Si ya hay datos guardados los carga; si no, guarda los de
    ejemplo. `reiniciar=True` descarta lo guardado y vuelve a los datos de ejemplo (antes hace un
    respaldo). Devuelve 'cargado' | 'nuevo' | 'reiniciado' | 'recuperado' | 'actualizado'
    ('recuperado' = el archivo estaba dañado y se restauró el último respaldo; 'actualizado' = los datos
    eran de una versión anterior de la aplicación: se guardó una copia y se abrió con datos de ejemplo)."""
    carpeta_datos = Path(ruta) if ruta else carpeta_por_defecto()
    carpeta_datos.mkdir(parents=True, exist_ok=True)
    _privado(carpeta_datos)
    _estado.update(carpeta=carpeta_datos, ultimo_error=None)
    correo.configurar(carpeta=carpeta_datos / "correos_salida")

    resultado = "nuevo"
    if reiniciar:
        if _ruta_estado().exists():
            _respaldar_archivos_en_disco("antes_de_reiniciar")     # lo que HAY en disco, no lo que hay en memoria
        datos.reiniciar()
        resultado = "reiniciado"
    elif _ruta_estado().exists():
        try:
            cargar()
            resultado = "cargado"
        except DatosDeOtraVersion as error:
            log.warning("Datos de otra versión: %s", error)
            _respaldar_archivos_en_disco("antes_de_actualizar")      # nada se pierde: queda una copia
            datos.reiniciar()
            resultado = "actualizado"
        except ErrorPersistencia as error:
            log.error("No se pudo cargar el estado: %s", error)
            resultado = _recuperar_de_respaldo(error)
    guardar()
    datos.registrar_observador(_al_cambiar)
    return resultado


def desactivar() -> None:
    """Apaga la persistencia (la usan las pruebas)."""
    datos.registrar_observador(None)
    _estado.update(carpeta=None, ultimo_guardado=None, ultimo_error=None)
    correo.configurar(carpeta=None)


def _al_cambiar() -> None:
    try:
        guardar()
    except Exception as error:                                   # p. ej. disco lleno: se avisa, no se cae
        _estado["ultimo_error"] = str(error)
        raise


def guardar() -> None:
    """Escribe el estado completo en disco (atómico)."""
    if not activa():
        return
    estado = datos.exportar_estado()
    estado["guardado_en"] = datetime.now().isoformat(timespec="seconds")
    contenidos = datos.contenidos_adjuntos()

    carpeta_adj = _dir_adjuntos()
    carpeta_adj.mkdir(parents=True, exist_ok=True)
    _privado(carpeta_adj)
    existentes = {p.name for p in carpeta_adj.glob("*.bin")}
    for id_adjunto, contenido in contenidos.items():
        nombre = f"{id_adjunto}.bin"
        if nombre not in existentes:
            _escribir_atomico(carpeta_adj / nombre, contenido)
    for sobrante in existentes - {f"{i}.bin" for i in contenidos}:
        try:
            (carpeta_adj / sobrante).unlink()
        except OSError:
            pass

    _escribir_atomico(_ruta_estado(), json.dumps(estado, ensure_ascii=False, indent=1).encode("utf-8"))
    _estado.update(ultimo_guardado=datetime.now(), ultimo_error=None)


def _leer_estado(texto: bytes, leer_adjunto) -> None:
    try:
        estado = json.loads(texto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ErrorPersistencia(f"El archivo de datos está dañado ({error}).") from error
    if not isinstance(estado, dict):
        raise ErrorPersistencia("El archivo de datos no tiene el formato esperado.")
    contenidos = {}
    for a in estado.get("adjuntos", []):
        try:
            contenidos[int(a["id"])] = leer_adjunto(int(a["id"]))
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise ErrorPersistencia(f"Falta un archivo adjunto ({error}).") from error
    try:
        datos.importar_estado(estado, contenidos)
    except datos.VersionIncompatible as error:
        raise DatosDeOtraVersion(f"Estos datos son de otra versión de SIGSAT y no se pueden cargar ({error}).") from error
    except ValueError as error:
        raise ErrorPersistencia(str(error)) from error


def cargar() -> None:
    """Reemplaza el estado en memoria por el guardado en disco (lanza ErrorPersistencia si no es válido)."""
    try:
        texto = _ruta_estado().read_bytes()
    except OSError as error:
        raise ErrorPersistencia(f"No se pudo leer el archivo de datos ({error}).") from error
    _leer_estado(texto, lambda i: (_dir_adjuntos() / f"{i}.bin").read_bytes())


def _recuperar_de_respaldo(error_original: ErrorPersistencia) -> str:
    dañado = _ruta_estado().with_name(f"estado_danado_{datetime.now():%Y%m%d_%H%M%S}.json")
    try:
        _ruta_estado().replace(dañado)                           # el archivo malo se conserva para revisarlo
    except OSError:
        pass
    for r in listar_respaldos():
        try:
            restaurar_respaldo(r["ruta"], respaldo_previo=False)
            log.warning("Se restauró el respaldo %s", r["nombre"])
            return "recuperado"
        except ErrorPersistencia:
            continue
    datos.reiniciar()
    log.warning("No hubo respaldo utilizable; se empieza con los datos de ejemplo (%s)", error_original)
    return "nuevo"


# --------------------------------------------------------------------------
# Respaldos
# --------------------------------------------------------------------------

def _nombre_respaldo(tipo: str, cuando: datetime) -> str:
    if tipo == "auto":
        return f"sigsat_auto_{cuando:%Y%m%d}.zip"                # uno por día
    return f"sigsat_{tipo}_{cuando:%Y%m%d_%H%M%S}.zip"


def crear_respaldo(tipo: str = "manual") -> Path:
    """Crea un .zip con el estado y los adjuntos. tipo: 'auto' | 'manual' | 'antes_de_restaurar' | 'antes_de_reiniciar'."""
    if not activa():
        raise ErrorPersistencia("La persistencia no está activa: no hay datos guardados que respaldar.")
    ahora = datetime.now()
    estado = datos.exportar_estado()
    estado["guardado_en"] = ahora.isoformat(timespec="seconds")
    destino = _dir_respaldos() / _nombre_respaldo(tipo, ahora)
    destino.parent.mkdir(parents=True, exist_ok=True)
    _privado(destino.parent)

    fd, tmp = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(NOMBRE_ESTADO, json.dumps(estado, ensure_ascii=False, indent=1))
            for i, contenido in datos.contenidos_adjuntos().items():
                z.writestr(f"adjuntos/{i}.bin", contenido)
            z.writestr("LEEME.txt", f"Respaldo de SIGSAT ({tipo}) creado el {ahora:%Y-%m-%d %H:%M:%S}.\n"
                                    "Se restaura desde Administración → Respaldos.\n")
        os.replace(tmp, destino)
        _privado(destino)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _depurar_respaldos()
    return destino


def _respaldar_archivos_en_disco(tipo: str) -> Path:
    """Respalda los archivos guardados tal como están (sin pasar por la memoria). Sirve aunque el archivo
    de datos esté dañado: es la red de seguridad antes de descartar lo guardado."""
    ahora = datetime.now()
    destino = _dir_respaldos() / _nombre_respaldo(tipo, ahora)
    destino.parent.mkdir(parents=True, exist_ok=True)
    _privado(destino.parent)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(_ruta_estado(), NOMBRE_ESTADO)
            if _dir_adjuntos().exists():
                for f in sorted(_dir_adjuntos().glob("*.bin")):
                    if f.stem.isdigit():
                        z.write(f, f"adjuntos/{f.name}")
            z.writestr("LEEME.txt", f"Copia de los datos tal como estaban en disco ({tipo}), {ahora:%Y-%m-%d %H:%M:%S}.\n")
        os.replace(tmp, destino)
        _privado(destino)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _depurar_respaldos()
    return destino


def listar_respaldos() -> list:
    """Respaldos disponibles, el más reciente primero."""
    if not activa() or not _dir_respaldos().exists():
        return []
    res = []
    for p in _dir_respaldos().glob("sigsat_*.zip"):
        m = _RE_RESPALDO.match(p.name)
        if not m:
            continue
        hora = m.group(3) or "000000"
        res.append({"nombre": p.name, "ruta": p, "tipo": m.group(1), "tamano": p.stat().st_size,
                    "fecha": datetime.strptime(m.group(2) + hora, "%Y%m%d%H%M%S")})
    res.sort(key=lambda r: (r["fecha"], r["nombre"]), reverse=True)
    return res


def _depurar_respaldos() -> None:
    """Conserva los últimos 14 respaldos automáticos y los últimos 30 de los demás tipos."""
    for es_auto, limite in ((True, RETENCION_AUTOMATICOS), (False, RETENCION_MANUALES)):
        grupo = [r for r in listar_respaldos() if (r["tipo"] == "auto") == es_auto]
        for r in grupo[limite:]:
            try:
                r["ruta"].unlink()
            except OSError:
                pass


def respaldo_diario():
    """Crea el respaldo automático de hoy si todavía no existe. Devuelve su ruta o None si ya estaba."""
    if not activa():
        return None
    if (_dir_respaldos() / _nombre_respaldo("auto", datetime.now())).exists():
        return None
    return crear_respaldo("auto")


def restaurar_respaldo(ruta, respaldo_previo: bool = True) -> dict:
    """Reemplaza TODOS los datos por los de un respaldo. Valida el .zip (nombres de archivo seguros,
    tamaños, estructura y bitácora íntegra) antes de aplicar nada y, por seguridad, hace primero un
    respaldo del estado actual. Lanza ErrorPersistencia con un mensaje claro si no se puede."""
    if not activa():
        raise ErrorPersistencia("La persistencia no está activa.")
    try:
        with zipfile.ZipFile(ruta) as z:
            infos = {i.filename: i for i in z.infolist()}
            for nombre, info in infos.items():
                if nombre not in (NOMBRE_ESTADO, "LEEME.txt") and not _RE_ADJUNTO.match(nombre):
                    raise ErrorPersistencia(f"El respaldo contiene un archivo no permitido ({nombre!r}).")
                limite = _MAX_ESTADO_BYTES if nombre == NOMBRE_ESTADO else _MAX_ADJUNTO_BYTES
                if info.file_size > limite:
                    raise ErrorPersistencia(f"El archivo {nombre!r} del respaldo es demasiado grande.")
            if NOMBRE_ESTADO not in infos:
                raise ErrorPersistencia("El respaldo no contiene los datos (falta estado.json).")
            texto = z.read(NOMBRE_ESTADO)
            if respaldo_previo and activa():
                crear_respaldo("antes_de_restaurar")
            _leer_estado(texto, lambda i: z.read(f"adjuntos/{i}.bin"))
    except zipfile.BadZipFile as error:
        raise ErrorPersistencia("El archivo de respaldo está dañado o no es un .zip válido.") from error
    except KeyError as error:
        raise ErrorPersistencia(f"Al respaldo le falta un archivo ({error}).") from error
    guardar()
    return {"solicitudes": len(datos.exportar_estado()["solicitudes"]), "usuarios": len(datos.usuarios_todos())}
