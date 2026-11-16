from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QAbstractItemView, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import datos
from estilos import TONO_ESTADO, TONO_PRIORIDAD, color_texto
from widgets.detalle_solicitud import DialogoDetalleSolicitud
from widgets.utiles import item_vence


class VistaSolicitudesAdmin(QWidget):
    """Todas las solicitudes del sistema. La prioridad sale del tiempo estimado de solución (menos tiempo = más
    prioridad) y las que no tienen técnico aparecen primero. Desde el detalle el Administrador las asigna o
    reasigna (RF-09: distribución de incidentes)."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(10)

        titulo = QLabel("Solicitudes")
        titulo.setObjectName("tituloVista")
        subtitulo = QLabel("Supervisa todas las solicitudes y distribuye las que aún no tienen técnico.")
        subtitulo.setObjectName("subtituloVista")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        filtros = QHBoxLayout()
        self.combo_area = QComboBox()
        self._recargar_areas()
        self.combo_estado = QComboBox()
        self.combo_estado.addItem("Todos los estatus", "")
        for e in datos.ESTADOS:
            self.combo_estado.addItem(e, e)
        self.chk_sin_asignar = QCheckBox("Solo sin asignar")
        self.chk_vencidas = QCheckBox("Solo vencidas")
        for w in (self.combo_area, self.combo_estado):
            w.currentIndexChanged.connect(lambda *_: self.actualizar())
        for w in (self.chk_sin_asignar, self.chk_vencidas):
            w.toggled.connect(lambda *_: self.actualizar())
        filtros.addWidget(self.combo_area)
        filtros.addWidget(self.combo_estado)
        filtros.addWidget(self.chk_sin_asignar)
        filtros.addWidget(self.chk_vencidas)
        filtros.addStretch()
        layout.addLayout(filtros)

        self.tabla = QTableWidget(0, 8)
        self.tabla.setHorizontalHeaderLabels(["Folio", "Tipo", "Área", "Solicitante", "Prioridad", "Estatus", "Técnico", "Vence"])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.cellDoubleClicked.connect(self._abrir_detalle)
        layout.addWidget(self.tabla)

        self.lbl_vacio = QLabel("")
        self.lbl_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_vacio.setStyleSheet("color:#64748B; padding:24px;")
        layout.addWidget(self.lbl_vacio)

        ayuda = QLabel("Doble clic en una fila para ver el detalle y asignarla a un técnico (o reasignarla).")
        ayuda.setStyleSheet("color:#94A3B8; font-size:11px;")
        layout.addWidget(ayuda)

    def _recargar_areas(self):
        actual = self.combo_area.currentData()
        self.combo_area.blockSignals(True)
        self.combo_area.clear()
        self.combo_area.addItem("Todas las áreas", "")
        for a in datos.areas_todas():
            self.combo_area.addItem(a["nombre"], a["nombre"])
        self.combo_area.setCurrentIndex(max(self.combo_area.findData(actual), 0))
        self.combo_area.blockSignals(False)

    def actualizar(self):
        self._recargar_areas()
        registros = datos.solicitudes_todas(
            self.usuario, area=self.combo_area.currentData(), estado=self.combo_estado.currentData(),
            sin_asignar=self.chk_sin_asignar.isChecked(), solo_vencidas=self.chk_vencidas.isChecked())

        orden = {p: i for i, p in enumerate(reversed(datos.PRIORIDADES))}      # Alta, Media, Baja
        registros = sorted(registros, key=lambda r: (r["asignada"], r["finalizada"], orden[r["prioridad"]]))
        self.tabla.setRowCount(len(registros))
        for fila, s in enumerate(registros):
            self.tabla.setItem(fila, 0, QTableWidgetItem(s["folio"]))
            self.tabla.setItem(fila, 1, QTableWidgetItem(s["tipo"]))
            self.tabla.setItem(fila, 2, QTableWidgetItem(s["area"] or "—"))
            self.tabla.setItem(fila, 3, QTableWidgetItem(s["solicitante"]))
            prioridad = QTableWidgetItem(f"{s['prioridad']} ({s['sla_horas']} h)")
            prioridad.setForeground(QColor(color_texto(TONO_PRIORIDAD[s["prioridad"]])))
            self.tabla.setItem(fila, 4, prioridad)
            estado = QTableWidgetItem(s["estado"])
            estado.setForeground(QColor(color_texto(TONO_ESTADO[s["estado"]])))
            self.tabla.setItem(fila, 5, estado)
            tecnico = QTableWidgetItem(s["agente_asignado"] or "Sin asignar")
            if not s["asignada"]:
                tecnico.setForeground(QColor("#B45309"))
            self.tabla.setItem(fila, 6, tecnico)
            self.tabla.setItem(fila, 7, item_vence(s))
            self.tabla.item(fila, 0).setData(Qt.UserRole, s["folio"])

        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        if registros:
            self.lbl_vacio.hide()
        else:
            self.lbl_vacio.setText("No hay solicitudes con esos filtros.")
            self.lbl_vacio.show()

    def _abrir_detalle(self, fila, _col):
        folio = self.tabla.item(fila, 0).data(Qt.UserRole)
        DialogoDetalleSolicitud(folio, self.usuario, al_guardar=self.actualizar, parent=self).exec()
