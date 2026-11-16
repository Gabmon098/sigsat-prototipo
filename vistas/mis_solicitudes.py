from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import datos
from estilos import TONO_ESTADO, TONO_PRIORIDAD, color_texto
from widgets.detalle_solicitud import DialogoDetalleSolicitud
from widgets.utiles import item_vence


class VistaMisSolicitudes(QWidget):
    """Tabla con las solicitudes del representante en sesión y el estatus que informa el técnico."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(10)

        cab = QHBoxLayout()
        col_titulos = QVBoxLayout()
        titulo = QLabel("Mis solicitudes")
        titulo.setObjectName("tituloVista")
        subtitulo = QLabel("Consulta el estatus y el historial de tus solicitudes.")
        subtitulo.setObjectName("subtituloVista")
        col_titulos.addWidget(titulo)
        col_titulos.addWidget(subtitulo)
        cab.addLayout(col_titulos)
        cab.addStretch()

        self.combo_filtro = QComboBox()
        self.combo_filtro.addItems(["Todos los estatus"] + datos.ESTADOS)
        self.combo_filtro.currentTextChanged.connect(lambda *_: self.actualizar())
        cab.addWidget(self.combo_filtro)
        layout.addLayout(cab)

        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(["Folio", "Tipo", "Prioridad", "Estatus", "Creada", "Fecha límite"])
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.cellDoubleClicked.connect(self._abrir_detalle)
        layout.addWidget(self.tabla)

        self.lbl_vacio = QLabel("")
        self.lbl_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_vacio.setStyleSheet("color:#64748B; padding:24px;")
        layout.addWidget(self.lbl_vacio)

        ayuda = QLabel("Doble clic en una fila para ver el detalle y la bitácora de seguimiento.")
        ayuda.setStyleSheet("color:#94A3B8; font-size:11px;")
        layout.addWidget(ayuda)

    def actualizar(self):
        filtro = self.combo_filtro.currentText()
        estado = "" if filtro == "Todos los estatus" else filtro
        registros = datos.solicitudes_de(self.usuario["id"], estado)

        self.tabla.setRowCount(len(registros))
        for fila, s in enumerate(registros):
            self.tabla.setItem(fila, 0, QTableWidgetItem(s["folio"]))
            self.tabla.setItem(fila, 1, QTableWidgetItem(s["tipo"]))

            item_prioridad = QTableWidgetItem(s["prioridad"])
            item_prioridad.setForeground(QColor(color_texto(TONO_PRIORIDAD[s["prioridad"]])))
            self.tabla.setItem(fila, 2, item_prioridad)

            # «Finalizado» pide una calificación del representante
            item_estado = QTableWidgetItem("Finalizado · califica el servicio" if s["por_calificar"] else s["estado"])
            item_estado.setForeground(QColor(color_texto(TONO_ESTADO[s["estado"]])))
            self.tabla.setItem(fila, 3, item_estado)

            self.tabla.setItem(fila, 4, QTableWidgetItem(s["fecha_creacion"]))
            self.tabla.setItem(fila, 5, item_vence(s))
            self.tabla.item(fila, 0).setData(Qt.UserRole, s["folio"])

        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        # Mensaje cuando no hay nada que mostrar (en vez de una tabla vacía sin explicación)
        if registros:
            self.lbl_vacio.hide()
        else:
            self.lbl_vacio.setText(f"No tienes solicitudes con estatus «{estado}»." if estado
                                   else "Aún no has registrado solicitudes.")
            self.lbl_vacio.show()

    def _abrir_detalle(self, fila, _col):
        folio = self.tabla.item(fila, 0).data(Qt.UserRole)
        dialogo = DialogoDetalleSolicitud(folio, self.usuario, al_guardar=self.actualizar, parent=self)
        dialogo.exec()
