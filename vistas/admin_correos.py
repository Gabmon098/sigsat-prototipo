import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton, QTextEdit
)
from PySide6.QtCore import Qt

import correo


class PestanaCorreos(QWidget):
    """Bandeja de los correos que envía el sistema (asignaciones, cambios de estatus y recuperación de
    contraseña). En modo desarrollo es la «bandeja de pruebas»: nada sale a Internet."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._registros = []
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        self.lbl_modo = QLabel("")
        self.lbl_modo.setWordWrap(True)
        self.lbl_modo.setStyleSheet("color:#64748B; font-size:12px;")
        lay.addWidget(self.lbl_modo)

        barra = QHBoxLayout()
        barra.addStretch()
        btn = QPushButton("Actualizar")
        btn.setObjectName("botonSecundario")
        btn.clicked.connect(self.actualizar)
        barra.addWidget(btn)
        lay.addLayout(barra)

        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["Fecha", "Para", "Asunto", "Tipo", "Estado"])
        self._tipos = {"asignacion": "Asignación", "estatus": "Cambio de estatus", "recuperacion": "Recuperación", "cuenta": "Cuenta"}
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.itemSelectionChanged.connect(self._mostrar_cuerpo)
        lay.addWidget(self.tabla, 3)

        self.lbl_vacio = QLabel("Todavía no se ha enviado ningún correo.")
        self.lbl_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_vacio.setStyleSheet("color:#64748B; padding:16px;")
        lay.addWidget(self.lbl_vacio)

        self.txt_cuerpo = QTextEdit()
        self.txt_cuerpo.setReadOnly(True)
        self.txt_cuerpo.setPlaceholderText("Selecciona un correo para ver su contenido.")
        lay.addWidget(self.txt_cuerpo, 2)

    def actualizar(self):
        modo = correo.modo()
        if modo == "smtp":
            self.lbl_modo.setText(f"Los correos se envían por el servidor SMTP configurado "
                                  f"({os.environ.get('SIGSAT_SMTP_HOST', '')}). Los mensajes con códigos de seguridad no se guardan aquí.")
        elif modo == "desarrollo":
            carpeta = correo.carpeta_salida()
            self.lbl_modo.setText("Modo desarrollo: no hay servidor de correo configurado (variable SIGSAT_SMTP_HOST), "
                                  "así que no se envía nada a Internet. Cada mensaje se guarda aquí"
                                  + (f" y como archivo .eml en {carpeta}." if carpeta else "."))
        else:
            self.lbl_modo.setText("Transporte de correo personalizado.")
        self._registros = correo.bandeja()
        self.tabla.setRowCount(len(self._registros))
        for fila, r in enumerate(self._registros):
            estado = {"enviado": "Enviado", "en cola": "En cola", "error": "Error"}.get(r["estado"], r["estado"])
            if r["estado"] == "error" and r["detalle"]:
                estado += f": {r['detalle']}"
            for col, valor in enumerate([r["fecha"].strftime("%Y-%m-%d %H:%M"), r["para"], r["asunto"],
                                         self._tipos.get(r["tipo"], r["tipo"]), estado]):
                item = QTableWidgetItem(valor)
                item.setData(Qt.UserRole, r["id"])
                self.tabla.setItem(fila, col, item)
        self.lbl_vacio.setVisible(not self._registros)
        self.txt_cuerpo.clear()

    def _mostrar_cuerpo(self):
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return
        r = self._registros[filas[0].row()]
        self.txt_cuerpo.setPlainText(f"Para: {r['para']}\nAsunto: {r['asunto']}\n\n{r['cuerpo']}")
