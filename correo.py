"""
Correo saliente de SIGSAT (RF-11 asignación, RF-12 cambio de estatus y recuperación
de contraseña). Solo usa la biblioteca estándar.

Cómo sale el correo:

* Si defines la variable de entorno ``SIGSAT_SMTP_HOST`` se usa ese servidor SMTP real.
* Si no, estás en **modo desarrollo**: no se envía nada a Internet; cada mensaje se
  guarda como archivo ``.eml`` en la carpeta ``correos_salida/`` y aparece en
  Administración → Correos enviados (es el equivalente a una "bandeja de pruebas").
  Así no se escribe por accidente a las direcciones de ejemplo.

Variables de entorno para el servidor real:

    SIGSAT_SMTP_HOST       servidor (obligatoria para enviar de verdad)
    SIGSAT_SMTP_PORT       puerto (587 con tls, 465 con ssl, 25 sin cifrado)
    SIGSAT_SMTP_SECURE     tls = STARTTLS (por defecto) · ssl = TLS implícito · none = sin cifrado
    SIGSAT_SMTP_USER / SIGSAT_SMTP_PASSWORD     si el servidor exige autenticación
    SIGSAT_MAIL_FROM       remitente (por defecto sigsat@techsolve.mx)

Seguridad: la conexión se cifra (TLS) validando el certificado del servidor, y NO se
envían usuario/contraseña por una conexión sin cifrar (salvo a localhost).

El envío se hace en un hilo aparte para que la ventana nunca se congele esperando
al servidor, y un fallo de correo jamás interrumpe la operación que lo originó.
"""

import logging
import os
import re
import smtplib
import ssl
import threading
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

log = logging.getLogger("sigsat.correo")

MAX_BANDEJA = 200            # cuántos mensajes se recuerdan en la bandeja interna
_RE_DIRECCION = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")
TEXTO_OCULTO = "[Contenido no almacenado: incluye un código de seguridad]"

_lock = threading.Lock()
_bandeja = []                # registros más recientes primero
_contador = 0
_config = {"asincrono": False, "transporte": None, "carpeta": None}


# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------

def configurar(asincrono=None, transporte="__sin_cambio__", carpeta="__sin_cambio__") -> None:
    """asincrono: enviar en un hilo aparte (la aplicación lo activa; las pruebas no).
    transporte: función(EmailMessage) que reemplaza el envío real (solo pruebas).
    carpeta: dónde guardar los .eml en modo desarrollo (None = no guardar archivos)."""
    if asincrono is not None:
        _config["asincrono"] = bool(asincrono)
    if transporte != "__sin_cambio__":
        _config["transporte"] = transporte
    if carpeta != "__sin_cambio__":
        _config["carpeta"] = Path(carpeta) if carpeta else None


def reiniciar() -> None:
    """Vacía la bandeja y vuelve a la configuración por defecto (pruebas)."""
    global _contador
    with _lock:
        _bandeja.clear()
        _contador = 0
    _config.update(asincrono=False, transporte=None, carpeta=None)


def modo() -> str:
    """'personalizado' (pruebas) · 'smtp' (servidor real) · 'desarrollo' (sin servidor)."""
    if _config["transporte"] is not None:
        return "personalizado"
    return "smtp" if os.environ.get("SIGSAT_SMTP_HOST", "").strip() else "desarrollo"


def carpeta_salida():
    return _config["carpeta"]


def bandeja() -> list:
    """Copia de los mensajes recientes (más nuevos primero)."""
    with _lock:
        return [dict(r) for r in _bandeja]


# --------------------------------------------------------------------------
# Envío
# --------------------------------------------------------------------------

def direccion_valida(direccion) -> bool:
    return bool(direccion) and len(direccion) <= 254 and bool(_RE_DIRECCION.match(direccion))


def _armar(para: str, asunto: str, cuerpo: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"SIGSAT <{os.environ.get('SIGSAT_MAIL_FROM', '').strip() or 'sigsat@techsolve.mx'}>"
    msg["To"] = para
    msg["Subject"] = re.sub(r"[\r\n]+", " ", asunto).strip()      # un asunto no puede traer saltos de línea
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="sigsat.local")
    msg.set_content(cuerpo, charset="utf-8")
    return msg


def enviar(para: str, asunto: str, cuerpo: str, tipo: str = "notificacion", sensible: bool = False):
    """Encola un correo. Devuelve su registro, o None si la dirección no es válida.
    Nunca lanza excepciones por problemas de envío: quedan anotados en el registro."""
    global _contador
    if not direccion_valida(para):
        log.warning("Correo omitido: dirección no válida (%r)", para)
        return None
    try:
        msg = _armar(para, asunto, cuerpo)
    except Exception as error:                                       # pragma: no cover (defensivo)
        log.warning("No se pudo armar el correo: %s", error)
        return None

    # Con servidor real, los mensajes con códigos de seguridad no se guardan en la bandeja interna.
    oculto = sensible and modo() == "smtp"
    with _lock:
        _contador += 1
        registro = {"id": _contador, "fecha": datetime.now().replace(microsecond=0), "para": para,
                    "asunto": msg["Subject"], "cuerpo": TEXTO_OCULTO if oculto else cuerpo,
                    "tipo": tipo, "estado": "en cola", "detalle": ""}
        _bandeja.insert(0, registro)
        del _bandeja[MAX_BANDEJA:]

    if _config["asincrono"]:
        threading.Thread(target=_despachar, args=(registro, msg), daemon=True).start()
    else:
        _despachar(registro, msg)
    return dict(registro)


def _despachar(registro: dict, msg: EmailMessage) -> None:
    try:
        transporte = _config["transporte"] or (_enviar_smtp if modo() == "smtp" else _guardar_eml)
        transporte(msg)
        resultado = ("enviado", "")
    except Exception as error:                                       # el correo falló: se anota, no se propaga
        log.warning("Falló el envío de correo a %s: %s", registro["para"], error)
        resultado = ("error", str(error)[:200])
    with _lock:
        registro["estado"], registro["detalle"] = resultado


def _guardar_eml(msg: EmailMessage) -> None:
    carpeta = _config["carpeta"]
    if carpeta is None:
        return
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".eml"
    (carpeta / nombre).write_bytes(msg.as_bytes())


def _enviar_smtp(msg: EmailMessage) -> None:
    host = os.environ.get("SIGSAT_SMTP_HOST", "").strip()
    seguridad = os.environ.get("SIGSAT_SMTP_SECURE", "tls").strip().lower()
    if seguridad not in ("tls", "ssl", "none"):
        raise RuntimeError("SIGSAT_SMTP_SECURE debe ser tls, ssl o none.")
    puerto = int(os.environ.get("SIGSAT_SMTP_PORT") or {"tls": 587, "ssl": 465, "none": 25}[seguridad])
    usuario = os.environ.get("SIGSAT_SMTP_USER", "")
    clave = os.environ.get("SIGSAT_SMTP_PASSWORD", "")
    if usuario and seguridad == "none" and host not in ("localhost", "127.0.0.1"):
        raise RuntimeError("Por seguridad no se envían credenciales por una conexión sin cifrar.")

    contexto = ssl.create_default_context()                          # valida el certificado del servidor
    if seguridad == "ssl":
        servidor = smtplib.SMTP_SSL(host, puerto, timeout=10, context=contexto)
    else:
        servidor = smtplib.SMTP(host, puerto, timeout=10)
    with servidor:
        servidor.ehlo()
        if seguridad == "tls":
            servidor.starttls(context=contexto)
            servidor.ehlo()
        if usuario:
            servidor.login(usuario, clave)
        servidor.send_message(msg)
