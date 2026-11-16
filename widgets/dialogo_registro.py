from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox, QWidget
)

import correo
import datos
from estilos import AZUL_OSCURO
from widgets.utiles import ajustar_a_pantalla, poner_con_scroll


class DialogoRegistro(QDialog):
    """«Creación de cuenta»: la persona se registra sola. Escribe sus datos, elige su usuario y su contraseña y la
    cuenta queda creada y activa al instante (ya no la crea un administrador). Siempre entra como Representante
    de Área, con el área y la sucursal que elija. Si alguien debe ser Técnico, el Administrador le cambia el rol."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crear una cuenta")
        ajustar_a_pantalla(self, 470, 740)
        self._creada = False
        self.usuario_creado = None            # usuario (login) de la cuenta creada, para precargarlo en el login
        self._construir_ui()

    def _campo(self, lay, etiqueta, maximo, marcador="", clave=False):
        lay.addSpacing(4)
        lay.addWidget(QLabel(etiqueta))
        c = QLineEdit()
        c.setMaxLength(maximo)
        c.setMinimumHeight(34)
        if marcador:
            c.setPlaceholderText(marcador)
        if clave:
            c.setEchoMode(QLineEdit.Password)
        lay.addWidget(c)
        return c

    def _construir_ui(self):
        cuerpo = QWidget()
        poner_con_scroll(self, cuerpo)
        lay = QVBoxLayout(cuerpo)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(6)

        titulo = QLabel("Crear una cuenta")
        titulo.setStyleSheet(f"font-size:18px; font-weight:700; color:{AZUL_OSCURO};")
        lay.addWidget(titulo)
        ayuda = QLabel("Escribe tus datos y elige tu usuario y tu contraseña. Tu cuenta se crea al instante como "
                       "Representante de Área; podrás iniciar sesión en cuanto termines.")
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color:#64748B; margin-bottom:6px;")
        lay.addWidget(ayuda)

        self.txt_nombre = self._campo(lay, "Nombre completo", datos.LIM_NOMBRE)
        self.txt_correo = self._campo(lay, "Correo", datos.LIM_CORREO)
        self.txt_usuario = self._campo(lay, "Usuario (para iniciar sesión)", datos.LIM_USUARIO, "Sin espacios")
        self.txt_correo.editingFinished.connect(self._sugerir_usuario)
        self.txt_contrasena = self._campo(lay, "Contraseña", datos.MAX_CONTRASENA,
                                          f"Mínimo {datos.MIN_CONTRASENA} caracteres", clave=True)
        self.txt_confirmar = self._campo(lay, "Repite la contraseña", datos.MAX_CONTRASENA, clave=True)
        self.chk_mostrar = QCheckBox("Mostrar contraseñas")
        self.chk_mostrar.toggled.connect(self._alternar_mostrar)
        lay.addWidget(self.chk_mostrar)

        lay.addSpacing(4)
        lay.addWidget(QLabel("Área que representas"))
        self.combo_area = QComboBox()
        self.combo_area.addItems(datos.areas_activas())
        self.combo_area.setMinimumHeight(34)
        lay.addWidget(self.combo_area)

        lay.addSpacing(4)
        lay.addWidget(QLabel("Sucursal"))
        self.combo_sucursal = QComboBox()
        self.combo_sucursal.addItems(datos.sucursales_activas())
        self.combo_sucursal.setMinimumHeight(34)
        lay.addWidget(self.combo_sucursal)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorLogin")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        lay.addWidget(self.lbl_error)

        self.lbl_exito = QLabel("")
        self.lbl_exito.setObjectName("avisoLogin")
        self.lbl_exito.setWordWrap(True)
        self.lbl_exito.hide()
        lay.addWidget(self.lbl_exito)

        fila = QHBoxLayout()
        fila.addStretch()
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("botonSecundario")
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_crear = QPushButton("Crear cuenta")
        self.btn_crear.setObjectName("botonPrimario")
        self.btn_crear.clicked.connect(self._crear)
        fila.addWidget(self.btn_cancelar)
        fila.addWidget(self.btn_crear)
        lay.addSpacing(8)
        lay.addLayout(fila)
        lay.addStretch()

    def _alternar_mostrar(self, visible: bool):
        modo = QLineEdit.Normal if visible else QLineEdit.Password
        self.txt_contrasena.setEchoMode(modo)
        self.txt_confirmar.setEchoMode(modo)

    def _sugerir_usuario(self):
        """Al terminar de escribir el correo, propone un usuario libre si todavía no se escribió uno."""
        if not self.txt_usuario.text().strip() and "@" in self.txt_correo.text():
            self.txt_usuario.setText(datos.sugerir_usuario(self.txt_correo.text()))

    def _crear(self):
        if self._creada:                        # ya se creó: el botón pasa a «Cerrar»
            self.accept()
            return
        self.lbl_error.hide()
        if self.txt_contrasena.text() != self.txt_confirmar.text():
            self.lbl_error.setText("Las contraseñas no coinciden.")
            self.lbl_error.show()
            return
        try:
            cuenta = datos.registrar_cuenta(self.txt_nombre.text(), self.txt_usuario.text(), self.txt_correo.text(),
                                            self.txt_contrasena.text(), self.combo_area.currentText(),
                                            self.combo_sucursal.currentText())
        except ValueError as error:
            self.lbl_error.setText(str(error))
            self.lbl_error.show()
            return
        texto = (f"¡Listo! Tu cuenta «{cuenta['usuario']}» fue creada. Ya puedes iniciar sesión con tu usuario "
                 "y tu contraseña.")
        if correo.modo() == "desarrollo":
            texto += ("\n\nModo desarrollo: no hay servidor de correo configurado, así que el correo de bienvenida "
                      "quedó en Administración → Correos enviados.")
        self._creada = True
        self.usuario_creado = cuenta["usuario"]
        for w in (self.txt_nombre, self.txt_correo, self.txt_usuario, self.txt_contrasena, self.txt_confirmar,
                  self.combo_area, self.combo_sucursal, self.chk_mostrar):
            w.setEnabled(False)
        self.txt_contrasena.clear()
        self.txt_confirmar.clear()
        self.lbl_exito.setText(texto)
        self.lbl_exito.show()
        self.btn_cancelar.hide()
        self.btn_crear.setText("Ir a iniciar sesión")
