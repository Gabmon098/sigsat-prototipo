"""
Modelo de datos del prototipo SIGSAT.

Esta capa simula la base de datos con estructuras en memoria. Los datos pueden
guardarse en disco y respaldarse con `persistencia.py` (la interfaz no cambia):
aquí no se sabe nada de archivos, solo de reglas de negocio.

Roles: **Representante de Área** (levanta las solicitudes; pertenece a un área y a una sucursal),
**Técnico** (atiende los reportes y informa su avance) y **Administrador** (mantenimiento del sistema,
distribución de las solicitudes y verificación de reportes y avances).

Qué hace que esta capa se parezca a una base de datos real:

* Cada cuenta, solicitud, área, sucursal, tipo y conversación tiene un **id**; las relaciones
  se guardan por id (solicitante_id, agente_id, area_id…), no por nombre. Así
  renombrar un área o a una persona se refleja solo en todo el historial. (Por herencia del
  prototipo, `agente_id` es el **técnico** asignado.)
* Las **reglas de negocio y validaciones viven aquí**, no en la interfaz: la UI solo
  muestra el resultado. Las funciones devuelven códigos de estado ('ok',
  'sin_cambios', ...) o lanzan ValueError / PermissionError con un mensaje claro.
* Las contraseñas se guardan con hash (seguridad.py), nunca en texto plano.
* **La bitácora es inmutable** (RNF-13): solo se agregan entradas, cada una queda
  encadenada con la anterior mediante un hash SHA-256 y `verificar_bitacora()`
  detecta cualquier alteración o borrado. Las solicitudes nunca se eliminan y una
  cuenta con historial se desactiva en lugar de borrarse.
* Los **catálogos** (áreas, sucursales y tipos de solicitud) solo permiten **agregar**: por regla del
  proyecto no se editan ni se eliminan. Cada tipo de solicitud lleva su **tiempo estimado de solución**
  (horas): de él salen la **prioridad** (menos tiempo, más prioridad) y la fecha límite de atención.
* **Ciclo del reporte** (lo informa el técnico): Sin visualizar → Visualizado → En proceso → Finalizado.
  Al finalizarse, el representante **califica** el servicio (1 a 5); la calificación no cambia el estatus.
* El Administrador **distribuye** las solicitudes (no hay asignación automática): una solicitud nueva queda
  «Sin asignar» hasta que él la asigna a un técnico.

Las funciones que devuelven solicitudes o conversaciones entregan copias
(diccionarios "de lectura") con los nombres ya resueltos: la interfaz no puede
modificar el estado interno por accidente.
"""

import functools
import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import archivos
import notificaciones
import seguridad
from permisos import puede, ROL_REPRESENTANTE, ROL_TECNICO, ROL_ADMINISTRADOR

log = logging.getLogger("sigsat.datos")

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

# Estatus del reporte, en el orden del flujo. Solo el técnico asignado los avanza (nunca retroceden);
# «Finalizado» es el último: después, el representante califica el servicio.
ESTADOS = ["Sin visualizar", "Visualizado", "En proceso", "Finalizado"]
ESTADO_FINAL = "Finalizado"
ESTADOS_TECNICO = ESTADOS[1:]           # lo que el técnico puede elegir («Sin visualizar» lo pone el sistema al asignar)
ESTADOS_SIN_ATENCION = (ESTADO_FINAL,)  # ya no se modifican
PRIORIDADES = ["Baja", "Media", "Alta"]
ROLES = [ROL_REPRESENTANTE, ROL_TECNICO, ROL_ADMINISTRADOR]
ESTADOS_CONVERSACION = ["Abierta", "En atención", "Cerrada"]

# Límites de longitud (la interfaz los aplica al escribir; aquí se verifican de nuevo)
LIM_NOMBRE = 100
LIM_USUARIO = 40
LIM_CORREO = 120
LIM_DESCRIPCION = 2000
LIM_COMENTARIO = 1000
LIM_ASUNTO = 150
LIM_MENSAJE = 2000
LIM_CATALOGO = 60
MIN_CONTRASENA = 8
MAX_CONTRASENA = 128

# Tiempo estimado de solución (RF-16): cada tipo de solicitud lo trae en horas; es también el plazo de atención
# (corre desde que se registra la solicitud). De él sale la prioridad: cuanto menor es el tiempo, mayor la prioridad.
LIMITE_ALTA_H = 24                      # hasta 24 h → Alta
LIMITE_MEDIA_H = 72                     # hasta 72 h → Media; más → Baja
MAX_HORAS_TIPO = 720


def prioridad_por_horas(horas: int) -> str:
    """Prioridad que corresponde a un tiempo estimado de solución (en horas)."""
    return "Alta" if horas <= LIMITE_ALTA_H else "Media" if horas <= LIMITE_MEDIA_H else "Baja"


# Recuperación de contraseña
CODIGO_VIGENCIA_MIN = 30
CODIGO_MAX_INTENTOS = 5                 # intentos equivocados con un mismo código
RECUPERACION_MAX_POR_CUENTA_HORA = 3
RECUPERACION_MAX_GLOBAL_HORA = 10
CUENTAS_MAX_POR_HORA = 20             # límite global de cuentas que se pueden registrar por hora (evita inundar el sistema)
_ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"      # sin 0/O/1/I/L para no confundir al copiarlo
_LARGO_CODIGO = 8

_FORMATO_FECHA = "%Y-%m-%d %H:%M"
_FORMATO_FECHA_SEG = "%Y-%m-%d %H:%M:%S"          # la bitácora lleva la hora exacta (con segundos)
_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GENESIS = "0" * 64

# --------------------------------------------------------------------------
# Estado interno (no usar fuera de este módulo)
# --------------------------------------------------------------------------

_AREAS = []                  # {"id", "nombre", "activa"}
_SUCURSALES = []             # {"id", "nombre", "activa"}
_TIPOS = []                  # {"id", "nombre", "horas" (tiempo estimado), "activo"}
_USUARIOS = []
_SOLICITUDES = []
_ADJUNTOS = []
_CONVERSACIONES = []
_CODIGOS = []                # códigos de recuperación (solo su hash)
_contadores = {"usuario": 0, "solicitud": 0, "conversacion": 0, "area": 0, "tipo": 0, "adjunto": 0, "codigo": 0,
               "bitacora": 0, "sucursal": 0}      # "bitacora" cuenta TODAS las entradas escritas: permite notar si se borró alguna
_limitador = seguridad.LimitadorIntentos()
_registros_recientes = []             # instantes de las cuentas registradas, para el límite global
_solicitudes_recuperacion = []      # instantes (datetime) de las solicitudes de código, para el límite global

_observador = None           # función que se llama después de cada cambio (la usa persistencia.py)


def registrar_observador(funcion) -> None:
    """persistencia.py se registra aquí para guardar en disco después de cada cambio."""
    global _observador
    _observador = funcion


def _cambio() -> None:
    if _observador is not None:
        try:
            _observador()
        except Exception:                                  # guardar nunca debe romper la operación
            log.exception("No se pudo guardar el estado")


def _mutador(funcion):
    """Marca una función pública que modifica datos: al terminar bien, avisa al observador."""
    @functools.wraps(funcion)
    def envoltura(*args, **kwargs):
        resultado = funcion(*args, **kwargs)
        _cambio()
        return resultado
    return envoltura


def _ahora() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def _hace(dias: int) -> datetime:
    return _ahora() - timedelta(days=dias)


def _ahora_exacta() -> datetime:
    """Momento actual al segundo (para la bitácora: la hora exacta del evento y un orden fiable)."""
    return datetime.now().replace(microsecond=0)


def _fmt(fecha):
    return fecha.strftime(_FORMATO_FECHA) if fecha else None


def _fmt_seg(fecha):
    return fecha.strftime(_FORMATO_FECHA_SEG) if fecha else None


# --------------------------------------------------------------------------
# Catálogos: áreas, sucursales y tipos de solicitud (RF-04) y tiempos de atención (RF-16)
# --------------------------------------------------------------------------

def _area_por_id(aid):
    return next((a for a in _AREAS if a["id"] == aid), None)


def _area_por_nombre(nombre, solo_activas=False):
    n = (nombre or "").strip().lower()
    return next((a for a in _AREAS if a["nombre"].lower() == n and (a["activa"] or not solo_activas)), None)


def _sucursal_por_id(sid):
    return next((x for x in _SUCURSALES if x["id"] == sid), None)


def _sucursal_por_nombre(nombre, solo_activas=False):
    n = (nombre or "").strip().lower()
    return next((x for x in _SUCURSALES if x["nombre"].lower() == n and (x["activa"] or not solo_activas)), None)


def _tipo_por_id(tid):
    return next((t for t in _TIPOS if t["id"] == tid), None)


def _tipo_por_nombre(nombre, solo_activos=False):
    n = (nombre or "").strip().lower()
    return next((t for t in _TIPOS if t["nombre"].lower() == n and (t["activo"] or not solo_activos)), None)


def _nombre_area(aid):
    a = _area_por_id(aid) if aid is not None else None
    return a["nombre"] if a else None


def _nombre_sucursal(sid):
    x = _sucursal_por_id(sid) if sid is not None else None
    return x["nombre"] if x else None


def areas_activas() -> list:
    """Nombres de las áreas activas (las que se pueden elegir al crear o pedir una cuenta de representante)."""
    return [a["nombre"] for a in _AREAS if a["activa"]]


def sucursales_activas() -> list:
    """Nombres de las sucursales activas (las que se pueden elegir al crear o pedir una cuenta de representante)."""
    return [x["nombre"] for x in _SUCURSALES if x["activa"]]


def tipos_activos() -> list:
    """Nombres de los tipos de solicitud que se pueden elegir al registrar una solicitud."""
    return [t["nombre"] for t in _TIPOS if t["activo"]]


def prioridad_de_tipo(tipo: str):
    """Prioridad que corresponde a un tipo de solicitud según su tiempo estimado (None si el tipo no existe).
    La asigna el catálogo: el representante no la elige."""
    t = _tipo_por_nombre(tipo)
    return prioridad_por_horas(t["horas"]) if t else None


def horas_de_tipo(tipo: str):
    """Tiempo estimado de solución (horas) de un tipo de solicitud; None si el tipo no existe."""
    t = _tipo_por_nombre(tipo)
    return t["horas"] if t else None


def _exigir(actor: dict, permiso: str, mensaje: str):
    if not actor or not puede(actor, permiso):
        raise PermissionError(mensaje)


def _validar_nombre_catalogo(nombre, existentes, excluir_id=None, etiqueta="El nombre") -> str:
    nombre = " ".join((nombre or "").split())
    if len(nombre) < 2:
        raise ValueError(f"{etiqueta} debe tener al menos 2 caracteres.")
    if len(nombre) > LIM_CATALOGO:
        raise ValueError(f"{etiqueta} es demasiado largo (máximo {LIM_CATALOGO} caracteres).")
    if any(e["nombre"].lower() == nombre.lower() and e["id"] != excluir_id for e in existentes):
        raise ValueError(f"Ya existe «{nombre}». Elige otro nombre.")
    return nombre


def _representantes_activos_de(area_id) -> list:
    return [u for u in _USUARIOS if u["rol"] == ROL_REPRESENTANTE and u["activo"] and u["area_id"] == area_id]


def _representantes_activos_en(sucursal_id) -> list:
    return [u for u in _USUARIOS if u["rol"] == ROL_REPRESENTANTE and u["activo"] and u["sucursal_id"] == sucursal_id]


def areas_todas() -> list:
    """Todas las áreas con el número de representantes activos que pertenecen a ellas."""
    return [{"id": a["id"], "nombre": a["nombre"], "activa": a["activa"],
             "representantes": len(_representantes_activos_de(a["id"]))} for a in _AREAS]


def sucursales_todas() -> list:
    """Todas las sucursales con el número de representantes activos que pertenecen a ellas."""
    return [{"id": x["id"], "nombre": x["nombre"], "activa": x["activa"],
             "representantes": len(_representantes_activos_en(x["id"]))} for x in _SUCURSALES]


def tipos_todos() -> list:
    return [{"id": t["id"], "nombre": t["nombre"], "horas": t["horas"], "prioridad": prioridad_por_horas(t["horas"]),
             "activo": t["activo"], "solicitudes": sum(1 for s in _SOLICITUDES if s["tipo_id"] == t["id"])}
            for t in _TIPOS]


def rangos_prioridad() -> list:
    """Cómo se clasifican las prioridades (de mayor a menor) y qué tipos de solicitud cae en cada una."""
    reglas = {"Alta": f"hasta {LIMITE_ALTA_H} horas", "Media": f"de {LIMITE_ALTA_H + 1} a {LIMITE_MEDIA_H} horas",
              "Baja": f"más de {LIMITE_MEDIA_H} horas"}
    return [{"prioridad": p, "regla": reglas[p],
             "tipos": [t["nombre"] for t in _TIPOS if t["activo"] and prioridad_por_horas(t["horas"]) == p]}
            for p in reversed(PRIORIDADES)]


@_mutador
def crear_area(actor: dict, nombre: str) -> dict:
    _exigir(actor, "catalogos.crear", "Tu rol no puede administrar los catálogos.")
    nombre = _validar_nombre_catalogo(nombre, _AREAS, etiqueta="El nombre del área")
    _contadores["area"] += 1
    a = {"id": _contadores["area"], "nombre": nombre, "activa": True}
    _AREAS.append(a)
    return dict(a)


@_mutador
def crear_sucursal(actor: dict, nombre: str) -> dict:
    _exigir(actor, "catalogos.crear", "Tu rol no puede administrar los catálogos.")
    nombre = _validar_nombre_catalogo(nombre, _SUCURSALES, etiqueta="El nombre de la sucursal")
    _contadores["sucursal"] += 1
    x = {"id": _contadores["sucursal"], "nombre": nombre, "activa": True}
    _SUCURSALES.append(x)
    return dict(x)


@_mutador
def actualizar_area(actor: dict, area_id: int, nombre: str, activa: bool = True) -> dict:
    """Renombra un área y/o la activa o desactiva. DESHABILITADO por regla del proyecto: ningún rol
    tiene el permiso `catalogos.editar`. No se puede desactivar un área con representantes activos o
    solicitudes sin finalizar."""
    _exigir(actor, "catalogos.editar", "Los catálogos no se pueden editar.")
    a = _area_por_id(area_id)
    if not a:
        raise ValueError("No encontramos esa área.")
    nombre = _validar_nombre_catalogo(nombre, _AREAS, area_id, "El nombre del área")
    if a["activa"] and not activa:
        _verificar_area_desactivable(a)
    a["nombre"], a["activa"] = nombre, bool(activa)
    return dict(a)


def _verificar_area_desactivable(a: dict) -> None:
    if _representantes_activos_de(a["id"]):
        raise ValueError(f"No se puede desactivar «{a['nombre']}»: todavía tiene representantes activos. Cámbialos de área primero.")
    if any(s["area_id"] == a["id"] and s["estado"] not in ESTADOS_SIN_ATENCION for s in _SOLICITUDES):
        raise ValueError(f"No se puede desactivar «{a['nombre']}»: tiene solicitudes sin finalizar.")


@_mutador
def eliminar_area(actor: dict, area_id: int) -> str:
    """Sin historial se borra; con historial se desactiva. DESHABILITADO por regla del proyecto: ningún
    rol tiene el permiso `catalogos.eliminar`. Devuelve 'eliminada' o 'desactivada'."""
    _exigir(actor, "catalogos.eliminar", "Los catálogos no se pueden eliminar.")
    a = _area_por_id(area_id)
    if not a:
        raise ValueError("No encontramos esa área.")
    _verificar_area_desactivable(a)
    en_uso = any(u["area_id"] == area_id for u in _USUARIOS) or any(s["area_id"] == area_id for s in _SOLICITUDES)
    if en_uso:
        a["activa"] = False
        return "desactivada"
    _AREAS.remove(a)
    return "eliminada"


def _verificar_sucursal_desactivable(x: dict) -> None:
    if _representantes_activos_en(x["id"]):
        raise ValueError(f"No se puede desactivar «{x['nombre']}»: todavía tiene representantes activos. Cámbialos de sucursal primero.")
    if any(s["sucursal_id"] == x["id"] and s["estado"] not in ESTADOS_SIN_ATENCION for s in _SOLICITUDES):
        raise ValueError(f"No se puede desactivar «{x['nombre']}»: tiene solicitudes sin finalizar.")


@_mutador
def actualizar_sucursal(actor: dict, sucursal_id: int, nombre: str, activa: bool = True) -> dict:
    """Renombra una sucursal y/o la activa o desactiva. DESHABILITADO por regla del proyecto: ningún rol
    tiene el permiso `catalogos.editar`."""
    _exigir(actor, "catalogos.editar", "Los catálogos no se pueden editar.")
    x = _sucursal_por_id(sucursal_id)
    if not x:
        raise ValueError("No encontramos esa sucursal.")
    nombre = _validar_nombre_catalogo(nombre, _SUCURSALES, sucursal_id, "El nombre de la sucursal")
    if x["activa"] and not activa:
        _verificar_sucursal_desactivable(x)
    x["nombre"], x["activa"] = nombre, bool(activa)
    return dict(x)


@_mutador
def eliminar_sucursal(actor: dict, sucursal_id: int) -> str:
    """Sin historial se borra; con historial se desactiva. DESHABILITADO por regla del proyecto: ningún
    rol tiene el permiso `catalogos.eliminar`. Devuelve 'eliminada' o 'desactivada'."""
    _exigir(actor, "catalogos.eliminar", "Los catálogos no se pueden eliminar.")
    x = _sucursal_por_id(sucursal_id)
    if not x:
        raise ValueError("No encontramos esa sucursal.")
    _verificar_sucursal_desactivable(x)
    if any(u["sucursal_id"] == sucursal_id for u in _USUARIOS) or any(s["sucursal_id"] == sucursal_id for s in _SOLICITUDES):
        x["activa"] = False
        return "desactivada"
    _SUCURSALES.remove(x)
    return "eliminada"


def _validar_horas(horas) -> int:
    if isinstance(horas, bool) or not isinstance(horas, int) or not 1 <= horas <= MAX_HORAS_TIPO:
        raise ValueError(f"Escribe el tiempo estimado de solución en horas (de 1 a {MAX_HORAS_TIPO}).")
    return horas


@_mutador
def crear_tipo(actor: dict, nombre: str, horas: int) -> dict:
    """Agrega un tipo de solicitud con su tiempo estimado de solución (horas): de él se calculan la prioridad
    (menos tiempo, más prioridad) y la fecha límite de sus solicitudes."""
    _exigir(actor, "catalogos.crear", "Tu rol no puede administrar los catálogos.")
    nombre = _validar_nombre_catalogo(nombre, _TIPOS, etiqueta="El nombre del tipo")
    horas = _validar_horas(horas)
    _contadores["tipo"] += 1
    t = {"id": _contadores["tipo"], "nombre": nombre, "horas": horas, "activo": True}
    _TIPOS.append(t)
    return dict(t)


@_mutador
def actualizar_tipo(actor: dict, tipo_id: int, nombre: str, horas: int, activo: bool = True) -> dict:
    """Edita un tipo. DESHABILITADO por regla del proyecto (permiso `catalogos.editar`). Los cambios de
    tiempo aplican a las solicitudes NUEVAS; las que ya existen conservan el suyo."""
    _exigir(actor, "catalogos.editar", "Los catálogos no se pueden editar.")
    t = _tipo_por_id(tipo_id)
    if not t:
        raise ValueError("No encontramos ese tipo de solicitud.")
    nombre = _validar_nombre_catalogo(nombre, _TIPOS, tipo_id, "El nombre del tipo")
    t["nombre"], t["horas"], t["activo"] = nombre, _validar_horas(horas), bool(activo)
    return dict(t)


@_mutador
def eliminar_tipo(actor: dict, tipo_id: int) -> str:
    """DESHABILITADO por regla del proyecto (permiso `catalogos.eliminar`)."""
    _exigir(actor, "catalogos.eliminar", "Los catálogos no se pueden eliminar.")
    t = _tipo_por_id(tipo_id)
    if not t:
        raise ValueError("No encontramos ese tipo de solicitud.")
    if any(s["tipo_id"] == tipo_id for s in _SOLICITUDES):
        t["activo"] = False
        return "desactivado"
    _TIPOS.remove(t)
    return "eliminado"


# --------------------------------------------------------------------------
# Usuarios y autenticación
# --------------------------------------------------------------------------

def _usuario_por_id(uid):
    return next((u for u in _USUARIOS if u["id"] == uid), None)


def _nombre(uid) -> str:
    """Nombre para mostrar de un autor; None = el Sistema."""
    u = _usuario_por_id(uid) if uid is not None else None
    return u["nombre"] if u else "Sistema"


def _publico(u: dict) -> dict:
    """Cuenta sin el hash de la contraseña: lo único que sale de esta capa."""
    return {"id": u["id"], "nombre": u["nombre"], "usuario": u["usuario"], "correo": u["correo"],
            "rol": u["rol"], "area": _nombre_area(u["area_id"]), "area_id": u["area_id"],
            "sucursal": _nombre_sucursal(u["sucursal_id"]), "sucursal_id": u["sucursal_id"], "activo": u["activo"]}


def _alta_usuario(nombre, usuario, contrasena, rol, area, correo, sucursal=None) -> dict:
    """Área y sucursal solo aplican al Representante de Área (el Técnico y el Administrador no las llevan)."""
    _contadores["usuario"] += 1
    a = _area_por_nombre(area) if rol == ROL_REPRESENTANTE else None
    suc = _sucursal_por_nombre(sucursal) if rol == ROL_REPRESENTANTE else None
    u = {
        "id": _contadores["usuario"],
        "nombre": nombre.strip(),
        "usuario": usuario.strip(),
        "correo": correo.strip(),
        "contrasena_hash": seguridad.hashear_contrasena(contrasena),
        "rol": rol,
        "area_id": a["id"] if a else None,
        "sucursal_id": suc["id"] if suc else None,
        "activo": True,
    }
    _USUARIOS.append(u)
    return u


def _cuenta_por_identificador(identificador: str, solo_activas=True):
    ident = (identificador or "").strip().lower()
    return next((u for u in _USUARIOS
                 if (u["activo"] or not solo_activas) and ident in (u["usuario"].lower(), u["correo"].lower())), None)


def autenticar(identificador: str, contrasena: str):
    """Valida usuario o correo + contraseña. Devuelve la cuenta (sin hash) o
    None. El rol lo determina la cuenta. Solo entran cuentas activas.

    Lanza seguridad.BloqueoTemporal si hubo demasiados intentos fallidos. El límite se
    lleva por CUENTA: escribir el usuario o el correo de la misma cuenta cuenta contra el
    mismo límite; si la cuenta no existe, se lleva por lo escrito (no se nota la diferencia)."""
    ident = (identificador or "").strip().lower()
    cuenta = _cuenta_por_identificador(ident)
    clave = f"id:{cuenta['id']}" if cuenta else f"u:{ident[:150]}"

    espera = _limitador.segundos_restantes(clave)
    if espera:
        raise seguridad.BloqueoTemporal(espera)

    hash_a_probar = cuenta["contrasena_hash"] if cuenta else seguridad.HASH_RELLENO
    correcta = seguridad.verificar_contrasena(contrasena or "", hash_a_probar)

    if cuenta and correcta:
        _limitador.registrar_exito(clave)
        return _publico(cuenta)

    _limitador.registrar_fallo(clave)
    espera = _limitador.segundos_restantes(clave)
    if espera:
        raise seguridad.BloqueoTemporal(espera)
    return None


def usuarios_todos() -> list:
    return [_publico(u) for u in _USUARIOS]


def usuarios_por_rol(rol: str) -> list:
    return [_publico(u) for u in _USUARIOS if u["rol"] == rol]


def buscar_usuario(uid: int):
    u = _usuario_por_id(uid)
    return _publico(u) if u else None


def usuario_login_disponible(usuario: str, excluir_id: int = None) -> bool:
    ident = (usuario or "").strip().lower()
    return not any(u["usuario"].lower() == ident and u["id"] != excluir_id for u in _USUARIOS)


def correo_disponible(correo: str, excluir_id: int = None) -> bool:
    ident = (correo or "").strip().lower()
    return not any(u["correo"].lower() == ident and u["id"] != excluir_id for u in _USUARIOS)


def validar_contrasena_nueva(contrasena: str) -> None:
    """Lanza ValueError si la contraseña no cumple las reglas."""
    contrasena = contrasena or ""
    if len(contrasena) < MIN_CONTRASENA:
        raise ValueError(f"La contraseña debe tener al menos {MIN_CONTRASENA} caracteres.")
    if len(contrasena) > MAX_CONTRASENA:
        raise ValueError(f"La contraseña es demasiado larga (máximo {MAX_CONTRASENA} caracteres).")


def _validar_usuario(nombre, usuario, correo, contrasena, rol, area, excluir_id, es_nueva, sucursal=None):
    """Lanza ValueError con un mensaje listo para mostrar si algo no es válido."""
    nombre, usuario, correo = (nombre or "").strip(), (usuario or "").strip(), (correo or "").strip()
    contrasena = contrasena or ""
    if not nombre or not usuario or not correo:
        raise ValueError("Completa nombre, usuario y correo.")
    if len(nombre) > LIM_NOMBRE or len(usuario) > LIM_USUARIO or len(correo) > LIM_CORREO:
        raise ValueError("Alguno de los campos es demasiado largo.")
    if re.search(r"\s", usuario):
        raise ValueError("El usuario para iniciar sesión no debe tener espacios.")
    if not _RE_CORREO.match(correo):
        raise ValueError("Escribe un correo válido.")
    if rol not in (ROL_REPRESENTANTE, ROL_TECNICO):
        raise ValueError("Elige un rol: Representante de Área o Técnico.")
    if rol == ROL_REPRESENTANTE:
        actual = _usuario_por_id(excluir_id) if excluir_id is not None else None
        # al editar, un representante puede conservar su área/sucursal aunque ya estén inactivas; para elegir otra deben estar activas
        a = _area_por_nombre(area)
        conserva = actual is not None and a is not None and actual["area_id"] == a["id"]
        if a is None or not (a["activa"] or conserva):
            raise ValueError("Elige el área que representa.")
        x = _sucursal_por_nombre(sucursal)
        conserva = actual is not None and x is not None and actual["sucursal_id"] == x["id"]
        if x is None or not (x["activa"] or conserva):
            raise ValueError("Elige la sucursal a la que pertenece.")
    if es_nueva and not contrasena:
        raise ValueError("Asigna una contraseña para la cuenta nueva.")
    if contrasena:
        validar_contrasena_nueva(contrasena)
    if not usuario_login_disponible(usuario, excluir_id):
        raise ValueError(f"El usuario '{usuario}' ya está en uso. Elige otro.")
    if not correo_disponible(correo, excluir_id):
        raise ValueError(f"El correo '{correo}' ya está registrado en otra cuenta.")


@_mutador
def crear_usuario(nombre, usuario, contrasena, rol, area, correo, sucursal=None) -> dict:
    """Alta de una cuenta de Representante de Área (con área y sucursal) o de Técnico. Lanza ValueError si hay datos inválidos."""
    _validar_usuario(nombre, usuario, correo, contrasena, rol, area, None, True, sucursal)
    return _publico(_alta_usuario(nombre, usuario, contrasena, rol, area, correo, sucursal))


@_mutador
def actualizar_usuario(uid, nombre, usuario, contrasena, rol, area, correo, activo=True, sucursal=None) -> dict:
    """Edita una cuenta. `contrasena` vacía conserva la actual. Las cuentas de
    Administrador no se gestionan desde aquí."""
    u = _usuario_por_id(uid)
    if not u:
        raise ValueError("No encontramos esa cuenta.")
    if u["rol"] == ROL_ADMINISTRADOR:
        raise PermissionError("Las cuentas de Administrador no se gestionan desde aquí.")
    _validar_usuario(nombre, usuario, correo, contrasena, rol, area, uid, False, sucursal)
    a = _area_por_nombre(area) if rol == ROL_REPRESENTANTE else None
    suc = _sucursal_por_nombre(sucursal) if rol == ROL_REPRESENTANTE else None
    u["nombre"] = nombre.strip()
    u["usuario"] = usuario.strip()
    u["correo"] = correo.strip()
    u["rol"] = rol
    u["area_id"] = a["id"] if a else None
    u["sucursal_id"] = suc["id"] if suc else None
    u["activo"] = bool(activo)
    if contrasena:
        u["contrasena_hash"] = seguridad.hashear_contrasena(contrasena)
    # Como todo se referencia por id, el nuevo nombre se ve solo en el historial.
    return _publico(u)


def cuenta_referenciada(uid: int) -> bool:
    """True si la persona aparece en alguna solicitud, bitácora, adjunto, conversación o mensaje."""
    for s in _SOLICITUDES:
        if uid in (s["solicitante_id"], s["agente_id"]) or any(b.autor_id == uid for b in s["bitacora"]):
            return True
    if any(a["subido_por_id"] == uid for a in _ADJUNTOS):
        return True
    for c in _CONVERSACIONES:
        if uid == c["solicitante_id"] or any(m["autor_id"] == uid for m in c["mensajes"]):
            return True
    return False


@_mutador
def eliminar_usuario(uid: int) -> str:
    """Sin historial: se borra la cuenta. Con historial: se desactiva (su nombre
    se conserva en solicitudes y conversaciones, pero ya no puede iniciar sesión;
    se puede reactivar editando la cuenta).  Devuelve 'eliminada' o 'desactivada'."""
    u = _usuario_por_id(uid)
    if not u:
        raise ValueError("No encontramos esa cuenta.")
    if u["rol"] == ROL_ADMINISTRADOR:
        raise PermissionError("Las cuentas de Administrador no se gestionan desde aquí.")
    if cuenta_referenciada(uid):
        u["activo"] = False
        return "desactivada"
    _USUARIOS.remove(u)
    _CODIGOS[:] = [c for c in _CODIGOS if c["usuario_id"] != uid]
    return "eliminada"


# --------------------------------------------------------------------------
# Registro de cuentas (el propio usuario crea su cuenta desde el login)
# --------------------------------------------------------------------------

@_mutador
def registrar_cuenta(nombre, usuario, correo, contrasena, area, sucursal) -> dict:
    """Autorregistro desde el login: la persona escribe sus datos y su cuenta queda creada y activa al instante;
    ya no depende de que un administrador la cree. No requiere sesión.

    - La cuenta nace SIEMPRE como Representante de Área (con el área y la sucursal que elige). Nadie puede
      registrarse como Técnico ni Administrador: si alguien debe ser Técnico, el Administrador cambia su rol.
    - Usuario y correo no pueden repetirse; la contraseña cumple la política mínima y se guarda solo como hash.
    - Límite global de `CUENTAS_MAX_POR_HORA` cuentas por hora, para que nadie llene el sistema de cuentas.
    Lanza ValueError con un mensaje listo para mostrar si algo no es válido. Devuelve la cuenta (sin secretos)."""
    nombre = " ".join((nombre or "").split())
    usuario = (usuario or "").strip()
    correo = (correo or "").strip()
    if not nombre or not usuario or not correo:
        raise ValueError("Completa tu nombre, tu usuario y tu correo.")
    if len(nombre) < 3:
        raise ValueError("Escribe tu nombre completo.")
    if not contrasena:
        raise ValueError("Elige una contraseña.")
    _validar_usuario(nombre, usuario, correo, contrasena, ROL_REPRESENTANTE, area, None, True, sucursal)
    ahora = datetime.now()
    _registros_recientes[:] = [t for t in _registros_recientes if ahora - t < timedelta(hours=1)]
    if len(_registros_recientes) >= CUENTAS_MAX_POR_HORA:
        raise ValueError("Se registraron demasiadas cuentas en la última hora. Inténtalo más tarde.")
    u = _alta_usuario(nombre, usuario, contrasena, ROL_REPRESENTANTE, area, correo, sucursal)
    _registros_recientes.append(ahora)
    try:
        admins = [_publico(x) for x in _USUARIOS if x["rol"] == ROL_ADMINISTRADOR and x["activo"]]
        notificaciones.cuenta_registrada(_publico(u), admins)
    except Exception:
        log.exception("No se pudo enviar el correo de bienvenida")
    return _publico(u)


def sugerir_usuario(correo: str) -> str:
    """Nombre de usuario libre sugerido a partir del correo (la parte anterior a la @)."""
    base = re.sub(r"[^a-z0-9._-]", "", (correo or "").split("@")[0].lower())[:LIM_USUARIO - 3] or "usuario"
    candidato, n = base, 1
    while not usuario_login_disponible(candidato):
        n += 1
        candidato = f"{base}{n}"
    return candidato


# --------------------------------------------------------------------------
# Recuperación de contraseña (código de un solo uso por correo)
# --------------------------------------------------------------------------

def _normalizar_codigo(codigo: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (codigo or "").upper())


def _formatear_codigo(codigo: str) -> str:
    mitad = len(codigo) // 2
    return f"{codigo[:mitad]}-{codigo[mitad:]}"


def _gasto_ficticio() -> None:
    """Gasta el mismo tiempo que una verificación real, para que la respuesta no delate si la cuenta existe."""
    seguridad.verificar_contrasena("x", seguridad.HASH_RELLENO)


@_mutador
def solicitar_recuperacion(identificador: str) -> None:
    """Genera un código de recuperación y lo envía al correo de la cuenta. No devuelve nada
    ni avisa si la cuenta existe: quien llama debe mostrar siempre el mismo mensaje.
    Límite: 3 códigos por hora por cuenta y 10 por hora en total."""
    ahora = datetime.now()
    _solicitudes_recuperacion[:] = [t for t in _solicitudes_recuperacion if ahora - t < timedelta(hours=1)]
    if len(_solicitudes_recuperacion) >= RECUPERACION_MAX_GLOBAL_HORA:
        _gasto_ficticio()
        return
    _solicitudes_recuperacion.append(ahora)

    cuenta = _cuenta_por_identificador(identificador)
    if not cuenta:
        _gasto_ficticio()
        return
    recientes = sum(1 for c in _CODIGOS if c["usuario_id"] == cuenta["id"] and ahora - c["creado_en"] < timedelta(hours=1))
    if recientes >= RECUPERACION_MAX_POR_CUENTA_HORA:
        _gasto_ficticio()
        return

    codigo = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(_LARGO_CODIGO))
    for c in _CODIGOS:                                        # un código nuevo deja sin efecto los anteriores
        if c["usuario_id"] == cuenta["id"]:
            c["usado"] = True
    _contadores["codigo"] += 1
    _CODIGOS.append({"id": _contadores["codigo"], "usuario_id": cuenta["id"],
                     "codigo_hash": seguridad.hashear_contrasena(codigo), "creado_en": ahora,
                     "expira_en": ahora + timedelta(minutes=CODIGO_VIGENCIA_MIN), "intentos": 0, "usado": False})
    del _CODIGOS[:-200]                                       # no crece sin límite
    try:
        notificaciones.codigo_recuperacion(_publico(cuenta), _formatear_codigo(codigo), CODIGO_VIGENCIA_MIN)
    except Exception:
        log.exception("No se pudo enviar el código de recuperación")


_MENSAJE_CODIGO = "El código no es válido o ya venció. Solicita uno nuevo."


def _comprobar_codigo(identificador: str, codigo: str):
    """Comprueba el código sin consumirlo. Devuelve (cuenta, registro) o lanza ValueError con un mensaje que
    es el mismo exista o no la cuenta. Cada intento equivocado cuenta: a los 5 el código queda anulado."""
    cuenta = _cuenta_por_identificador(identificador)
    ahora = datetime.now()
    registro = None
    if cuenta:
        registro = next((c for c in reversed(_CODIGOS)
                         if c["usuario_id"] == cuenta["id"] and not c["usado"]
                         and c["expira_en"] > ahora and c["intentos"] < CODIGO_MAX_INTENTOS), None)
    if not registro:
        _gasto_ficticio()
        raise ValueError(_MENSAJE_CODIGO)
    if not seguridad.verificar_contrasena(_normalizar_codigo(codigo), registro["codigo_hash"]):
        registro["intentos"] += 1
        if registro["intentos"] >= CODIGO_MAX_INTENTOS:
            registro["usado"] = True
        _cambio()                                             # el conteo de intentos también se guarda
        raise ValueError(_MENSAJE_CODIGO)
    return cuenta, registro


@_mutador
def verificar_codigo(identificador: str, codigo: str) -> None:
    """Paso 2 de la recuperación: confirma que el código es correcto SIN usarlo (aún falta elegir la contraseña
    nueva). Lanza ValueError si no es válido; los intentos equivocados cuentan igual que en el cambio final."""
    _comprobar_codigo(identificador, codigo)


@_mutador
def restablecer_con_codigo(identificador: str, codigo: str, contrasena_nueva: str) -> None:
    """Cambia la contraseña con el código recibido por correo. Lanza ValueError con un mensaje
    listo para mostrar. El mensaje del código es siempre el mismo (no revela si la cuenta existe).
    Un código se invalida tras 5 intentos equivocados, al vencer (30 min) o al usarse."""
    validar_contrasena_nueva(contrasena_nueva)
    cuenta, _ = _comprobar_codigo(identificador, codigo)
    cuenta["contrasena_hash"] = seguridad.hashear_contrasena(contrasena_nueva)
    for c in _CODIGOS:
        if c["usuario_id"] == cuenta["id"]:
            c["usado"] = True
    _limitador.registrar_exito(f"id:{cuenta['id']}")          # la cuenta queda desbloqueada


# --------------------------------------------------------------------------
# Bitácora inmutable (RNF-13)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EntradaBitacora:
    """Una línea de la bitácora. Es inmutable (frozen) y lleva el hash de la anterior:
    si alguien modifica, borra o reordena entradas, la cadena deja de cuadrar."""
    seq: int
    fecha: datetime
    autor_id: object
    evento: str
    hash_prev: str
    hash: str


def _calcular_hash(solicitud_id, seq, fecha, autor_id, evento, hash_prev) -> str:
    base = "\x1f".join([str(solicitud_id), str(seq), fecha.isoformat(), "" if autor_id is None else str(autor_id),
                        evento, hash_prev])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _bitacora(s: dict, autor_id, evento: str, fecha=None):
    """ÚNICO punto por donde se escribe en la bitácora: solo agrega, nunca edita ni borra."""
    previa = s["bitacora"][-1].hash if s["bitacora"] else _GENESIS
    seq = len(s["bitacora"]) + 1
    fecha = fecha or _ahora_exacta()
    entrada = EntradaBitacora(seq, fecha, autor_id, evento, previa,
                              _calcular_hash(s["id"], seq, fecha, autor_id, evento, previa))
    s["bitacora"] = s["bitacora"] + (entrada,)              # tupla: no admite del/asignación por posición
    _contadores["bitacora"] += 1


def _problemas_bitacora(solicitudes: list, total_esperado: int) -> list:
    problemas = []
    total = 0
    for s in solicitudes:
        previa = _GENESIS
        total += len(s["bitacora"])
        for i, e in enumerate(s["bitacora"], start=1):
            if e.seq != i or e.hash_prev != previa:
                problemas.append(f"{s['folio']}: la entrada {i} no encadena con la anterior (¿se borró o reordenó algo?).")
                break
            if e.hash != _calcular_hash(s["id"], e.seq, e.fecha, e.autor_id, e.evento, e.hash_prev):
                problemas.append(f"{s['folio']}: la entrada {i} fue modificada.")
                break
            previa = e.hash
    if total < total_esperado:      # borrar las ÚLTIMAS entradas deja una cadena válida; el contador global lo delata
        problemas.append(f"Faltan {total_esperado - total} entradas de bitácora (se escribieron {total_esperado} y hay {total}).")
    elif total > total_esperado:
        problemas.append(f"Sobran {total - total_esperado} entradas de bitácora que no se registraron al escribirlas.")
    return problemas


def verificar_bitacora() -> list:
    """Revisa la cadena de hashes de todas las solicitudes y que no falte ninguna entrada. Devuelve la lista
    de problemas encontrados (vacía = la bitácora está íntegra). Es una protección «a prueba de alteraciones
    evidentes» (tamper-evident): detecta que algo cambió, pero no impide que quien tenga acceso total al
    archivo de datos recalcule todos los hashes; la garantía fuerte es la de la base de datos del servidor."""
    return _problemas_bitacora(_SOLICITUDES, _contadores["bitacora"])


LIM_TEXTO_BUSQUEDA = 100
LIMITE_BITACORA = 1000       # filas que devuelve la consulta como máximo (las más recientes)


def _solicitudes_con_bitacora_visible(actor: dict) -> list:
    """Solicitudes cuya bitácora puede consultar el usuario: todas (el Administrador) o, para un técnico, las
    que tiene asignadas. Lanza PermissionError si su rol no consulta bitácora."""
    if puede(actor, "bitacora.ver_todas"):
        return list(_SOLICITUDES)
    if puede(actor, "bitacora.ver_asignadas"):
        return [s for s in _SOLICITUDES if s["agente_id"] == actor["id"]]
    raise PermissionError("Tu rol no puede consultar la bitácora.")


def historial_de_solicitud(actor: dict, folio: str) -> list:
    """Historial de atención de UNA solicitud (de la más antigua a la más reciente): qué pasó, cuándo y quién
    lo hizo. Lo consulta quien puede ver sus reportes: el Administrador (todas) o el Técnico (las suyas).
    Devuelve [] si el folio no existe o no es visible para ese usuario. Es de solo lectura (copias).
    Lanza PermissionError si el rol no consulta reportes."""
    folio = (folio or "").strip().lower()
    s = next((x for x in _solicitudes_con_bitacora_visible(actor) if x["folio"].lower() == folio), None)
    if not s:
        return []
    return [{"n": e.seq, "fecha": _fmt_seg(e.fecha), "autor": _nombre(e.autor_id), "autor_id": e.autor_id,
             "evento": e.evento} for e in s["bitacora"]]


def autores_bitacora(actor: dict) -> list:
    """Quiénes aparecen como autores en la bitácora que el usuario puede consultar: [(id, nombre)], con
    (None, 'Sistema') si hay eventos automáticos. Sirve para el filtro por autor."""
    ids, hay_sistema = set(), False
    for s in _solicitudes_con_bitacora_visible(actor):
        for e in s["bitacora"]:
            if e.autor_id is None:
                hay_sistema = True
            else:
                ids.add(e.autor_id)
    res = sorted(((i, _nombre(i)) for i in ids), key=lambda x: x[1].lower())
    return ([(None, "Sistema")] if hay_sistema else []) + res


def consultar_bitacora(actor: dict, desde=None, hasta=None, folio: str = "", autor="", texto: str = "",
                       limite: int = LIMITE_BITACORA):
    """RF-21: consulta la bitácora de las solicitudes que el usuario puede ver, con filtros opcionales.
    Es de SOLO LECTURA: devuelve copias, nunca las entradas internas.

    - desde / hasta: fechas (`date`), ambos extremos incluidos.
    - folio: parte del folio («0002» o «SIGSAT-0002»).
    - autor: id de una cuenta, o la palabra "sistema" para los eventos automáticos; "" = todos.
    - texto: palabra o frase dentro del evento (sin distinguir mayúsculas).

    Devuelve (filas, total): las `limite` más recientes y cuántas coinciden en total. Cada fila:
    folio, fecha, autor, evento y n.º de entrada.
    Lanza PermissionError si el rol no consulta bitácora y ValueError si un filtro no es válido."""
    visibles = _solicitudes_con_bitacora_visible(actor)
    if isinstance(desde, datetime):
        desde = desde.date()
    if isinstance(hasta, datetime):
        hasta = hasta.date()
    if desde and hasta and desde > hasta:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    folio = (folio or "").strip().lower()
    texto = (texto or "").strip().lower()
    if len(folio) > 30 or len(texto) > LIM_TEXTO_BUSQUEDA:
        raise ValueError(f"El texto de búsqueda es demasiado largo (máximo {LIM_TEXTO_BUSQUEDA} caracteres).")
    if autor not in ("", None, "sistema") and (isinstance(autor, bool) or not isinstance(autor, int)):
        raise ValueError("Autor no válido.")
    if not isinstance(limite, int) or isinstance(limite, bool) or limite < 1:
        raise ValueError("El límite debe ser un número positivo.")

    filas = []
    for s in visibles:
        if folio and folio not in s["folio"].lower():
            continue
        for e in s["bitacora"]:
            if desde and e.fecha.date() < desde:
                continue
            if hasta and e.fecha.date() > hasta:
                continue
            if autor == "sistema" and e.autor_id is not None:
                continue
            if isinstance(autor, int) and e.autor_id != autor:
                continue
            if texto and texto not in e.evento.lower():
                continue
            filas.append((e.fecha, s["id"], e.seq, {"folio": s["folio"], "fecha": _fmt_seg(e.fecha),
                                                    "autor": _nombre(e.autor_id), "autor_id": e.autor_id,
                                                    "evento": e.evento, "n": e.seq}))
    filas.sort(key=lambda f: (f[0], f[1], f[2]), reverse=True)
    return [f[3] for f in filas[:limite]], len(filas)


# --------------------------------------------------------------------------
# Solicitudes (tickets) y reportes de avance
# --------------------------------------------------------------------------

def _solicitud_por_folio(folio: str):
    return next((s for s in _SOLICITUDES if s["folio"] == folio), None)


def _vence(s: dict) -> datetime:
    """Fecha límite: el tiempo estimado del tipo corre desde que se registra la solicitud."""
    return s["plazo_desde"] + timedelta(hours=s["sla_horas"])


def _vencida(s: dict, ahora=None) -> bool:
    """Pasó su fecha límite sin haberse finalizado. Sigue pudiendo atenderse (y se cuenta como «fuera de tiempo»)."""
    return s["estado"] not in ESTADOS_SIN_ATENCION and (ahora or datetime.now()) > _vence(s)


def _ver_solicitud(s: dict) -> dict:
    """Copia de lectura con los nombres resueltos y las fechas en texto."""
    tipo = _tipo_por_id(s["tipo_id"])
    finalizada = s["finalizada_en"] is not None
    return {
        "id": s["id"],
        "folio": s["folio"],
        "tipo": tipo["nombre"] if tipo else "—",
        "tipo_id": s["tipo_id"],
        "area": _nombre_area(s["area_id"]),
        "area_id": s["area_id"],
        "sucursal": _nombre_sucursal(s["sucursal_id"]),
        "sucursal_id": s["sucursal_id"],
        "descripcion": s["descripcion"],
        "prioridad": s["prioridad"],
        "estado": s["estado"],
        "solicitante": _nombre(s["solicitante_id"]),
        "solicitante_id": s["solicitante_id"],
        "agente_asignado": _nombre(s["agente_id"]) if s["agente_id"] is not None else None,   # el técnico
        "agente_id": s["agente_id"],
        "asignada": s["agente_id"] is not None,
        "fecha_creacion": _fmt(s["creada_en"]),
        "fecha_finalizacion": _fmt(s["finalizada_en"]),       # cuando el técnico la marcó «Finalizado»
        "fecha_calificacion": _fmt(s["calificada_en"]),       # cuando el representante calificó el servicio
        "calificacion": s["calificacion"],
        "finalizada": finalizada,
        "por_calificar": finalizada and s["calificacion"] is None,    # el representante aún no califica
        "sla_horas": s["sla_horas"],
        "vence": _fmt(_vence(s)),
        "vencida": _vencida(s),
        "cumplio_sla": (s["finalizada_en"] <= _vence(s)) if finalizada else None,
        "n_adjuntos": sum(1 for a in _ADJUNTOS if a["solicitud_id"] == s["id"]),
        "bitacora": [{"fecha": _fmt_seg(b.fecha), "autor": _nombre(b.autor_id), "evento": b.evento} for b in s["bitacora"]],
    }


def buscar_por_folio(folio: str):
    s = _solicitud_por_folio(folio)
    return _ver_solicitud(s) if s else None


def puede_ver_solicitud(usuario: dict, s: dict) -> bool:
    """Representante: solo las suyas. Técnico: las que tiene asignadas. Administrador: todas."""
    if puede(usuario, "solicitud.ver_todas"):
        return True
    if puede(usuario, "solicitud.ver_propias") and s["solicitante_id"] == usuario["id"]:
        return True
    if puede(usuario, "solicitud.ver_asignadas") and s["agente_id"] == usuario["id"]:
        return True
    return False


def solicitud_visible(usuario: dict, folio: str):
    """La solicitud (copia de lectura) si el usuario tiene derecho a verla; si no, None."""
    s = buscar_por_folio(folio)
    return s if s and puede_ver_solicitud(usuario, s) else None


def solicitudes_de(solicitante_id: int, estado: str = "") -> list:
    res = [s for s in _SOLICITUDES if s["solicitante_id"] == solicitante_id
           and (not estado or s["estado"] == estado)]
    res.sort(key=lambda s: (s["creada_en"], s["id"]), reverse=True)
    return [_ver_solicitud(s) for s in res]


def _filtrar(desde=None, hasta=None, area="", tipo="", estado="", prioridad="", agente_id=None,
             sin_asignar=False, solo_vencidas=False, sucursal="", excluir_finalizados=False) -> list:
    """Solicitudes que cumplen TODOS los filtros dados (los vacíos no filtran)."""
    ahora = datetime.now()
    res = []
    for s in _SOLICITUDES:
        if desde and s["creada_en"].date() < desde:
            continue
        if hasta and s["creada_en"].date() > hasta:
            continue
        if area and _nombre_area(s["area_id"]) != area:
            continue
        if sucursal and _nombre_sucursal(s["sucursal_id"]) != sucursal:
            continue
        if tipo and (_tipo_por_id(s["tipo_id"]) or {}).get("nombre") != tipo:
            continue
        if estado and s["estado"] != estado:
            continue
        if excluir_finalizados and s["estado"] in ESTADOS_SIN_ATENCION:
            continue
        if prioridad and s["prioridad"] != prioridad:
            continue
        if agente_id is not None and s["agente_id"] != agente_id:
            continue
        if sin_asignar and s["agente_id"] is not None:
            continue
        if solo_vencidas and not _vencida(s, ahora):
            continue
        res.append(s)
    res.sort(key=lambda s: (s["creada_en"], s["id"]), reverse=True)
    return [_ver_solicitud(s) for s in res]


def solicitudes_todas(actor: dict, area="", estado="", agente_id=None, sin_asignar=False, solo_vencidas=False) -> list:
    """Todas las solicitudes del sistema (supervisión y distribución). Solo para quien tiene
    el permiso solicitud.ver_todas (el Administrador)."""
    _exigir(actor, "solicitud.ver_todas", "Tu rol no puede ver todas las solicitudes.")
    return _filtrar(area=area, estado=estado, agente_id=agente_id, sin_asignar=sin_asignar, solo_vencidas=solo_vencidas)


def _normalizar_filtros_reporte(desde, hasta, estado, prioridad):
    if isinstance(desde, datetime):
        desde = desde.date()
    if isinstance(hasta, datetime):
        hasta = hasta.date()
    if desde and hasta and desde > hasta:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    for valor, lista, texto in ((estado, ESTADOS, "estatus"), (prioridad, PRIORIDADES, "prioridad")):
        if valor and valor not in lista:
            raise ValueError(f"Filtro de {texto} no válido.")
    return desde, hasta


def solicitudes_reporte(actor: dict, desde=None, hasta=None, area="", tipo="", estado="", prioridad="",
                        agente_id=None, solo_vencidas=False) -> list:
    """Solicitudes para un reporte filtrable (RF-24). Fechas: `date` (se compara con la de creación,
    ambos extremos incluidos). Solo para quien tiene el permiso reportes.ver."""
    _exigir(actor, "reportes.ver", "Tu rol no puede generar reportes.")
    desde, hasta = _normalizar_filtros_reporte(desde, hasta, estado, prioridad)
    return _filtrar(desde, hasta, area, tipo, estado, prioridad, agente_id, False, solo_vencidas)


def listar_reportes(actor: dict, desde=None, hasta=None, estado="", prioridad="", area="", agente_id=None,
                    sucursal="", incluir_finalizados=False, solo_vencidas=False) -> list:
    """Bandeja de reportes (cada solicitud con el avance que informa el técnico), con filtros por fecha de
    creación, estatus, prioridad, área, sucursal y técnico. Con `incluir_finalizados=False` es la bandeja
    de trabajo; con True es el listado completo, incluidos los Finalizados. El Administrador ve todos;
    un Técnico, solo los suyos (el filtro de técnico se ignora). Lanza PermissionError a los demás roles."""
    if puede(actor, "reportes.ver"):
        propio = False
    elif puede(actor, "reportes.ver_propios"):
        propio = True
    else:
        raise PermissionError("Tu rol no puede consultar los reportes.")
    desde, hasta = _normalizar_filtros_reporte(desde, hasta, estado, prioridad)
    if propio:
        agente_id = actor["id"]
    return _filtrar(desde, hasta, area, "", estado, prioridad, agente_id, False, solo_vencidas, sucursal,
                    excluir_finalizados=not incluir_finalizados)


def _nueva_solicitud(tipo_id, descripcion, area_id, sucursal_id, solicitante_id, creada_en, **extra) -> dict:
    _contadores["solicitud"] += 1
    n = _contadores["solicitud"]
    t = _tipo_por_id(tipo_id)
    s = {
        "id": n,
        "folio": f"SIGSAT-{n:04d}",
        "tipo_id": tipo_id,
        "area_id": area_id,                                  # el área y la sucursal del representante que la levanta
        "sucursal_id": sucursal_id,
        "descripcion": descripcion,
        "prioridad": prioridad_por_horas(t["horas"]),         # sale del tiempo estimado del tipo, no la elige el representante
        "estado": "Sin visualizar",
        "solicitante_id": solicitante_id,
        "agente_id": None,
        "creada_en": creada_en,
        "plazo_desde": creada_en,
        "finalizada_en": None,
        "calificada_en": None,
        "calificacion": None,
        "sla_horas": t["horas"],                              # la fecha límite queda fija al registrarla
        "bitacora": (),
    }
    s.update(extra)
    _SOLICITUDES.append(s)
    return s


@_mutador
def crear_solicitud(tipo: str, descripcion: str, usuario: dict, adjuntos=None) -> dict:
    """Check-in de una solicitud. La levanta un Representante de Área: el **área** y la **sucursal** salen de
    su cuenta; la **prioridad** y la fecha límite salen del tiempo estimado del tipo de solicitud. Queda
    «Sin asignar» hasta que el Administrador la distribuya (se le avisa por correo). `adjuntos` (opcional,
    solo al crearla): lista de (nombre, bytes). Lanza ValueError si algo no es válido (y no se crea nada)."""
    if not puede(usuario, "solicitud.crear"):
        raise PermissionError("Tu rol no puede registrar solicitudes.")
    cuenta = _usuario_por_id(usuario["id"])
    if cuenta is None or cuenta["area_id"] is None or cuenta["sucursal_id"] is None:
        raise ValueError("Tu cuenta no tiene área y sucursal asignadas. Pídele al administrador que las registre.")
    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValueError("Describe tu solicitud antes de enviarla.")
    if len(descripcion) > LIM_DESCRIPCION:
        raise ValueError(f"La descripción es demasiado larga (máximo {LIM_DESCRIPCION} caracteres).")
    t = _tipo_por_nombre(tipo, solo_activos=True)
    if t is None:
        raise ValueError("Elige un tipo de solicitud válido.")
    adjuntos = list(adjuntos or [])
    if len(adjuntos) > archivos.MAX_ADJUNTOS_POR_SOLICITUD:
        raise ValueError(f"Máximo {archivos.MAX_ADJUNTOS_POR_SOLICITUD} archivos por solicitud.")
    validados = [(archivos.validar_adjunto(nombre, contenido), bytes(contenido)) for nombre, contenido in adjuntos]

    s = _nueva_solicitud(t["id"], descripcion, cuenta["area_id"], cuenta["sucursal_id"], cuenta["id"], _ahora())
    _bitacora(s, cuenta["id"], "Solicitud creada")
    for meta, contenido in validados:
        _guardar_adjunto(s, cuenta["id"], meta, contenido)
    _bitacora(s, None, "Pendiente de asignación: el Administrador la distribuirá a un técnico")
    _avisar_por_asignar(s)
    return _ver_solicitud(s)


def _usuario_activo(uid):
    u = _usuario_por_id(uid) if uid is not None else None
    return _publico(u) if u else None


def _avisar_asignacion(s: dict, agente_id: int, anterior_id=None, por=None, motivo="") -> None:
    """RF-11: correo de asignación o reasignación. Un fallo de correo nunca interrumpe la operación."""
    try:
        notificaciones.solicitud_asignada(
            _ver_solicitud(s), _publico(_usuario_por_id(agente_id)), _usuario_activo(s["solicitante_id"]),
            _usuario_activo(anterior_id), por, motivo)
    except Exception:
        log.exception("No se pudo enviar el correo de asignación")


def _avisar_calificacion(s: dict) -> None:
    """Correo al técnico con la calificación que recibió."""
    try:
        notificaciones.servicio_calificado(_ver_solicitud(s), _usuario_activo(s["agente_id"]), _usuario_activo(s["solicitante_id"]))
    except Exception:
        log.exception("No se pudo enviar el correo de calificación")


def _avisar_por_asignar(s: dict) -> None:
    """Avisa a los administradores que hay una solicitud nueva por distribuir."""
    try:
        admins = [_publico(u) for u in _USUARIOS if u["rol"] == ROL_ADMINISTRADOR and u["activo"]]
        notificaciones.solicitud_por_asignar(_ver_solicitud(s), admins)
    except Exception:
        log.exception("No se pudo enviar el aviso de solicitud por asignar")


def _avisar_estatus(s: dict, estado_anterior: str, comentario: str) -> None:
    """RF-12: correo de cambio de estatus al representante que levantó la solicitud."""
    try:
        notificaciones.estatus_cambiado(_ver_solicitud(s), estado_anterior, comentario, _usuario_activo(s["solicitante_id"]))
    except Exception:
        log.exception("No se pudo enviar el correo de cambio de estatus")


@_mutador
def asignar_solicitud(folio: str, actor: dict, agente_id: int, motivo: str = "") -> str:
    """RF-09: el Administrador distribuye una solicitud: la asigna a un técnico activo o la REASIGNA a otro
    (también si ya está vencida). Al asignarla, el reporte vuelve a «Sin visualizar» para el técnico nuevo. Queda
    en la bitácora (con el motivo) y se avisa por correo al técnico, al representante y al técnico anterior.
    Devuelve 'ok' | 'sin_cambios' | 'finalizada' | 'no_existe'."""
    _exigir(actor, "solicitud.asignar", "Tu rol no puede asignar solicitudes.")
    motivo = (motivo or "").strip()
    if len(motivo) > LIM_COMENTARIO:
        raise ValueError(f"El motivo es demasiado largo (máximo {LIM_COMENTARIO} caracteres).")
    s = _solicitud_por_folio(folio)
    if s is None:
        return "no_existe"
    tecnico = _usuario_por_id(agente_id)
    if not tecnico or tecnico["rol"] != ROL_TECNICO or not tecnico["activo"]:
        raise ValueError("Elige un técnico activo.")
    if s["estado"] in ESTADOS_SIN_ATENCION:
        return "finalizada"
    if s["agente_id"] == tecnico["id"]:
        return "sin_cambios"

    anterior_id = s["agente_id"]
    s["agente_id"] = tecnico["id"]
    s["estado"] = "Sin visualizar"
    sufijo = f" — Motivo: {motivo}" if motivo else ""
    if anterior_id is None:
        evento = f"Asignada a {tecnico['nombre']} por {actor['nombre']}{sufijo}"
    else:
        evento = f"Reasignada de {_nombre(anterior_id)} a {tecnico['nombre']} por {actor['nombre']}{sufijo}"
    _bitacora(s, actor["id"], evento)
    _avisar_asignacion(s, tecnico["id"], anterior_id, actor["nombre"], motivo)
    return "ok"


def _solicitud_del_tecnico(folio: str, tecnico: dict):
    """La solicitud si el técnico puede atenderla (debe tenerla asignada); lanza PermissionError si no."""
    if not puede(tecnico, "solicitud.atender"):
        raise PermissionError("Tu rol no puede atender solicitudes.")
    s = _solicitud_por_folio(folio)
    if s is not None and s["agente_id"] != tecnico["id"]:
        raise PermissionError("Esta solicitud no está asignada a ti.")
    return s


@_mutador
def registrar_visualizacion(folio: str, tecnico: dict) -> str:
    """El técnico abrió el reporte por primera vez: pasa de «Sin visualizar» a «Visualizado» (queda en la
    bitácora y se avisa al representante). Devuelve 'ok' | 'sin_cambios' (ya estaba visualizado o avanzado)
    | 'no_existe'. PermissionError si la solicitud no es suya."""
    s = _solicitud_del_tecnico(folio, tecnico)
    if s is None:
        return "no_existe"
    if s["estado"] != "Sin visualizar":
        return "sin_cambios"
    s["estado"] = "Visualizado"
    _bitacora(s, tecnico["id"], "Estatus actualizado a 'Visualizado'")
    _avisar_estatus(s, "Sin visualizar", "")
    return "ok"


@_mutador
def actualizar_por_tecnico(folio: str, tecnico: dict, nuevo_estado: str, comentario: str = "") -> str:
    """El técnico asignado informa su avance: cambia el estatus (solo hacia adelante: Visualizado → En proceso →
    Finalizado) y/o agrega un comentario. «Finalizado» exige un comentario con el reporte final y deja la
    solicitud lista para que el representante califique el servicio. Un cambio de estatus se avisa por correo
    al representante. Una solicitud vencida sigue pudiendo atenderse (se contará como fuera de tiempo).
    Devuelve 'ok' | 'sin_cambios' | 'finalizada' | 'no_existe'. ValueError si hay datos inválidos."""
    s = _solicitud_del_tecnico(folio, tecnico)
    if s is None:
        return "no_existe"
    comentario = (comentario or "").strip()
    if nuevo_estado not in ESTADOS_TECNICO and nuevo_estado != s["estado"]:
        raise ValueError("Elige un estatus válido.")
    if len(comentario) > LIM_COMENTARIO:
        raise ValueError(f"El comentario es demasiado largo (máximo {LIM_COMENTARIO} caracteres).")
    if s["estado"] in ESTADOS_SIN_ATENCION:
        return "finalizada"
    cambia_estado = nuevo_estado != s["estado"]
    if cambia_estado and ESTADOS.index(nuevo_estado) < ESTADOS.index(s["estado"]):
        raise ValueError(f"El estatus no puede retroceder de «{s['estado']}» a «{nuevo_estado}».")
    if cambia_estado and nuevo_estado == ESTADO_FINAL and not comentario:
        raise ValueError("Para finalizar, escribe el reporte final de lo que se hizo.")
    if not cambia_estado and not comentario:
        return "sin_cambios"      # no se escribe nada en la bitácora

    if cambia_estado:
        anterior = s["estado"]
        evento = f"Estatus actualizado a '{nuevo_estado}'" + (f" — {comentario}" if comentario else "")
        if nuevo_estado == ESTADO_FINAL:
            evento += " (pendiente de calificación del representante)"
            s["finalizada_en"] = _ahora()
        s["estado"] = nuevo_estado
        _bitacora(s, tecnico["id"], evento)
        _avisar_estatus(s, anterior, comentario)
    else:
        _bitacora(s, tecnico["id"], comentario)
    return "ok"


@_mutador
def calificar_servicio(folio: str, usuario: dict, calificacion: int) -> str:
    """El representante que levantó la solicitud **califica el servicio recibido** (1 a 5) cuando ya está
    «Finalizado». Se califica una sola vez y no cambia el estatus. Devuelve 'ok' | 'no_aplica' (no es suya,
    no está finalizada o ya la calificó)."""
    if not puede(usuario, "solicitud.calificar"):
        raise PermissionError("Tu rol no puede calificar el servicio.")
    if isinstance(calificacion, bool) or not isinstance(calificacion, int) or not 1 <= calificacion <= 5:
        raise ValueError("Elige una calificación de 1 a 5.")
    s = _solicitud_por_folio(folio)
    if (not s or s["estado"] != ESTADO_FINAL or s["solicitante_id"] != usuario["id"]
            or s["calificacion"] is not None):
        return "no_aplica"
    s["calificacion"] = calificacion
    s["calificada_en"] = _ahora()
    _bitacora(s, usuario["id"], f"El representante calificó el servicio recibido ({calificacion}/5)")
    _avisar_calificacion(s)
    return "ok"


# --------------------------------------------------------------------------
# Adjuntos (opcionales)
# --------------------------------------------------------------------------

def _guardar_adjunto(s: dict, autor_id: int, meta: dict, contenido: bytes) -> dict:
    _contadores["adjunto"] += 1
    a = {"id": _contadores["adjunto"], "solicitud_id": s["id"], "nombre": meta["nombre"], "tipo": meta["tipo"],
         "tamano": meta["tamano"], "subido_por_id": autor_id, "fecha": _ahora(), "contenido": contenido}
    _ADJUNTOS.append(a)
    _bitacora(s, autor_id, f"Adjuntó el archivo «{meta['nombre']}» ({archivos.formato_tamano(meta['tamano'])})")
    return a


def _meta_adjunto(a: dict) -> dict:
    return {"id": a["id"], "nombre": a["nombre"], "tipo": a["tipo"], "tamano": a["tamano"],
            "subido_por": _nombre(a["subido_por_id"]), "subido_por_id": a["subido_por_id"], "fecha": _fmt(a["fecha"])}


def _puede_adjuntar(usuario: dict, s: dict) -> bool:
    """Agregar archivos a una solicitud YA CREADA. Por regla del proyecto, los archivos solo se adjuntan al
    registrar la solicitud: ningún rol tiene el permiso `solicitud.adjuntar_despues`."""
    if not puede(usuario, "solicitud.adjuntar_despues"):
        return False
    es_dueno = puede(usuario, "solicitud.ver_propias") and s["solicitante_id"] == usuario["id"]
    return es_dueno or (puede(usuario, "solicitud.atender") and puede_ver_solicitud(usuario, _ver_solicitud(s)))


def puede_adjuntar(usuario: dict, folio: str) -> bool:
    """True si el usuario puede agregar archivos a esa solicitud ya creada (hoy, ningún rol)."""
    s = _solicitud_por_folio(folio)
    return bool(s) and s["estado"] not in ESTADOS_SIN_ATENCION and _puede_adjuntar(usuario, s)


@_mutador
def agregar_adjunto(folio: str, usuario: dict, nombre: str, contenido: bytes) -> dict:
    """Agrega un archivo a una solicitud ya creada. DESHABILITADO por regla del proyecto (permiso
    `solicitud.adjuntar_despues`): los archivos solo se adjuntan al crear la solicitud."""
    s = _solicitud_por_folio(folio)
    if s is None:
        raise ValueError("No encontramos la solicitud.")
    if not _puede_adjuntar(usuario, s):
        raise PermissionError("Los archivos solo se pueden adjuntar al registrar la solicitud.")
    if s["estado"] in ESTADOS_SIN_ATENCION:
        raise ValueError("La solicitud ya está resuelta y no admite más archivos.")
    if sum(1 for a in _ADJUNTOS if a["solicitud_id"] == s["id"]) >= archivos.MAX_ADJUNTOS_POR_SOLICITUD:
        raise ValueError(f"Máximo {archivos.MAX_ADJUNTOS_POR_SOLICITUD} archivos por solicitud.")
    meta = archivos.validar_adjunto(nombre, contenido)
    return _meta_adjunto(_guardar_adjunto(s, usuario["id"], meta, bytes(contenido)))


def adjuntos_de(folio: str, usuario: dict) -> list:
    """Archivos de una solicitud (sin el contenido). Lista vacía si el usuario no puede verla."""
    s = _solicitud_por_folio(folio)
    if s is None or not puede_ver_solicitud(usuario, _ver_solicitud(s)):
        return []
    return [_meta_adjunto(a) for a in _ADJUNTOS if a["solicitud_id"] == s["id"]]


def obtener_adjunto(adjunto_id: int, usuario: dict):
    """(metadatos, bytes) del archivo, o None si no existe o el usuario no puede ver su solicitud."""
    a = next((x for x in _ADJUNTOS if x["id"] == adjunto_id), None)
    s = next((x for x in _SOLICITUDES if a and x["id"] == a["solicitud_id"]), None)
    if not a or not s or not puede_ver_solicitud(usuario, _ver_solicitud(s)):
        return None
    return _meta_adjunto(a), a["contenido"]


@_mutador
def quitar_adjunto(adjunto_id: int, usuario: dict) -> str:
    """Quita un archivo (solo quien lo subió). DESHABILITADO por regla del proyecto (permiso
    `solicitud.adjuntar_despues`): lo adjuntado al crear la solicitud ya no se modifica. El retiro quedaría
    anotado en la bitácora. Devuelve 'ok' | 'no_existe'."""
    if not puede(usuario, "solicitud.adjuntar_despues"):
        raise PermissionError("Los archivos adjuntos ya no se pueden modificar una vez creada la solicitud.")
    a = next((x for x in _ADJUNTOS if x["id"] == adjunto_id), None)
    s = next((x for x in _SOLICITUDES if a and x["id"] == a["solicitud_id"]), None)
    if not a or not s:
        return "no_existe"
    if a["subido_por_id"] != usuario["id"]:
        raise PermissionError("Solo quien subió el archivo puede quitarlo.")
    if s["estado"] in ESTADOS_SIN_ATENCION:
        raise ValueError("La solicitud ya está resuelta y no admite cambios.")
    _ADJUNTOS.remove(a)
    _bitacora(s, usuario["id"], f"Retiró el archivo «{a['nombre']}»")
    return "ok"


# --------------------------------------------------------------------------
# Indicadores (KPIs), carga de trabajo (RF-23)
# --------------------------------------------------------------------------

def _horas(s: dict) -> float:
    """Horas que tardó el equipo en finalizar la solicitud (de que se registró a que se marcó «Finalizado»)."""
    return (s["finalizada_en"] - s["creada_en"]).total_seconds() / 3600


def _promedio(valores, decimales=1) -> float:
    return round(sum(valores) / len(valores), decimales) if valores else 0.0


def calcular_kpis() -> dict:
    """Panel de indicadores del Administrador."""
    total = len(_SOLICITUDES)
    por_estado = {e: sum(1 for s in _SOLICITUDES if s["estado"] == e) for e in ESTADOS}
    por_area = {}
    for a in _AREAS:                       # las áreas inactivas solo aparecen si tienen historial
        n = sum(1 for s in _SOLICITUDES if s["area_id"] == a["id"])
        if a["activa"] or n:
            por_area[a["nombre"]] = n
    por_sucursal = {}
    for x in _SUCURSALES:
        n = sum(1 for s in _SOLICITUDES if s["sucursal_id"] == x["id"])
        if x["activa"] or n:
            por_sucursal[x["nombre"]] = n

    finalizadas = [s for s in _SOLICITUDES if s["finalizada_en"]]
    ahora = datetime.now()

    # tiempo promedio de atención por área y por tipo (solicitudes finalizadas)
    tiempo_por_area = {}
    for a in _AREAS:
        horas = [_horas(s) for s in finalizadas if s["area_id"] == a["id"]]
        if horas:
            tiempo_por_area[a["nombre"]] = {"promedio_h": _promedio(horas), "finalizadas": len(horas)}
    tiempo_por_tipo = {}
    for t in _TIPOS:
        horas = [_horas(s) for s in finalizadas if s["tipo_id"] == t["id"]]
        if horas:
            tiempo_por_tipo[t["nombre"]] = {"promedio_h": _promedio(horas), "finalizadas": len(horas)}

    # satisfacción promedio de las áreas (calificaciones que dieron sus representantes)
    satisfaccion_por_area = {}
    for a in _AREAS:
        notas = [s["calificacion"] for s in _SOLICITUDES if s["area_id"] == a["id"] and s["calificacion"]]
        if notas:
            satisfaccion_por_area[a["nombre"]] = {"promedio": _promedio(notas), "calificadas": len(notas)}
    calificaciones = [s["calificacion"] for s in _SOLICITUDES if s["calificacion"]]
    en_tiempo = sum(1 for s in finalizadas if s["finalizada_en"] <= _vence(s))

    return {
        "total": total,
        "por_estado": por_estado,
        "por_area": por_area,
        "por_sucursal": por_sucursal,
        "sin_asignar": sum(1 for s in _SOLICITUDES if s["agente_id"] is None and s["estado"] not in ESTADOS_SIN_ATENCION),
        "tiempo_promedio_h": _promedio([_horas(s) for s in finalizadas]),
        "tiempo_por_area": tiempo_por_area,
        "tiempo_por_tipo": tiempo_por_tipo,
        "vencidas": sum(1 for s in _SOLICITUDES if _vencida(s, ahora)),                 # abiertas y ya fuera de plazo
        "fuera_de_tiempo": len(finalizadas) - en_tiempo,                                 # finalizadas después de su límite
        "efectividad_pct": round(100 * en_tiempo / len(finalizadas)) if finalizadas else None,
        "satisfaccion_prom": _promedio(calificaciones),
        "satisfaccion_por_area": satisfaccion_por_area,
    }


def carga_trabajo() -> list:
    """Carga de trabajo de cada técnico activo: cuántos reportes abiertos tiene (y en qué estatus), cuántos
    están vencidos, cuántos finalizó y en cuánto tiempo. Sirve al Administrador para distribuir el trabajo."""
    ahora = datetime.now()
    res = []
    for u in _USUARIOS:
        if u["rol"] != ROL_TECNICO or not u["activo"]:
            continue
        mias = [s for s in _SOLICITUDES if s["agente_id"] == u["id"]]
        abiertas = [s for s in mias if s["estado"] not in ESTADOS_SIN_ATENCION]
        finalizadas = [s for s in mias if s["finalizada_en"]]
        res.append({
            "agente_id": u["id"], "agente": u["nombre"],
            "abiertas": len(abiertas),
            "sin_visualizar": sum(1 for s in abiertas if s["estado"] == "Sin visualizar"),
            "visualizadas": sum(1 for s in abiertas if s["estado"] == "Visualizado"),
            "en_proceso": sum(1 for s in abiertas if s["estado"] == "En proceso"),
            "vencidas": sum(1 for s in abiertas if _vencida(s, ahora)),
            "finalizadas": len(finalizadas),
            "tiempo_promedio_h": _promedio([_horas(s) for s in finalizadas]),
        })
    res.sort(key=lambda r: (-r["abiertas"], r["agente"]))
    return res


# --------------------------------------------------------------------------
# Mesa de gestión de TI — canal de comunicación directo
# --------------------------------------------------------------------------

def _conversacion_por_codigo(codigo: str):
    return next((c for c in _CONVERSACIONES if c["codigo"] == codigo), None)


def _ver_conversacion(c: dict) -> dict:
    sol = next((s for s in _SOLICITUDES if s["id"] == c["solicitud_id"]), None)
    return {
        "id": c["codigo"],               # la interfaz identifica la conversación por su código
        "asunto": c["asunto"],
        "solicitante": _nombre(c["solicitante_id"]),
        "solicitante_id": c["solicitante_id"],
        "folio": sol["folio"] if sol else None,
        "estado": c["estado"],
        "rol_solicitante": (_usuario_por_id(c["solicitante_id"]) or {}).get("rol", ""),
        "mensajes": [{"fecha": _fmt(m["fecha"]), "autor": _nombre(m["autor_id"]),
                      "autor_id": m["autor_id"], "rol": m["rol"], "texto": m["texto"]}
                     for m in c["mensajes"]],
    }


def _mensaje(c: dict, autor_id, rol: str, texto: str, fecha=None):
    c["mensajes"].append({"autor_id": autor_id, "rol": rol, "texto": texto, "fecha": fecha or _ahora()})


def _nueva_conversacion(solicitante_id, asunto, mensaje, solicitud_id, creada_en) -> dict:
    _contadores["conversacion"] += 1
    n = _contadores["conversacion"]
    c = {
        "id": n,
        "codigo": f"MESA-{n:04d}",
        "asunto": asunto,
        "solicitante_id": solicitante_id,
        "solicitud_id": solicitud_id,
        "estado": "Abierta",
        "mensajes": [],
    }
    _mensaje(c, solicitante_id, (_usuario_por_id(solicitante_id) or {}).get("rol", ""), mensaje, creada_en)
    _CONVERSACIONES.insert(0, c)
    return c


def buscar_conversacion(codigo: str):
    c = _conversacion_por_codigo(codigo)
    return _ver_conversacion(c) if c else None


def puede_ver_conversacion(usuario: dict, c: dict) -> bool:
    """Representante y Técnico: las que abrieron ellos. Administrador: todas."""
    if puede(usuario, "mesa.ver_todas"):
        return True
    return puede(usuario, "mesa.crear_conversacion") and c["solicitante_id"] == usuario["id"]


def puede_escribir_en(usuario: dict, c: dict) -> bool:
    """Escribe quien abrió la conversación o quien tenga permiso de responder (Administrador); nunca en una cerrada."""
    if c["estado"] == "Cerrada" or not puede_ver_conversacion(usuario, c):
        return False
    return c["solicitante_id"] == usuario["id"] or puede(usuario, "mesa.responder")


def conversaciones_visibles(usuario: dict, estado: str = "") -> list:
    res = [c for c in _CONVERSACIONES
           if puede_ver_conversacion(usuario, c)
           and (not estado or c["estado"] == estado)]
    return [_ver_conversacion(c) for c in res]


@_mutador
def crear_conversacion(usuario: dict, asunto: str, mensaje: str, folio: str = None) -> dict:
    """Abre una conversación con la Administración. Si trae solicitud relacionada, debe ser del propio
    representante o, en el caso de un técnico, una que tenga asignada."""
    if not puede(usuario, "mesa.crear_conversacion"):
        raise PermissionError("Tu rol no puede abrir conversaciones.")
    asunto, mensaje = (asunto or "").strip(), (mensaje or "").strip()
    if not asunto or not mensaje:
        raise ValueError("Escribe un asunto y un mensaje.")
    if len(asunto) > LIM_ASUNTO:
        raise ValueError(f"El asunto es demasiado largo (máximo {LIM_ASUNTO} caracteres).")
    if len(mensaje) > LIM_MENSAJE:
        raise ValueError(f"El mensaje es demasiado largo (máximo {LIM_MENSAJE} caracteres).")
    solicitud_id = None
    if folio:
        s = _solicitud_por_folio(folio)
        if not s or not puede_ver_solicitud(usuario, s):
            raise ValueError("Elige una solicitud de la lista o deja «Ninguna».")
        solicitud_id = s["id"]
    return _ver_conversacion(_nueva_conversacion(usuario["id"], asunto, mensaje, solicitud_id, _ahora()))


@_mutador
def enviar_mensaje(codigo: str, usuario: dict, texto: str) -> bool:
    """El Administrador que responde pasa la conversación a «En atención». False si no se pudo enviar."""
    c = _conversacion_por_codigo(codigo)
    texto = (texto or "").strip()
    if not c or not texto or not puede_escribir_en(usuario, c):
        return False
    if len(texto) > LIM_MENSAJE:
        raise ValueError(f"El mensaje es demasiado largo (máximo {LIM_MENSAJE} caracteres).")
    if puede(usuario, "mesa.responder") and c["estado"] == "Abierta":
        c["estado"] = "En atención"
    _mensaje(c, usuario["id"], usuario["rol"], texto)
    return True


@_mutador
def cerrar_conversacion(codigo: str, usuario: dict) -> bool:
    c = _conversacion_por_codigo(codigo)
    if (not c or not puede(usuario, "mesa.cerrar") or c["estado"] == "Cerrada"
            or not puede_ver_conversacion(usuario, c)):
        return False
    c["estado"] = "Cerrada"
    _mensaje(c, None, "Sistema", f"{usuario['nombre']} cerró la conversación.")
    return True


# --------------------------------------------------------------------------
# Datos de ejemplo (semilla) — las fechas son relativas a "ahora"
# --------------------------------------------------------------------------

_AREAS_DEMO = ["Contabilidad", "Ventas", "Recursos Humanos", "Compras", "Operaciones"]
_SUCURSALES_DEMO = ["Matriz CDMX", "Monterrey", "Guadalajara"]

# (tipo, tiempo estimado de solución en horas; de ahí sale la prioridad: menos tiempo = más prioridad)
_TIPOS_DEMO = [
    ("Incidencia de software", 12),
    ("Incidencia de hardware", 48),
    ("Mantenimiento correctivo", 60),
    ("Consultoría tecnológica", 96),
    ("Solicitud de nuevo acceso", 120),
    ("Mantenimiento preventivo", 168),
    ("Desarrollo de aplicación", 240),
]

# NOTA: las contraseñas de demostración solo aparecen aquí y en el README; en
# memoria se guardan únicamente con hash. Si cambias alguna, ejecuta `python main.py --reiniciar`
# para que se apliquen (los datos guardados en disco conservan las contraseñas anteriores).
# (nombre, usuario, contraseña, rol, área, correo, sucursal)
_CUENTAS_DEMO = [
    ("Sebastián Estrada", "sestrada", "Est_001", ROL_TECNICO, None, "sestradaa01@ipn.mx", None),
    ("Daniel López", "dlopez", "Lop_002", ROL_TECNICO, None, "dlopeza1900@ipn.mx", None),
    ("Zyanya Arriaga", "zarriaga", "Arr_003", ROL_TECNICO, None, "zarriagai2100@alumno.ipn.mx", None),
    ("Gabriel Santiago", "gsantiago", "San_004", ROL_TECNICO, None, "gsantiagog1800@alumno.ipn.mx", None),
    ("Jesús Montes", "jmontes", "Mon_005", ROL_TECNICO, None, "jmontest2200@alumno.ipn.mx", None),
    ("Ana Reyes", "areyes", "Rey_006", ROL_REPRESENTANTE, "Contabilidad", "areyes@techsolve.mx", "Matriz CDMX"),
    ("Carlos Peña", "cpena", "Pen_007", ROL_REPRESENTANTE, "Ventas", "cpena@clienteext.mx", "Monterrey"),
    ("Laura Ríos", "lrios", "Rio_008", ROL_REPRESENTANTE, "Recursos Humanos", "lrios@techsolve.mx", "Guadalajara"),
    ("Dirección General", "direccion", "Dir_000", ROL_ADMINISTRADOR, None, "direccion@techsolve.mx", None),
]


def _id_por_login(login: str) -> int:
    return next(u["id"] for u in _USUARIOS if u["usuario"] == login)


def _sembrar_catalogos():
    for nombre in _AREAS_DEMO:
        _contadores["area"] += 1
        _AREAS.append({"id": _contadores["area"], "nombre": nombre, "activa": True})
    for nombre in _SUCURSALES_DEMO:
        _contadores["sucursal"] += 1
        _SUCURSALES.append({"id": _contadores["sucursal"], "nombre": nombre, "activa": True})
    for nombre, horas in _TIPOS_DEMO:
        _contadores["tipo"] += 1
        _TIPOS.append({"id": _contadores["tipo"], "nombre": nombre, "horas": horas, "activo": True})


def _sembrar_solicitudes():
    """Solicitudes de ejemplo, una de cada situación para probar los flujos: finalizada y calificada,
    en proceso, visualizada, sin visualizar, finalizada esperando la calificación (la de Ana: pruébala con
    la cuenta areyes), y dos sin asignar (para que el administrador las distribuya)."""
    d, h = (lambda n: timedelta(days=n)), (lambda n: timedelta(hours=n))
    ejemplos = [
        dict(tipo="Incidencia de hardware", descripcion="La impresora del área no responde.",
             solicitante="areyes", agente="sestrada", estado="Finalizado", hace=d(6), final=d(4), calificacion=5),
        dict(tipo="Incidencia de software", descripcion="Error al iniciar sesión en el ERP.",
             solicitante="cpena", agente="sestrada", estado="En proceso", hace=h(10), final=None, calificacion=None),
        dict(tipo="Solicitud de nuevo acceso", descripcion="Acceso a VPN para trabajo remoto.",
             solicitante="areyes", agente=None, estado="Sin visualizar", hace=d(1), final=None, calificacion=None),
        dict(tipo="Desarrollo de aplicación", descripcion="Ajuste al módulo de reportes mensuales.",
             solicitante="lrios", agente="dlopez", estado="Visualizado", hace=d(3), final=None, calificacion=None),
        dict(tipo="Mantenimiento preventivo", descripcion="Revisión trimestral de switches.",
             solicitante="areyes", agente="zarriaga", estado="Finalizado", hace=d(12), final=d(10), calificacion=None),
        dict(tipo="Consultoría tecnológica", descripcion="Evaluación de proveedor de nube para respaldo.",
             solicitante="cpena", agente=None, estado="Sin visualizar", hace=timedelta(0), final=None, calificacion=None),
        dict(tipo="Mantenimiento correctivo", descripcion="El equipo de la recepción se reinicia solo.",
             solicitante="lrios", agente="gsantiago", estado="Sin visualizar", hace=h(5), final=None, calificacion=None),
    ]
    ahora = _ahora()
    for ej in ejemplos:
        sol = _usuario_por_id(_id_por_login(ej["solicitante"]))
        agente_id = _id_por_login(ej["agente"]) if ej["agente"] else None
        creada = ahora - ej["hace"]
        final = ahora - ej["final"] if ej["final"] is not None else None
        s = _nueva_solicitud(_tipo_por_nombre(ej["tipo"])["id"], ej["descripcion"], sol["area_id"], sol["sucursal_id"],
                             sol["id"], creada, estado=ej["estado"], agente_id=agente_id, finalizada_en=final,
                             calificada_en=final, calificacion=ej["calificacion"])
        _bitacora(s, sol["id"], "Solicitud creada", creada)
        if agente_id:
            _bitacora(s, _id_por_login("direccion"), f"Asignada a {_nombre(agente_id)} por Dirección General", creada)
        if ej["estado"] in ("Visualizado", "En proceso", "Finalizado"):
            _bitacora(s, agente_id, "Estatus actualizado a 'Visualizado'", creada)
        if ej["estado"] in ("En proceso", "Finalizado"):
            _bitacora(s, agente_id, "Estatus actualizado a 'En proceso'", creada)
        if final:
            _bitacora(s, agente_id, "Estatus actualizado a 'Finalizado' — Trabajo concluido (pendiente de calificación del representante)", final)
        if ej["calificacion"]:
            _bitacora(s, sol["id"], f"El representante calificó el servicio recibido ({ej['calificacion']}/5)", final)
        if not agente_id:
            _bitacora(s, None, "Pendiente de asignación: el Administrador la distribuirá a un técnico", creada)


def _sembrar_conversaciones():
    ana, carlos, sebastian = _id_por_login("areyes"), _id_por_login("cpena"), _id_por_login("sestrada")
    direccion = _id_por_login("direccion")

    c1 = _nueva_conversacion(ana, "No puedo imprimir desde mi equipo",
                             "Buenos días, la impresora del área sigue sin responder aunque ya la reinicié.",
                             1, _hace(5))
    c1["estado"] = "En atención"
    _mensaje(c1, direccion, ROL_ADMINISTRADOR,
             "Hola Ana, el técnico ya revisó la cola de impresión. Hoy mismo se reinstala el controlador.", _hace(5))

    _nueva_conversacion(carlos, "Duda sobre el tiempo de atención de mi solicitud",
                        "¿Me pueden confirmar en cuánto tiempo revisarán el error del ERP?", 2, _hace(1))
    _nueva_conversacion(sebastian, "Falta una refacción para la impresora",
                        "Necesito autorización para comprar un kit de fusor; sin él no puedo finalizar el reporte.", 1, _hace(2))


def _vaciar():
    for lista in (_AREAS, _SUCURSALES, _TIPOS, _USUARIOS, _SOLICITUDES, _ADJUNTOS, _CONVERSACIONES, _CODIGOS,
                  _registros_recientes, _solicitudes_recuperacion):
        lista.clear()
    for clave in _contadores:
        _contadores[clave] = 0
    _limitador.reiniciar()


def reiniciar():
    """Vuelve a los datos de ejemplo (también se usa en las pruebas automatizadas)."""
    _vaciar()
    _sembrar_catalogos()
    for nombre, usuario, contrasena, rol, area, correo, sucursal in _CUENTAS_DEMO:
        _alta_usuario(nombre, usuario, contrasena, rol, area, correo, sucursal)
    _sembrar_solicitudes()
    _sembrar_conversaciones()
    _cambio()


# --------------------------------------------------------------------------
# Exportar / importar el estado completo (lo usan persistencia.py y los respaldos)
# --------------------------------------------------------------------------

VERSION_ESTADO = 3


class VersionIncompatible(ValueError):
    """Los datos son de otra versión de la aplicación (formato anterior o posterior)."""


def _iso(d):
    return d.isoformat() if d else None


def _dt(texto):
    return datetime.fromisoformat(texto) if texto else None


def exportar_estado() -> dict:
    """Estado completo en tipos simples (listo para JSON). El contenido de los adjuntos NO va aquí:
    se obtiene con `contenidos_adjuntos()`."""
    return {
        "version": VERSION_ESTADO,
        "contadores": dict(_contadores),
        "areas": [dict(a) for a in _AREAS],
        "sucursales": [dict(x) for x in _SUCURSALES],
        "tipos": [dict(t) for t in _TIPOS],
        "usuarios": [dict(u) for u in _USUARIOS],
        "solicitudes": [
            {**{k: v for k, v in s.items() if k not in ("creada_en", "plazo_desde", "finalizada_en", "calificada_en", "bitacora")},
             "creada_en": _iso(s["creada_en"]), "plazo_desde": _iso(s["plazo_desde"]),
             "finalizada_en": _iso(s["finalizada_en"]), "calificada_en": _iso(s["calificada_en"]),
             "bitacora": [{"seq": b.seq, "fecha": _iso(b.fecha), "autor_id": b.autor_id, "evento": b.evento,
                           "hash_prev": b.hash_prev, "hash": b.hash} for b in s["bitacora"]]}
            for s in _SOLICITUDES],
        "adjuntos": [{**{k: v for k, v in a.items() if k not in ("contenido", "fecha")}, "fecha": _iso(a["fecha"])}
                     for a in _ADJUNTOS],
        "conversaciones": [
            {**{k: v for k, v in c.items() if k != "mensajes"},
             "mensajes": [{**m, "fecha": _iso(m["fecha"])} for m in c["mensajes"]]} for c in _CONVERSACIONES],
        "codigos": [{**c, "creado_en": _iso(c["creado_en"]), "expira_en": _iso(c["expira_en"])} for c in _CODIGOS],
    }


def contenidos_adjuntos() -> dict:
    """{id_adjunto: bytes} de todos los archivos adjuntos."""
    return {a["id"]: a["contenido"] for a in _ADJUNTOS}


def importar_estado(estado: dict, contenidos: dict) -> None:
    """Reemplaza TODO el estado por el recibido. Valida la estructura y la integridad de la bitácora
    ANTES de tocar nada: si algo no cuadra lanza ValueError y el estado actual queda intacto."""
    try:
        if estado.get("version") != VERSION_ESTADO:
            raise VersionIncompatible(f"versión de datos no compatible ({estado.get('version')!r})")
        nuevo = {
            "contadores": {k: int(estado["contadores"][k]) for k in _contadores},   # claves de más (respaldos viejos) se ignoran
            "areas": [{"id": int(a["id"]), "nombre": str(a["nombre"]), "activa": bool(a["activa"])} for a in estado["areas"]],
            "sucursales": [{"id": int(x["id"]), "nombre": str(x["nombre"]), "activa": bool(x["activa"])} for x in estado["sucursales"]],
            "tipos": [{"id": int(t["id"]), "nombre": str(t["nombre"]),
                       "horas": int(t["horas"]) if 1 <= int(t["horas"]) <= MAX_HORAS_TIPO else (_ for _ in ()).throw(ValueError("horas")),
                       "activo": bool(t["activo"])} for t in estado["tipos"]],
            "usuarios": [{"id": int(u["id"]), "nombre": str(u["nombre"]), "usuario": str(u["usuario"]),
                          "correo": str(u["correo"]), "contrasena_hash": str(u["contrasena_hash"]),
                          "rol": u["rol"] if u["rol"] in ROLES else (_ for _ in ()).throw(ValueError("rol")),
                          "area_id": None if u["area_id"] is None else int(u["area_id"]),
                          "sucursal_id": None if u["sucursal_id"] is None else int(u["sucursal_id"]), "activo": bool(u["activo"])}
                         for u in estado["usuarios"]],
            "solicitudes": [], "adjuntos": [], "conversaciones": [], "codigos": [],
        }
        for s in estado["solicitudes"]:
            if s["estado"] not in ESTADOS or s["prioridad"] not in PRIORIDADES:
                raise ValueError("estado o prioridad no válidos")
            nuevo["solicitudes"].append({
                "id": int(s["id"]), "folio": str(s["folio"]), "tipo_id": int(s["tipo_id"]), "area_id": int(s["area_id"]),
                "sucursal_id": int(s["sucursal_id"]),
                "descripcion": str(s["descripcion"]), "prioridad": s["prioridad"], "estado": s["estado"],
                "solicitante_id": int(s["solicitante_id"]),
                "agente_id": None if s["agente_id"] is None else int(s["agente_id"]),
                "creada_en": _dt(s["creada_en"]), "plazo_desde": _dt(s["plazo_desde"]),
                "finalizada_en": _dt(s["finalizada_en"]), "calificada_en": _dt(s["calificada_en"]),
                "calificacion": None if s["calificacion"] is None else int(s["calificacion"]),
                "sla_horas": int(s["sla_horas"]),
                "bitacora": tuple(EntradaBitacora(int(b["seq"]), _dt(b["fecha"]), b["autor_id"], str(b["evento"]),
                                                  str(b["hash_prev"]), str(b["hash"])) for b in s["bitacora"]),
            })
        for a in estado["adjuntos"]:
            contenido = contenidos.get(int(a["id"]))
            if contenido is None:
                raise ValueError(f"falta el archivo adjunto {a['id']}")
            nuevo["adjuntos"].append({"id": int(a["id"]), "solicitud_id": int(a["solicitud_id"]), "nombre": str(a["nombre"]),
                                      "tipo": str(a["tipo"]), "tamano": int(a["tamano"]),
                                      "subido_por_id": int(a["subido_por_id"]), "fecha": _dt(a["fecha"]),
                                      "contenido": bytes(contenido)})
        for c in estado["conversaciones"]:
            nuevo["conversaciones"].append({
                "id": int(c["id"]), "codigo": str(c["codigo"]), "asunto": str(c["asunto"]),
                "solicitante_id": int(c["solicitante_id"]),
                "solicitud_id": None if c["solicitud_id"] is None else int(c["solicitud_id"]),
                "estado": c["estado"] if c["estado"] in ESTADOS_CONVERSACION else (_ for _ in ()).throw(ValueError("estado")),
                "mensajes": [{"autor_id": m["autor_id"], "rol": str(m["rol"]), "texto": str(m["texto"]),
                              "fecha": _dt(m["fecha"])} for m in c["mensajes"]]})
        for c in estado.get("codigos", []):
            nuevo["codigos"].append({"id": int(c["id"]), "usuario_id": int(c["usuario_id"]), "codigo_hash": str(c["codigo_hash"]),
                                     "creado_en": _dt(c["creado_en"]), "expira_en": _dt(c["expira_en"]),
                                     "intentos": int(c["intentos"]), "usado": bool(c["usado"])})
    except VersionIncompatible:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"El archivo de datos no es válido ({error}).") from error

    # la integridad de la bitácora se comprueba sobre el estado NUEVO antes de aplicarlo
    problemas = _problemas_bitacora(nuevo["solicitudes"], nuevo["contadores"]["bitacora"])
    if problemas:
        raise ValueError("La bitácora de los datos no está íntegra: " + problemas[0])

    _vaciar()
    _contadores.update(nuevo["contadores"])
    _AREAS.extend(nuevo["areas"])
    _SUCURSALES.extend(nuevo["sucursales"])
    _TIPOS.extend(nuevo["tipos"])
    _USUARIOS.extend(nuevo["usuarios"])
    _SOLICITUDES.extend(nuevo["solicitudes"])
    _ADJUNTOS.extend(nuevo["adjuntos"])
    _CONVERSACIONES.extend(nuevo["conversaciones"])
    _CODIGOS.extend(nuevo["codigos"])


reiniciar()
