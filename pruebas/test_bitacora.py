"""RNF-13: la bitácora es inmutable y se puede verificar su integridad."""

import dataclasses
import unittest

from pruebas.base import Base
import datos


class PruebasBitacoraInmutable(Base):
    def test_la_bitacora_de_ejemplo_esta_integra(self):
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_las_entradas_estan_encadenadas_con_hash(self):
        s = self.nueva()
        entradas = self.interna(s["folio"])["bitacora"]
        self.assertEqual(entradas[0].hash_prev, "0" * 64)
        datos.asignar_solicitud(s["folio"], self.admin, self.gabriel["id"])
        datos.actualizar_por_tecnico(s["folio"], self.gabriel, "En proceso", "Revisando")
        entradas = self.interna(s["folio"])["bitacora"]
        self.assertGreaterEqual(len(entradas), 3)
        for anterior, actual in zip(entradas, entradas[1:]):
            self.assertEqual(actual.hash_prev, anterior.hash)
        self.assertEqual([e.seq for e in entradas], list(range(1, len(entradas) + 1)))
        self.assertEqual(len({e.hash for e in entradas}), len(entradas))

    def test_una_entrada_no_se_puede_modificar(self):
        e = self.interna("SIGSAT-0002")["bitacora"][0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.evento = "Evento falso"

    def test_la_lista_de_entradas_no_admite_borrar_ni_reemplazar(self):
        entradas = self.interna("SIGSAT-0002")["bitacora"]
        self.assertIsInstance(entradas, tuple)
        with self.assertRaises(TypeError):
            del entradas[0]
        with self.assertRaises(TypeError):
            entradas[0] = entradas[1]
        with self.assertRaises(AttributeError):
            entradas.append(entradas[0])

    def test_la_vista_de_lectura_no_expone_el_estado_interno(self):
        v = datos.buscar_por_folio("SIGSAT-0002")
        v["bitacora"].clear()
        v["bitacora"].append({"fecha": "x", "autor": "x", "evento": "falso"})
        self.assertEqual(len(datos.buscar_por_folio("SIGSAT-0002")["bitacora"]), 4)
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_se_detecta_una_entrada_modificada(self):
        s = self.interna("SIGSAT-0002")
        s["bitacora"] = (dataclasses.replace(s["bitacora"][0], evento="Solicitud creada (editada)"),) + s["bitacora"][1:]
        problemas = datos.verificar_bitacora()
        self.assertEqual(len(problemas), 1)
        self.assertIn("SIGSAT-0002", problemas[0])
        self.assertIn("modificada", problemas[0])

    def test_se_detecta_una_entrada_borrada(self):
        s = self.interna("SIGSAT-0001")
        s["bitacora"] = s["bitacora"][:1] + s["bitacora"][2:]
        self.assertIn("no encadena", datos.verificar_bitacora()[0])

    def test_se_detecta_que_se_borro_la_ultima_entrada(self):
        # quitar la ÚLTIMA entrada deja una cadena válida más corta: lo delata el contador global
        s = self.interna("SIGSAT-0001")
        s["bitacora"] = s["bitacora"][:-1]
        problemas = datos.verificar_bitacora()
        self.assertEqual(len(problemas), 1)
        self.assertIn("Faltan 1 entradas", problemas[0])

    def test_se_detecta_que_se_borro_toda_la_bitacora_de_una_solicitud(self):
        self.interna("SIGSAT-0002")["bitacora"] = ()
        self.assertIn("Faltan 4 entradas", datos.verificar_bitacora()[0])

    def test_se_detecta_un_reordenamiento(self):
        s = self.interna("SIGSAT-0001")
        s["bitacora"] = s["bitacora"][:2] + (s["bitacora"][3], s["bitacora"][2])
        self.assertNotEqual(datos.verificar_bitacora(), [])

    def test_se_detecta_un_cambio_de_autor_o_de_fecha(self):
        s = self.interna("SIGSAT-0002")
        s["bitacora"] = (dataclasses.replace(s["bitacora"][0], autor_id=99),) + s["bitacora"][1:]
        self.assertIn("modificada", datos.verificar_bitacora()[0])
        datos.reiniciar()
        s = self.interna("SIGSAT-0002")
        s["bitacora"] = (dataclasses.replace(s["bitacora"][0], fecha=s["bitacora"][0].fecha.replace(year=2001)),) + s["bitacora"][1:]
        self.assertIn("modificada", datos.verificar_bitacora()[0])

    def test_ninguna_funcion_publica_borra_solicitudes_ni_entradas(self):
        publicas = [n for n in dir(datos) if not n.startswith("_") and callable(getattr(datos, n))]
        sospechosas = [n for n in publicas if any(p in n for p in ("borrar", "eliminar_solicitud", "editar_bitacora", "quitar_entrada"))]
        self.assertEqual(sospechosas, [])
        self.assertFalse(hasattr(datos, "eliminar_solicitud"))

    def test_una_cuenta_con_historial_se_desactiva_y_la_bitacora_conserva_su_nombre(self):
        datos.eliminar_usuario(self.sebastian["id"])
        self.assertFalse(datos.buscar_usuario(self.sebastian["id"])["activo"])
        eventos = datos.buscar_por_folio("SIGSAT-0001")["bitacora"]
        self.assertTrue(any(b["autor"] == "Sebastián Estrada" for b in eventos))
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_las_acciones_de_cada_flujo_quedan_en_la_bitacora_con_su_autor(self):
        s = self.nueva_sin_asignar(tipo="Incidencia de software")
        datos.asignar_solicitud(s["folio"], self.admin, self.sebastian["id"], "Motivo X")
        datos.registrar_visualizacion(s["folio"], self.sebastian)
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "En proceso", "Revisando")
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Listo")
        datos.calificar_servicio(s["folio"], self.ana, 5)
        b = datos.buscar_por_folio(s["folio"])["bitacora"]
        autores = [x["autor"] for x in b]
        self.assertEqual(autores, ["Ana Reyes", "Sistema", "Dirección General", "Sebastián Estrada", "Sebastián Estrada",
                                   "Sebastián Estrada", "Ana Reyes"])
        self.assertIn("calificó el servicio", b[-1]["evento"])
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_agregar_catalogos_no_rompe_la_cadena(self):
        datos.crear_area(self.admin, "Seguridad")
        datos.crear_sucursal(self.admin, "Puebla")
        datos.crear_tipo(self.admin, "Auditoría", 10)
        self.nueva(tipo="Auditoría")
        self.assertEqual(datos.verificar_bitacora(), [])


if __name__ == "__main__":
    unittest.main()
