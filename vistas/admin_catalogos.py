from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton, QMessageBox, QScrollArea, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import datos
from estilos import TONO_PRIORIDAD, color_texto
from permisos import puede
from widgets.dialogos_catalogo import DialogoArea, DialogoSucursal, DialogoTipo


def _tabla(columnas, alto_min=130):
    t = QTableWidget(0, len(columnas))
    t.setHorizontalHeaderLabels(columnas)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setMinimumHeight(alto_min)
    return t


def _boton(texto, primario=False, habilitado=True):
    b = QPushButton(texto)
    b.setObjectName("botonPrimario" if primario else "botonSecundario")
    b.setEnabled(habilitado)
    return b


class VistaCatalogos(QWidget):
    """RF-04: catálogos del sistema.

    Por regla del proyecto los catálogos **solo permiten agregar** elementos nuevos: no se editan ni se
    eliminan (los botones «Editar» y «Eliminar» solo aparecen si algún rol recibe los permisos
    `catalogos.editar` / `catalogos.eliminar`, que hoy nadie tiene).

    * Áreas y sucursales: a las que pertenecen los representantes de área.
    * Tipos de solicitud: cada uno lleva su tiempo estimado de solución; de él salen la prioridad (a menor
      tiempo, mayor prioridad) y la fecha límite de sus solicitudes.
    * Clasificación por prioridad: qué tipos caen en cada prioridad (consulta).
    """

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._puede_editar = puede(usuario, "catalogos.editar")
        self._puede_eliminar = puede(usuario, "catalogos.eliminar")
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        cuerpo = QWidget()
        scroll.setWidget(cuerpo)
        raiz.addWidget(scroll)
        lay = QVBoxLayout(cuerpo)
        lay.setContentsMargins(4, 8, 8, 8)
        lay.setSpacing(8)

        regla = QLabel("Los catálogos solo permiten agregar elementos nuevos: no se editan ni se eliminan, para "
                       "conservar la trazabilidad del historial.")
        regla.setWordWrap(True)
        regla.setStyleSheet("color:#64748B; font-size:11px;")
        lay.addWidget(regla)

        # ---- áreas
        lay.addWidget(self._titulo("Áreas"))
        self.tabla_areas = _tabla(["Área", "Representantes activos"])
        self.tabla_areas.itemSelectionChanged.connect(self._botones)
        lay.addWidget(self.tabla_areas)
        fila = QHBoxLayout()
        fila.addStretch()
        self.btn_area_eliminar = _boton("Eliminar", habilitado=False)
        self.btn_area_editar = _boton("Editar", habilitado=False)
        self.btn_area_nueva = _boton("Nueva área", primario=True)
        self.btn_area_eliminar.clicked.connect(self._eliminar_area)
        self.btn_area_editar.clicked.connect(self._editar_area)
        self.btn_area_nueva.clicked.connect(self._nueva_area)
        self.btn_area_editar.setVisible(self._puede_editar)
        self.btn_area_eliminar.setVisible(self._puede_eliminar)
        for b in (self.btn_area_eliminar, self.btn_area_editar, self.btn_area_nueva):
            fila.addWidget(b)
        lay.addLayout(fila)
        if self._puede_editar:
            self.tabla_areas.cellDoubleClicked.connect(lambda *_: self._editar_area())

        # ---- sucursales
        lay.addWidget(self._titulo("Sucursales"))
        self.tabla_sucursales = _tabla(["Sucursal", "Representantes activos"])
        self.tabla_sucursales.itemSelectionChanged.connect(self._botones)
        lay.addWidget(self.tabla_sucursales)
        fila = QHBoxLayout()
        fila.addStretch()
        self.btn_suc_eliminar = _boton("Eliminar", habilitado=False)
        self.btn_suc_editar = _boton("Editar", habilitado=False)
        self.btn_suc_nueva = _boton("Nueva sucursal", primario=True)
        self.btn_suc_eliminar.clicked.connect(self._eliminar_sucursal)
        self.btn_suc_editar.clicked.connect(self._editar_sucursal)
        self.btn_suc_nueva.clicked.connect(self._nueva_sucursal)
        self.btn_suc_editar.setVisible(self._puede_editar)
        self.btn_suc_eliminar.setVisible(self._puede_eliminar)
        for b in (self.btn_suc_eliminar, self.btn_suc_editar, self.btn_suc_nueva):
            fila.addWidget(b)
        lay.addLayout(fila)
        if self._puede_editar:
            self.tabla_sucursales.cellDoubleClicked.connect(lambda *_: self._editar_sucursal())

        # ---- tipos
        lay.addWidget(self._titulo("Tipos de solicitud"))
        self.tabla_tipos = _tabla(["Tipo de solicitud", "Tiempo estimado", "Prioridad que se asigna"], alto_min=190)
        self.tabla_tipos.itemSelectionChanged.connect(self._botones)
        lay.addWidget(self.tabla_tipos)
        fila = QHBoxLayout()
        fila.addStretch()
        self.btn_tipo_eliminar = _boton("Eliminar", habilitado=False)
        self.btn_tipo_editar = _boton("Editar", habilitado=False)
        self.btn_tipo_nuevo = _boton("Nuevo tipo", primario=True)
        self.btn_tipo_eliminar.clicked.connect(self._eliminar_tipo)
        self.btn_tipo_editar.clicked.connect(self._editar_tipo)
        self.btn_tipo_nuevo.clicked.connect(self._nuevo_tipo)
        self.btn_tipo_editar.setVisible(self._puede_editar)
        self.btn_tipo_eliminar.setVisible(self._puede_eliminar)
        for b in (self.btn_tipo_eliminar, self.btn_tipo_editar, self.btn_tipo_nuevo):
            fila.addWidget(b)
        lay.addLayout(fila)
        if self._puede_editar:
            self.tabla_tipos.cellDoubleClicked.connect(lambda *_: self._editar_tipo())

        # ---- clasificación por prioridad
        lay.addWidget(self._titulo("Clasificación por prioridad"))
        ayuda = QLabel("La prioridad de cada solicitud sale del tiempo estimado de solución de su tipo (no la elige "
                       "quien la registra): a menor tiempo, mayor prioridad. Alta: "
                       f"{datos.rangos_prioridad()[0]['regla']} · Media: {datos.rangos_prioridad()[1]['regla']} · "
                       f"Baja: {datos.rangos_prioridad()[2]['regla']}.")
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color:#64748B; font-size:11px;")
        lay.addWidget(ayuda)
        self.tabla_prioridades = _tabla(["Prioridad", "Tipos de solicitud con esa prioridad"], alto_min=120)
        self.tabla_prioridades.setSelectionMode(QAbstractItemView.NoSelection)
        lay.addWidget(self.tabla_prioridades)

        fijos = QLabel("Estatus: " + ", ".join(datos.ESTADOS) + "   (lista fija del flujo de atención)")
        fijos.setWordWrap(True)
        fijos.setStyleSheet("color:#94A3B8; font-size:11px; margin-top:6px;")
        lay.addWidget(fijos)
        lay.addStretch()

    @staticmethod
    def _titulo(texto):
        lbl = QLabel(texto)
        lbl.setStyleSheet("font-weight:700; font-size:14px; margin-top:6px;")
        return lbl

    # ----------------------------------------------------------- datos
    def actualizar(self):
        self._areas = datos.areas_todas()
        self.tabla_areas.setRowCount(len(self._areas))
        for i, a in enumerate(self._areas):
            self._poner(self.tabla_areas, i, 0, a["nombre"], a["id"], atenuar=not a["activa"])
            self._poner(self.tabla_areas, i, 1, a["representantes"], a["id"], atenuar=not a["activa"], centrado=True)
        self._sucursales = datos.sucursales_todas()
        self.tabla_sucursales.setRowCount(len(self._sucursales))
        for i, x in enumerate(self._sucursales):
            self._poner(self.tabla_sucursales, i, 0, x["nombre"], x["id"], atenuar=not x["activa"])
            self._poner(self.tabla_sucursales, i, 1, x["representantes"], x["id"], atenuar=not x["activa"], centrado=True)
        self._tipos = datos.tipos_todos()
        self.tabla_tipos.setRowCount(len(self._tipos))
        for i, t in enumerate(self._tipos):
            self._poner(self.tabla_tipos, i, 0, t["nombre"], t["id"], atenuar=not t["activo"])
            self._poner(self.tabla_tipos, i, 1, f"{t['horas']} h", t["id"], atenuar=not t["activo"], centrado=True)
            item = self._poner(self.tabla_tipos, i, 2, t["prioridad"], t["id"], atenuar=not t["activo"])
            item.setForeground(QColor(color_texto(TONO_PRIORIDAD[t["prioridad"]])))
        clasif = datos.rangos_prioridad()
        self.tabla_prioridades.setRowCount(len(clasif))
        for i, c in enumerate(clasif):
            p = self._poner(self.tabla_prioridades, i, 0, c["prioridad"], c["prioridad"])
            p.setForeground(QColor(color_texto(TONO_PRIORIDAD[c["prioridad"]])))
            self._poner(self.tabla_prioridades, i, 1, ", ".join(c["tipos"]) or "—", c["prioridad"])
        self._botones()

    @staticmethod
    def _poner(tabla, fila, col, valor, id_, atenuar=False, centrado=False):
        item = QTableWidgetItem(str(valor))
        item.setData(Qt.UserRole, id_)
        if centrado:
            item.setTextAlignment(Qt.AlignCenter)
        if atenuar:
            item.setForeground(QColor("#64748B"))
        tabla.setItem(fila, col, item)
        return item

    def _id_seleccionado(self, tabla):
        filas = tabla.selectionModel().selectedRows()
        return tabla.item(filas[0].row(), 0).data(Qt.UserRole) if filas else None

    def _area_sel(self):
        i = self._id_seleccionado(self.tabla_areas)
        return next((a for a in self._areas if a["id"] == i), None)

    def _sucursal_sel(self):
        i = self._id_seleccionado(self.tabla_sucursales)
        return next((x for x in self._sucursales if x["id"] == i), None)

    def _tipo_sel(self):
        i = self._id_seleccionado(self.tabla_tipos)
        return next((t for t in self._tipos if t["id"] == i), None)

    def _botones(self):
        a, t, x = self._area_sel(), self._tipo_sel(), self._sucursal_sel()
        self.btn_suc_editar.setEnabled(x is not None and self._puede_editar)
        self.btn_suc_eliminar.setEnabled(x is not None and x["activa"] and self._puede_eliminar)
        self.btn_area_editar.setEnabled(a is not None and self._puede_editar)
        self.btn_area_eliminar.setEnabled(a is not None and a["activa"] and self._puede_eliminar)
        self.btn_tipo_editar.setEnabled(t is not None and self._puede_editar)
        self.btn_tipo_eliminar.setEnabled(t is not None and t["activo"] and self._puede_eliminar)

    # ---------------------------------------------------------- acciones
    def _nueva_area(self):
        if DialogoArea(self.usuario, parent=self).exec():
            self.actualizar()

    def _editar_area(self):
        a = self._area_sel()
        if a and self._puede_editar and DialogoArea(self.usuario, a, parent=self).exec():
            self.actualizar()

    def _eliminar_area(self):
        a = self._area_sel()
        if not a or not self._puede_eliminar:
            return
        if QMessageBox.question(self, "Eliminar área", f"¿Eliminar el área «{a['nombre']}»?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            resultado = datos.eliminar_area(self.usuario, a["id"])
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "No se puede eliminar", str(error))
            return
        QMessageBox.information(self, "Área " + resultado, f"El área «{a['nombre']}» quedó {resultado}.")
        self.actualizar()

    def _nueva_sucursal(self):
        if DialogoSucursal(self.usuario, parent=self).exec():
            self.actualizar()

    def _editar_sucursal(self):
        x = self._sucursal_sel()
        if x and self._puede_editar and DialogoSucursal(self.usuario, x, parent=self).exec():
            self.actualizar()

    def _eliminar_sucursal(self):
        x = self._sucursal_sel()
        if not x or not self._puede_eliminar:
            return
        if QMessageBox.question(self, "Eliminar sucursal", f"¿Eliminar la sucursal «{x['nombre']}»?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            resultado = datos.eliminar_sucursal(self.usuario, x["id"])
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "No se puede eliminar", str(error))
            return
        QMessageBox.information(self, "Sucursal " + resultado, f"La sucursal «{x['nombre']}» quedó {resultado}.")
        self.actualizar()

    def _nuevo_tipo(self):
        if DialogoTipo(self.usuario, parent=self).exec():
            self.actualizar()

    def _editar_tipo(self):
        t = self._tipo_sel()
        if t and self._puede_editar and DialogoTipo(self.usuario, t, parent=self).exec():
            self.actualizar()

    def _eliminar_tipo(self):
        t = self._tipo_sel()
        if not t or not self._puede_eliminar:
            return
        if QMessageBox.question(self, "Eliminar tipo", f"¿Eliminar el tipo «{t['nombre']}»?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            resultado = datos.eliminar_tipo(self.usuario, t["id"])
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "No se puede eliminar", str(error))
            return
        QMessageBox.information(self, "Tipo " + resultado, f"El tipo «{t['nombre']}» quedó {resultado}.")
        self.actualizar()
