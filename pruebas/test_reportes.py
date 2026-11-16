"""RF-24 (reportes filtrables) y RF-25 (exportación a Excel y PDF)."""

import os
import tempfile
import unittest
from datetime import date, timedelta

from pruebas.base import Base
import datos
import reportes


class PruebasFiltros(Base):
    def folios(self, **filtros):
        return sorted(f["folio"] for f in reportes.generar(self.admin, **filtros)["filas"])

    def test_sin_filtros_trae_todo(self):
        r = reportes.generar(self.admin)
        self.assertEqual(r["resumen"]["total"], 7)
        self.assertEqual(r["etiquetas_filtros"], [])
        self.assertEqual(r["generado_por"], "Dirección General")

    def test_solo_el_administrador_genera_reportes(self):
        for actor in (self.ana, self.sebastian):
            with self.subTest(rol=actor["rol"]), self.assertRaises(PermissionError):
                reportes.generar(actor)

    def test_cada_filtro_por_separado(self):
        self.assertEqual(self.folios(area="Contabilidad"), ["SIGSAT-0001", "SIGSAT-0003", "SIGSAT-0005"])
        self.assertEqual(self.folios(tipo="Mantenimiento preventivo"), ["SIGSAT-0005"])
        self.assertEqual(self.folios(estado="Finalizado"), ["SIGSAT-0001", "SIGSAT-0005"])
        self.assertEqual(self.folios(estado="Visualizado"), ["SIGSAT-0004"])
        self.assertEqual(self.folios(prioridad="Alta"), ["SIGSAT-0002"])
        self.assertEqual(self.folios(agente_id=self.zyanya["id"]), ["SIGSAT-0005"])
        self.assertEqual(self.folios(solo_vencidas=True), [])
        self.envejecer("SIGSAT-0002", 100)
        self.assertEqual(self.folios(solo_vencidas=True), ["SIGSAT-0002"])

    def test_filtros_combinados(self):
        self.assertEqual(self.folios(area="Contabilidad", estado="Finalizado"), ["SIGSAT-0001", "SIGSAT-0005"])
        self.assertEqual(self.folios(area="Contabilidad", estado="Finalizado", prioridad="Media"), ["SIGSAT-0001"])
        self.assertEqual(self.folios(area="Contabilidad", estado="Finalizado", prioridad="Alta"), [])

    def test_rango_de_fechas_incluye_ambos_extremos(self):
        hoy = date.today()
        # SIGSAT-0001 se creó hace 6 días, 0003 hace 1, 0004 hace 3, 0005 hace 12, 0006 hoy, 0002 hace 10 horas y 0007 hace 5
        self.assertEqual(self.folios(desde=hoy - timedelta(days=2)), ["SIGSAT-0002", "SIGSAT-0003", "SIGSAT-0006", "SIGSAT-0007"])
        self.assertEqual(self.folios(hasta=hoy - timedelta(days=6)), ["SIGSAT-0001", "SIGSAT-0005"])
        self.assertEqual(self.folios(desde=hoy - timedelta(days=6), hasta=hoy - timedelta(days=6)), ["SIGSAT-0001"])
        self.assertEqual(self.folios(desde=hoy + timedelta(days=1)), [])
        self.assertEqual(len(self.folios(desde=hoy - timedelta(days=60), hasta=hoy)), 7)

    def test_filtros_invalidos(self):
        with self.assertRaisesRegex(ValueError, "fecha inicial"):
            reportes.generar(self.admin, desde=date.today(), hasta=date.today() - timedelta(days=1))
        with self.assertRaisesRegex(ValueError, "estatus"):
            reportes.generar(self.admin, estado="Inventado")
        with self.assertRaisesRegex(ValueError, "prioridad"):
            reportes.generar(self.admin, prioridad="Urgente")

    def test_las_etiquetas_describen_los_filtros(self):
        r = reportes.generar(self.admin, desde=date(2026, 1, 5), area="Contabilidad", agente_id=self.sebastian["id"], solo_vencidas=True)
        self.assertEqual(r["etiquetas_filtros"], ["Desde: 2026-01-05", "Área: Contabilidad", "Técnico: Sebastián Estrada", "Solo solicitudes vencidas"])


class PruebasResumen(Base):
    def test_resumen_de_los_datos_de_ejemplo(self):
        r = reportes.generar(self.admin)["resumen"]
        self.assertEqual((r["total"], r["finalizadas"], r["vencidas"]), (7, 2, 0))
        self.assertEqual(r["tiempo_promedio_h"], 48.0)
        self.assertEqual(r["efectividad_pct"], 100)
        self.assertEqual(r["satisfaccion"], 5.0)                      # solo la 0001 está calificada
        self.assertEqual(r["por_estado"], {"Sin visualizar": 3, "Visualizado": 1, "En proceso": 1, "Finalizado": 2})
        self.assertEqual(r["por_prioridad"], {"Alta": 1, "Media": 2, "Baja": 4})
        self.assertEqual(r["por_area"]["Contabilidad"], {"total": 3, "finalizadas": 2, "vencidas": 0, "promedio_h": 48.0})
        self.assertEqual(r["por_agente"]["Sin asignar"]["total"], 2)

    def test_el_resumen_coincide_con_los_indicadores_del_panel(self):
        r, k = reportes.generar(self.admin)["resumen"], datos.calcular_kpis()
        self.assertEqual(r["total"], k["total"])
        self.assertEqual(r["vencidas"], k["vencidas"])
        self.assertEqual(r["tiempo_promedio_h"], k["tiempo_promedio_h"])
        self.assertEqual(r["por_estado"], k["por_estado"])

    def test_reporte_vacio(self):
        r = reportes.generar(self.admin, area="Compras", estado="Finalizado")
        self.assertEqual(r["resumen"]["total"], 0)
        self.assertIsNone(r["resumen"]["tiempo_promedio_h"])
        self.assertIsNone(r["resumen"]["efectividad_pct"])

    def test_las_filas_traen_horas_y_plazo(self):
        filas = {f["folio"]: f for f in reportes.generar(self.admin)["filas"]}
        self.assertEqual(filas["SIGSAT-0001"]["horas"], 48.0)
        self.assertEqual(filas["SIGSAT-0001"]["plazo"], "Cumplido")
        self.assertIsNone(filas["SIGSAT-0002"]["horas"])
        self.assertEqual(filas["SIGSAT-0002"]["plazo"], "Vigente")
        self.assertEqual(filas["SIGSAT-0004"]["plazo"], "Vigente")
        self.assertEqual(filas["SIGSAT-0005"]["plazo"], "Cumplido")                # finalizada a tiempo, aún sin calificar
        self.assertEqual(filas["SIGSAT-0002"]["finalizacion"], "")
        self.assertNotEqual(filas["SIGSAT-0001"]["finalizacion"], "")


class PruebasExportacion(Base):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def ruta(self, nombre):
        return os.path.join(self.dir.name, nombre)

    def leer(self, nombre):
        with open(self.ruta(nombre), "rb") as f:
            return f.read()

    def test_excel_tiene_resumen_y_detalle_con_los_mismos_datos(self):
        from openpyxl import load_workbook
        r = reportes.generar(self.admin, area="Contabilidad")
        reportes.exportar_excel(r, self.ruta("r.xlsx"))
        wb = load_workbook(self.ruta("r.xlsx"))
        self.assertEqual(wb.sheetnames, ["Resumen", "Solicitudes"])
        det = wb["Solicitudes"]
        self.assertEqual([c.value for c in det[1]][:5], ["Folio", "Tipo", "Área", "Prioridad", "Estatus"])
        self.assertEqual(sorted(det.cell(row=i, column=1).value for i in range(2, det.max_row + 1)), ["SIGSAT-0001", "SIGSAT-0003", "SIGSAT-0005"])
        self.assertEqual(det.freeze_panes, "B2")
        self.assertTrue(det.auto_filter.ref.startswith("A1:"))
        texto = " ".join(str(c.value) for fila in wb["Resumen"].iter_rows() for c in fila if c.value is not None)
        self.assertIn("Área: Contabilidad", texto)
        self.assertIn("Solicitudes", texto)

    def test_excel_no_interpreta_el_texto_del_usuario_como_formula(self):
        from openpyxl import load_workbook
        self.nueva(desc='=HYPERLINK("http://malo.example","clic")')
        self.nueva(desc="@SUM(1+1)")
        self.nueva(desc="+cmd|' /C calc'!A0")
        reportes.exportar_excel(reportes.generar(self.admin), self.ruta("r.xlsx"))
        det = load_workbook(self.ruta("r.xlsx"))["Solicitudes"]
        col_desc = [c.value for c in det[1]].index("Descripción") + 1
        for i in range(2, det.max_row + 1):
            celda = det.cell(row=i, column=col_desc)
            self.assertEqual(celda.data_type, "s", f"fila {i}: «{celda.value}» no debe ser fórmula")

    def test_el_pdf_es_valido_y_tiene_paginas(self):
        r = reportes.generar(self.admin)
        reportes.exportar_pdf(r, self.ruta("r.pdf"))
        datos_pdf = self.leer("r.pdf")
        self.assertTrue(datos_pdf.startswith(b"%PDF-"))
        self.assertGreater(len(datos_pdf), 2000)
        self.assertIn(b"%%EOF", datos_pdf[-64:])

    def test_el_pdf_soporta_texto_raro_sin_romperse(self):
        self.nueva(desc="<b>negrita</b> & <script>alert(1)</script> ñandú ≥ 😀 日本語 " + "largo " * 80)
        reportes.exportar_pdf(reportes.generar(self.admin), self.ruta("r.pdf"))
        self.assertTrue(self.leer("r.pdf").startswith(b"%PDF-"))

    def test_pdf_con_muchas_solicitudes_ocupa_varias_paginas(self):
        for i in range(120):
            self.nueva(desc=f"Solicitud número {i}")
        reportes.exportar_pdf(reportes.generar(self.admin), self.ruta("r.pdf"))
        contenido = self.leer("r.pdf")
        self.assertGreater(contenido.count(b"/Type /Page\n") + contenido.count(b"/Type /Page "), 3)

    def test_reporte_vacio_se_exporta(self):
        r = reportes.generar(self.admin, area="Compras", estado="Finalizado")
        reportes.exportar_excel(r, self.ruta("v.xlsx"))
        reportes.exportar_pdf(r, self.ruta("v.pdf"))
        self.assertTrue(os.path.getsize(self.ruta("v.xlsx")) > 0 and os.path.getsize(self.ruta("v.pdf")) > 0)

    def test_si_falta_la_biblioteca_se_explica_como_instalarla(self):
        import builtins
        from unittest import mock
        r = reportes.generar(self.admin)
        original = builtins.__import__

        def sin(prefijo):
            def falso(nombre, *a, **k):
                if nombre == prefijo or nombre.startswith(prefijo + "."):
                    raise ImportError(f"simulado: no está instalado {prefijo}")
                return original(nombre, *a, **k)
            return falso

        with mock.patch("builtins.__import__", sin("openpyxl")):
            with self.assertRaisesRegex(reportes.DependenciaFaltante, "pip install openpyxl"):
                reportes.exportar_excel(r, self.ruta("x.xlsx"))
        with mock.patch("builtins.__import__", sin("reportlab")):
            with self.assertRaisesRegex(reportes.DependenciaFaltante, "pip install reportlab"):
                reportes.exportar_pdf(r, self.ruta("x.pdf"))


if __name__ == "__main__":
    unittest.main()
