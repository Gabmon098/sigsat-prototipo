from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QAbstractItemView, QCheckBox, QDateEdit, QPushButton, QGridLayout, QFrame
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor

import datos
from estilos import TONO_ESTADO, TONO_PRIORIDAD, color_texto
from permisos import puede, ROL_TECNICO
from widgets.detalle_solicitud import DialogoDetalleSolicitud
from widgets.utiles import item_vence


class VistaBandejaReportes(QWidget):
    """Reportes: cada solicitud con el avance que informa el técnico (Sin visualizar, Visualizado, En proceso
    y Finalizado), con filtros por fecha, estatus, prioridad, área y técnico. Es la ÚNICA vista de seguimiento:
    la antigua «Bitácora» se fundió aquí. Al elegir un reporte, abajo aparece su **historial de atención**
    (qué pasó, cuándo y quién lo hizo), que es de solo lectura. Es «Reportes» del Administrador y «Mis
    reportes» del Técnico (que solo ve los suyos)."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._ve_todos = puede(usuario, "reportes.ver")
        self._construir_ui()
        self.actualizar()

    # ------------------------------------------------------------------ UI
    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(10)

        if self._ve_todos:
            texto_titulo = "Reportes"
            texto_sub = "Avance que informa cada técnico en todas las solicitudes, incluidas las finalizadas, y su historial de atención."
        else:
            texto_titulo = "Mis reportes"
            texto_sub = "Las solicitudes que el administrador te asignó. Ábrelas para atenderlas; las finalizadas quedan aquí."
        titulo = QLabel(texto_titulo)
        titulo.setObjectName("tituloVista")
        subtitulo = QLabel(texto_sub)
        subtitulo.setObjectName("subtituloVista")
        subtitulo.setWordWrap(True)
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

        self.combo_estado = QComboBox()
        self.combo_estado.addItem("Todos los estatus", "")
        for e in datos.ESTADOS:                                   # incluye «Finalizado»
            self.combo_estado.addItem(e, e)
        self.combo_prioridad = QComboBox()
        self.combo_prioridad.addItem("Todas las prioridades", "")
        for p in reversed(datos.PRIORIDADES):
            self.combo_prioridad.addItem(p, p)
        self.combo_area = QComboBox()
        self.combo_agente = QComboBox()
        self._recargar_opciones()
        self.chk_vencidas = QCheckBox("Solo vencidos")

        rejilla.addWidget(self.chk_desde, 0, 0)
        rejilla.addWidget(self.date_desde, 0, 1)
        rejilla.addWidget(self.chk_hasta, 0, 2)
        rejilla.addWidget(self.date_hasta, 0, 3)
        rejilla.addWidget(self.combo_estado, 1, 0, 1, 2)
        rejilla.addWidget(self.combo_prioridad, 1, 2, 1, 2)
        rejilla.addWidget(self.combo_area, 0, 4)
        rejilla.addWidget(self.combo_agente, 1, 4)
        rejilla.addWidget(self.chk_vencidas, 0, 5)
        self.combo_agente.setVisible(self._ve_todos)       # un técnico solo ve los suyos: no hay a quién filtrar
        layout.addLayout(rejilla)

        barra = QHBoxLayout()
        self.btn_buscar = QPushButton("Buscar")
        self.btn_buscar.setObjectName("botonPrimario")
        self.btn_buscar.clicked.connect(self.consultar)
        self.btn_limpiar = QPushButton("Limpiar filtros")
        self.btn_limpiar.setObjectName("botonSecundario")
        self.btn_limpiar.clicked.connect(self.limpiar_filtros)
        barra.addWidget(self.btn_buscar)
        barra.addWidget(self.btn_limpiar)
        barra.addStretch()
        layout.addLayout(barra)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorLogin")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        self.lbl_integridad = QLabel("")
        self.lbl_integridad.setWordWrap(True)
        self.lbl_integridad.setVisible(self._ve_todos)
        layout.addWidget(self.lbl_integridad)

        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setStyleSheet("color:#33414F; font-weight:600; padding:2px 0;")
        layout.addWidget(self.lbl_resumen)

        self.tabla = QTableWidget(0, 9)
        self.tabla.setHorizontalHeaderLabels(
            ["Folio", "Tipo", "Área", "Sucursal", "Prioridad", "Estatus", "Técnico", "Creada", "Vence"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setMinimumHeight(190)
        self.tabla.cellDoubleClicked.connect(self._abrir_detalle)
        self.tabla.itemSelectionChanged.connect(self._mostrar_historial)
        layout.addWidget(self.tabla, 3)

        self.lbl_vacio = QLabel("")
        self.lbl_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_vacio.setStyleSheet("color:#64748B; padding:24px;")
        self.lbl_vacio.hide()
        layout.addWidget(self.lbl_vacio)

        ayuda = QLabel("Selecciona un reporte para ver su historial de atención. Doble clic para abrir el detalle"
                       + (" y atenderlo." if not self._ve_todos else "."))
        ayuda.setStyleSheet("color:#94A3B8; font-size:11px;")
        layout.addWidget(ayuda)

        # ---- Historial de atención del reporte seleccionado (antes «Bitácora»)
        panel = QFrame()
        panel.setObjectName("panelHistorial")
        panel.setStyleSheet("QFrame#panelHistorial { border-top:1px solid #E2E8F0; }")
        lay_h = QVBoxLayout(panel)
        lay_h.setContentsMargins(0, 8, 0, 0)
        lay_h.setSpacing(6)
        self.lbl_historial = QLabel("Historial de atención")
        self.lbl_historial.setStyleSheet("font-weight:700; font-size:14px;")
        lay_h.addWidget(self.lbl_historial)
        self.tabla_historial = QTableWidget(0, 3)
        self.tabla_historial.setHorizontalHeaderLabels(["Fecha y hora", "Autor", "Evento"])
        self.tabla_historial.verticalHeader().setVisible(False)
        self.tabla_historial.setEditTriggers(QAbstractItemView.NoEditTriggers)       # solo lectura
        self.tabla_historial.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_historial.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla_historial.horizontalHeader().setStretchLastSection(True)
        self.tabla_historial.setMinimumHeight(170)
        lay_h.addWidget(self.tabla_historial)
        self.lbl_historial_vacio = QLabel("Selecciona un reporte de la lista para ver su historial de atención.")
        self.lbl_historial_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_historial_vacio.setStyleSheet("color:#64748B; padding:14px;")
        lay_h.addWidget(self.lbl_historial_vacio)
        layout.addWidget(panel, 2)

    # ------------------------------------------------------------- filtros
    def _recargar_opciones(self):
        """Vuelve a llenar áreas y técnicos conservando la elección (el administrador pudo crear catálogos)."""
        def llenar(combo, primero, items, vacio):
            actual = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(primero, vacio)
            for texto, valor in items:
                combo.addItem(texto, valor)
            combo.setCurrentIndex(max(combo.findData(actual), 0))
            combo.blockSignals(False)
        llenar(self.combo_area, "Todas las áreas", [(a["nombre"], a["nombre"]) for a in datos.areas_todas()], "")
        llenar(self.combo_agente, "Todos los técnicos",
               [(u["nombre"], u["id"]) for u in datos.usuarios_por_rol(ROL_TECNICO)], None)

    def _filtros(self) -> dict:
        return {
            "desde": self.date_desde.date().toPython() if self.chk_desde.isChecked() else None,
            "hasta": self.date_hasta.date().toPython() if self.chk_hasta.isChecked() else None,
            "estado": self.combo_estado.currentData(), "prioridad": self.combo_prioridad.currentData(),
            "area": self.combo_area.currentData(),
            "agente_id": self.combo_agente.currentData() if self._ve_todos else None,
            "solo_vencidas": self.chk_vencidas.isChecked(), "incluir_finalizados": True,
        }

    def limpiar_filtros(self):
        for chk in (self.chk_desde, self.chk_hasta, self.chk_vencidas):
            chk.setChecked(False)
        for c in (self.combo_estado, self.combo_prioridad, self.combo_area, self.combo_agente):
            c.setCurrentIndex(0)
        self.consultar()

    def actualizar(self):
        self._recargar_opciones()
        self.consultar()

    def _estado_integridad(self):
        if not self._ve_todos:
            return
        problemas = datos.verificar_bitacora()
        if problemas:
            self.lbl_integridad.setText("⚠ Integridad: se detectaron alteraciones en el historial — " + problemas[0])
            self.lbl_integridad.setStyleSheet("background:#FBE1DE; color:#9B2A1F; border-radius:6px; padding:6px 10px; font-weight:600;")
        else:
            self.lbl_integridad.setText("✔ Integridad verificada: ningún evento del historial fue modificado, borrado ni reordenado.")
            self.lbl_integridad.setStyleSheet("color:#14603A; font-size:12px;")

    def folio_seleccionado(self):
        filas = self.tabla.selectionModel().selectedRows()
        item = self.tabla.item(filas[0].row(), 0) if filas else None
        return item.data(Qt.UserRole) if item else None

    def consultar(self):
        try:
            registros = datos.listar_reportes(self.usuario, **self._filtros())
        except ValueError as error:                       # p. ej. fecha inicial posterior a la final
            self.lbl_error.setText(str(error))
            self.lbl_error.show()
            return
        self.lbl_error.hide()
        self._estado_integridad()
        folio_previo = self.folio_seleccionado()
        orden = {p: i for i, p in enumerate(reversed(datos.PRIORIDADES))}      # Alta, Media, Baja
        registros = sorted(registros, key=lambda r: (r["finalizada"], orden[r["prioridad"]]))

        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(registros))
        for fila, s in enumerate(registros):
            valores = [s["folio"], s["tipo"], s["area"] or "—", s["sucursal"] or "—"]
            for col, v in enumerate(valores):
                self.tabla.setItem(fila, col, QTableWidgetItem(v))
            prioridad = QTableWidgetItem(s["prioridad"])
            prioridad.setForeground(QColor(color_texto(TONO_PRIORIDAD[s["prioridad"]])))
            self.tabla.setItem(fila, 4, prioridad)
            estado = QTableWidgetItem(s["estado"])
            estado.setForeground(QColor(color_texto(TONO_ESTADO[s["estado"]])))
            self.tabla.setItem(fila, 5, estado)
            tecnico = QTableWidgetItem(s["agente_asignado"] or "Sin asignar")
            if not s["asignada"]:
                tecnico.setForeground(QColor("#B45309"))
            self.tabla.setItem(fila, 6, tecnico)
            self.tabla.setItem(fila, 7, QTableWidgetItem(s["fecha_creacion"]))
            self.tabla.setItem(fila, 8, item_vence(s))
            self.tabla.item(fila, 0).setData(Qt.UserRole, s["folio"])

        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Si el reporte que estaba seleccionado sigue en la lista, se conserva la selección.
        self.tabla.clearSelection()
        for fila in range(self.tabla.rowCount()):
            if folio_previo and self.tabla.item(fila, 0).data(Qt.UserRole) == folio_previo:
                self.tabla.selectRow(fila)
                break
        self.tabla.blockSignals(False)
        self._mostrar_historial()

        finalizados = sum(1 for r in registros if r["finalizada"])
        self.lbl_resumen.setText(f"{len(registros)} reporte{'s' if len(registros) != 1 else ''}"
                                 + (f" · {finalizados} finalizado{'s' if finalizados != 1 else ''}" if finalizados else ""))
        if registros:
            self.lbl_vacio.hide()
        else:
            self.lbl_vacio.setText("No hay reportes con esos filtros." if self._hay_filtros()
                                   else ("Aún no hay reportes." if self._ve_todos else "No tienes reportes asignados."))
            self.lbl_vacio.show()

    def _hay_filtros(self) -> bool:
        f = self._filtros()
        return any(f[k] for k in ("desde", "hasta", "estado", "prioridad", "area", "solo_vencidas")) or f["agente_id"] is not None

    # -------------------------------------------------- historial de atención
    def _mostrar_historial(self):
        folio = self.folio_seleccionado()
        eventos = datos.historial_de_solicitud(self.usuario, folio) if folio else []
        self.lbl_historial.setText(f"Historial de atención — {folio}" if folio else "Historial de atención")
        self.tabla_historial.setRowCount(len(eventos))
        for i, e in enumerate(eventos):
            for j, v in enumerate((e["fecha"], e["autor"], e["evento"])):
                item = QTableWidgetItem(v)
                if j == 1 and e["autor_id"] is None:
                    item.setForeground(QColor("#64748B"))        # eventos automáticos del sistema
                self.tabla_historial.setItem(i, j, item)
        self.tabla_historial.resizeColumnsToContents()
        self.tabla_historial.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla_historial.setVisible(bool(folio))
        self.lbl_historial_vacio.setVisible(not folio)

    def _abrir_detalle(self, fila, _col):
        folio = self.tabla.item(fila, 0).data(Qt.UserRole)
        DialogoDetalleSolicitud(folio, self.usuario, al_guardar=self.actualizar, parent=self).exec()
