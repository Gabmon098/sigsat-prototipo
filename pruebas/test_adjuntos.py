"""Archivos adjuntos opcionales: validación, límites, permisos y retiro."""

import unittest

from pruebas.base import Base
import archivos
import datos

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50
PDF = b"%PDF-1.4\n" + b"0" * 50


class PruebasValidacionArchivos(unittest.TestCase):
    def test_archivos_validos(self):
        for nombre, contenido, tipo in [("captura.PNG", PNG, "image/png"), ("doc.pdf", PDF, "application/pdf"),
                                        ("foto.jpeg", b"\xff\xd8\xff\xe0abc", "image/jpeg"), ("error.log", b"ERROR algo", "text/plain"),
                                        ("datos.csv", b"a,b\n1,2", "text/csv"), ("hoja.xlsx", b"PK\x03\x04zz", None)]:
            with self.subTest(nombre=nombre):
                meta = archivos.validar_adjunto(nombre, contenido)
                self.assertEqual(meta["tamano"], len(contenido))
                if tipo:
                    self.assertEqual(meta["tipo"], tipo)

    def test_extensiones_peligrosas_o_desconocidas_se_rechazan(self):
        for nombre in ("virus.exe", "script.bat", "macro.docm", "app.js", "comprimido.zip", "sinextension", "doble.pdf.exe", "x.html"):
            with self.subTest(nombre=nombre), self.assertRaisesRegex(ValueError, "No se aceptan"):
                archivos.validar_adjunto(nombre, b"contenido")

    def test_el_contenido_debe_corresponder_a_la_extension(self):
        for nombre, contenido in [("falso.pdf", b"esto no es un pdf"), ("falso.png", PDF), ("falso.jpg", PNG),
                                  ("falso.docx", b"texto"), ("binario.txt", b"abc\x00def")]:
            with self.subTest(nombre=nombre), self.assertRaisesRegex(ValueError, "no corresponde"):
                archivos.validar_adjunto(nombre, contenido)

    def test_vacio_y_demasiado_grande(self):
        with self.assertRaisesRegex(ValueError, "vacío"):
            archivos.validar_adjunto("a.txt", b"")
        with self.assertRaisesRegex(ValueError, "máximo es 5.0 MB"):
            archivos.validar_adjunto("a.txt", b"x" * (archivos.MAX_TAMANO_ADJUNTO + 1))
        archivos.validar_adjunto("a.txt", b"x" * archivos.MAX_TAMANO_ADJUNTO)

    def test_el_nombre_se_limpia_y_no_admite_rutas(self):
        self.assertEqual(archivos.validar_adjunto("../../etc/passwd.txt", b"x")["nombre"], "passwd.txt")
        self.assertEqual(archivos.validar_adjunto("C:\\Users\\yo\\informe.txt", b"x")["nombre"], "informe.txt")
        self.assertEqual(archivos.validar_adjunto("a<b>c:d.txt", b"x")["nombre"], "a_b_c_d.txt")
        self.assertEqual(archivos.validar_adjunto("con\x00nulo\x1f.txt", b"x")["nombre"], "connulo.txt")
        for malo in ("", "   ", "...", "/"):
            with self.subTest(nombre=malo), self.assertRaisesRegex(ValueError, "nombre válido"):
                archivos.validar_adjunto(malo, b"x")
        with self.assertRaisesRegex(ValueError, "demasiado largo"):
            archivos.validar_adjunto("a" * 101 + ".txt", b"x")

    def test_formato_de_tamano(self):
        self.assertEqual(archivos.formato_tamano(850), "850 B")
        self.assertEqual(archivos.formato_tamano(2048), "2.0 KB")
        self.assertEqual(archivos.formato_tamano(3 * 1024 * 1024), "3.0 MB")


class PruebasAdjuntos(Base):
    """Regla del proyecto: los archivos se adjuntan SOLO al registrar la solicitud. Ni el solicitante ni el
    agente (ni nadie) pueden agregar o quitar archivos de una solicitud ya creada."""

    def test_se_puede_adjuntar_al_registrar_la_solicitud(self):
        s = self.nueva(adjuntos=[("captura.png", PNG), ("error.log", b"Traceback...")])
        self.assertEqual(s["n_adjuntos"], 2)
        lista = datos.adjuntos_de(s["folio"], self.ana)
        self.assertEqual([a["nombre"] for a in lista], ["captura.png", "error.log"])
        self.assertEqual(lista[0]["subido_por"], "Ana Reyes")
        eventos = [b["evento"] for b in datos.buscar_por_folio(s["folio"])["bitacora"]]
        self.assertTrue(any("Adjuntó el archivo «captura.png»" in e for e in eventos))

    def test_es_opcional(self):
        self.assertEqual(self.nueva()["n_adjuntos"], 0)
        self.assertEqual(self.nueva(adjuntos=[])["n_adjuntos"], 0)

    def test_si_un_archivo_no_sirve_no_se_crea_nada(self):
        antes = len(datos.solicitudes_de(self.ana["id"]))
        with self.assertRaisesRegex(ValueError, "No se aceptan"):
            self.nueva(adjuntos=[("bueno.png", PNG), ("malo.exe", b"MZ")])
        self.assertEqual(len(datos.solicitudes_de(self.ana["id"])), antes)
        self.assertEqual(len(datos._ADJUNTOS), 0)

    def test_maximo_de_archivos_por_solicitud(self):
        demasiados = [(f"a{i}.txt", b"x") for i in range(archivos.MAX_ADJUNTOS_POR_SOLICITUD + 1)]
        with self.assertRaisesRegex(ValueError, "Máximo"):
            self.nueva(adjuntos=demasiados)
        s = self.nueva(adjuntos=demasiados[:archivos.MAX_ADJUNTOS_POR_SOLICITUD])
        self.assertEqual(s["n_adjuntos"], archivos.MAX_ADJUNTOS_POR_SOLICITUD)

    def test_el_solicitante_no_puede_subir_archivos_a_una_solicitud_ya_creada(self):
        s = self.nueva()
        with self.assertRaisesRegex(PermissionError, "solo se pueden adjuntar al registrar"):
            datos.agregar_adjunto(s["folio"], self.ana, "tarde.pdf", PDF)
        self.assertFalse(datos.puede_adjuntar(self.ana, s["folio"]))
        self.assertEqual(datos.buscar_por_folio(s["folio"])["n_adjuntos"], 0)

    def test_el_agente_no_puede_adjuntar_archivos_a_una_solicitud_creada(self):
        s = self.nueva(tipo="Incidencia de software")
        for agente in (self.sebastian, self.gabriel):
            with self.subTest(agente=agente["usuario"]), self.assertRaises(PermissionError):
                datos.agregar_adjunto(s["folio"], agente, "guia.pdf", PDF)
            self.assertFalse(datos.puede_adjuntar(agente, s["folio"]))
        with self.assertRaises(PermissionError):
            datos.agregar_adjunto(s["folio"], self.admin, "x.pdf", PDF)
        self.assertEqual(datos.buscar_por_folio(s["folio"])["n_adjuntos"], 0)

    def test_lo_adjuntado_al_crear_no_se_puede_quitar(self):
        s = self.nueva(adjuntos=[("a.txt", b"x")])
        id_adj = datos.adjuntos_de(s["folio"], self.ana)[0]["id"]
        with self.assertRaises(PermissionError):
            datos.quitar_adjunto(id_adj, self.ana)
        self.assertEqual(len(datos.adjuntos_de(s["folio"], self.ana)), 1)

    def test_quien_no_participa_no_ve_ni_descarga(self):
        s = self.nueva(adjuntos=[("secreto.txt", b"contenido privado")])
        id_adj = datos.adjuntos_de(s["folio"], self.ana)[0]["id"]
        self.assertEqual(datos.adjuntos_de(s["folio"], self.carlos), [])
        self.assertIsNone(datos.obtener_adjunto(id_adj, self.carlos))
        self.assertIsNone(datos.obtener_adjunto(id_adj, self.zyanya))                 # agente de otra área
        self.assertIsNotNone(datos.obtener_adjunto(id_adj, self.sebastian))           # agente de la solicitud
        self.assertIsNotNone(datos.obtener_adjunto(id_adj, self.admin))               # el administrador supervisa

    def test_obtener_devuelve_el_contenido_exacto(self):
        s = self.nueva(adjuntos=[("a.png", PNG)])
        meta, contenido = datos.obtener_adjunto(datos.adjuntos_de(s["folio"], self.ana)[0]["id"], self.ana)
        self.assertEqual(contenido, PNG)
        self.assertEqual(meta["tipo"], "image/png")
        self.assertIsNone(datos.obtener_adjunto(99999, self.ana))

    def test_un_adjunto_cuenta_como_historial_de_la_cuenta(self):
        self.nueva(adjuntos=[("a.txt", b"x")])
        self.assertTrue(datos.cuenta_referenciada(self.ana["id"]))

    def test_si_algun_dia_se_habilitara_adjuntar_despues_funcionaria(self):
        from unittest import mock
        import permisos
        with mock.patch.dict(permisos.PERMISOS_POR_ROL, {"Representante de Área": permisos.PERMISOS_POR_ROL["Representante de Área"] | {"solicitud.adjuntar_despues"}}):
            s = self.nueva()
            self.assertTrue(datos.puede_adjuntar(self.ana, s["folio"]))
            meta = datos.agregar_adjunto(s["folio"], self.ana, "extra.pdf", PDF)
            self.assertEqual(meta["nombre"], "extra.pdf")
            self.assertEqual(datos.quitar_adjunto(meta["id"], self.ana), "ok")
            with self.assertRaises(PermissionError):
                datos.agregar_adjunto(s["folio"], self.carlos, "x.pdf", PDF)             # solo el dueño


if __name__ == "__main__":
    unittest.main()
