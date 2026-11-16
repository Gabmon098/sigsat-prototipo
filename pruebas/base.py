"""Utilidades comunes de las pruebas nuevas (no son pruebas)."""

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import correo
import datos
import persistencia


def cuenta(login):
    return next(u for u in datos.usuarios_todos() if u["usuario"] == login)


class Base(unittest.TestCase):
    """Cada prueba parte de los datos de ejemplo, sin guardar en disco y con un «buzón» de correo falso."""

    def setUp(self):
        persistencia.desactivar()
        correo.reiniciar()
        datos.reiniciar()
        self.buzon = []
        correo.configurar(transporte=lambda msg: self.buzon.append(msg))
        self.admin = cuenta("direccion")
        self.ana = cuenta("areyes")
        self.carlos = cuenta("cpena")
        self.sebastian = cuenta("sestrada")
        self.gabriel = cuenta("gsantiago")
        self.zyanya = cuenta("zarriaga")
        self.laura = cuenta("lrios")

    def tearDown(self):
        persistencia.desactivar()
        correo.reiniciar()

    # ---- ayudantes
    # Tipo de ejemplo de cada prioridad (la prioridad sale del tiempo estimado del tipo, no la elige quien solicita)
    TIPO_DE_PRIORIDAD = {"Alta": "Incidencia de software", "Media": "Incidencia de hardware", "Baja": "Solicitud de nuevo acceso"}

    def nueva(self, tipo=None, prioridad=None, usuario=None, desc="No abre el sistema", tecnico=None, **kw):
        """Registra una solicitud como Representante de Área (por omisión Ana) y, por comodidad, la deja asignada
        al técnico `tecnico` (por omisión Sebastián). Con `tecnico=False` queda sin asignar. Si se pide una
        `prioridad` se usa el tipo de esa prioridad."""
        tipo = tipo or self.TIPO_DE_PRIORIDAD[prioridad or "Alta"]
        s = datos.crear_solicitud(tipo, desc, usuario or self.ana, **kw)
        if tecnico is not False:
            datos.asignar_solicitud(s["folio"], self.admin, (tecnico or self.sebastian)["id"])
            s = datos.buscar_por_folio(s["folio"])
        return s

    def nueva_sin_asignar(self, tipo=None, prioridad=None, usuario=None, desc="No abre el sistema"):
        return self.nueva(tipo, prioridad, usuario, desc, tecnico=False)

    def interna(self, folio):
        return datos._solicitud_por_folio(folio)

    def envejecer(self, folio, horas):
        """Hace que la solicitud se haya registrado hace `horas` horas (simula el paso del tiempo)."""
        s = self.interna(folio)
        s["creada_en"] = s["plazo_desde"] = datetime.now().replace(second=0, microsecond=0) - timedelta(hours=horas)

    def correos(self, para=None):
        res = [m for m in self.buzon]
        return [m for m in res if para is None or m["To"] == para]

    def asuntos(self):
        return [m["Subject"] for m in self.buzon]

    def cuerpo(self, mensaje):
        return mensaje.get_content()
