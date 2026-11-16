from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QCheckBox, QWidget
)

import datos
from permisos import ROL_REPRESENTANTE, ROL_TECNICO
from widgets.utiles import ajustar_a_pantalla, poner_con_scroll


class DialogoUsuario(QDialog):
    """Edición de una cuenta de Representante de Área (con área y sucursal) o de Técnico: nombre, rol (p. ej.
    pasar a alguien a Técnico), correo, usuario, contraseña y si está activa. Las cuentas NO las crea el
    Administrador: cada persona se registra desde el login. Las cuentas de Administrador no se gestionan aquí.
    (Sin `usuario_existente` el diálogo sigue sirviendo para un alta interna, que la pantalla ya no ofrece.)
    Las validaciones las hace la capa de datos; aquí solo se muestra el mensaje de error."""

    def __init__(self, usuario_existente: dict = None, parent=None):
        super().__init__(parent)
        self.usuario_existente = usuario_existente  # None = alta interna
        self.setWindowTitle("Nueva cuenta" if usuario_existente is None else "Editar cuenta")
        ajustar_a_pantalla(self, 420, 530)
        self._construir_ui()
        if usuario_existente:
            self._precargar(usuario_existente)
        self._actualizar_area_visible()

    def _construir_ui(self):
        cuerpo = QWidget()
        poner_con_scroll(self, cuerpo)
        layout = QVBoxLayout(cuerpo)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Nombre completo"))
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setMaxLength(datos.LIM_NOMBRE)
        layout.addWidget(self.txt_nombre)

        layout.addSpacing(6)
        layout.addWidget(QLabel("Rol"))
        self.combo_rol = QComboBox()
        self.combo_rol.addItems([ROL_REPRESENTANTE, ROL_TECNICO])
        self.combo_rol.currentTextChanged.connect(self._actualizar_area_visible)
        layout.addWidget(self.combo_rol)

        self.lbl_area = QLabel("Área")
        self.combo_area = QComboBox()
        self.combo_area.addItems(datos.areas_activas())
        layout.addWidget(self.lbl_area)
        layout.addWidget(self.combo_area)
        self.lbl_sucursal = QLabel("Sucursal")
        self.combo_sucursal = QComboBox()
        self.combo_sucursal.addItems(datos.sucursales_activas())
        layout.addWidget(self.lbl_sucursal)
        layout.addWidget(self.combo_sucursal)

        layout.addSpacing(6)
        layout.addWidget(QLabel("Correo"))
        self.txt_correo = QLineEdit()
        self.txt_correo.setMaxLength(datos.LIM_CORREO)
        layout.addWidget(self.txt_correo)

        layout.addSpacing(6)
        layout.addWidget(QLabel("Usuario (para iniciar sesión)"))
        self.txt_usuario = QLineEdit()
        self.txt_usuario.setMaxLength(datos.LIM_USUARIO)
        layout.addWidget(self.txt_usuario)

        layout.addSpacing(6)
        etiqueta_pass = ("Contraseña" if self.usuario_existente is None
                         else "Contraseña (dejar en blanco para no cambiarla)")
        layout.addWidget(QLabel(etiqueta_pass))
        self.txt_contrasena = QLineEdit()
        self.txt_contrasena.setEchoMode(QLineEdit.Password)
        self.txt_contrasena.setMaxLength(datos.MAX_CONTRASENA)
        self.txt_contrasena.setPlaceholderText(f"Mínimo {datos.MIN_CONTRASENA} caracteres")
        layout.addWidget(self.txt_contrasena)

        # Solo al editar: una cuenta desactivada se puede reactivar desde aquí.
        self.chk_activa = QCheckBox("Cuenta activa (puede iniciar sesión)")
        self.chk_activa.setChecked(True)
        self.chk_activa.setVisible(self.usuario_existente is not None)
        layout.addSpacing(4)
        layout.addWidget(self.chk_activa)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorLogin")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        layout.addStretch()

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setObjectName("botonSecundario")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("Guardar")
        btn_guardar.setObjectName("botonPrimario")
        btn_guardar.clicked.connect(self._guardar)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        layout.addLayout(botones)

    def _precargar(self, u: dict):
        self.txt_nombre.setText(u["nombre"])
        self.combo_rol.setCurrentText(u["rol"])
        if u["area"]:
            self.combo_area.setCurrentText(u["area"])
        if u.get("sucursal"):
            self.combo_sucursal.setCurrentText(u["sucursal"])
        self.txt_correo.setText(u["correo"])
        self.txt_usuario.setText(u["usuario"])
        self.chk_activa.setChecked(u["activo"])
        # La contraseña nunca se precarga; en edición se deja en blanco.

    def _actualizar_area_visible(self):
        es_representante = self.combo_rol.currentText() == ROL_REPRESENTANTE
        for w in (self.lbl_area, self.combo_area, self.lbl_sucursal, self.combo_sucursal):
            w.setVisible(es_representante)

    def _guardar(self):
        rol = self.combo_rol.currentText()
        area = self.combo_area.currentText() if rol == ROL_REPRESENTANTE else None
        sucursal = self.combo_sucursal.currentText() if rol == ROL_REPRESENTANTE else None
        try:
            if self.usuario_existente is None:
                datos.crear_usuario(self.txt_nombre.text(), self.txt_usuario.text(),
                                    self.txt_contrasena.text(), rol, area, self.txt_correo.text(), sucursal)
            else:
                datos.actualizar_usuario(
                    self.usuario_existente["id"], self.txt_nombre.text(), self.txt_usuario.text(),
                    self.txt_contrasena.text(), rol, area, self.txt_correo.text(),
                    activo=self.chk_activa.isChecked(), sucursal=sucursal)
        except (ValueError, PermissionError) as error:
            self.lbl_error.setText(str(error))
            self.lbl_error.show()
            return
        self.accept()
