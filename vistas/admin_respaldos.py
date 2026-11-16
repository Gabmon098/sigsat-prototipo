import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

import archivos
import persistencia

_TIPOS = {"auto": "Automático (diario)", "manual": "Manual", "antes_de_restaurar": "Antes de restaurar",
          "antes_de_reiniciar": "Antes de reiniciar", "antes_de_actualizar": "Antes de actualizar la app"}


class PestanaRespaldos(QWidget):
    """Respaldos de los datos (RNF-09): crear, ver y restaurar copias. (La bitácora de cada solicitud se ve en su
    detalle; su integridad se verifica sola al cargar o restaurar datos, no aquí.)"""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._respaldos = []
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setStyleSheet("color:#33414F;")
        lay.addWidget(self.lbl_estado)

        barra = QHBoxLayout()
        self.btn_carpeta = QPushButton("Abrir carpeta")
        self.btn_carpeta.setObjectName("botonSecundario")
        self.btn_carpeta.clicked.connect(self._abrir_carpeta)
        self.btn_archivo = QPushButton("Restaurar desde archivo…")
        self.btn_archivo.setObjectName("botonSecundario")
        self.btn_archivo.clicked.connect(self._restaurar_desde_archivo)
        self.btn_restaurar = QPushButton("Restaurar el seleccionado")
        self.btn_restaurar.setObjectName("botonSecundario")
        self.btn_restaurar.setEnabled(False)
        self.btn_restaurar.clicked.connect(self.restaurar_seleccionado)
        self.btn_crear = QPushButton("Crear respaldo ahora")
        self.btn_crear.setObjectName("botonPrimario")
        self.btn_crear.clicked.connect(self.crear_respaldo)
        barra.addStretch()
        for b in (self.btn_carpeta, self.btn_archivo, self.btn_restaurar, self.btn_crear):
            barra.addWidget(b)
        lay.addLayout(barra)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Fecha", "Tipo", "Tamaño", "Archivo"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.itemSelectionChanged.connect(
            lambda: self.btn_restaurar.setEnabled(persistencia.activa() and bool(self.tabla.selectionModel().selectedRows())))
        lay.addWidget(self.tabla)

        self.lbl_vacio = QLabel("")
        self.lbl_vacio.setAlignment(Qt.AlignCenter)
        self.lbl_vacio.setStyleSheet("color:#64748B; padding:16px;")
        lay.addWidget(self.lbl_vacio)

        nota = QLabel(f"Se crea un respaldo automático cada día (se conservan los últimos {persistencia.RETENCION_AUTOMATICOS}). "
                      "Restaurar reemplaza TODOS los datos actuales; antes se guarda una copia de seguridad del estado actual.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#94A3B8; font-size:11px;")
        lay.addWidget(nota)

    def actualizar(self):
        activa = persistencia.activa()
        for b in (self.btn_crear, self.btn_archivo, self.btn_carpeta):
            b.setEnabled(activa)
        if not activa:
            self.lbl_estado.setText("Los datos NO se están guardando en disco (la aplicación se abrió con --sin-guardar): "
                                    "al cerrarla se pierden los cambios y no hay respaldos.")
            self._respaldos = []
        else:
            info = persistencia.informacion()
            ultimo = info["ultimo_guardado"].strftime("%Y-%m-%d %H:%M:%S") if info["ultimo_guardado"] else "—"
            texto = f"Los datos se guardan automáticamente en {info['carpeta']} (último guardado: {ultimo})."
            if info["ultimo_error"]:
                texto += f"\n⚠ El último guardado falló: {info['ultimo_error']}"
            self.lbl_estado.setText(texto)
            self._respaldos = persistencia.listar_respaldos()
        self.tabla.setRowCount(len(self._respaldos))
        for i, r in enumerate(self._respaldos):
            valores = [r["fecha"].strftime("%Y-%m-%d %H:%M"), _TIPOS.get(r["tipo"], r["tipo"]),
                       archivos.formato_tamano(r["tamano"]), r["nombre"]]
            for j, v in enumerate(valores):
                self.tabla.setItem(i, j, QTableWidgetItem(v))
        self.lbl_vacio.setText("" if self._respaldos else ("Todavía no hay respaldos." if activa else ""))
        self.lbl_vacio.setVisible(not self._respaldos and activa)
        self.btn_restaurar.setEnabled(False)

    # ---------------------------------------------------------- acciones
    def crear_respaldo(self):
        try:
            ruta = persistencia.crear_respaldo("manual")
        except (persistencia.ErrorPersistencia, OSError) as error:
            QMessageBox.warning(self, "No se pudo crear el respaldo", str(error))
            return None
        QMessageBox.information(self, "Respaldo creado", f"El respaldo se guardó en:\n{ruta}")
        self.actualizar()
        return ruta

    def restaurar_seleccionado(self):
        filas = self.tabla.selectionModel().selectedRows()
        if filas:
            self._restaurar(self._respaldos[filas[0].row()]["ruta"])

    def _restaurar_desde_archivo(self):
        ruta, _f = QFileDialog.getOpenFileName(self, "Elegir respaldo", str(persistencia.carpeta_respaldos()), "Respaldos (*.zip)")
        if ruta:
            self._restaurar(ruta)

    def _restaurar(self, ruta) -> bool:
        aviso = (f"¿Restaurar los datos del respaldo «{os.path.basename(str(ruta))}»?\n\n"
                 "Se REEMPLAZARÁN todos los datos actuales (cuentas, solicitudes, catálogos…). Antes se guardará "
                 "una copia de seguridad del estado actual.")
        if QMessageBox.question(self, "Restaurar respaldo", aviso, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        try:
            resumen = persistencia.restaurar_respaldo(ruta)
        except (persistencia.ErrorPersistencia, OSError) as error:
            QMessageBox.warning(self, "No se pudo restaurar", f"{error}\n\nLos datos actuales no se modificaron.")
            return False
        QMessageBox.information(
            self, "Datos restaurados",
            f"Se restauraron {resumen['solicitudes']} solicitudes y {resumen['usuarios']} cuentas.\n\n"
            "Cierra sesión y vuelve a entrar para ver todo actualizado.")
        self.actualizar()
        return True

    def _abrir_carpeta(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(persistencia.carpeta_respaldos())))
