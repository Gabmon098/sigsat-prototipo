"""RNF-09: los datos se guardan en disco y se respaldan cada día; los respaldos se pueden restaurar."""

import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from pruebas.base import Base, cuenta
import datos
import persistencia

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


class BasePersistencia(Base):
    def setUp(self):
        super().setUp()
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.carpeta = Path(self._dir.name) / "datos"

    def abrir(self, **kw):
        return persistencia.activar(self.carpeta, **kw)

    def reabrir(self):
        """Simula cerrar la aplicación y volver a abrirla: la memoria vuelve a empezar de cero."""
        persistencia.desactivar()
        datos.reiniciar()
        return self.abrir()

    def estado_json(self):
        return json.loads((self.carpeta / "estado.json").read_text(encoding="utf-8"))


class PruebasGuardado(BasePersistencia):
    def test_la_primera_vez_guarda_los_datos_de_ejemplo(self):
        self.assertEqual(self.abrir(), "nuevo")
        self.assertTrue((self.carpeta / "estado.json").exists())
        self.assertEqual(len(self.estado_json()["solicitudes"]), 7)

    def test_los_cambios_sobreviven_a_cerrar_y_abrir(self):
        self.abrir()
        s = self.nueva(adjuntos=[("captura.png", PNG)])
        datos.asignar_solicitud(s["folio"], self.admin, self.gabriel["id"], "motivo")
        datos.crear_area(self.admin, "Seguridad")
        datos.crear_tipo(self.admin, "Caída del servidor", 4)
        datos.crear_conversacion(self.ana, "Duda", "Hola")
        datos.actualizar_usuario(self.zyanya["id"], "Zyanya A.", "zarriaga", "NuevaClave-99", "Técnico",
                                 None, "zarriagai2100@alumno.ipn.mx")

        self.assertEqual(self.reabrir(), "cargado")
        v = datos.buscar_por_folio(s["folio"])
        self.assertEqual(v["agente_asignado"], "Gabriel Santiago")
        self.assertEqual(v["n_adjuntos"], 1)
        self.assertIn("Seguridad", datos.areas_activas())
        self.assertEqual(datos.prioridad_de_tipo("Caída del servidor"), "Alta")
        self.assertEqual(len(datos.conversaciones_visibles(self.admin)), 4)
        self.assertIsNotNone(datos.autenticar("zarriaga", "NuevaClave-99"))               # la contraseña nueva se conserva
        meta, contenido = datos.obtener_adjunto(datos.adjuntos_de(s["folio"], self.ana)[0]["id"], self.ana)
        self.assertEqual(contenido, PNG)
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_los_ids_y_folios_siguen_donde_se_quedaron(self):
        self.abrir()
        self.nueva()
        self.reabrir()
        self.assertEqual(self.nueva()["folio"], "SIGSAT-0009")
        self.assertEqual(datos.crear_conversacion(self.ana, "x", "y")["id"], "MESA-0004")

    def test_las_contrasenas_se_guardan_solo_con_hash(self):
        self.abrir()
        texto = (self.carpeta / "estado.json").read_text(encoding="utf-8")
        for clave in ("Rey_006", "Est_001", "Dir_000"):
            self.assertNotIn(clave, texto)
        self.assertIn("scrypt", texto)

    def test_los_adjuntos_van_en_archivos_aparte_y_no_en_el_json(self):
        self.abrir()
        self.nueva(adjuntos=[("a.png", PNG)])
        self.assertTrue(list((self.carpeta / "adjuntos").glob("*.bin")))
        self.assertNotIn("contenido", self.estado_json()["adjuntos"][0])
        # un archivo que ya no está en los datos se borra del disco en el siguiente guardado
        datos._ADJUNTOS.clear()
        persistencia.guardar()
        self.assertFalse(list((self.carpeta / "adjuntos").glob("*.bin")))

    def test_el_guardado_es_atomico_y_no_deja_temporales(self):
        self.abrir()
        for i in range(5):
            self.nueva(desc=f"solicitud {i}")
        self.assertEqual(list(self.carpeta.glob("*.tmp")), [])
        json.loads((self.carpeta / "estado.json").read_text(encoding="utf-8"))            # siempre es un JSON completo

    def test_si_falla_el_guardado_la_operacion_no_se_cae_y_se_registra_el_error(self):
        from unittest import mock
        self.abrir()
        with mock.patch.object(persistencia, "_escribir_atomico", side_effect=OSError("disco lleno")):
            s = self.nueva()                                                              # no lanza
        self.assertIsNotNone(datos.buscar_por_folio(s["folio"]))
        self.assertIn("disco lleno", persistencia.informacion()["ultimo_error"])
        self.nueva()                                                                       # al volver a funcionar, se recupera
        self.assertIsNone(persistencia.informacion()["ultimo_error"])

    def test_reiniciar_vuelve_a_los_datos_de_ejemplo_y_antes_hace_respaldo(self):
        self.abrir()
        self.nueva()
        persistencia.desactivar()
        self.assertEqual(self.abrir(reiniciar=True), "reiniciado")
        self.assertEqual(len(datos.solicitudes_todas(self.admin)), 7)
        tipos = [r["tipo"] for r in persistencia.listar_respaldos()]
        self.assertIn("antes_de_reiniciar", tipos)

    def test_sin_persistencia_no_se_escribe_nada(self):
        self.nueva()
        self.assertFalse(self.carpeta.exists())
        self.assertFalse(persistencia.activa())


class PruebasArchivoDanado(BasePersistencia):
    def test_un_json_danado_se_recupera_del_ultimo_respaldo(self):
        self.abrir()
        persistencia.crear_respaldo("manual")
        s = self.nueva()                                                                  # cambio posterior al respaldo
        persistencia.desactivar()
        (self.carpeta / "estado.json").write_text("{ esto no es json", encoding="utf-8")
        datos.reiniciar()
        self.assertEqual(self.abrir(), "recuperado")
        self.assertIsNone(datos.buscar_por_folio(s["folio"]), "se perdió lo posterior al respaldo")
        self.assertEqual(len(datos.solicitudes_todas(self.admin)), 7)
        self.assertEqual(len(list(self.carpeta.glob("estado_danado_*.json"))), 1, "el archivo dañado se conserva")

    def test_sin_respaldo_utilizable_se_abre_con_datos_de_ejemplo(self):
        self.abrir()
        persistencia.desactivar()
        (self.carpeta / "estado.json").write_text("basura", encoding="utf-8")
        datos.reiniciar()
        self.assertEqual(self.abrir(), "nuevo")
        self.assertEqual(len(datos.solicitudes_todas(self.admin)), 7)
        self.assertTrue(list(self.carpeta.glob("estado_danado_*.json")))

    def test_una_bitacora_alterada_en_disco_no_se_carga(self):
        self.abrir()
        persistencia.crear_respaldo("manual")
        persistencia.desactivar()
        estado = self.estado_json()
        estado["solicitudes"][1]["bitacora"][0]["evento"] = "Evento falsificado"
        (self.carpeta / "estado.json").write_text(json.dumps(estado), encoding="utf-8")
        datos.reiniciar()
        self.assertEqual(self.abrir(), "recuperado", "se detecta la alteración y se restaura el respaldo íntegro")
        self.assertNotIn("falsificado", str(datos.buscar_por_folio("SIGSAT-0002")["bitacora"]))
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_una_entrada_borrada_en_disco_tambien_se_detecta(self):
        self.abrir()
        persistencia.crear_respaldo("manual")
        persistencia.desactivar()
        estado = self.estado_json()
        estado["solicitudes"][1]["bitacora"].pop()                                        # quita la última entrada
        (self.carpeta / "estado.json").write_text(json.dumps(estado), encoding="utf-8")
        datos.reiniciar()
        self.assertEqual(self.abrir(), "recuperado")

    def test_falta_un_adjunto_en_disco(self):
        self.abrir()
        self.nueva(adjuntos=[("a.png", PNG)])
        persistencia.crear_respaldo("manual")
        persistencia.desactivar()
        for f in (self.carpeta / "adjuntos").glob("*.bin"):
            f.unlink()
        datos.reiniciar()
        self.assertEqual(self.abrir(), "recuperado")

    def test_un_estado_invalido_no_modifica_lo_que_hay_en_memoria(self):
        self.abrir()
        antes = datos.exportar_estado()
        malo = datos.exportar_estado()
        malo["usuarios"][0]["rol"] = "Superusuario"
        with self.assertRaises(ValueError):
            datos.importar_estado(malo, {})
        malo2 = datos.exportar_estado()
        del malo2["tipos"]
        with self.assertRaises(ValueError):
            datos.importar_estado(malo2, {})
        self.assertEqual(datos.exportar_estado(), antes)


class PruebasRespaldos(BasePersistencia):
    def test_el_respaldo_es_un_zip_con_estado_y_adjuntos(self):
        self.abrir()
        self.nueva(adjuntos=[("a.png", PNG)])
        ruta = persistencia.crear_respaldo("manual")
        with zipfile.ZipFile(ruta) as z:
            nombres = set(z.namelist())
        self.assertTrue({"estado.json", "LEEME.txt", "adjuntos/1.bin"} <= nombres)
        self.assertTrue(ruta.name.startswith("sigsat_manual_"))

    def test_el_respaldo_diario_se_crea_una_sola_vez_al_dia(self):
        self.abrir()
        primero = persistencia.respaldo_diario()
        self.assertIsNotNone(primero)
        self.assertRegex(primero.name, r"^sigsat_auto_\d{8}\.zip$")
        self.assertIsNone(persistencia.respaldo_diario())
        self.assertEqual(len([r for r in persistencia.listar_respaldos() if r["tipo"] == "auto"]), 1)

    def test_se_conservan_solo_los_ultimos_14_respaldos_automaticos(self):
        self.abrir()
        carpeta = self.carpeta / "respaldos"
        carpeta.mkdir(exist_ok=True)
        base = datetime.now()
        for i in range(1, 20):                                  # 19 días anteriores
            (carpeta / f"sigsat_auto_{(base - timedelta(days=i)):%Y%m%d}.zip").write_bytes(b"x")
        persistencia.respaldo_diario()                          # hoy: dispara la depuración
        autos = [r for r in persistencia.listar_respaldos() if r["tipo"] == "auto"]
        self.assertEqual(len(autos), persistencia.RETENCION_AUTOMATICOS)
        self.assertEqual(autos[0]["fecha"].date(), base.date(), "el de hoy se conserva")

    def test_los_manuales_no_los_borra_la_depuracion_de_automaticos(self):
        self.abrir()
        manual = persistencia.crear_respaldo("manual")
        for i in range(1, 20):
            (self.carpeta / "respaldos" / f"sigsat_auto_{(datetime.now() - timedelta(days=i)):%Y%m%d}.zip").write_bytes(b"x")
        persistencia.respaldo_diario()
        self.assertTrue(manual.exists())

    def test_restaurar_vuelve_al_estado_del_respaldo(self):
        self.abrir()
        ruta = persistencia.crear_respaldo("manual")
        s = self.nueva(adjuntos=[("a.png", PNG)])
        datos.crear_area(self.admin, "Seguridad")
        datos.crear_tipo(self.admin, "Caída del servidor", 4)
        resumen = persistencia.restaurar_respaldo(ruta)
        self.assertEqual(resumen["solicitudes"], 7)
        self.assertIsNone(datos.buscar_por_folio(s["folio"]))
        self.assertNotIn("Seguridad", datos.areas_activas())
        self.assertIsNone(datos.prioridad_de_tipo("Caída del servidor"))
        self.assertEqual(datos.verificar_bitacora(), [])
        self.assertEqual(self.estado_json()["solicitudes"].__len__(), 7, "lo restaurado también queda guardado en disco")
        self.assertFalse(list((self.carpeta / "adjuntos").glob("*.bin")))

    def test_restaurar_primero_hace_una_copia_del_estado_actual(self):
        self.abrir()
        ruta = persistencia.crear_respaldo("manual")
        s = self.nueva()
        persistencia.restaurar_respaldo(ruta)
        seguridad = [r for r in persistencia.listar_respaldos() if r["tipo"] == "antes_de_restaurar"]
        self.assertEqual(len(seguridad), 1)
        persistencia.restaurar_respaldo(seguridad[0]["ruta"])                            # y con ella se puede deshacer
        self.assertIsNotNone(datos.buscar_por_folio(s["folio"]))

    def _zip(self, nombre, miembros):
        ruta = Path(self._dir.name) / nombre
        with zipfile.ZipFile(ruta, "w") as z:
            for n, c in miembros.items():
                z.writestr(n, c)
        return ruta

    def test_un_respaldo_malicioso_o_danado_se_rechaza_sin_tocar_nada(self):
        self.abrir()
        antes = datos.exportar_estado()
        estado = json.dumps(antes)
        casos = {
            "ruta fuera de la carpeta (zip slip)": {"estado.json": estado, "../../evil.txt": "x"},
            "archivo no permitido": {"estado.json": estado, "programa.exe": "MZ"},
            "adjunto con nombre raro": {"estado.json": estado, "adjuntos/../x.bin": "x"},
            "sin estado.json": {"LEEME.txt": "hola"},
            "json invalido": {"estado.json": "{ no es json"},
            "estructura incompleta": {"estado.json": json.dumps({"version": 1})},
            "version desconocida": {"estado.json": json.dumps({**antes, "version": 99})},
        }
        for nombre, miembros in casos.items():
            with self.subTest(caso=nombre):
                with self.assertRaises(persistencia.ErrorPersistencia):
                    persistencia.restaurar_respaldo(self._zip("malo.zip", miembros))
                self.assertEqual(datos.exportar_estado(), antes, "el estado actual no debe cambiar")
        noZip = Path(self._dir.name) / "noes.zip"
        noZip.write_bytes(b"esto no es un zip")
        with self.assertRaisesRegex(persistencia.ErrorPersistencia, "dañado"):
            persistencia.restaurar_respaldo(noZip)
        self.assertFalse((Path(self._dir.name).parent / "evil.txt").exists())

    def test_un_respaldo_con_la_bitacora_alterada_se_rechaza(self):
        self.abrir()
        estado = datos.exportar_estado()
        estado["solicitudes"][0]["bitacora"][0]["evento"] = "falsificado"
        antes = datos.exportar_estado()
        with self.assertRaisesRegex(persistencia.ErrorPersistencia, "íntegra"):
            persistencia.restaurar_respaldo(self._zip("alterado.zip", {"estado.json": json.dumps(estado)}))
        self.assertEqual(datos.exportar_estado(), antes)

    def test_sin_persistencia_no_hay_respaldos(self):
        with self.assertRaises(persistencia.ErrorPersistencia):
            persistencia.crear_respaldo()
        self.assertEqual(persistencia.listar_respaldos(), [])
        self.assertIsNone(persistencia.respaldo_diario())

    def test_nombres_de_respaldo_que_no_son_nuestros_se_ignoran(self):
        self.abrir()
        persistencia.crear_respaldo("manual")
        (self.carpeta / "respaldos" / "notas.zip").write_bytes(b"x")
        (self.carpeta / "respaldos" / "sigsat_raro_20260101.zip").write_bytes(b"x")
        self.assertEqual(len(persistencia.listar_respaldos()), 1)

    @unittest.skipIf(os.name == "nt", "los permisos POSIX no aplican en Windows")
    def test_los_archivos_se_guardan_con_permisos_privados(self):
        self.abrir()
        self.assertEqual((self.carpeta / "estado.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.carpeta.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()


class PruebasReinicioProtegeLosDatos(BasePersistencia):
    def test_reiniciar_guarda_antes_un_respaldo_de_lo_que_habia_en_disco(self):
        self.abrir()
        s = self.nueva(adjuntos=[("a.png", PNG)])
        # «se cierra la aplicación» y se vuelve a abrir con --reiniciar: en memoria solo hay datos de ejemplo
        persistencia.desactivar()
        datos.reiniciar()
        self.assertIsNone(datos.buscar_por_folio(s["folio"]))
        self.assertEqual(self.abrir(reiniciar=True), "reiniciado")
        self.assertIsNone(datos.buscar_por_folio(s["folio"]), "los datos quedaron en blanco, como se pidió")

        respaldos = [r for r in persistencia.listar_respaldos() if r["tipo"] == "antes_de_reiniciar"]
        self.assertEqual(len(respaldos), 1)
        persistencia.restaurar_respaldo(respaldos[0]["ruta"])                            # y con él se recupera todo
        self.assertIsNotNone(datos.buscar_por_folio(s["folio"]))
        self.assertEqual(datos.buscar_por_folio(s["folio"])["n_adjuntos"], 1)

    def test_reiniciar_respalda_aunque_el_archivo_este_danado(self):
        self.abrir()
        persistencia.desactivar()
        (self.carpeta / "estado.json").write_text("{ dañado", encoding="utf-8")
        datos.reiniciar()
        self.assertEqual(self.abrir(reiniciar=True), "reiniciado")
        self.assertEqual(len([r for r in persistencia.listar_respaldos() if r["tipo"] == "antes_de_reiniciar"]), 1)
