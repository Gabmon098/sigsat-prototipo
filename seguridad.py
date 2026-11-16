"""
Seguridad del prototipo SIGSAT: contraseñas con hash y límite de intentos
fallidos de inicio de sesión.

Solo usa la biblioteca estándar (hashlib / hmac), así que no agrega
dependencias. En el sistema real (Sprint 3) esto pasa a bcrypt/argon2 del
back-end; aquí se conserva la misma idea: nunca se guarda la contraseña en
texto plano y la comparación no revela cuánto coincide.
"""

import hashlib
import hmac
import math
import os
import time

# --------------------------------------------------------------------------
# Hash de contraseñas
# --------------------------------------------------------------------------
# Formato almacenado:  algoritmo$sal_hex$hash_hex
# Se guarda el algoritmo para poder cambiarlo después sin invalidar cuentas.

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
_PBKDF2_ITER = 200_000


def hashear_contrasena(contrasena: str) -> str:
    sal = os.urandom(16)
    datos = contrasena.encode("utf-8")
    try:
        h = hashlib.scrypt(datos, salt=sal, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
        algoritmo = "scrypt"
    except (AttributeError, ValueError):
        # Python compilado sin scrypt (OpenSSL antiguo): se usa PBKDF2.
        h = hashlib.pbkdf2_hmac("sha256", datos, sal, _PBKDF2_ITER)
        algoritmo = "pbkdf2"
    return f"{algoritmo}${sal.hex()}${h.hex()}"


def verificar_contrasena(contrasena: str, almacenado: str) -> bool:
    try:
        algoritmo, sal_hex, hash_hex = almacenado.split("$")
        sal = bytes.fromhex(sal_hex)
        esperado = bytes.fromhex(hash_hex)
        datos = contrasena.encode("utf-8")
        if algoritmo == "scrypt":
            h = hashlib.scrypt(datos, salt=sal, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=len(esperado))
        elif algoritmo == "pbkdf2":
            h = hashlib.pbkdf2_hmac("sha256", datos, sal, _PBKDF2_ITER, dklen=len(esperado))
        else:
            return False
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(h, esperado)


# Hash de relleno: se verifica cuando la cuenta no existe, para que el tiempo
# de respuesta no revele si el usuario existe o no.
HASH_RELLENO = hashear_contrasena(os.urandom(12).hex())


# --------------------------------------------------------------------------
# Límite de intentos fallidos
# --------------------------------------------------------------------------

MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 60


class BloqueoTemporal(Exception):
    """Demasiados intentos fallidos: hay que esperar `segundos` para reintentar."""

    def __init__(self, segundos: int):
        super().__init__(f"Bloqueado temporalmente ({segundos} s)")
        self.segundos = segundos


class LimitadorIntentos:
    """Cuenta fallos por identificador (usuario o correo) y bloquea un rato
    al llegar al máximo. El reloj es inyectable para poder probarlo."""

    def __init__(self, maximo: int = MAX_INTENTOS, bloqueo: int = BLOQUEO_SEGUNDOS, reloj=time.monotonic):
        self.maximo = maximo
        self.bloqueo = bloqueo
        self._reloj = reloj
        self._estado = {}   # clave -> [fallos, bloqueado_hasta]

    def segundos_restantes(self, clave: str) -> int:
        est = self._estado.get(clave)
        if not est or est[1] is None:
            return 0
        restante = est[1] - self._reloj()
        if restante <= 0:
            del self._estado[clave]      # el bloqueo terminó: se empieza de cero
            return 0
        return math.ceil(restante)

    def registrar_fallo(self, clave: str) -> None:
        if self.segundos_restantes(clave):
            return
        est = self._estado.setdefault(clave, [0, None])
        est[0] += 1
        if est[0] >= self.maximo:
            est[0] = 0
            est[1] = self._reloj() + self.bloqueo

    def registrar_exito(self, clave: str) -> None:
        self._estado.pop(clave, None)

    def reiniciar(self) -> None:
        self._estado.clear()
