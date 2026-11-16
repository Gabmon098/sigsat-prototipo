from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTabWidget, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import datos
from vistas.admin_catalogos import VistaCatalogos
from vistas.admin_correos import PestanaCorreos
from vistas.admin_respaldos import PestanaRespaldos
from widgets.dialogo_usuario import DialogoUsuario


class VistaAdministracion(QWidget):
    """Administración de usuarios y catálogos (áreas, tipos de solicitud)
    descrita en el documento como parte de las funciones del rol Administrador."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._construir_ui()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(10)

        titulo = QLabel("Administración")
        titulo.setObjectName("tituloVista")
        subtitulo = QLabel("Roles de las cuentas (que cada persona crea al registrarse), catálogos, correos y respaldos.")
        subtitulo.setObjectName("subtituloVista")
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._pestana_usuarios(), "Usuarios y roles")
        self.pestana_catalogos = VistaCatalogos(self.usuario)
        self.tabs.addTab(self.pestana_catalogos, "Catálogos")
        self.pestana_correos = PestanaCorreos(self.usuario)
        self.tabs.addTab(self.pestana_correos, "Correos enviados")
        self.pestana_respaldos = PestanaRespaldos(self.usuario)
        self.tabs.addTab(self.pestana_respaldos, "Respaldos")
        self.tabs.currentChanged.connect(lambda *_: self.actualizar())
        layout.addWidget(self.tabs)

    def actualizar(self):
        """Se llama al abrir la pantalla y al cambiar de pestaña: refresca lo que pudo cambiar en otra parte."""
        self._llenar_tabla()
        self.pestana_catalogos.actualizar()
        self.pestana_correos.actualizar()
        self.pestana_respaldos.actualizar()

    # ------------------------------------------------------------ usuarios
    def _pestana_usuarios(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        barra = QHBoxLayout()
        ayuda = QLabel("Cada persona crea su cuenta desde «Creación de cuenta» (entra como Representante de Área). "
                       "Aquí puedes cambiar su rol —por ejemplo a Técnico—, desactivarla o eliminarla. "
                       "Las cuentas de Administrador no se gestionan desde aquí.")
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color:#94A3B8; font-size:11px;")
        barra.addWidget(ayuda)
        barra.addStretch()

        self.btn_editar = QPushButton("Editar")
        self.btn_editar.setObjectName("botonSecundario")
        self.btn_editar.setEnabled(False)
        self.btn_editar.clicked.connect(self._editar_cuenta)

        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_eliminar.setObjectName("botonSecundario")
        self.btn_eliminar.setEnabled(False)
        self.btn_eliminar.clicked.connect(self._eliminar_cuenta)

        barra.addWidget(self.btn_editar)
        barra.addWidget(self.btn_eliminar)
        lay.addLayout(barra)

        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(["Nombre", "Usuario", "Rol", "Área", "Sucursal", "Correo", "Cuenta"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.itemSelectionChanged.connect(self._actualizar_botones)
        self.tabla.cellDoubleClicked.connect(lambda *_: self._editar_cuenta())
        lay.addWidget(self.tabla)

        self._llenar_tabla()
        return w

    def _llenar_tabla(self):
        cuentas = datos.usuarios_todos()
        self.tabla.setRowCount(len(cuentas))
        for fila, u in enumerate(cuentas):
            valores = [u["nombre"], u["usuario"], u["rol"], u["area"] or "—", u["sucursal"] or "—", u["correo"],
                       "Activa" if u["activo"] else "Inactiva"]
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setData(Qt.UserRole, u["id"])
                if not u["activo"]:
                    item.setForeground(QColor("#64748B"))     # fila atenuada: cuenta desactivada
                self.tabla.setItem(fila, col, item)
        self._actualizar_botones()

    def _cuenta_seleccionada(self):
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return datos.buscar_usuario(self.tabla.item(filas[0].row(), 0).data(Qt.UserRole))

    def _actualizar_botones(self):
        cuenta = self._cuenta_seleccionada()
        gestionable = cuenta is not None and cuenta["rol"] != "Administrador"
        self.btn_editar.setEnabled(gestionable)
        # Una cuenta ya inactiva no se vuelve a eliminar; se reactiva desde «Editar».
        self.btn_eliminar.setEnabled(gestionable and cuenta["activo"])

    def _editar_cuenta(self):
        cuenta = self._cuenta_seleccionada()
        if not cuenta or cuenta["rol"] == "Administrador":
            return
        dialogo = DialogoUsuario(usuario_existente=cuenta, parent=self)
        if dialogo.exec():
            self._llenar_tabla()

    def _eliminar_cuenta(self):
        cuenta = self._cuenta_seleccionada()
        if not cuenta or cuenta["rol"] == "Administrador" or not cuenta["activo"]:
            return
        aviso = f"¿Eliminar la cuenta de {cuenta['nombre']} ({cuenta['usuario']})?"
        if datos.cuenta_referenciada(cuenta["id"]):
            aviso += ("\n\nEsta persona aparece en solicitudes o conversaciones existentes; "
                      "su nombre se conservará en el historial, pero ya no podrá iniciar sesión.")
        respuesta = QMessageBox.question(
            self, "Eliminar cuenta", aviso, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if respuesta != QMessageBox.Yes:
            return
        resultado = datos.eliminar_usuario(cuenta["id"])
        if resultado == "eliminada":
            QMessageBox.information(self, "Cuenta eliminada", f"La cuenta de {cuenta['nombre']} fue eliminada.")
        else:
            QMessageBox.information(
                self, "Cuenta desactivada",
                f"La cuenta de {cuenta['nombre']} quedó desactivada: su nombre se conserva en el "
                "historial, pero ya no puede iniciar sesión. Puedes reactivarla desde «Editar».")
        self._llenar_tabla()
