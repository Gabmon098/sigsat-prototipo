"""Recuperación de contraseña por código enviado al correo, y bloqueo por intentos fallidos (por cuenta)."""

import re
import unittest
from datetime import datetime, timedelta

from pruebas.base import Base
import datos
import seguridad


class PruebasRecuperacion(Base):
    def pedir(self, identificador="dlopez"):
        """Pide un código y devuelve (código, mensaje) tal como lo leería la persona en su correo."""
        antes = len(self.buzon)
        datos.solicitar_recuperacion(identificador)
        if len(self.buzon) == antes:
            return None, None
        m = self.buzon[-1]
        codigo = re.search(r"\b([A-Z2-9]{4}-[A-Z2-9]{4})\b", self.cuerpo(m)).group(1)
        return codigo, m

    def test_se_envia_un_codigo_al_correo_de_la_cuenta(self):
        codigo, m = self.pedir("dlopez")
        self.assertEqual(m["To"], "dlopeza1900@ipn.mx")
        self.assertRegex(codigo, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertNotRegex(codigo, r"[01OIL]", "sin caracteres que se confunden al copiarlo")
        self.assertIn("30 minutos", self.cuerpo(m))

    def test_tambien_funciona_con_el_correo_y_sin_importar_mayusculas(self):
        codigo, m = self.pedir("DLOPEZA1900@IPN.MX")
        self.assertIsNotNone(codigo)

    def test_con_el_codigo_se_cambia_la_contrasena(self):
        codigo, _ = self.pedir("dlopez")
        datos.restablecer_con_codigo("dlopez", codigo, "NuevaClave-99")
        self.assertIsNotNone(datos.autenticar("dlopez", "NuevaClave-99"))
        self.assertIsNone(datos.autenticar("dlopez", "Lop_002"))

    def test_el_codigo_acepta_minusculas_espacios_y_sin_guion(self):
        codigo, _ = self.pedir("dlopez")
        datos.restablecer_con_codigo("dlopez", "  " + codigo.lower().replace("-", " ") + " ", "NuevaClave-99")
        self.assertIsNotNone(datos.autenticar("dlopez", "NuevaClave-99"))

    def test_el_codigo_solo_sirve_una_vez(self):
        codigo, _ = self.pedir("dlopez")
        datos.restablecer_con_codigo("dlopez", codigo, "NuevaClave-99")
        with self.assertRaisesRegex(ValueError, "no es válido"):
            datos.restablecer_con_codigo("dlopez", codigo, "OtraClave-1234")

    def test_un_codigo_vencido_no_sirve(self):
        codigo, _ = self.pedir("dlopez")
        for c in datos._CODIGOS:
            c["expira_en"] = datetime.now() - timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, "no es válido o ya venció"):
            datos.restablecer_con_codigo("dlopez", codigo, "NuevaClave-99")
        self.assertIsNotNone(datos.autenticar("dlopez", "Lop_002"), "la contraseña no debió cambiar")

    def test_el_codigo_vale_30_minutos(self):
        self.pedir("dlopez")
        c = datos._CODIGOS[-1]
        self.assertAlmostEqual((c["expira_en"] - c["creado_en"]).total_seconds(), 30 * 60, delta=2)

    def test_un_codigo_equivocado_se_invalida_tras_5_intentos(self):
        codigo, _ = self.pedir("dlopez")
        for i in range(datos.CODIGO_MAX_INTENTOS):
            with self.assertRaisesRegex(ValueError, "no es válido"):
                datos.restablecer_con_codigo("dlopez", "AAAA-BBBB", "NuevaClave-99")
        with self.assertRaisesRegex(ValueError, "no es válido"):                       # ni siquiera el bueno
            datos.restablecer_con_codigo("dlopez", codigo, "NuevaClave-99")
        self.assertIsNotNone(datos.autenticar("dlopez", "Lop_002"))

    def test_pedir_otro_codigo_deja_sin_efecto_el_anterior(self):
        primero, _ = self.pedir("dlopez")
        segundo, _ = self.pedir("dlopez")
        with self.assertRaisesRegex(ValueError, "no es válido"):
            datos.restablecer_con_codigo("dlopez", primero, "NuevaClave-99")
        datos.restablecer_con_codigo("dlopez", segundo, "NuevaClave-99")

    def test_el_codigo_de_una_cuenta_no_sirve_para_otra(self):
        codigo, _ = self.pedir("dlopez")
        datos.solicitar_recuperacion("areyes")
        with self.assertRaisesRegex(ValueError, "no es válido"):
            datos.restablecer_con_codigo("areyes", codigo, "NuevaClave-99")

    def test_la_contrasena_nueva_debe_cumplir_las_reglas_y_no_gasta_el_codigo(self):
        codigo, _ = self.pedir("dlopez")
        with self.assertRaisesRegex(ValueError, "al menos 8"):
            datos.restablecer_con_codigo("dlopez", codigo, "corta")
        with self.assertRaisesRegex(ValueError, "demasiado larga"):
            datos.restablecer_con_codigo("dlopez", codigo, "x" * 129)
        datos.restablecer_con_codigo("dlopez", codigo, "Correcta-123")                 # el código sigue vigente

    def test_cuenta_inexistente_o_desactivada_no_envia_nada_ni_lo_delata(self):
        self.assertEqual(self.pedir("noexiste"), (None, None))
        datos.actualizar_usuario(self.gabriel["id"], "Gabriel Santiago", "gsantiago", "", "Técnico", None,
                                 "gsantiagog1800@alumno.ipn.mx", activo=False)
        self.assertEqual(self.pedir("gsantiago"), (None, None))
        # quien llama no recibe ninguna señal: la función no devuelve nada ni lanza errores
        self.assertIsNone(datos.solicitar_recuperacion("noexiste"))
        self.assertIsNone(datos.solicitar_recuperacion("dlopez"))
        # y el error al canjear es el mismo exista o no la cuenta
        mensajes = set()
        for ident in ("noexiste", "areyes", "gsantiago"):
            with self.assertRaises(ValueError) as cm:
                datos.restablecer_con_codigo(ident, "AAAA-BBBB", "NuevaClave-99")
            mensajes.add(str(cm.exception))
        self.assertEqual(len(mensajes), 1)

    def test_limite_de_3_codigos_por_hora_por_cuenta(self):
        for i in range(datos.RECUPERACION_MAX_POR_CUENTA_HORA):
            self.assertIsNotNone(self.pedir("dlopez")[0], f"solicitud {i + 1}")
        self.assertEqual(self.pedir("dlopez"), (None, None))
        self.assertIsNotNone(self.pedir("areyes")[0], "otra cuenta no se ve afectada")

    def test_limite_global_por_hora(self):
        cuentas = ["dlopez", "areyes", "cpena", "zarriaga", "sestrada", "gsantiago", "jmontes", "direccion"]
        enviados = 0
        for i in range(datos.RECUPERACION_MAX_GLOBAL_HORA + 3):
            enviados += self.pedir(cuentas[i % len(cuentas)])[0] is not None
        self.assertLessEqual(enviados, datos.RECUPERACION_MAX_GLOBAL_HORA)
        self.assertEqual(self.pedir("direccion"), (None, None))

    def test_el_codigo_se_guarda_solo_como_hash(self):
        codigo, _ = self.pedir("dlopez")
        registro = datos._CODIGOS[-1]
        self.assertNotIn(codigo.replace("-", ""), registro["codigo_hash"])
        self.assertTrue(registro["codigo_hash"].startswith(("scrypt", "pbkdf2")))
        self.assertNotIn(codigo.replace("-", ""), str(datos.exportar_estado()))

    def test_restablecer_levanta_el_bloqueo_de_la_cuenta(self):
        for _ in range(seguridad.MAX_INTENTOS - 1):
            self.assertIsNone(datos.autenticar("dlopez", "mala"))
        with self.assertRaises(seguridad.BloqueoTemporal):
            datos.autenticar("dlopez", "mala")
        codigo, _ = self.pedir("dlopez")
        datos.restablecer_con_codigo("dlopez", codigo, "NuevaClave-99")
        self.assertIsNotNone(datos.autenticar("dlopez", "NuevaClave-99"))

    def test_el_correo_del_codigo_se_oculta_en_la_bandeja_si_hay_servidor_real(self):
        from unittest import mock
        import correo
        correo.configurar(transporte=lambda m: None)                       # no se manda nada de verdad
        with mock.patch.object(correo, "modo", return_value="smtp"):
            datos.solicitar_recuperacion("dlopez")
        reg = correo.bandeja()[0]
        self.assertIn("no almacenado", reg["cuerpo"])
        self.assertNotRegex(reg["cuerpo"], r"[A-Z2-9]{4}-[A-Z2-9]{4}")

    def test_en_modo_desarrollo_el_codigo_si_queda_visible_en_la_bandeja(self):
        datos.solicitar_recuperacion("dlopez")
        self.assertRegex(__import__("correo").bandeja()[0]["cuerpo"], r"[A-Z2-9]{4}-[A-Z2-9]{4}")


class PruebasBloqueoPorCuenta(Base):
    def test_cinco_fallos_bloquean_la_cuenta(self):
        for _ in range(seguridad.MAX_INTENTOS - 1):
            self.assertIsNone(datos.autenticar("areyes", "mala"))
        with self.assertRaises(seguridad.BloqueoTemporal) as cm:
            datos.autenticar("areyes", "mala")
        self.assertLessEqual(cm.exception.segundos, seguridad.BLOQUEO_SEGUNDOS)
        with self.assertRaises(seguridad.BloqueoTemporal):                                  # ni con la clave correcta
            datos.autenticar("areyes", "Rey_006")

    def test_usuario_y_correo_de_la_misma_cuenta_cuentan_contra_el_mismo_limite(self):
        datos.autenticar("areyes", "mala")
        datos.autenticar("areyes@techsolve.mx", "mala")
        datos.autenticar("AREYES", "mala")
        datos.autenticar("AREYES@TECHSOLVE.MX", "mala")
        with self.assertRaises(seguridad.BloqueoTemporal):
            datos.autenticar("areyes", "mala")

    def test_el_bloqueo_no_afecta_a_otras_cuentas(self):
        for _ in range(seguridad.MAX_INTENTOS):
            try:
                datos.autenticar("areyes", "mala")
            except seguridad.BloqueoTemporal:
                pass
        self.assertIsNotNone(datos.autenticar("cpena", "Pen_007"))

    def test_una_cuenta_inexistente_se_bloquea_igual(self):
        for _ in range(seguridad.MAX_INTENTOS - 1):
            self.assertIsNone(datos.autenticar("fantasma", "x"))
        with self.assertRaises(seguridad.BloqueoTemporal):
            datos.autenticar("fantasma", "x")

    def test_un_acierto_reinicia_la_cuenta(self):
        for _ in range(seguridad.MAX_INTENTOS - 1):
            datos.autenticar("areyes", "mala")
        self.assertIsNotNone(datos.autenticar("areyes", "Rey_006"))
        for _ in range(seguridad.MAX_INTENTOS - 1):
            self.assertIsNone(datos.autenticar("areyes", "mala"))


if __name__ == "__main__":
    unittest.main()
