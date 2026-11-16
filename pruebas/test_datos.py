"""Pruebas de la capa de datos (reglas de negocio, validaciones y seguridad).

Ejecutar desde la carpeta del proyecto:   python -m unittest discover -s pruebas -v
No necesitan PySide6 ni abrir ventanas.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datos
import seguridad


def cuenta(login: str) -> dict:
    return next(u for u in datos.usuarios_todos() if u["usuario"] == login)


class PruebaBase(unittest.TestCase):
    def setUp(self):
        datos.reiniciar()
        self.ana = cuenta("areyes")          # Representante de Área (Contabilidad, Matriz CDMX)
        self.carlos = cuenta("cpena")        # Representante de Área (Ventas, Monterrey)
        self.laura = cuenta("lrios")         # Representante de Área (Recursos Humanos, Guadalajara)
        self.sebastian = cuenta("sestrada")  # Técnico
        self.gabriel = cuenta("gsantiago")   # Técnico
        self.zyanya = cuenta("zarriaga")     # Técnico
        self.direccion = cuenta("direccion")  # Administrador


class PruebasSeguridad(PruebaBase):
    def test_hash_no_es_texto_plano_y_se_verifica(self):
        h = seguridad.hashear_contrasena("Clave-1234")
        self.assertNotIn("Clave-1234", h)
        self.assertTrue(seguridad.verificar_contrasena("Clave-1234", h))
        self.assertFalse(seguridad.verificar_contrasena("clave-1234", h))
        self.assertNotEqual(h, seguridad.hashear_contrasena("Clave-1234"))   # sal distinta
        self.assertFalse(seguridad.verificar_contrasena("x", "basura"))

    def test_la_cuenta_publica_no_expone_el_hash(self):
        for u in datos.usuarios_todos():
            self.assertNotIn("contrasena_hash", u)
            self.assertNotIn("contrasena", u)

    def test_login_por_usuario_y_por_correo(self):
        self.assertEqual(datos.autenticar("sestrada", "Est_001")["nombre"], "Sebastián Estrada")
        self.assertEqual(datos.autenticar("  SESTRADAA01@IPN.MX ", "Est_001")["usuario"], "sestrada")
        self.assertIsNone(datos.autenticar("sestrada", "mala"))
        self.assertIsNone(datos.autenticar("nadie", "Est_001"))

    def test_bloqueo_tras_intentos_fallidos(self):
        for _ in range(seguridad.MAX_INTENTOS - 1):
            self.assertIsNone(datos.autenticar("areyes", "mala"))
        with self.assertRaises(seguridad.BloqueoTemporal):
            datos.autenticar("areyes", "mala")
        # aun con la contraseña correcta, mientras dura el bloqueo no entra
        with self.assertRaises(seguridad.BloqueoTemporal):
            datos.autenticar("areyes", "Rey_006")
        # otra cuenta no se ve afectada
        self.assertIsNotNone(datos.autenticar("cpena", "Pen_007"))

    def test_limitador_se_libera_con_el_tiempo(self):
        reloj = [0.0]
        lim = seguridad.LimitadorIntentos(maximo=3, bloqueo=60, reloj=lambda: reloj[0])
        for _ in range(3):
            lim.registrar_fallo("x")
        self.assertGreater(lim.segundos_restantes("x"), 0)
        reloj[0] = 61
        self.assertEqual(lim.segundos_restantes("x"), 0)
        lim.registrar_fallo("x")
        self.assertEqual(lim.segundos_restantes("x"), 0)   # empieza de cero

    def test_un_acierto_reinicia_los_fallos(self):
        for _ in range(seguridad.MAX_INTENTOS - 1):
            datos.autenticar("areyes", "mala")
        self.assertIsNotNone(datos.autenticar("areyes", "Rey_006"))
        for _ in range(seguridad.MAX_INTENTOS - 1):
            self.assertIsNone(datos.autenticar("areyes", "mala"))


class PruebasCuentas(PruebaBase):
    def alta(self, **kw):
        base = dict(nombre="Luis Mora", usuario="lmora", contrasena="Clave-1234",
                    rol="Representante de Área", area="Compras", correo="lmora@techsolve.mx", sucursal="Monterrey")
        base.update(kw)
        return datos.crear_usuario(**base)

    def test_alta_correcta_y_login(self):
        u = self.alta()
        self.assertEqual((u["rol"], u["area"], u["sucursal"]), ("Representante de Área", "Compras", "Monterrey"))
        self.assertIsNotNone(datos.autenticar("lmora", "Clave-1234"))

    def test_validaciones(self):
        casos = {
            "campos vacíos": dict(nombre=" "),
            "usuario con espacios": dict(usuario="l mora"),
            "correo inválido": dict(correo="sin-arroba"),
            "contraseña corta": dict(contrasena="corta"),
            "sin contraseña": dict(contrasena=""),
            "rol inválido": dict(rol="Administrador"),
            "rol que ya no existe": dict(rol="Agente"),
            "representante sin área": dict(area=None),
            "representante sin sucursal": dict(sucursal=None),
            "área inexistente": dict(area="Inventada"),
            "sucursal inexistente": dict(sucursal="Inventada"),
            "usuario repetido": dict(usuario="AREYES"),
            "correo repetido": dict(correo="AReyes@techsolve.mx"),
            "nombre muy largo": dict(nombre="x" * 101),
        }
        for nombre, datos_malos in casos.items():
            with self.subTest(nombre), self.assertRaises(ValueError):
                self.alta(**datos_malos)
        self.assertEqual(len(datos.usuarios_todos()), 9)    # ninguna se coló

    def test_solo_los_representantes_tienen_area_y_sucursal(self):
        t = self.alta(nombre="Téc", usuario="tec", correo="tec@x.mx", rol="Técnico", area=None, sucursal=None)
        self.assertEqual((t["area"], t["sucursal"]), (None, None))
        # aunque se manden, un técnico no las guarda
        t2 = self.alta(nombre="Téc2", usuario="tec2", correo="tec2@x.mx", rol="Técnico")
        self.assertEqual((t2["area"], t2["sucursal"]), (None, None))

    def test_renombrar_se_refleja_en_todo_el_historial(self):
        datos.actualizar_usuario(self.ana["id"], "Ana R. Reyes", "areyes", "", "Representante de Área", "Contabilidad",
                                 "areyes@techsolve.mx", sucursal="Matriz CDMX")
        self.assertTrue(all(s["solicitante"] == "Ana R. Reyes" for s in datos.solicitudes_de(self.ana["id"])))
        conv = datos.conversaciones_visibles(cuenta("areyes"))[0]
        self.assertEqual(conv["solicitante"], "Ana R. Reyes")
        self.assertEqual(conv["mensajes"][0]["autor"], "Ana R. Reyes")

    def test_editar_sin_contrasena_conserva_la_actual(self):
        datos.actualizar_usuario(self.ana["id"], "Ana", "areyes", "", "Representante de Área", "Contabilidad",
                                 "areyes@techsolve.mx", sucursal="Matriz CDMX")
        self.assertIsNotNone(datos.autenticar("areyes", "Rey_006"))
        datos.actualizar_usuario(self.ana["id"], "Ana", "areyes", "NuevaClave-9", "Representante de Área", "Contabilidad",
                                 "areyes@techsolve.mx", sucursal="Matriz CDMX")
        self.assertIsNone(datos.autenticar("areyes", "Rey_006"))
        self.assertIsNotNone(datos.autenticar("areyes", "NuevaClave-9"))

    def test_cuenta_con_historial_se_desactiva_y_se_puede_reactivar(self):
        self.assertEqual(datos.eliminar_usuario(self.ana["id"]), "desactivada")
        self.assertFalse(datos.buscar_usuario(self.ana["id"])["activo"])
        self.assertIsNone(datos.autenticar("areyes", "Rey_006"))
        self.assertEqual(datos.solicitudes_de(self.ana["id"])[0]["solicitante"], "Ana Reyes")
        datos.actualizar_usuario(self.ana["id"], "Ana Reyes", "areyes", "", "Representante de Área", "Contabilidad",
                                 "areyes@techsolve.mx", activo=True, sucursal="Matriz CDMX")
        self.assertIsNotNone(datos.autenticar("areyes", "Rey_006"))

    def test_cuenta_sin_historial_se_elimina(self):
        u = self.alta()
        self.assertEqual(datos.eliminar_usuario(u["id"]), "eliminada")
        self.assertIsNone(datos.buscar_usuario(u["id"]))

    def test_no_se_gestionan_cuentas_de_administrador(self):
        with self.assertRaises(PermissionError):
            datos.eliminar_usuario(self.direccion["id"])
        with self.assertRaises(PermissionError):
            datos.actualizar_usuario(self.direccion["id"], "X", "x", "", "Técnico", None, "x@x.mx")


class PruebasSolicitudes(PruebaBase):
    def nueva(self, usuario=None, **kw):
        base = dict(tipo="Incidencia de software", descripcion="No abre el sistema")
        base.update(kw)
        return datos.crear_solicitud(base["tipo"], base["descripcion"], usuario or self.ana)

    def asignada(self, tecnico=None, **kw):
        s = self.nueva(**kw)
        datos.asignar_solicitud(s["folio"], self.direccion, (tecnico or self.sebastian)["id"])
        return s["folio"]

    def test_crear_toma_area_sucursal_y_prioridad_de_la_cuenta_y_del_tipo(self):
        s = self.nueva(tipo="Solicitud de nuevo acceso")
        self.assertEqual(s["folio"], "SIGSAT-0008")
        self.assertEqual((s["area"], s["sucursal"]), ("Contabilidad", "Matriz CDMX"))
        self.assertEqual(s["prioridad"], "Baja")                       # 120 h de tiempo estimado
        self.assertEqual(s["sla_horas"], 120)
        self.assertEqual(s["estado"], "Sin visualizar")
        self.assertFalse(s["asignada"])
        self.assertIsNone(s["agente_asignado"])
        self.assertEqual(s["bitacora"][0]["evento"], "Solicitud creada")
        self.assertIn("Pendiente de asignación", s["bitacora"][1]["evento"])

    def test_la_prioridad_sale_del_tiempo_estimado(self):
        self.assertEqual(self.nueva(tipo="Incidencia de software")["prioridad"], "Alta")      # 12 h
        self.assertEqual(self.nueva(tipo="Mantenimiento correctivo")["prioridad"], "Media")   # 60 h
        self.assertEqual(self.nueva(tipo="Desarrollo de aplicación")["prioridad"], "Baja")    # 240 h
        self.assertEqual([datos.prioridad_por_horas(h) for h in (1, 24, 25, 72, 73)],
                         ["Alta", "Alta", "Media", "Media", "Baja"])

    def test_validaciones_de_creacion(self):
        for kw in (dict(descripcion="   "), dict(descripcion="x" * 2001), dict(tipo="Inventado")):
            with self.subTest(kw), self.assertRaises(ValueError):
                self.nueva(**kw)

    def test_solo_los_representantes_crean(self):
        for u in (self.sebastian, self.direccion):
            with self.subTest(u["usuario"]), self.assertRaises(PermissionError):
                self.nueva(usuario=u)

    def test_cada_representante_ve_solo_las_suyas(self):
        s = self.nueva()
        self.assertIn(s["folio"], [x["folio"] for x in datos.solicitudes_de(self.ana["id"])])
        self.assertNotIn(s["folio"], [x["folio"] for x in datos.solicitudes_de(self.carlos["id"])])
        self.assertIsNone(datos.solicitud_visible(self.carlos, s["folio"]))
        self.assertIsNotNone(datos.solicitud_visible(self.ana, s["folio"]))

    def test_el_tecnico_solo_ve_las_que_tiene_asignadas(self):
        folio = self.asignada()
        self.assertIsNotNone(datos.solicitud_visible(self.sebastian, folio))
        self.assertIsNone(datos.solicitud_visible(self.zyanya, folio))
        self.assertIsNotNone(datos.solicitud_visible(self.direccion, folio))
        sin = self.nueva()["folio"]
        self.assertIsNone(datos.solicitud_visible(self.sebastian, sin))

    def test_el_administrador_distribuye(self):
        s = self.nueva()
        with self.assertRaises(PermissionError):
            datos.asignar_solicitud(s["folio"], self.sebastian, self.sebastian["id"])
        with self.assertRaises(PermissionError):
            datos.asignar_solicitud(s["folio"], self.ana, self.sebastian["id"])
        with self.assertRaises(ValueError):
            datos.asignar_solicitud(s["folio"], self.direccion, self.ana["id"])      # un representante no es técnico
        self.assertEqual(datos.asignar_solicitud(s["folio"], self.direccion, self.sebastian["id"]), "ok")
        self.assertEqual(datos.asignar_solicitud(s["folio"], self.direccion, self.sebastian["id"]), "sin_cambios")
        self.assertEqual(datos.asignar_solicitud("SIGSAT-9999", self.direccion, self.sebastian["id"]), "no_existe")
        d = datos.buscar_por_folio(s["folio"])
        self.assertEqual((d["agente_asignado"], d["estado"], d["asignada"]), ("Sebastián Estrada", "Sin visualizar", True))

    def test_reasignar_reinicia_el_estatus(self):
        folio = self.asignada()
        datos.registrar_visualizacion(folio, self.sebastian)
        datos.actualizar_por_tecnico(folio, self.sebastian, "En proceso", "")
        self.assertEqual(datos.asignar_solicitud(folio, self.direccion, self.gabriel["id"], "Está de vacaciones"), "ok")
        d = datos.buscar_por_folio(folio)
        self.assertEqual((d["agente_asignado"], d["estado"]), ("Gabriel Santiago", "Sin visualizar"))
        self.assertIn("Reasignada de Sebastián Estrada a Gabriel Santiago", d["bitacora"][-1]["evento"])
        self.assertIn("Está de vacaciones", d["bitacora"][-1]["evento"])

    def test_no_se_asigna_una_finalizada(self):
        self.assertEqual(datos.asignar_solicitud("SIGSAT-0001", self.direccion, self.gabriel["id"]), "finalizada")

    def test_el_tecnico_abre_el_reporte_y_queda_visualizado(self):
        folio = self.asignada()
        self.assertEqual(datos.registrar_visualizacion(folio, self.sebastian), "ok")
        self.assertEqual(datos.buscar_por_folio(folio)["estado"], "Visualizado")
        self.assertEqual(datos.registrar_visualizacion(folio, self.sebastian), "sin_cambios")
        with self.assertRaises(PermissionError):
            datos.registrar_visualizacion(folio, self.zyanya)               # no es suya
        with self.assertRaises(PermissionError):
            datos.registrar_visualizacion(folio, self.ana)
        self.assertEqual(datos.registrar_visualizacion("SIGSAT-9999", self.sebastian), "no_existe")

    def test_el_estatus_solo_avanza(self):
        folio = self.asignada()
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "En proceso", "Empecé"), "ok")
        with self.assertRaisesRegex(ValueError, "no puede retroceder"):
            datos.actualizar_por_tecnico(folio, self.sebastian, "Visualizado", "")
        with self.assertRaisesRegex(ValueError, "estatus válido"):
            datos.actualizar_por_tecnico(folio, self.sebastian, "Sin visualizar", "")
        with self.assertRaisesRegex(ValueError, "estatus válido"):
            datos.actualizar_por_tecnico(folio, self.sebastian, "Cerrada", "")

    def test_finalizar_exige_el_reporte_final(self):
        folio = self.asignada()
        with self.assertRaisesRegex(ValueError, "reporte final"):
            datos.actualizar_por_tecnico(folio, self.sebastian, "Finalizado", "  ")
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "Finalizado", "Listo, se reinstaló"), "ok")
        d = datos.buscar_por_folio(folio)
        self.assertEqual(d["estado"], "Finalizado")
        self.assertTrue(d["finalizada"] and d["por_calificar"])
        self.assertIsNotNone(d["fecha_finalizacion"])
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "En proceso", "x"), "finalizada")

    def test_solo_el_tecnico_asignado_actualiza(self):
        folio = self.asignada()
        with self.assertRaises(PermissionError):
            datos.actualizar_por_tecnico(folio, self.zyanya, "En proceso", "")
        with self.assertRaises(PermissionError):
            datos.actualizar_por_tecnico(folio, self.direccion, "En proceso", "")
        with self.assertRaises(PermissionError):
            datos.actualizar_por_tecnico(folio, self.ana, "En proceso", "")

    def test_actualizar_sin_cambios_no_escribe_en_la_bitacora(self):
        folio = self.asignada()
        datos.registrar_visualizacion(folio, self.sebastian)
        antes = len(datos.buscar_por_folio(folio)["bitacora"])
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "Visualizado", ""), "sin_cambios")
        self.assertEqual(len(datos.buscar_por_folio(folio)["bitacora"]), antes)

    def test_solo_comentario(self):
        folio = self.asignada()
        datos.registrar_visualizacion(folio, self.sebastian)
        datos.actualizar_por_tecnico(folio, self.sebastian, "Visualizado", "Llamé al usuario")
        d = datos.buscar_por_folio(folio)
        self.assertEqual(d["estado"], "Visualizado")
        self.assertEqual(d["bitacora"][-1]["evento"], "Llamé al usuario")

    def test_validaciones_de_actualizacion(self):
        folio = self.asignada()
        with self.assertRaises(ValueError):
            datos.actualizar_por_tecnico(folio, self.sebastian, "Inventado", "")
        with self.assertRaises(ValueError):
            datos.actualizar_por_tecnico(folio, self.sebastian, "En proceso", "x" * 1001)

    def test_una_solicitud_vencida_se_puede_seguir_atendiendo(self):
        folio = self.asignada()
        s = datos._solicitud_por_folio(folio)
        s["creada_en"] = s["plazo_desde"] = s["creada_en"] - __import__("datetime").timedelta(hours=100)
        self.assertTrue(datos.buscar_por_folio(folio)["vencida"])
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "Finalizado", "Ya quedó"), "ok")
        d = datos.buscar_por_folio(folio)
        self.assertFalse(d["vencida"])
        self.assertFalse(d["cumplio_sla"])                                   # se cuenta como fuera de tiempo

    def test_calificar_el_servicio(self):
        folio = self.asignada()
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 5), "no_aplica")      # aún no finalizada
        datos.actualizar_por_tecnico(folio, self.sebastian, "Finalizado", "Listo")
        self.assertEqual(datos.calificar_servicio(folio, self.carlos, 5), "no_aplica")   # no es suya
        for mala in (0, 6, "5", None, True):
            with self.subTest(mala), self.assertRaises(ValueError):
                datos.calificar_servicio(folio, self.ana, mala)
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 4), "ok")
        d = datos.buscar_por_folio(folio)
        self.assertEqual((d["estado"], d["calificacion"]), ("Finalizado", 4))        # calificar no cambia el estatus
        self.assertFalse(d["por_calificar"])
        self.assertIsNotNone(d["fecha_calificacion"])
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 1), "no_aplica")      # solo una vez
        for u in (self.sebastian, self.direccion):
            with self.assertRaises(PermissionError):
                datos.calificar_servicio(folio, u, 5)

    def test_listar_reportes_por_rol(self):
        admin = datos.listar_reportes(self.direccion)
        self.assertEqual({s["folio"] for s in admin}, {"SIGSAT-0002", "SIGSAT-0003", "SIGSAT-0004", "SIGSAT-0006", "SIGSAT-0007"})
        self.assertEqual(len(datos.listar_reportes(self.direccion, incluir_finalizados=True)), 7)
        mios = datos.listar_reportes(self.sebastian)
        self.assertEqual([s["folio"] for s in mios], ["SIGSAT-0002"])
        self.assertEqual({s["folio"] for s in datos.listar_reportes(self.sebastian, incluir_finalizados=True)},
                         {"SIGSAT-0001", "SIGSAT-0002"})
        # el filtro de técnico no deja a un técnico ver los de otro
        self.assertEqual({s["folio"] for s in datos.listar_reportes(self.sebastian, agente_id=self.gabriel["id"])},
                         {"SIGSAT-0002"})
        for u in (self.ana, self.carlos):
            with self.assertRaises(PermissionError):
                datos.listar_reportes(u)

    def test_filtros_de_reportes(self):
        r = datos.listar_reportes
        self.assertEqual({s["folio"] for s in r(self.direccion, estado="Sin visualizar")}, {"SIGSAT-0003", "SIGSAT-0006", "SIGSAT-0007"})
        self.assertEqual({s["folio"] for s in r(self.direccion, estado="Visualizado")}, {"SIGSAT-0004"})
        self.assertEqual({s["folio"] for s in r(self.direccion, prioridad="Alta")}, {"SIGSAT-0002"})
        self.assertEqual({s["folio"] for s in r(self.direccion, area="Ventas")}, {"SIGSAT-0002", "SIGSAT-0006"})
        self.assertEqual({s["folio"] for s in r(self.direccion, sucursal="Guadalajara")}, {"SIGSAT-0004", "SIGSAT-0007"})
        self.assertEqual({s["folio"] for s in r(self.direccion, agente_id=self.gabriel["id"])}, {"SIGSAT-0007"})
        self.assertEqual(r(self.direccion, solo_vencidas=True), [])
        with self.assertRaises(ValueError):
            r(self.direccion, estado="Cerrada")
        with self.assertRaises(ValueError):
            r(self.direccion, prioridad="Urgente")

    def test_kpis(self):
        k = datos.calcular_kpis()
        self.assertEqual(k["total"], 7)
        self.assertEqual(k["por_estado"], {"Sin visualizar": 3, "Visualizado": 1, "En proceso": 1, "Finalizado": 2})
        self.assertEqual(k["vencidas"], 0)
        self.assertEqual(k["fuera_de_tiempo"], 0)
        self.assertEqual(k["efectividad_pct"], 100)
        self.assertEqual(k["tiempo_promedio_h"], 48.0)
        self.assertEqual(k["satisfaccion_prom"], 5.0)                    # solo la 0001 está calificada
        self.assertEqual(k["satisfaccion_por_area"], {"Contabilidad": {"promedio": 5.0, "calificadas": 1}})
        self.assertEqual(k["sin_asignar"], 2)
        self.assertEqual(k["por_area"]["Contabilidad"], 3)
        self.assertEqual(k["por_sucursal"]["Guadalajara"], 2)

    def test_carga_de_trabajo_por_tecnico(self):
        carga = {c["agente"]: c for c in datos.carga_trabajo()}
        self.assertEqual(len(carga), 5)
        s = carga["Sebastián Estrada"]
        self.assertEqual((s["abiertas"], s["en_proceso"], s["finalizadas"]), (1, 1, 1))
        g = carga["Gabriel Santiago"]
        self.assertEqual((g["abiertas"], g["sin_visualizar"]), (1, 1))

    def test_la_interfaz_no_puede_modificar_el_estado_interno(self):
        s = datos.buscar_por_folio("SIGSAT-0002")
        s["estado"] = "Finalizado"
        s["bitacora"].clear()
        original = datos.buscar_por_folio("SIGSAT-0002")
        self.assertEqual(original["estado"], "En proceso")
        self.assertTrue(original["bitacora"])


class PruebasMesa(PruebaBase):
    def test_visibilidad_por_rol(self):
        self.assertEqual(len(datos.conversaciones_visibles(self.ana)), 1)
        self.assertEqual(len(datos.conversaciones_visibles(self.carlos)), 1)
        self.assertEqual([c["id"] for c in datos.conversaciones_visibles(self.sebastian)], ["MESA-0003"])
        self.assertEqual(datos.conversaciones_visibles(self.gabriel), [])
        self.assertEqual(len(datos.conversaciones_visibles(self.direccion)), 3)
        self.assertEqual(len(datos.conversaciones_visibles(self.direccion, "Abierta")), 2)

    def test_crear_conversacion(self):
        c = datos.crear_conversacion(self.ana, "Duda", "Hola", "SIGSAT-0003")
        self.assertEqual(c["id"], "MESA-0004")
        self.assertEqual((c["folio"], c["estado"], c["rol_solicitante"]), ("SIGSAT-0003", "Abierta", "Representante de Área"))
        with self.assertRaises(ValueError):
            datos.crear_conversacion(self.ana, "Duda", "Hola", "SIGSAT-0002")   # solicitud de otra persona
        with self.assertRaises(ValueError):
            datos.crear_conversacion(self.ana, "", "Hola")
        with self.assertRaises(ValueError):
            datos.crear_conversacion(self.ana, "Duda", "x" * 2001)
        with self.assertRaises(PermissionError):
            datos.crear_conversacion(self.direccion, "Duda", "Hola")             # el admin responde, no abre

    def test_el_tecnico_abre_conversaciones_sobre_sus_reportes(self):
        c = datos.crear_conversacion(self.sebastian, "Duda", "Hola", "SIGSAT-0002")
        self.assertEqual(c["rol_solicitante"], "Técnico")
        with self.assertRaises(ValueError):
            datos.crear_conversacion(self.sebastian, "Duda", "Hola", "SIGSAT-0004")   # no es suyo

    def test_el_administrador_responde_y_la_pasa_a_en_atencion(self):
        self.assertTrue(datos.enviar_mensaje("MESA-0002", self.direccion, "Lo reviso"))
        c = datos.buscar_conversacion("MESA-0002")
        self.assertEqual(c["estado"], "En atención")
        self.assertEqual(c["mensajes"][-1]["rol"], "Administrador")

    def test_nadie_escribe_donde_no_debe(self):
        self.assertFalse(datos.enviar_mensaje("MESA-0001", self.carlos, "hola"))       # no es suya
        self.assertFalse(datos.enviar_mensaje("MESA-0001", self.gabriel, "hola"))      # otro técnico
        self.assertFalse(datos.enviar_mensaje("MESA-0001", self.ana, "   "))           # vacío
        self.assertTrue(datos.enviar_mensaje("MESA-0001", self.ana, "gracias"))

    def test_cerrar(self):
        self.assertFalse(datos.cerrar_conversacion("MESA-0002", self.carlos))          # el dueño no cierra
        self.assertTrue(datos.cerrar_conversacion("MESA-0002", self.direccion))
        self.assertFalse(datos.cerrar_conversacion("MESA-0002", self.direccion))       # ya cerrada
        self.assertFalse(datos.enviar_mensaje("MESA-0002", self.carlos, "otra cosa"))  # cerrada: no se escribe

    def test_mensajes_propios_se_identifican_por_id(self):
        c = datos.buscar_conversacion("MESA-0001")
        self.assertEqual(c["mensajes"][0]["autor_id"], self.ana["id"])
        self.assertEqual(c["mensajes"][1]["autor_id"], self.direccion["id"])


if __name__ == "__main__":
    unittest.main()
