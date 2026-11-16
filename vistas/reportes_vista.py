from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QAbstractItemView, QCheckBox, QDateEdit, QPushButton, QMessageBox, QFileDialog, QGridLayout
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor

import datos
import reportes
from permisos import ROL_TECNICO
from estilos import TONO_ESTADO, TONO_PRIORIDAD, color_texto


class VistaAnaliticaReportes(QWidget):
    """Análisis de solicitudes y reportes filtrables (RF-24) con exportación a Excel y PDF (RF-25). La tabla, el Excel y el PDF
    salen del mismo reporte, así siempre coinciden."""

    COLUMNAS = [("Folio", "folio"), ("Tipo", "tipo"), ("Área", "area"), ("Prioridad", "prioridad"), ("Estatus", "estado"),
                ("Solicitante", "solicitante"), ("Técnico", "agente"), ("Creada", "creada"), ("Plazo", "plazo"),
                ("Horas", "horas")]

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self.reporte = None
        self._construir_ui()
        self.generar()

    # ------------------------------------------------------------------ UI
    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(10)

        titulo = QLabel("Análisis y exportación")
        titulo.setObjectName("tituloVista")
        subtitulo = QLabel("Filtra las solicitudes, revisa el resumen y expórtalo a Excel o PDF.")
        subtitulo.setObjectName("subtituloVista")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(12)
        rejilla.setVerticalSpacing(6)

        self.chk_desde = QCheckBox("Desde")
        self.date_desde = QDateEdit(QDate.currentDate().addMonths(-1))
        self.chk_hasta = QCheckBox("Hasta")
        self.date_hasta = QDateEdit(QDate.currentDate())
        for chk, fecha in ((self.chk_desde, self.date_desde), (self.chk_hasta, self.date_hasta)):
            fecha.setCalendarPopup(True)
            fecha.setDisplayFormat("yyyy-MM-dd")
            fecha.setEnabled(False)
            chk.toggled.connect(fecha.setEnabled)

        def combo(primero, valores):
            c = QComboBox()
            c.addItem(primero, "")
            for v in valores:
                c.addItem(v, v)
            return c

        self.combo_area = combo("Todas las áreas", [])
        self.combo_tipo = combo("Todos los tipos", [])
        self.combo_estado = combo("Todos los estatus", datos.ESTADOS)
        self.combo_prioridad = combo("Todas las prioridades", reversed(datos.PRIORIDADES))
        self.combo_agente = QComboBox()
        self._recargar_opciones()
        self.chk_vencidas = QCheckBox("Solo vencidas")

        rejilla.addWidget(self.chk_desde, 0, 0)
        rejilla.addWidget(self.date_desde, 0, 1)
        rejilla.addWidget(self.chk_hasta, 0, 2)
        rejilla.addWidget(self.date_hasta, 0, 3)
        rejilla.addWidget(self.combo_area, 0, 4)
        rejilla.addWidget(self.combo_tipo, 0, 5)
        rejilla.addWidget(self.combo_estado, 1, 0, 1, 2)
        rejilla.addWidget(self.combo_prioridad, 1, 2, 1, 2)
        rejilla.addWidget(self.combo_agente, 1, 4)
        rejilla.addWidget(self.chk_vencidas, 1, 5)
        layout.addLayout(rejilla)

        barra = QHBoxLayout()
        self.btn_generar = QPushButton("Generar reporte")
        self.btn_generar.setObjectName("botonPrimario")
        self.btn_generar.clicked.connect(self.generar)
        self.btn_limpiar = QPushButton("Limpiar filtros")
        self.btn_limpiar.setObjectName("botonSecundario")
        self.btn_limpiar.clicked.connect(self.limpiar_filtros)
        self.btn_excel = QPushButton("Exportar a Excel")
        self.btn_excel.setObjectName("botonSecundario")
        self.btn_excel.clicked.connect(lambda: self.exportar("excel"))
        self.btn_pdf = QPushButton("Exportar a PDF")
        self.btn_pdf.setObjectName("botonSecundario")
        self.btn_pdf.clicked.connect(lambda: self.exportar("pdf"))
        barra.addWidget(self.btn_generar)
        barra.addWidget(self.btn_limpiar)
        barra.addStretch()
        barra.addWidget(self.btn_excel)
        barra.addWidget(self.btn_pdf)
        layout.addLayout(barra)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorLogin")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setStyleSheet("color:#33414F; font-weight:600; padding:4px 0;")
        layout.addWidget(self.lbl_resumen)

        self.tabla = QTableWidget(0, len(self.COLUMNAS))
        self.tabla.setHorizontalHeaderLabels([c[0] for c in self.COLUMNAS])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.tabla)

        self.lbl_vacio = QLabel("No hay solicitudes con esos filtros.")
        self.lbl_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_vacio.setStyleSheet("color:#64748B; padding:24px;")
        self.lbl_vacio.hide()
        layout.addWidget(self.lbl_vacio)

    # ------------------------------------------------------------- filtros
    def _recargar_opciones(self):
        """Llena (o vuelve a llenar) las listas de áreas, tipos y agentes conservando lo que estaba elegido,
        porque el administrador puede haber creado o renombrado catálogos desde la última vez."""
        def llenar(combo, primero, items):
            actual = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(primero, "" if combo is not self.combo_agente else None)
            for texto, valor in items:
                combo.addItem(texto, valor)
            indice = combo.findData(actual)
            combo.setCurrentIndex(max(indice, 0))
            combo.blockSignals(False)
        llenar(self.combo_area, "Todas las áreas", [(a["nombre"], a["nombre"]) for a in datos.areas_todas()])
        llenar(self.combo_tipo, "Todos los tipos", [(t["nombre"], t["nombre"]) for t in datos.tipos_todos()])
        llenar(self.combo_agente, "Todos los técnicos", [(u["nombre"], u["id"]) for u in datos.usuarios_por_rol(ROL_TECNICO)])

    def _filtros(self) -> dict:
        return {
            "desde": self.date_desde.date().toPython() if self.chk_desde.isChecked() else None,
            "hasta": self.date_hasta.date().toPython() if self.chk_hasta.isChecked() else None,
            "area": self.combo_area.currentData(), "tipo": self.combo_tipo.currentData(),
            "estado": self.combo_estado.currentData(), "prioridad": self.combo_prioridad.currentData(),
            "agente_id": self.combo_agente.currentData(), "solo_vencidas": self.chk_vencidas.isChecked(),
        }

    def limpiar_filtros(self):
        for chk in (self.chk_desde, self.chk_hasta, self.chk_vencidas):
            chk.setChecked(False)
        for c in (self.combo_area, self.combo_tipo, self.combo_estado, self.combo_prioridad, self.combo_agente):
            c.setCurrentIndex(0)
        self.generar()

    def actualizar(self):
        self._recargar_opciones()
        self.generar()

    def generar(self):
        try:
            self.reporte = reportes.generar(self.usuario, **self._filtros())
        except ValueError as error:                       # p. ej. fecha inicial posterior a la final
            self.lbl_error.setText(str(error))
            self.lbl_error.show()
            return
        self.lbl_error.hide()
        r = self.reporte["resumen"]
        partes = [f"{r['total']} solicitudes", f"{r['finalizadas']} finalizadas", f"{r['vencidas']} vencidas",
                  f"tiempo promedio {reportes._fmt_num(r['tiempo_promedio_h'], ' h')}",
                  f"efectividad en tiempo {reportes._fmt_num(r['efectividad_pct'], ' %')}"]
        self.lbl_resumen.setText("  ·  ".join(partes))

        filas = self.reporte["filas"]
        self.tabla.setRowCount(len(filas))
        for i, f in enumerate(filas):
            for j, (_enc, clave) in enumerate(self.COLUMNAS):
                valor = f[clave]
                item = QTableWidgetItem("—" if valor in (None, "") else str(valor))
                if clave == "prioridad":
                    item.setForeground(QColor(color_texto(TONO_PRIORIDAD[valor])))
                elif clave == "estado":
                    item.setForeground(QColor(color_texto(TONO_ESTADO[valor])))
                elif clave == "plazo" and valor in ("Vencida", "Fuera de plazo"):
                    item.setForeground(QColor("#B91C1C"))
                self.tabla.setItem(i, j, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.lbl_vacio.setVisible(not filas)
        self.btn_excel.setEnabled(True)
        self.btn_pdf.setEnabled(True)

    # ---------------------------------------------------------- exportación
    def exportar(self, formato: str, ruta: str = None):
        """formato: 'excel' | 'pdf'. Sin `ruta` pregunta dónde guardar. Devuelve la ruta o None."""
        if self.reporte is None:
            self.generar()
        if self.reporte is None:
            return None
        extension, filtro = (".xlsx", "Libro de Excel (*.xlsx)") if formato == "excel" else (".pdf", "Documento PDF (*.pdf)")
        if ruta is None:
            sugerido = f"reporte_sigsat_{datetime.now():%Y%m%d_%H%M}{extension}"
            ruta, _f = QFileDialog.getSaveFileName(self, "Guardar reporte", sugerido, filtro)
            if not ruta:
                return None
        if not ruta.lower().endswith(extension):
            ruta += extension
        try:
            (reportes.exportar_excel if formato == "excel" else reportes.exportar_pdf)(self.reporte, ruta)
        except reportes.DependenciaFaltante as error:
            QMessageBox.warning(self, "Falta una biblioteca", str(error))
            return None
        except OSError as error:                           # archivo abierto en Excel, sin permiso, disco lleno…
            QMessageBox.warning(self, "No se pudo guardar",
                                f"No se pudo guardar el archivo (¿está abierto en otro programa?):\n{error.strerror or error}")
            return None
        QMessageBox.information(self, "Reporte exportado", f"El reporte se guardó en:\n{ruta}")
        return ruta
