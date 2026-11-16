"""Pantallas propias del modelo de 3 roles: bandeja de reportes con filtros, bitácora general,
panel de indicadores con pestañas y registro de cuenta con sucursal."""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import datos
from estilos import QSS_APP, paleta_clara
from pruebas.base import cuenta
from vistas.bandeja_reportes import VistaBandejaReportes
from vistas.dashboard_admin import VistaDashboardAdmin
from widgets.dialogo_registro import DialogoRegistro

APP = QApplication.instance() or QApplication([])
APP.setStyle("Fusion")
APP.setPalette(paleta_clara())
APP.setStyleSheet(QSS_APP)


class PruebasRolesUI(unittest.TestCase):
    def setUp(self):
        datos.reiniciar()
        self.admin = cuenta("direccion")

    def test_filtros_de_la_bandeja_del_administrador(self):
        v = VistaBandejaReportes(self.admin)
        self.assertEqual(v.tabla.rowCount(), 7)
        v.combo_prioridad.setCurrentIndex(v.combo_prioridad.findData("Alta"))
        v.consultar()
        self.assertTrue(all(v.tabla.item(i, 4).text() == "Alta" for i in range(v.tabla.rowCount())))
        v.limpiar_filtros()
        v.combo_agente.setCurrentIndex(v.combo_agente.findData(cuenta("sestrada")["id"]))
        v.consultar()
        self.assertEqual(v.tabla.rowCount(), 2)
        v.limpiar_filtros()
        v.combo_area.setCurrentIndex(v.combo_area.findData("Ventas"))
        v.consultar()
        self.assertEqual({v.tabla.item(i, 2).text() for i in range(v.tabla.rowCount())}, {"Ventas"})
        v.combo_estado.setCurrentText("Visualizado")
        v.combo_area.setCurrentIndex(0)
        v.consultar()
        self.assertEqual(v.tabla.rowCount(), 1)

    def test_la_bandeja_muestra_primero_lo_abierto_y_lo_urgente(self):
        v = VistaBandejaReportes(self.admin)
        estados = [v.tabla.item(i, 5).text() for i in range(v.tabla.rowCount())]
        self.assertEqual(estados[-2:], ["Finalizado", "Finalizado"])

    def test_el_tecnico_solo_ve_los_suyos_y_no_tiene_filtro_de_tecnico(self):
        v = VistaBandejaReportes(cuenta("dlopez"))
        self.assertEqual(v.tabla.rowCount(), 1)
        self.assertEqual(v.tabla.item(0, 0).text(), "SIGSAT-0004")
        self.assertTrue(v.combo_agente.isHidden())
        with self.assertRaises(PermissionError):
            VistaBandejaReportes(cuenta("areyes"))

    def test_reportes_es_una_sola_vista_con_el_historial_dentro(self):
        v = VistaBandejaReportes(self.admin)
        self.assertEqual(v.tabla.rowCount(), 7)
        self.assertFalse(hasattr(v, "pestanas"), "ya no hay pestañas Reportes/Eventos")
        v.tabla.selectRow(0)
        self.assertGreater(v.tabla_historial.rowCount(), 0)
        v.actualizar()
        v.grab()

    def test_panel_de_indicadores_tiene_dos_pestanas(self):
        v = VistaDashboardAdmin(self.admin)
        self.assertEqual([v.pestanas.tabText(i) for i in range(2)], ["Indicadores", "Análisis y exportación"])
        v.actualizar()
        v.grab()

    def test_registro_de_cuenta_pide_area_y_sucursal(self):
        d = DialogoRegistro()
        d.txt_nombre.setText("Laura Méndez Ortiz")
        d.txt_correo.setText("laura.mendez@ipn.mx")
        d.txt_usuario.setText("lmendez")
        d.txt_contrasena.setText("Clave-12345")
        d.txt_confirmar.setText("Clave-12345")
        d.combo_area.setCurrentIndex(0)
        d.combo_sucursal.setCurrentIndex(0)
        d._crear()
        nueva = cuenta("lmendez")
        self.assertEqual(nueva["rol"], "Representante de Área")
        self.assertTrue(nueva["area"] and nueva["sucursal"])


if __name__ == "__main__":
    unittest.main()
