from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QCheckBox
)
from PySide6.QtCore import Qt, Signal

import datos
from estilos import AZUL_OSCURO, BLANCO
from seguridad import BloqueoTemporal
from widgets.dialogo_recuperacion import DialogoRecuperacion
from widgets.dialogo_registro import DialogoRegistro
from widgets.utiles import ajustar_a_pantalla


class VentanaLogin(QWidget):
    """Inicio de sesión con usuario (o correo) y contraseña. El rol y los
    permisos los determina la cuenta autenticada, no una selección manual."""

    acceso_concedido = Signal(dict)

    def __init__(self, aviso: str = ""):
        super().__init__()
        self.setWindowTitle("SIGSAT — Acceso")
        ajustar_a_pantalla(self, 920, 580, centrar=True, limitar=False)
        self._construir_ui()
        if aviso:                      # p. ej. "Tu sesión expiró por inactividad"
            self.lbl_aviso.setText(aviso)
            self.lbl_aviso.show()

    def _construir_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        panel_izq = QFrame()
        panel_izq.setObjectName("panelLoginIzq")
        panel_izq.setFixedWidth(360)
        lay_izq = QVBoxLayout(panel_izq)
        lay_izq.setContentsMargins(40, 60, 40, 40)
        lay_izq.setAlignment(Qt.AlignTop)

        titulo = QLabel("SIGSAT")
        titulo.setStyleSheet(f"color:{BLANCO}; font-size: 34px; font-weight: 800;")
        subtitulo = QLabel("Sistema de Gestión de Solicitudes\ny Seguimiento de Atención de Tickets")
        subtitulo.setWordWrap(True)
        subtitulo.setStyleSheet("color:#C9D6EA; font-size: 13px; margin-top: 6px;")

        lay_izq.addWidget(titulo)
        lay_izq.addWidget(subtitulo)
        lay_izq.addStretch()
        

        panel_der = QFrame()
        panel_der.setObjectName("panelLoginDer")
        lay_der = QVBoxLayout(panel_der)
        lay_der.setContentsMargins(70, 60, 70, 40)
        lay_der.setAlignment(Qt.AlignTop)

        encabezado = QLabel("Iniciar sesión")
        encabezado.setStyleSheet(f"font-size: 22px; font-weight: 700; color:{AZUL_OSCURO};")
        ayuda = QLabel("Ingresa con tu cuenta.")
        ayuda.setStyleSheet("color:#64748B; margin-bottom: 20px;")
        ayuda.setWordWrap(True)

        self.txt_usuario = QLineEdit()
        self.txt_usuario.setPlaceholderText("Usuario o correo")
        self.txt_usuario.setMinimumHeight(36)

        self.txt_contrasena = QLineEdit()
        self.txt_contrasena.setPlaceholderText("Contraseña")
        self.txt_contrasena.setEchoMode(QLineEdit.Password)
        self.txt_contrasena.setMinimumHeight(36)

        self.chk_mostrar = QCheckBox("Mostrar contraseña")
        self.chk_mostrar.toggled.connect(
            lambda v: self.txt_contrasena.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password))

        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setObjectName("avisoLogin")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.hide()

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorLogin")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        btn_entrar = QPushButton("Entrar")
        btn_entrar.setObjectName("botonPrimario")
        btn_entrar.setCursor(Qt.PointingHandCursor)
        btn_entrar.setMinimumHeight(38)
        btn_entrar.clicked.connect(self._entrar)
        self.txt_usuario.returnPressed.connect(self._entrar)
        self.txt_contrasena.returnPressed.connect(self._entrar)

        lay_der.addWidget(encabezado)
        lay_der.addWidget(ayuda)
        lay_der.addWidget(QLabel("Usuario o correo"))
        lay_der.addWidget(self.txt_usuario)
        lay_der.addSpacing(12)
        lay_der.addWidget(QLabel("Contraseña"))
        lay_der.addWidget(self.txt_contrasena)
        lay_der.addWidget(self.chk_mostrar)
        lay_der.addWidget(self.lbl_aviso)
        lay_der.addWidget(self.lbl_error)
        lay_der.addSpacing(16)
        lay_der.addWidget(btn_entrar)

        self.btn_olvide = QPushButton("¿Olvidaste tu contraseña?")
        self.btn_olvide.setObjectName("botonEnlace")
        self.btn_olvide.setCursor(Qt.PointingHandCursor)
        self.btn_olvide.clicked.connect(self._recuperar)
        lay_der.addWidget(self.btn_olvide)

        self.btn_registro = QPushButton("Creación de cuenta")
        self.btn_registro.setObjectName("botonEnlace")
        self.btn_registro.setCursor(Qt.PointingHandCursor)
        self.btn_registro.clicked.connect(self._crear_cuenta)
        lay_der.addWidget(self.btn_registro)
        lay_der.addStretch()


        layout.addWidget(panel_izq)
        layout.addWidget(panel_der, 1)
        self.txt_usuario.setFocus()

    def _recuperar(self):
        dialogo = DialogoRecuperacion(self.txt_usuario.text().strip(), parent=self)
        if dialogo.exec():
            self.lbl_error.hide()
            self.lbl_aviso.setText("Tu contraseña se actualizó. Inicia sesión con la nueva.")
            self.lbl_aviso.show()
            self.txt_contrasena.clear()
            self.txt_contrasena.setFocus()

    def _crear_cuenta(self):
        dialogo = DialogoRegistro(parent=self)
        dialogo.exec()
        if dialogo.usuario_creado:             # la cuenta ya existe: se deja el usuario listo para entrar
            self.lbl_error.hide()
            self.txt_usuario.setText(dialogo.usuario_creado)
            self.lbl_aviso.setText("Tu cuenta fue creada. Inicia sesión con tu usuario y tu contraseña.")
            self.lbl_aviso.show()
            self.txt_contrasena.clear()
            self.txt_contrasena.setFocus()

    def _mostrar_error(self, texto: str):
        self.lbl_aviso.hide()
        self.lbl_error.setText(texto)
        self.lbl_error.show()
        self.txt_contrasena.clear()
        self.txt_contrasena.setFocus()

    def _entrar(self):
        identificador = self.txt_usuario.text().strip()
        contrasena = self.txt_contrasena.text()
        if not identificador or not contrasena:
            self._mostrar_error("Usuario o contraseña incorrectos.")
            return
        try:
            usuario = datos.autenticar(identificador, contrasena)
        except BloqueoTemporal as bloqueo:
            self._mostrar_error(
                f"Demasiados intentos fallidos. Intenta de nuevo en {bloqueo.segundos} segundos.")
            return
        if usuario is None:
            self._mostrar_error("Usuario o contraseña incorrectos.")
            return
        self.lbl_error.hide()
        self.lbl_aviso.hide()
        self.txt_contrasena.clear()
        self.acceso_concedido.emit(usuario)
