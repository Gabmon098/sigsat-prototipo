"""Reglas del modelo de tres roles: las vencidas se siguen atendiendo (y cuentan como fuera de tiempo), el
representante califica el servicio una vez finalizado, el Administrador distribuye (no hay asignación
automática), la prioridad sale del tiempo estimado del tipo y las cuentas de demostración."""

import unittest
from datetime import datetime, timedelta

from pruebas.base import Base, cuenta
import correo
import datos
import persistencia


class PruebasVencidas(Base):
    def vencida(self):
        """Una solicitud en proceso que ya pasó su fecha límite (Alta: 12 h)."""
        s = self.nueva(tipo="Incidencia de software")
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "En proceso", "Empecé a revisarla")
        self.envejecer(s["folio"], 30)
        self.assertTrue(datos.buscar_por_folio(s["folio"])["vencida"])
        return s["folio"]

    def test_una_vencida_se_sigue_atendiendo(self):
        folio = self.vencida()
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "En proceso", "Sigo con ello"), "ok")
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "Finalizado", "Listo, con retraso"), "ok")
        d = datos.buscar_por_folio(folio)
        self.assertEqual(d["estado"], "Finalizado")
        self.assertIs(d["cumplio_sla"], False)                    # se cuenta como fuera de tiempo
        self.assertFalse(d["vencida"])                            # ya no está abierta

    def test_la_vencida_se_puede_reasignar(self):
        folio = self.vencida()
        self.assertEqual(datos.asignar_solicitud(folio, self.admin, self.gabriel["id"], "Se venció"), "ok")
        self.assertEqual(datos.buscar_por_folio(folio)["agente_id"], self.gabriel["id"])
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.gabriel, "Visualizado", "x"), "ok")

    def test_no_existe_el_congelamiento(self):
        self.assertFalse(hasattr(datos, "MENSAJE_VENCIDA"))
        self.assertFalse(hasattr(datos, "tomar_solicitud"))

    def test_justo_antes_del_limite_no_esta_vencida(self):
        s = self.nueva(tipo="Incidencia de software")
        self.envejecer(s["folio"], 11)
        self.assertFalse(datos.buscar_por_folio(s["folio"])["vencida"])

    def test_una_finalizada_no_se_considera_vencida_aunque_pase_el_tiempo(self):
        s = self.nueva(tipo="Incidencia de software")
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Listo")
        self.envejecer(s["folio"], 1000)
        self.assertFalse(datos.buscar_por_folio(s["folio"])["vencida"])
        self.assertEqual(datos.calificar_servicio(s["folio"], self.ana, 5), "ok")          # el representante aún puede calificar


class PruebasCalificacionTrasFinalizar(Base):
    def finalizada(self, **kw):
        s = self.nueva(tipo="Incidencia de software", **kw)
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Reinicié el servicio")
        return s["folio"]

    def test_finalizar_deja_la_solicitud_por_calificar(self):
        folio = self.finalizada()
        d = datos.buscar_por_folio(folio)
        self.assertEqual(d["estado"], "Finalizado")
        self.assertTrue(d["por_calificar"])
        self.assertTrue(d["finalizada"])
        self.assertIsNotNone(d["fecha_finalizacion"])
        self.assertIsNone(d["fecha_calificacion"])
        self.assertIsNone(d["calificacion"])
        self.assertIn("pendiente de calificación", d["bitacora"][-1]["evento"])

    def test_el_representante_califica_y_el_estatus_no_cambia(self):
        folio = self.finalizada()
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 4), "ok")
        d = datos.buscar_por_folio(folio)
        self.assertEqual((d["estado"], d["calificacion"], d["por_calificar"]), ("Finalizado", 4, False))
        self.assertIsNotNone(d["fecha_calificacion"])
        self.assertIn("calificó el servicio recibido (4/5)", d["bitacora"][-1]["evento"])

    def test_no_se_califica_antes_de_finalizar(self):
        s = self.nueva()
        for _ in ("Sin visualizar", "En proceso"):
            self.assertEqual(datos.calificar_servicio(s["folio"], self.ana, 5), "no_aplica")
            datos.actualizar_por_tecnico(s["folio"], self.sebastian, "En proceso", "")
        self.assertIsNone(datos.buscar_por_folio(s["folio"])["calificacion"])

    def test_solo_el_dueno_califica_y_solo_una_vez(self):
        folio = self.finalizada()
        self.assertEqual(datos.calificar_servicio(folio, self.carlos, 5), "no_aplica")
        with self.assertRaises(PermissionError):
            datos.calificar_servicio(folio, self.sebastian, 5)
        with self.assertRaises(PermissionError):
            datos.calificar_servicio(folio, self.admin, 5)
        for mala in (0, 6, -1, 3.5, "5", None, True):
            with self.subTest(calificacion=mala), self.assertRaises(ValueError):
                datos.calificar_servicio(folio, self.ana, mala)
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 5), "ok")
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 1), "no_aplica")
        self.assertEqual(datos.buscar_por_folio(folio)["calificacion"], 5)

    def test_el_tecnico_no_modifica_una_finalizada(self):
        folio = self.finalizada()
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "En proceso", "x"), "finalizada")
        datos.calificar_servicio(folio, self.ana, 5)
        self.assertEqual(datos.actualizar_por_tecnico(folio, self.sebastian, "Finalizado", "x"), "finalizada")
        self.assertEqual(datos.buscar_por_folio(folio)["estado"], "Finalizado")

    def test_no_existe_el_cierre_ni_el_rechazo_de_la_solucion(self):
        import notificaciones
        for nombre in ("validar_cierre", "rechazar_solucion", "actualizar_por_agente"):
            self.assertFalse(hasattr(datos, nombre), nombre)
        self.assertFalse(hasattr(notificaciones, "solucion_rechazada"))
        self.assertFalse(hasattr(notificaciones, "solicitud_cerrada"))

    def test_una_nota_baja_tambien_se_registra(self):
        folio = self.finalizada()
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 1), "ok")
        self.assertEqual(datos.buscar_por_folio(folio)["calificacion"], 1)

    def test_el_tiempo_de_atencion_se_mide_hasta_la_finalizacion_no_hasta_la_calificacion(self):
        folio = self.finalizada()
        self.envejecer(folio, 10)
        self.interna(folio)["finalizada_en"] = self.interna(folio)["creada_en"] + timedelta(hours=6)
        h = datos._horas(self.interna(folio))
        self.assertAlmostEqual(h, 6, delta=0.01)

    def test_las_solicitudes_de_ejemplo_muestran_cada_situacion(self):
        estados = {s["folio"]: s["estado"] for s in datos.solicitudes_todas(self.admin)}
        self.assertEqual(estados, {"SIGSAT-0001": "Finalizado", "SIGSAT-0002": "En proceso", "SIGSAT-0003": "Sin visualizar",
                                   "SIGSAT-0004": "Visualizado", "SIGSAT-0005": "Finalizado", "SIGSAT-0006": "Sin visualizar",
                                   "SIGSAT-0007": "Sin visualizar"})
        self.assertTrue(datos.buscar_por_folio("SIGSAT-0005")["por_calificar"])
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0005")["solicitante"], "Ana Reyes")
        self.assertEqual(datos.calificar_servicio("SIGSAT-0005", self.ana, 4), "ok")      # la demo se puede probar

    def test_las_finalizadas_cuentan_en_el_historial_del_representante(self):
        self.assertEqual({s["folio"] for s in datos.solicitudes_de(self.ana["id"], "Finalizado")}, {"SIGSAT-0001", "SIGSAT-0005"})


class PruebasDistribucionManual(Base):
    """El sistema no asigna solo: cada solicitud espera a que el Administrador la distribuya."""

    def test_la_solicitud_nueva_queda_sin_asignar(self):
        for usuario in (self.ana, self.carlos, self.laura):
            with self.subTest(usuario=usuario["usuario"]):
                s = self.nueva(usuario=usuario, tecnico=False)
                self.assertIsNone(s["agente_asignado"])
                self.assertEqual(s["estado"], "Sin visualizar")
                self.assertFalse(s["asignada"])

    def test_el_area_y_la_sucursal_son_las_de_la_cuenta(self):
        for usuario, area, sucursal in [(self.ana, "Contabilidad", "Matriz CDMX"), (self.carlos, "Ventas", "Monterrey"),
                                        (self.laura, "Recursos Humanos", "Guadalajara")]:
            with self.subTest(usuario=usuario["usuario"]):
                s = self.nueva(usuario=usuario, tecnico=False)
                self.assertEqual((s["area"], s["sucursal"]), (area, sucursal))

    def test_el_representante_sin_area_o_sucursal_no_puede_solicitar(self):
        datos._usuario_por_id(self.ana["id"])["area_id"] = None
        with self.assertRaisesRegex(ValueError, "área y sucursal"):
            self.nueva(tecnico=False)
        self.assertEqual(len(datos.solicitudes_de(self.ana["id"])), 3, "no se creó ninguna solicitud")

    def test_no_existe_la_asignacion_automatica(self):
        self.assertFalse(hasattr(datos, "_agente_para_area"))
        self.assertFalse(hasattr(datos, "solicitudes_bandeja"))

    def test_la_bitacora_registra_que_espera_asignacion(self):
        s = self.nueva(tecnico=False)
        eventos = s["bitacora"]
        self.assertEqual(eventos[0]["evento"], "Solicitud creada")
        self.assertEqual((eventos[1]["autor"], eventos[1]["evento"]),
                         ("Sistema", "Pendiente de asignación: el Administrador la distribuirá a un técnico"))

    def test_la_solicitud_asignada_aparece_en_los_reportes_de_ese_tecnico(self):
        s = self.nueva(tecnico=self.zyanya)
        self.assertIn(s["folio"], [x["folio"] for x in datos.listar_reportes(self.zyanya)])
        self.assertNotIn(s["folio"], [x["folio"] for x in datos.listar_reportes(self.sebastian)])

    def test_un_tecnico_desactivado_no_recibe_solicitudes(self):
        datos.actualizar_usuario(self.gabriel["id"], "Gabriel Santiago", "gsantiago", "", "Técnico", None,
                                 "gsantiagog1800@alumno.ipn.mx", activo=False)
        s = self.nueva(tecnico=False)
        with self.assertRaisesRegex(ValueError, "técnico activo"):
            datos.asignar_solicitud(s["folio"], self.admin, self.gabriel["id"])


class PruebasPrioridadPorTiempo(Base):
    def test_la_prioridad_sale_del_tiempo_estimado_del_tipo(self):
        esperadas = {"Incidencia de software": "Alta", "Incidencia de hardware": "Media", "Mantenimiento correctivo": "Media",
                     "Solicitud de nuevo acceso": "Baja", "Desarrollo de aplicación": "Baja",
                     "Mantenimiento preventivo": "Baja", "Consultoría tecnológica": "Baja"}
        for tipo, prioridad in esperadas.items():
            with self.subTest(tipo=tipo):
                self.assertEqual(datos.prioridad_de_tipo(tipo), prioridad)
                self.assertEqual(self.nueva(tipo=tipo, tecnico=False)["prioridad"], prioridad)

    def test_un_tipo_inexistente(self):
        self.assertIsNone(datos.prioridad_de_tipo("Inventado"))

    def test_los_limites_entre_prioridades(self):
        self.assertEqual([datos.prioridad_por_horas(h) for h in (1, 24, 25, 72, 73, 720)],
                         ["Alta", "Alta", "Media", "Media", "Baja", "Baja"])


class PruebasCuentasDemo(Base):
    NUEVAS = {"sestrada": "Est_001", "dlopez": "Lop_002", "zarriaga": "Arr_003", "gsantiago": "San_004",
              "jmontes": "Mon_005", "areyes": "Rey_006", "cpena": "Pen_007", "lrios": "Rio_008", "direccion": "Dir_000"}

    def test_las_contrasenas_de_demostracion(self):
        for usuario, clave in self.NUEVAS.items():
            with self.subTest(usuario=usuario):
                self.assertIsNotNone(datos.autenticar(usuario, clave))

    def test_las_contrasenas_anteriores_ya_no_sirven(self):
        for usuario, vieja in [("sestrada", "Est-7Kp2"), ("areyes", "Rey-3Xn5"), ("direccion", "Dir-5Wz7")]:
            self.assertIsNone(datos.autenticar(usuario, vieja))

    def test_todas_las_cuentas_tienen_un_correo_valido(self):
        for u in datos.usuarios_todos():
            self.assertTrue(correo.direccion_valida(u["correo"]), f"{u['usuario']}: {u['correo']!r}")

    def test_el_correo_de_ana_recibe_notificaciones(self):
        self.assertEqual(self.ana["correo"], "areyes@techsolve.mx")
        self.buzon.clear()
        self.nueva()                                         # se crea y se asigna: avisa a Ana
        self.assertIn("areyes@techsolve.mx", [m["To"] for m in self.buzon])

    def test_cuentas_y_roles(self):
        roles = {u["usuario"]: u["rol"] for u in datos.usuarios_todos()}
        self.assertEqual(roles["direccion"], "Administrador")
        self.assertEqual({k for k, v in roles.items() if v == "Técnico"}, {"sestrada", "dlopez", "zarriaga", "gsantiago", "jmontes"})
        self.assertEqual({k for k, v in roles.items() if v == "Representante de Área"}, {"areyes", "cpena", "lrios"})

    def test_solo_existen_tres_roles(self):
        self.assertEqual(set(datos.ROLES), {"Administrador", "Representante de Área", "Técnico"})
        self.assertEqual({u["rol"] for u in datos.usuarios_todos()}, set(datos.ROLES))

    def test_los_representantes_traen_area_y_sucursal_y_los_demas_no(self):
        for u in datos.usuarios_todos():
            if u["rol"] == "Representante de Área":
                self.assertTrue(u["area"] and u["sucursal"], u["usuario"])
            else:
                self.assertEqual((u["area"], u["sucursal"]), (None, None), u["usuario"])


class PruebasVersionDeDatos(Base):
    def test_datos_de_una_version_anterior_se_respaldan_y_se_reinicia_con_los_nuevos(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            carpeta = Path(d) / "datos"
            carpeta.mkdir()
            (carpeta / "estado.json").write_text(json.dumps({"version": 2, "usuarios": []}), encoding="utf-8")
            self.assertEqual(persistencia.activar(carpeta), "actualizado")
            self.assertEqual([r["tipo"] for r in persistencia.listar_respaldos()], ["antes_de_actualizar"])
            self.assertIsNotNone(datos.autenticar("sestrada", "Est_001"))                # ya con las cuentas nuevas
            self.assertEqual(len(datos.solicitudes_todas(self.admin)), 7)
            persistencia.desactivar()
            self.assertEqual(persistencia.activar(carpeta), "cargado")                    # la siguiente vez ya es normal
            persistencia.desactivar()

    def test_la_version_del_estado_es_la_del_modelo_de_tres_roles(self):
        self.assertEqual(datos.VERSION_ESTADO, 3)
        self.assertEqual(datos.exportar_estado()["version"], 3)

    def test_un_respaldo_de_otra_version_no_se_puede_restaurar(self):
        import json
        import tempfile
        import zipfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            persistencia.activar(Path(d) / "datos")
            viejo = Path(d) / "viejo.zip"
            with zipfile.ZipFile(viejo, "w") as z:
                z.writestr("estado.json", json.dumps({"version": 2}))
            antes = datos.exportar_estado()
            with self.assertRaisesRegex(persistencia.ErrorPersistencia, "otra versión"):
                persistencia.restaurar_respaldo(viejo)
            self.assertEqual(datos.exportar_estado(), antes)
            persistencia.desactivar()


if __name__ == "__main__":
    unittest.main()
