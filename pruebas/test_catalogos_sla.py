"""RF-04 (catálogos: solo se agregan), RF-16 (el tipo trae su tiempo estimado; de él salen la prioridad y la
fecha límite) y RF-23 (tiempos por área y tipo)."""

import unittest
from unittest import mock

import permisos
from pruebas.base import Base, cuenta
import datos


def con_permisos(*nombres):
    """Concede (solo durante la prueba) permisos que hoy ningún rol tiene, para comprobar que ese código
    sigue funcionando bien si algún día se vuelven a habilitar."""
    return mock.patch.dict(permisos.PERMISOS_POR_ROL,
                           {"Administrador": permisos.PERMISOS_POR_ROL["Administrador"] | set(nombres)})


class PruebasCatalogosSoloAgregar(Base):
    def test_el_administrador_puede_agregar_areas_sucursales_y_tipos(self):
        a = datos.crear_area(self.admin, "  Seguridad   Informática ")
        self.assertEqual(a["nombre"], "Seguridad Informática")           # espacios normalizados
        self.assertIn("Seguridad Informática", datos.areas_activas())
        x = datos.crear_sucursal(self.admin, "Puebla")
        self.assertEqual(x["nombre"], "Puebla")
        self.assertIn("Puebla", datos.sucursales_activas())
        t = datos.crear_tipo(self.admin, "Auditoría de seguridad", 10)
        self.assertEqual((t["horas"], datos.prioridad_de_tipo("Auditoría de seguridad")), (10, "Alta"))
        self.assertIn("Auditoría de seguridad", datos.tipos_activos())

    def test_los_catalogos_no_se_editan_ni_se_eliminan(self):
        area = next(a for a in datos.areas_todas() if a["nombre"] == "Contabilidad")
        suc = next(x for x in datos.sucursales_todas() if x["nombre"] == "Monterrey")
        tipo = next(t for t in datos.tipos_todos() if t["nombre"] == "Incidencia de hardware")
        with self.assertRaisesRegex(PermissionError, "no se pueden editar"):
            datos.actualizar_area(self.admin, area["id"], "Otro nombre", True)
        with self.assertRaisesRegex(PermissionError, "no se pueden eliminar"):
            datos.eliminar_area(self.admin, area["id"])
        with self.assertRaisesRegex(PermissionError, "no se pueden editar"):
            datos.actualizar_sucursal(self.admin, suc["id"], "Otra", True)
        with self.assertRaisesRegex(PermissionError, "no se pueden eliminar"):
            datos.eliminar_sucursal(self.admin, suc["id"])
        with self.assertRaisesRegex(PermissionError, "no se pueden editar"):
            datos.actualizar_tipo(self.admin, tipo["id"], "Otro", 5, True)
        with self.assertRaisesRegex(PermissionError, "no se pueden eliminar"):
            datos.eliminar_tipo(self.admin, tipo["id"])
        # y nada cambió
        self.assertIn("Contabilidad", datos.areas_activas())
        self.assertIn("Monterrey", datos.sucursales_activas())
        self.assertEqual(datos.prioridad_de_tipo("Incidencia de hardware"), "Media")
        self.assertEqual(len(datos.tipos_activos()), 7)

    def test_ningun_rol_tiene_los_permisos_deshabilitados(self):
        for rol, permisos_del_rol in permisos.PERMISOS_POR_ROL.items():
            for p in permisos.PERMISOS_DESHABILITADOS:
                self.assertNotIn(p, permisos_del_rol, f"{rol} no debe tener {p}")

    def test_solo_el_administrador_agrega_catalogos(self):
        for actor in (self.ana, self.sebastian):
            with self.subTest(rol=actor["rol"]):
                with self.assertRaises(PermissionError):
                    datos.crear_area(actor, "Seguridad")
                with self.assertRaises(PermissionError):
                    datos.crear_sucursal(actor, "Puebla")
                with self.assertRaises(PermissionError):
                    datos.crear_tipo(actor, "Nuevo", 10)
        self.assertEqual(len(datos.areas_activas()), 5)
        self.assertEqual(len(datos.sucursales_activas()), 3)

    def test_validaciones_de_alta(self):
        for malo, texto in [("", "al menos 2"), ("A", "al menos 2"), ("x" * 61, "demasiado largo"),
                            ("seguridad informática", None), ("CONTABILIDAD", "Ya existe")]:
            if texto is None:
                datos.crear_area(self.admin, "Seguridad informática")
                continue
            with self.subTest(nombre=malo[:12]), self.assertRaisesRegex(ValueError, texto):
                datos.crear_area(self.admin, malo)
        with self.assertRaisesRegex(ValueError, "Ya existe"):
            datos.crear_sucursal(self.admin, "monterrey")
        with self.assertRaisesRegex(ValueError, "Ya existe"):
            datos.crear_tipo(self.admin, "incidencia de hardware", 48)
        for mala in (None, "", "10", 0, -5, 721, 1.5, True):
            with self.subTest(horas=mala), self.assertRaisesRegex(ValueError, "tiempo estimado"):
                datos.crear_tipo(self.admin, "Tipo con tiempo malo", mala)

    def test_clasificacion_por_prioridad(self):
        c = {x["prioridad"]: x for x in datos.rangos_prioridad()}
        self.assertEqual([x["prioridad"] for x in datos.rangos_prioridad()], ["Alta", "Media", "Baja"])
        self.assertEqual(c["Alta"]["tipos"], ["Incidencia de software"])
        self.assertEqual(set(c["Media"]["tipos"]), {"Incidencia de hardware", "Mantenimiento correctivo"})
        self.assertEqual(set(c["Baja"]["tipos"]), {"Consultoría tecnológica", "Solicitud de nuevo acceso",
                                                  "Mantenimiento preventivo", "Desarrollo de aplicación"})
        datos.crear_tipo(self.admin, "Caída del servidor", 4)
        self.assertIn("Caída del servidor", {x["prioridad"]: x for x in datos.rangos_prioridad()}["Alta"]["tipos"])

    def test_a_menor_tiempo_mayor_prioridad(self):
        tipos = sorted(datos.tipos_todos(), key=lambda t: t["horas"])
        rango = {"Alta": 0, "Media": 1, "Baja": 2}
        self.assertEqual([rango[t["prioridad"]] for t in tipos], sorted(rango[t["prioridad"]] for t in tipos))

    def test_un_tipo_nuevo_asigna_su_prioridad_y_plazo_a_las_solicitudes(self):
        datos.crear_tipo(self.admin, "Caída del servidor", 4)
        s = self.nueva(tipo="Caída del servidor")
        self.assertEqual((s["prioridad"], s["sla_horas"]), ("Alta", 4))

    def test_el_alta_de_cuentas_exige_area_y_sucursal_activas(self):
        with self.assertRaisesRegex(ValueError, "área"):
            datos.crear_usuario("Luis", "luis", "Clave-1234", "Representante de Área", "No existe", "l@x.mx", "Monterrey")
        with self.assertRaisesRegex(ValueError, "sucursal"):
            datos.crear_usuario("Luis", "luis", "Clave-1234", "Representante de Área", "Ventas", "l@x.mx", "No existe")

    def test_el_representante_nuevo_levanta_solicitudes_con_su_area_y_sucursal(self):
        datos.crear_area(self.admin, "Seguridad")
        datos.crear_sucursal(self.admin, "Puebla")
        datos.crear_usuario("Luis Mora", "lmora", "Clave-1234", "Representante de Área", "Seguridad", "lmora@techsolve.mx", "Puebla")
        s = self.nueva(usuario=cuenta("lmora"), tecnico=False)
        self.assertEqual((s["area"], s["sucursal"], s["solicitante"]), ("Seguridad", "Puebla", "Luis Mora"))

    # ---- el código de edición/eliminación sigue siendo correcto si algún día se habilita
    def test_si_se_habilitara_editar_y_eliminar_funcionaria(self):
        with con_permisos("catalogos.editar", "catalogos.eliminar"):
            area = datos.crear_area(self.admin, "Temporal")
            self.assertEqual(datos.eliminar_area(self.admin, area["id"]), "eliminada")
            suc = datos.crear_sucursal(self.admin, "Temporal")
            self.assertEqual(datos.eliminar_sucursal(self.admin, suc["id"]), "eliminada")
            tipo = next(t for t in datos.tipos_todos() if t["nombre"] == "Incidencia de hardware")
            datos.actualizar_tipo(self.admin, tipo["id"], "Incidencia de equipos", 10, True)
            self.assertEqual(datos.prioridad_de_tipo("Incidencia de equipos"), "Alta")
            self.assertEqual(datos.buscar_por_folio("SIGSAT-0001")["tipo"], "Incidencia de equipos")   # historial al día
            self.assertEqual(datos.eliminar_tipo(self.admin, tipo["id"]), "desactivado")              # tiene historial
            contabilidad = next(a for a in datos.areas_todas() if a["nombre"] == "Contabilidad")
            with self.assertRaisesRegex(ValueError, "representantes activos"):
                datos.actualizar_area(self.admin, contabilidad["id"], "Contabilidad", False)
            matriz = next(x for x in datos.sucursales_todas() if x["nombre"] == "Matriz CDMX")
            with self.assertRaisesRegex(ValueError, "representantes activos"):
                datos.actualizar_sucursal(self.admin, matriz["id"], "Matriz CDMX", False)

    def test_el_historial_conserva_el_plazo_aunque_cambie_el_del_tipo(self):
        vieja = self.nueva(tipo="Incidencia de hardware")
        with con_permisos("catalogos.editar"):
            tipo = next(t for t in datos.tipos_todos() if t["nombre"] == "Incidencia de hardware")
            datos.actualizar_tipo(self.admin, tipo["id"], "Incidencia de hardware", 10, True)
        nueva = self.nueva(tipo="Incidencia de hardware")
        self.assertEqual(datos.buscar_por_folio(vieja["folio"])["prioridad"], "Media")
        self.assertEqual(datos.buscar_por_folio(vieja["folio"])["sla_horas"], 48)
        self.assertEqual((nueva["prioridad"], nueva["sla_horas"]), ("Alta", 10))


class PruebasPlazos(Base):
    def test_el_tipo_lleva_su_tiempo_estimado(self):
        self.assertEqual(datos.horas_de_tipo("Incidencia de software"), 12)
        self.assertIsNone(datos.horas_de_tipo("Inventado"))
        self.assertIsNone(datos.prioridad_de_tipo("Inventado"))
        for t in datos.tipos_todos():
            self.assertIn("horas", t)

    def test_la_solicitud_lleva_prioridad_y_plazo_del_tipo(self):
        for tipo, prioridad, horas in [("Incidencia de software", "Alta", 12), ("Incidencia de hardware", "Media", 48),
                                       ("Solicitud de nuevo acceso", "Baja", 120)]:
            with self.subTest(tipo=tipo):
                s = self.nueva(tipo=tipo)
                self.assertEqual((s["prioridad"], s["sla_horas"]), (prioridad, horas))
                self.assertFalse(s["vencida"])
                self.assertIsNone(s["cumplio_sla"])

    def test_el_representante_no_puede_elegir_la_prioridad_ni_el_area(self):
        import inspect
        parametros = list(inspect.signature(datos.crear_solicitud).parameters)
        self.assertEqual(parametros, ["tipo", "descripcion", "usuario", "adjuntos"])

    def test_vencimiento_y_conteo_de_vencidas(self):
        s = self.nueva(prioridad="Alta")                                  # plazo 12 h
        base = datos.calcular_kpis()["vencidas"]
        self.envejecer(s["folio"], 11)
        self.assertFalse(datos.buscar_por_folio(s["folio"])["vencida"])
        self.envejecer(s["folio"], 13)
        self.assertTrue(datos.buscar_por_folio(s["folio"])["vencida"])
        self.assertEqual(datos.calcular_kpis()["vencidas"], base + 1)

    def test_finalizada_no_cuenta_como_vencida_y_se_marca_si_cumplio(self):
        a = self.nueva(prioridad="Alta")
        self.envejecer(a["folio"], 10)
        datos.actualizar_por_tecnico(a["folio"], self.sebastian, "Finalizado", "Listo")        # a tiempo (10 h < 12 h)
        self.assertIs(datos.buscar_por_folio(a["folio"])["cumplio_sla"], True)
        self.envejecer(a["folio"], 500)             # una finalizada nunca figura como vencida, aunque pase el tiempo
        self.assertFalse(datos.buscar_por_folio(a["folio"])["vencida"])
        datos.calificar_servicio(a["folio"], self.ana, 5)
        self.assertFalse(datos.buscar_por_folio(a["folio"])["vencida"])

    def test_efectividad_en_tiempo_y_fuera_de_tiempo(self):
        k = datos.calcular_kpis()
        self.assertEqual((k["efectividad_pct"], k["fuera_de_tiempo"]), (100, 0))     # las 2 finalizadas de ejemplo cumplieron
        s = self.nueva(prioridad="Alta")
        self.envejecer(s["folio"], 40)                                               # vencida (40 h > 12 h)
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Se resolvió tarde")
        k = datos.calcular_kpis()
        self.assertEqual((k["efectividad_pct"], k["fuera_de_tiempo"]), (67, 1))      # 2 de 3

    def test_sin_finalizadas_no_hay_efectividad(self):
        for s in datos._SOLICITUDES:
            s["finalizada_en"] = None
        self.assertIsNone(datos.calcular_kpis()["efectividad_pct"])

    def test_tiempo_promedio_por_area_y_por_tipo(self):
        k = datos.calcular_kpis()
        self.assertEqual(k["tiempo_por_area"]["Contabilidad"], {"promedio_h": 48.0, "finalizadas": 2})
        self.assertEqual(k["tiempo_por_tipo"]["Incidencia de hardware"]["finalizadas"], 1)
        self.assertNotIn("Ventas", k["tiempo_por_area"], "sin solicitudes finalizadas no hay promedio")

        s = self.nueva(tipo="Incidencia de hardware")
        self.envejecer(s["folio"], 10)
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Listo")
        k = datos.calcular_kpis()
        self.assertAlmostEqual(k["tiempo_por_area"]["Contabilidad"]["promedio_h"], (48 + 48 + 10) / 3, delta=0.2)
        self.assertEqual(k["tiempo_por_area"]["Contabilidad"]["finalizadas"], 3)
        self.assertAlmostEqual(k["tiempo_promedio_h"], (48 + 48 + 10) / 3, delta=0.2)

    def test_satisfaccion_por_area(self):
        s = self.nueva(usuario=self.carlos)
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Listo")
        datos.calificar_servicio(s["folio"], self.carlos, 3)
        k = datos.calcular_kpis()
        self.assertEqual(k["satisfaccion_por_area"]["Ventas"], {"promedio": 3.0, "calificadas": 1})
        self.assertEqual(k["satisfaccion_por_area"]["Contabilidad"], {"promedio": 5.0, "calificadas": 1})
        self.assertEqual(k["satisfaccion_prom"], 4.0)

    def test_las_areas_y_sucursales_nuevas_salen_en_indicadores(self):
        datos.crear_area(self.admin, "Vacía")
        datos.crear_sucursal(self.admin, "Vacía también")
        k = datos.calcular_kpis()
        self.assertEqual(k["por_area"]["Vacía"], 0)
        self.assertEqual(k["por_sucursal"]["Vacía también"], 0)


if __name__ == "__main__":
    unittest.main()
