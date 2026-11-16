"""Bitácora de auditoría (RF-21): consulta de los eventos de todas las solicitudes, con filtros, por rol y de solo lectura."""

import unittest
from datetime import date, datetime, timedelta

from pruebas.base import Base, cuenta
import datos


class PruebasConsultaBitacora(Base):
    def consulta(self, actor=None, **filtros):
        return datos.consultar_bitacora(actor or self.admin, **filtros)

    def test_el_administrador_ve_los_eventos_de_todas_las_solicitudes(self):
        filas, total = self.consulta()
        self.assertEqual(total, 24)
        self.assertEqual(len(filas), 24)
        self.assertEqual({f["folio"] for f in filas}, {f"SIGSAT-000{i}" for i in range(1, 8)})
        self.assertTrue(all(set(f) >= {"folio", "fecha", "autor", "evento", "n"} for f in filas))

    def test_va_de_lo_mas_reciente_a_lo_mas_antiguo(self):
        s = self.nueva()
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "En proceso", "Revisando")
        filas, _ = self.consulta()
        fechas = [f["fecha"] for f in filas]
        self.assertEqual(fechas, sorted(fechas, reverse=True))
        self.assertEqual(filas[0]["folio"], s["folio"])                                      # lo más reciente va primero
        self.assertEqual(filas[0]["evento"], "Estatus actualizado a 'En proceso' — Revisando")

    def test_un_tecnico_solo_ve_la_bitacora_de_sus_solicitudes(self):
        filas, total = self.consulta(self.sebastian)
        self.assertEqual({f["folio"] for f in filas}, {"SIGSAT-0001", "SIGSAT-0002"})        # las suyas
        self.assertEqual(total, 10)
        filas, _ = self.consulta(self.zyanya)
        self.assertEqual({f["folio"] for f in filas}, {"SIGSAT-0005"})
        self.assertNotIn("SIGSAT-0004", str(self.consulta(self.sebastian)))

    def test_al_reasignar_la_bitacora_pasa_al_tecnico_nuevo(self):
        datos.asignar_solicitud("SIGSAT-0002", self.admin, self.zyanya["id"], "pasa a otro técnico")
        folios = {f["folio"] for f in self.consulta(self.zyanya)[0]}
        self.assertIn("SIGSAT-0002", folios)
        self.assertNotIn("SIGSAT-0002", {f["folio"] for f in self.consulta(self.sebastian)[0]})

    def test_el_representante_no_consulta_la_bitacora_general(self):
        with self.assertRaisesRegex(PermissionError, "bitácora"):
            self.consulta(self.ana)
        with self.assertRaises(PermissionError):
            datos.autores_bitacora(self.carlos)

    def test_filtro_por_folio(self):
        for texto in ("0002", "SIGSAT-0002", "sigsat-0002", " 0002 "):
            with self.subTest(texto=texto):
                filas, total = self.consulta(folio=texto)
                self.assertEqual({f["folio"] for f in filas}, {"SIGSAT-0002"})
                self.assertEqual(total, 4)
        self.assertEqual(self.consulta(folio="9999"), ([], 0))

    def test_filtro_por_autor_y_por_sistema(self):
        filas, _ = self.consulta(autor=self.ana["id"])
        self.assertTrue(filas and all(f["autor"].startswith("Ana Reyes") for f in filas))
        filas, _ = self.consulta(autor="sistema")
        self.assertTrue(filas and all(f["autor"] == "Sistema" and f["autor_id"] is None for f in filas))
        self.assertEqual(self.consulta(autor=99999), ([], 0))

    def test_filtro_por_texto_sin_distinguir_mayusculas(self):
        filas, _ = self.consulta(texto="ASIGNADA")
        self.assertTrue(filas and all("asignada" in f["evento"].lower() for f in filas))
        self.assertEqual(self.consulta(texto="no existe esta frase"), ([], 0))

    def test_filtro_por_fechas_incluye_ambos_extremos(self):
        hoy = date.today()
        self.assertEqual(self.consulta(desde=hoy + timedelta(days=1))[1], 0)
        self.assertEqual(self.consulta(hasta=hoy - timedelta(days=60))[1], 0)
        self.assertEqual(self.consulta(desde=hoy - timedelta(days=60), hasta=hoy + timedelta(days=1))[1], 24)
        # la solicitud 0001 se creó hace 6 días: su evento aparece con ese día exacto en ambos extremos
        dia = hoy - timedelta(days=6)
        filas, _ = self.consulta(desde=dia, hasta=dia, folio="0001")
        self.assertTrue(filas and all(f["fecha"].startswith(dia.isoformat()) for f in filas))
        self.assertEqual(self.consulta(desde=datetime.now(), hasta=datetime.now())[1], self.consulta(desde=hoy, hasta=hoy)[1])

    def test_filtros_combinados(self):
        filas, total = self.consulta(folio="0001", autor=self.ana["id"], texto="calificó")
        self.assertEqual(total, 1)
        self.assertIn("calificó el servicio recibido (5/5)", filas[0]["evento"])

    def test_filtros_invalidos(self):
        with self.assertRaisesRegex(ValueError, "fecha inicial"):
            self.consulta(desde=date.today(), hasta=date.today() - timedelta(days=1))
        with self.assertRaisesRegex(ValueError, "demasiado largo"):
            self.consulta(texto="x" * 101)
        for malo in (True, 1.5, [1], {"a": 1}, "otro"):
            with self.subTest(autor=malo), self.assertRaisesRegex(ValueError, "Autor"):
                self.consulta(autor=malo)
        for limite in (0, -1, "5", True, None):
            with self.subTest(limite=limite), self.assertRaisesRegex(ValueError, "límite"):
                self.consulta(limite=limite)

    def test_el_limite_devuelve_lo_mas_reciente_y_el_total(self):
        filas, total = self.consulta(limite=3)
        self.assertEqual((len(filas), total), (3, 24))
        todas, _ = self.consulta()
        self.assertEqual(filas, todas[:3])

    def test_los_autores_disponibles_dependen_de_lo_que_se_puede_ver(self):
        admin = {n for _i, n in datos.autores_bitacora(self.admin)}
        tecnico = {n for _i, n in datos.autores_bitacora(self.sebastian)}
        self.assertIn("Sistema", admin)
        self.assertIn("Dirección General", admin)
        self.assertIn("Daniel López", admin)
        self.assertNotIn("Daniel López", tecnico, "un técnico no ve autores de solicitudes ajenas")
        self.assertTrue(tecnico < admin)


class PruebasHoraExacta(Base):
    def test_los_eventos_nuevos_llevan_la_hora_exacta_con_segundos(self):
        s = self.nueva()
        fecha = datos.buscar_por_folio(s["folio"])["bitacora"][0]["fecha"]
        self.assertRegex(fecha, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        entrada = self.interna(s["folio"])["bitacora"][0]
        self.assertAlmostEqual((datetime.now() - entrada.fecha).total_seconds(), 0, delta=5)
        self.assertEqual(entrada.fecha.microsecond, 0)

    def test_el_orden_distingue_eventos_del_mismo_minuto(self):
        a = self.nueva(tipo="Incidencia de software")
        b = self.nueva(tipo="Incidencia de software", usuario=self.carlos)
        # se fuerza que el evento de la solicitud MÁS ANTIGUA ocurra DESPUÉS (un segundo más tarde)
        datos.actualizar_por_tecnico(a["folio"], self.sebastian, "En proceso", "último evento")
        ultimo = self.interna(a["folio"])["bitacora"]
        mas_tarde = ultimo[-1].fecha + timedelta(seconds=1)
        import dataclasses
        self.interna(a["folio"])["bitacora"] = ultimo[:-1] + (dataclasses.replace(ultimo[-1], fecha=mas_tarde),)
        filas, _ = datos.consultar_bitacora(self.admin)
        self.assertEqual(filas[0]["evento"].split(" — ")[-1], "último evento")
        self.assertEqual(filas[0]["folio"], a["folio"])

    def test_la_cadena_de_hashes_sigue_integra_con_los_segundos(self):
        self.nueva()
        self.assertEqual(datos.verificar_bitacora(), [])


class PruebasBitacoraSoloLectura(Base):
    def test_consultar_devuelve_copias_y_no_expone_el_estado_interno(self):
        filas, _ = datos.consultar_bitacora(self.admin)
        filas[0]["evento"] = "ALTERADO"
        filas.clear()
        nuevas, total = datos.consultar_bitacora(self.admin)
        self.assertEqual(total, 24)
        self.assertNotIn("ALTERADO", str(nuevas))
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_las_filas_solo_contienen_datos_simples_y_las_mismas_claves(self):
        filas, _ = datos.consultar_bitacora(self.admin)
        for f in filas:
            self.assertEqual(set(f), {"folio", "fecha", "autor", "autor_id", "evento", "n"})
            for valor in f.values():
                self.assertIn(type(valor), (str, int, type(None)), "no debe filtrarse ningún objeto interno")

    def test_no_existe_ninguna_funcion_para_editar_o_borrar_eventos(self):
        publicas = [n for n in dir(datos) if not n.startswith("_") and callable(getattr(datos, n))]
        sospechosas = [n for n in publicas if any(p in n for p in ("editar_bitacora", "borrar_bitacora", "eliminar_bitacora",
                                                                  "modificar_bitacora", "quitar_evento", "borrar_evento"))]
        self.assertEqual(sospechosas, [])

    def test_consultar_no_cambia_nada_ni_escribe_en_la_bitacora(self):
        antes = datos.exportar_estado()
        for _ in range(3):
            datos.consultar_bitacora(self.admin, texto="asignada")
            datos.autores_bitacora(self.admin)
        self.assertEqual(datos.exportar_estado(), antes)

    def test_la_bitacora_consultada_coincide_con_la_del_detalle_de_cada_solicitud(self):
        filas, _ = datos.consultar_bitacora(self.admin, folio="0001")
        detalle = datos.buscar_por_folio("SIGSAT-0001")["bitacora"]
        self.assertEqual(sorted(f["evento"] for f in filas), sorted(b["evento"] for b in detalle))
        self.assertEqual(sorted(f["fecha"] for f in filas), sorted(b["fecha"] for b in detalle))

    def test_los_eventos_nuevos_aparecen_en_la_consulta(self):
        s = self.nueva(tipo="Incidencia de software")
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Listo")
        datos.calificar_servicio(s["folio"], self.ana, 4)
        eventos = [f["evento"] for f in datos.consultar_bitacora(self.admin, folio=s["folio"])[0]]
        for esperado in ("Solicitud creada", "Asignada a Sebastián Estrada", "Estatus actualizado a 'Finalizado'", "calificó el servicio recibido (4/5)"):
            self.assertTrue(any(esperado in e for e in eventos), esperado)


if __name__ == "__main__":
    unittest.main()
