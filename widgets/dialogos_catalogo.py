from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox, QWidget, QSpinBox
)

import datos
from widgets.utiles import ajustar_a_pantalla, poner_con_scroll


class _DialogoBase(QDialog):
    def _armar(self, titulo: str, alto: int):
        self.setWindowTitle(titulo)
        ajustar_a_pantalla(self, 420, alto)
        cuerpo = QWidget()
        poner_con_scroll(self, cuerpo)
        lay = QVBoxLayout(cuerpo)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(6)
        return lay

    def _pie(self, lay):
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorLogin")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        lay.addWidget(self.lbl_error)
        fila = QHBoxLayout()
        fila.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setObjectName("botonSecundario")
        cancelar.clicked.connect(self.reject)
        guardar = QPushButton("Guardar")
        guardar.setObjectName("botonPrimario")
        guardar.clicked.connect(self._guardar)
        fila.addWidget(cancelar)
        fila.addWidget(guardar)
        lay.addSpacing(8)
        lay.addLayout(fila)

    def _error(self, texto):
        self.lbl_error.setText(texto)
        self.lbl_error.show()


class DialogoArea(_DialogoBase):
    """Alta de un área (y su edición, solo si algún rol tiene el permiso `catalogos.editar`)."""

    def __init__(self, actor: dict, area: dict = None, parent=None):
        super().__init__(parent)
        self.actor, self.area = actor, area
        lay = self._armar("Nueva área" if area is None else "Editar área", 250)
        lay.addWidget(QLabel("Nombre del área"))
        self.txt_nombre = QLineEdit(area["nombre"] if area else "")
        self.txt_nombre.setMaxLength(datos.LIM_CATALOGO)
        lay.addWidget(self.txt_nombre)
        if area is None:
            nota = QLabel("Una vez creada, el área no se puede editar ni eliminar. Después podrás dar de alta a su "
                          "representante en Usuarios y roles.")
            nota.setWordWrap(True)
            nota.setStyleSheet("color:#64748B; font-size:11px;")
            lay.addWidget(nota)
        self.chk_activa = QCheckBox("Área activa")
        self.chk_activa.setChecked(area["activa"] if area else True)
        self.chk_activa.setVisible(area is not None)
        lay.addWidget(self.chk_activa)
        self._pie(lay)

    def _guardar(self):
        try:
            if self.area is None:
                datos.crear_area(self.actor, self.txt_nombre.text())
            else:
                datos.actualizar_area(self.actor, self.area["id"], self.txt_nombre.text(), self.chk_activa.isChecked())
        except (ValueError, PermissionError) as error:
            self._error(str(error))
            return
        self.accept()


class DialogoSucursal(_DialogoBase):
    """Alta de una sucursal (y su edición, solo si algún rol tiene el permiso `catalogos.editar`)."""

    def __init__(self, actor: dict, sucursal: dict = None, parent=None):
        super().__init__(parent)
        self.actor, self.sucursal = actor, sucursal
        lay = self._armar("Nueva sucursal" if sucursal is None else "Editar sucursal", 250)
        lay.addWidget(QLabel("Nombre de la sucursal"))
        self.txt_nombre = QLineEdit(sucursal["nombre"] if sucursal else "")
        self.txt_nombre.setMaxLength(datos.LIM_CATALOGO)
        lay.addWidget(self.txt_nombre)
        if sucursal is None:
            nota = QLabel("Una vez creada, la sucursal no se puede editar ni eliminar.")
            nota.setWordWrap(True)
            nota.setStyleSheet("color:#64748B; font-size:11px;")
            lay.addWidget(nota)
        self.chk_activa = QCheckBox("Sucursal activa")
        self.chk_activa.setChecked(sucursal["activa"] if sucursal else True)
        self.chk_activa.setVisible(sucursal is not None)
        lay.addWidget(self.chk_activa)
        self._pie(lay)

    def _guardar(self):
        try:
            if self.sucursal is None:
                datos.crear_sucursal(self.actor, self.txt_nombre.text())
            else:
                datos.actualizar_sucursal(self.actor, self.sucursal["id"], self.txt_nombre.text(), self.chk_activa.isChecked())
        except (ValueError, PermissionError) as error:
            self._error(str(error))
            return
        self.accept()


class DialogoTipo(_DialogoBase):
    """Alta de un tipo de solicitud con su tiempo estimado de solución (y su edición, solo si algún rol tiene
    `catalogos.editar`). De las horas salen la prioridad y la fecha límite de sus solicitudes."""

    def __init__(self, actor: dict, tipo: dict = None, parent=None):
        super().__init__(parent)
        self.actor, self.tipo = actor, tipo
        lay = self._armar("Nuevo tipo de solicitud" if tipo is None else "Editar tipo de solicitud", 360)
        lay.addWidget(QLabel("Nombre del tipo"))
        self.txt_nombre = QLineEdit(tipo["nombre"] if tipo else "")
        self.txt_nombre.setMaxLength(datos.LIM_CATALOGO)
        lay.addWidget(self.txt_nombre)

        lay.addSpacing(6)
        lay.addWidget(QLabel("Tiempo estimado de solución (horas)"))
        self.spin_horas = QSpinBox()
        self.spin_horas.setRange(1, datos.MAX_HORAS_TIPO)
        self.spin_horas.setValue(tipo["horas"] if tipo else 48)
        self.spin_horas.valueChanged.connect(self._actualizar_prioridad)
        lay.addWidget(self.spin_horas)
        self.lbl_prioridad = QLabel("")
        self.lbl_prioridad.setWordWrap(True)
        self.lbl_prioridad.setStyleSheet("color:#64748B; font-size:11px;")
        lay.addWidget(self.lbl_prioridad)
        self._actualizar_prioridad()

        self.chk_activo = QCheckBox("Tipo activo")
        self.chk_activo.setChecked(tipo["activo"] if tipo else True)
        self.chk_activo.setVisible(tipo is not None)
        lay.addWidget(self.chk_activo)
        self._pie(lay)

    def _actualizar_prioridad(self):
        horas = self.spin_horas.value()
        self.lbl_prioridad.setText(f"Prioridad que tendrán sus solicitudes: {datos.prioridad_por_horas(horas)}. "
                                   "A menor tiempo, mayor prioridad; quien registra la solicitud no la elige. "
                                   "Ese tiempo también es su fecha límite de atención.")

    def _guardar(self):
        horas = self.spin_horas.value()
        try:
            if self.tipo is None:
                datos.crear_tipo(self.actor, self.txt_nombre.text(), horas)
            else:
                datos.actualizar_tipo(self.actor, self.tipo["id"], self.txt_nombre.text(), horas,
                                      self.chk_activo.isChecked())
        except (ValueError, PermissionError) as error:
            self._error(str(error))
            return
        self.accept()
