from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QMessageBox, QStackedWidget, QWidget
)

import correo
import datos
from estilos import AZUL_OSCURO
from widgets.utiles import ajustar_a_pantalla, poner_con_scroll

PASO_USUARIO, PASO_CODIGO, PASO_CONTRASENA = 0, 1, 2
_TITULOS = ("Escribe tu usuario", "Escribe el código que te enviamos", "Elige tu nueva contraseña")


class DialogoRecuperacion(QDialog):
    """«¿Olvidaste tu contraseña?» en tres pantallas, una por paso:
    1) usuario o correo → se envía un código al correo registrado,
    2) código recibido → se comprueba antes de seguir,
    3) contraseña nueva (y su confirmación).
    El mensaje del paso 1 es el mismo exista o no la cuenta."""

    def __init__(self, identificador: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recuperar contraseña")
        ajustar_a_pantalla(self, 480, 380)
        self._construir_ui(identificador)

    # ------------------------------------------------------------------ interfaz
    def _construir_ui(self, identificador):
        cuerpo = QWidget()
        poner_con_scroll(self, cuerpo)
        lay = QVBoxLayout(cuerpo)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(6)

        titulo = QLabel("Recuperar contraseña")
        titulo.setStyleSheet(f"font-size:18px; font-weight:700; color:{AZUL_OSCURO};")
        lay.addWidget(titulo)
        self.lbl_paso = QLabel("")
        self.lbl_paso.setStyleSheet("color:#1E4D8C; font-weight:600;")
        lay.addWidget(self.lbl_paso)

        self.paginas = QStackedWidget()
        self.paginas.addWidget(self._pagina_usuario(identificador))
        self.paginas.addWidget(self._pagina_codigo())
        self.paginas.addWidget(self._pagina_contrasena())
        lay.addWidget(self.paginas, 1)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorLogin")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        lay.addWidget(self.lbl_error)
        self._mostrar_paso(PASO_USUARIO)

    def _texto(self, contenido: str) -> QLabel:
        e = QLabel(contenido)
        e.setWordWrap(True)
        e.setStyleSheet("color:#64748B; margin-bottom:4px;")
        return e

    def _campo(self, marcador: str, maximo: int, clave: bool = False) -> QLineEdit:
        c = QLineEdit()
        c.setPlaceholderText(marcador)
        c.setMaxLength(maximo)
        c.setMinimumHeight(34)
        if clave:
            c.setEchoMode(QLineEdit.Password)
        return c

    def _boton(self, texto: str, nombre: str, accion) -> QPushButton:
        b = QPushButton(texto)
        b.setObjectName(nombre)
        b.clicked.connect(accion)
        return b

    def _fila_botones(self, *botones) -> QHBoxLayout:
        f = QHBoxLayout()
        f.addStretch()
        for b in botones:
            f.addWidget(b)
        return f

    # Pantalla 1: usuario
    def _pagina_usuario(self, identificador) -> QWidget:
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(self._texto("Escribe tu usuario o tu correo y te enviaremos un código al correo registrado."))
        self.txt_usuario = self._campo("Usuario o correo", datos.LIM_CORREO)
        self.txt_usuario.setText(identificador)
        self.txt_usuario.returnPressed.connect(self._enviar_codigo)
        lay.addWidget(self.txt_usuario)
        lay.addStretch()
        self.btn_enviar = self._boton("Enviar código", "botonPrimario", self._enviar_codigo)
        lay.addLayout(self._fila_botones(self._boton("Cancelar", "botonSecundario", self.reject), self.btn_enviar))
        return p

    # Pantalla 2: código
    def _pagina_codigo(self) -> QWidget:
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(0, 8, 0, 0)
        self.lbl_envio = self._texto("")
        lay.addWidget(self.lbl_envio)
        lay.addWidget(self._texto(f"Escribe el código recibido. Vale {datos.CODIGO_VIGENCIA_MIN} minutos."))
        self.txt_codigo = self._campo("Código (ej. K7QM-3XPD)", 20)
        self.txt_codigo.returnPressed.connect(self._verificar_codigo)
        lay.addWidget(self.txt_codigo)
        self.btn_reenviar = self._boton("Reenviar código", "botonEnlace", self._reenviar_codigo)
        lay.addWidget(self.btn_reenviar)
        lay.addStretch()
        self.btn_verificar = self._boton("Verificar código", "botonPrimario", self._verificar_codigo)
        self.btn_atras = self._boton("Atrás", "botonSecundario", lambda: self._mostrar_paso(PASO_USUARIO))
        lay.addLayout(self._fila_botones(self.btn_atras, self.btn_verificar))
        return p

    # Pantalla 3: contraseña nueva
    def _pagina_contrasena(self) -> QWidget:
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(self._texto("El código es correcto. Elige tu nueva contraseña."))
        self.txt_nueva = self._campo(f"Contraseña nueva (mínimo {datos.MIN_CONTRASENA} caracteres)",
                                     datos.MAX_CONTRASENA, clave=True)
        self.txt_confirmar = self._campo("Repite la contraseña", datos.MAX_CONTRASENA, clave=True)
        self.txt_confirmar.returnPressed.connect(self._cambiar)
        lay.addWidget(self.txt_nueva)
        lay.addWidget(self.txt_confirmar)
        self.chk_mostrar = QCheckBox("Mostrar contraseñas")
        self.chk_mostrar.toggled.connect(self._alternar_mostrar)
        lay.addWidget(self.chk_mostrar)
        lay.addStretch()
        self.btn_cambiar = self._boton("Cambiar contraseña", "botonPrimario", self._cambiar)
        lay.addLayout(self._fila_botones(self._boton("Cancelar", "botonSecundario", self.reject), self.btn_cambiar))
        return p

    # ------------------------------------------------------------------ lógica
    def _mostrar_paso(self, paso: int):
        self.paginas.setCurrentIndex(paso)
        self.lbl_paso.setText(f"Paso {paso + 1} de 3 · {_TITULOS[paso]}")
        self.lbl_error.hide()
        foco = (self.txt_usuario, self.txt_codigo, self.txt_nueva)[paso]
        foco.setFocus()

    def _alternar_mostrar(self, visible: bool):
        modo = QLineEdit.Normal if visible else QLineEdit.Password
        self.txt_nueva.setEchoMode(modo)
        self.txt_confirmar.setEchoMode(modo)

    def _mostrar_error(self, texto: str):
        self.lbl_error.setText(texto)
        self.lbl_error.show()

    def _pedir_codigo(self) -> bool:
        ident = self.txt_usuario.text().strip()
        if not ident:
            self._mostrar_error("Escribe tu usuario o tu correo.")
            return False
        datos.solicitar_recuperacion(ident)
        # Mismo mensaje exista o no la cuenta: así nadie averigua qué usuarios hay.
        texto = ("Si existe una cuenta con ese usuario o correo, enviamos un código al correo registrado. "
                 "Revisa también tu carpeta de spam.")
        if correo.modo() == "desarrollo":
            carpeta = correo.carpeta_salida()
            texto += ("\n\nModo desarrollo: no hay servidor de correo configurado, así que no se envió nada a "
                      "Internet. El mensaje quedó en Administración → Correos enviados"
                      + (f" y en la carpeta {carpeta}." if carpeta else "."))
        self.lbl_envio.setText(texto)
        return True

    def _enviar_codigo(self):
        if self._pedir_codigo():
            self._mostrar_paso(PASO_CODIGO)

    def _reenviar_codigo(self):
        if self._pedir_codigo():
            self.lbl_error.hide()
            self.txt_codigo.clear()
            self.txt_codigo.setFocus()

    def _verificar_codigo(self):
        if not self.txt_codigo.text().strip():
            self._mostrar_error("Escribe el código que recibiste por correo.")
            return
        try:
            datos.verificar_codigo(self.txt_usuario.text().strip(), self.txt_codigo.text())
        except ValueError as error:
            self._mostrar_error(str(error))
            return
        self._mostrar_paso(PASO_CONTRASENA)

    def _cambiar(self):
        if self.txt_nueva.text() != self.txt_confirmar.text():
            self._mostrar_error("Las contraseñas no coinciden.")
            return
        try:
            datos.restablecer_con_codigo(self.txt_usuario.text().strip(), self.txt_codigo.text(), self.txt_nueva.text())
        except ValueError as error:
            self._mostrar_error(str(error))
            return
        QMessageBox.information(self, "Contraseña actualizada",
                                "Tu contraseña se actualizó. Ya puedes iniciar sesión con la nueva.")
        self.accept()
