"""RF-09 (el Administrador distribuye: asigna y reasigna) y carga de trabajo del técnico."""

import unittest

from pruebas.base import Base
import datos


class PruebasAsignacion(Base):
    def test_solo_quien_tiene_permiso_asigna(self):
        for actor in (self.ana, self.sebastian):
            with self.subTest(rol=actor["rol"]), self.assertRaises(PermissionError):
                datos.asignar_solicitud("SIGSAT-0003", actor, self.zyanya["id"])
        self.assertIsNone(datos.buscar_por_folio("SIGSAT-0003")["agente_id"])

    def test_asignar_una_solicitud_sin_tecnico(self):
        self.assertEqual(datos.asignar_solicitud("SIGSAT-0003", self.admin, self.zyanya["id"], "Tiene la VPN"), "ok")
        s = datos.buscar_por_folio("SIGSAT-0003")
        self.assertEqual(s["agente_asignado"], "Zyanya Arriaga")
        self.assertEqual(s["estado"], "Sin visualizar")
        evento = s["bitacora"][-1]
        self.assertEqual(evento["autor"], "Dirección General")            # queda quién la asignó
        self.assertIn("Asignada a Zyanya Arriaga", evento["evento"])
        self.assertIn("Tiene la VPN", evento["evento"])

    def test_reasignar_a_otro_tecnico(self):
        self.assertEqual(datos.asignar_solicitud("SIGSAT-0002", self.admin, self.gabriel["id"], "Sebastián está saturado"), "ok")
        s = datos.buscar_por_folio("SIGSAT-0002")
        self.assertEqual(s["agente_asignado"], "Gabriel Santiago")
        self.assertEqual(s["estado"], "Sin visualizar")                    # para el técnico nuevo empieza de cero
        self.assertIn("Reasignada de Sebastián Estrada a Gabriel Santiago", s["bitacora"][-1]["evento"])
        self.assertEqual(s["area"], "Ventas")                              # el área es la del representante: no cambia
        self.assertIn("SIGSAT-0002", [x["folio"] for x in datos.listar_reportes(self.gabriel)])
        self.assertNotIn("SIGSAT-0002", [x["folio"] for x in datos.listar_reportes(self.sebastian)])

    def test_casos_sin_cambio_o_no_permitidos(self):
        self.assertEqual(datos.asignar_solicitud("SIGSAT-0002", self.admin, self.sebastian["id"]), "sin_cambios")
        self.assertEqual(datos.asignar_solicitud("SIGSAT-0001", self.admin, self.gabriel["id"]), "finalizada")
        self.assertEqual(datos.asignar_solicitud("SIGSAT-9999", self.admin, self.gabriel["id"]), "no_existe")
        for malo in (self.ana["id"], self.admin["id"], 9999):                 # no es técnico / no existe
            with self.subTest(id=malo), self.assertRaisesRegex(ValueError, "técnico activo"):
                datos.asignar_solicitud("SIGSAT-0003", self.admin, malo)
        datos.actualizar_usuario(self.gabriel["id"], "Gabriel Santiago", "gsantiago", "", "Técnico", None,
                                 "gsantiagog1800@alumno.ipn.mx", activo=False)
        with self.assertRaisesRegex(ValueError, "técnico activo"):             # un técnico desactivado no recibe trabajo
            datos.asignar_solicitud("SIGSAT-0003", self.admin, self.gabriel["id"])
        with self.assertRaisesRegex(ValueError, "demasiado largo"):
            datos.asignar_solicitud("SIGSAT-0003", self.admin, self.zyanya["id"], "x" * 1001)

    def test_el_administrador_ve_todas_las_solicitudes_pero_no_las_atiende(self):
        todas = datos.solicitudes_todas(self.admin)
        self.assertEqual(len(todas), 7)
        self.assertIsNotNone(datos.solicitud_visible(self.admin, "SIGSAT-0002"))
        with self.assertRaises(PermissionError):
            datos.actualizar_por_tecnico("SIGSAT-0002", self.admin, "En proceso", "x")
        with self.assertRaises(PermissionError):
            datos.registrar_visualizacion("SIGSAT-0003", self.admin)

    def test_los_demas_roles_no_ven_todas(self):
        with self.assertRaises(PermissionError):
            datos.solicitudes_todas(self.ana)
        with self.assertRaises(PermissionError):
            datos.solicitudes_todas(self.sebastian)
        self.assertIsNone(datos.solicitud_visible(self.ana, "SIGSAT-0002"))           # ajena

    def test_filtros_de_solicitudes_todas(self):
        self.assertEqual({s["folio"] for s in datos.solicitudes_todas(self.admin, sin_asignar=True)}, {"SIGSAT-0003", "SIGSAT-0006"})
        self.assertEqual({s["area"] for s in datos.solicitudes_todas(self.admin, area="Contabilidad")}, {"Contabilidad"})
        self.assertEqual([s["folio"] for s in datos.solicitudes_todas(self.admin, estado="Visualizado")], ["SIGSAT-0004"])
        self.assertEqual(datos.solicitudes_todas(self.admin, solo_vencidas=True), [])
        self.assertEqual([s["folio"] for s in datos.solicitudes_todas(self.admin, agente_id=self.zyanya["id"])], ["SIGSAT-0005"])
        self.assertEqual({s["folio"] for s in datos.solicitudes_todas(self.admin, estado="Finalizado")}, {"SIGSAT-0001", "SIGSAT-0005"})

    def test_solicitudes_vencidas_aparecen_como_vencidas(self):
        self.envejecer("SIGSAT-0002", 100)                       # 12 h de plazo
        self.assertEqual([s["folio"] for s in datos.solicitudes_todas(self.admin, solo_vencidas=True)], ["SIGSAT-0002"])
        # una vencida se puede reasignar
        self.assertEqual(datos.asignar_solicitud("SIGSAT-0002", self.admin, self.gabriel["id"]), "ok")


class PruebasCargaDeTrabajo(Base):
    def test_carga_de_los_datos_de_ejemplo(self):
        carga = {c["agente"]: c for c in datos.carga_trabajo()}
        self.assertEqual(set(carga), {"Sebastián Estrada", "Daniel López", "Zyanya Arriaga", "Gabriel Santiago", "Jesús Montes"})
        sebas = carga["Sebastián Estrada"]
        self.assertEqual((sebas["abiertas"], sebas["en_proceso"], sebas["finalizadas"], sebas["vencidas"]), (1, 1, 1, 0))
        self.assertEqual(sebas["tiempo_promedio_h"], 48.0)
        self.assertEqual(carga["Jesús Montes"]["abiertas"], 0)
        daniel = carga["Daniel López"]
        self.assertEqual((daniel["visualizadas"], daniel["abiertas"]), (1, 1))
        zyanya = carga["Zyanya Arriaga"]
        self.assertEqual((zyanya["abiertas"], zyanya["finalizadas"]), (0, 1), "una «Finalizado» ya no es trabajo abierto")

    def test_la_carga_cambia_al_asignar_y_al_finalizar(self):
        datos.asignar_solicitud("SIGSAT-0003", self.admin, self.zyanya["id"])
        datos.asignar_solicitud("SIGSAT-0006", self.admin, self.zyanya["id"])
        carga = {c["agente"]: c for c in datos.carga_trabajo()}
        self.assertEqual(carga["Zyanya Arriaga"]["abiertas"], 2)
        self.assertEqual(carga["Zyanya Arriaga"]["sin_visualizar"], 2)
        datos.registrar_visualizacion("SIGSAT-0003", self.zyanya)
        datos.actualizar_por_tecnico("SIGSAT-0003", self.zyanya, "Finalizado", "Listo")
        carga = {c["agente"]: c for c in datos.carga_trabajo()}
        self.assertEqual((carga["Zyanya Arriaga"]["abiertas"], carga["Zyanya Arriaga"]["finalizadas"]), (1, 2))

    def test_ordenada_de_mayor_a_menor_carga_y_sin_tecnicos_inactivos(self):
        carga = datos.carga_trabajo()
        self.assertEqual(carga[0]["abiertas"], max(c["abiertas"] for c in carga))
        self.assertEqual([c["abiertas"] for c in carga], sorted((c["abiertas"] for c in carga), reverse=True))
        datos.actualizar_usuario(self.zyanya["id"], "Zyanya Arriaga", "zarriaga", "", "Técnico", None,
                                 "zarriagai2100@alumno.ipn.mx", activo=False)
        self.assertNotIn("Zyanya Arriaga", [c["agente"] for c in datos.carga_trabajo()])


if __name__ == "__main__":
    unittest.main()
