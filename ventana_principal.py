import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer

from estilos import AZUL_OSCURO
from widgets.utiles import ajustar_a_pantalla, crear_area_desplazable
from vistas.nueva_solicitud import VistaNuevaSolicitud
from vistas.mis_solicitudes import VistaMisSolicitudes
from vistas.bandeja_reportes import VistaBandejaReportes
from vistas.dashboard_admin import VistaDashboardAdmin
from vistas.administracion import VistaAdministracion
from vistas.mesa_ti import VistaMesaTI
from vistas.solicitudes_admin import VistaSolicitudesAdmin
from permisos import ROL_REPRESENTANTE, ROL_TECNICO, ROL_ADMINISTRADOR


# Cada entrada: (etiqueta del menú, fábrica de la vista)
MENU_POR_ROL = {
    ROL_REPRESENTANTE: [
        ("Nueva solicitud", lambda u: VistaNuevaSolicitud(u)),
        ("Mis solicitudes", lambda u: VistaMisSolicitudes(u)),
        ("Mesa de Servicio", lambda u: VistaMesaTI(u)),
    ],
    ROL_TECNICO: [
        ("Mis reportes", lambda u: VistaBandejaReportes(u)),
        ("Mesa de Servicio", lambda u: VistaMesaTI(u)),
    ],
    ROL_ADMINISTRADOR: [
        ("Panel de indicadores", lambda u: VistaDashboardAdmin(u)),
        ("Solicitudes", lambda u: VistaSolicitudesAdmin(u)),
        ("Reportes", lambda u: VistaBandejaReportes(u)),
        ("Administración", lambda u: VistaAdministracion(u)),
        ("Mesa de Servicio", lambda u: VistaMesaTI(u)),
    ],
}


SESION_INACTIVIDAD_S = 2 * 60 * 60      # la sesión se cierra tras 2 h sin actividad (igual que la web)
_EVENTOS_ACTIVIDAD = (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel)


class VentanaPrincipal(QMainWindow):
    # El texto indica el motivo (vacío = cierre normal); se muestra en el login.
    cerrar_sesion = Signal(str)

    def __init__(self, usuario: dict, inactividad_s: int = SESION_INACTIVIDAD_S):
        super().__init__()
        self.usuario = usuario
        self._inactividad_s = inactividad_s
        self.setWindowTitle(f"SIGSAT — {usuario['nombre']} ({usuario['rol']})")
        ajustar_a_pantalla(self, 1180, 720, centrar=True, limitar=False)   # cabe en la pantalla; se puede maximizar
        self._construir_ui()
        self._iniciar_control_inactividad()

    # --------------------------------------------- caducidad por inactividad
    def _iniciar_control_inactividad(self):
        self._ultima_actividad = time.monotonic()
        QApplication.instance().installEventFilter(self)
        self._reloj = QTimer(self)
        self._reloj.setInterval(30_000)
        self._reloj.timeout.connect(self._revisar_inactividad)
        self._reloj.start()

    def eventFilter(self, objeto, evento):
        if evento.type() in _EVENTOS_ACTIVIDAD:
            self._ultima_actividad = time.monotonic()
        return False

    def _revisar_inactividad(self):
        if time.monotonic() - self._ultima_actividad > self._inactividad_s:
            self._reloj.stop()
            self.cerrar_sesion.emit("Tu sesión expiró por inactividad. Inicia sesión de nuevo.")

    def closeEvent(self, evento):
        self._reloj.stop()
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(evento)

    def _construir_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._construir_sidebar())

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.vistas_cargadas = {}
        self._vistas = []
        opciones = MENU_POR_ROL.get(self.usuario["rol"], [])
        for etiqueta, fabrica in opciones:
            vista = fabrica(self.usuario)
            self.vistas_cargadas[etiqueta] = vista
            self._vistas.append(vista)
            # Cada pantalla va dentro de un área desplazable: si la ventana (o la pantalla) es más chica de lo
            # que la pantalla necesita, aparece una barra de desplazamiento en vez de salirse de la pantalla.
            self.stack.addWidget(crear_area_desplazable(vista))

        if self.botones_menu:
            self.botones_menu[0].setChecked(True)
            self.stack.setCurrentIndex(0)

    def _construir_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop)

        titulo = QLabel("SIGSAT")
        titulo.setObjectName("sidebarTitulo")
        subtitulo = QLabel(f"{self.usuario['nombre']}\nRol: {self.usuario['rol']}")
        subtitulo.setObjectName("sidebarSubtitulo")
        lay.addWidget(titulo)
        lay.addWidget(subtitulo)

        self.grupo_botones = QButtonGroup(self)
        self.grupo_botones.setExclusive(True)
        self.botones_menu = []

        opciones = MENU_POR_ROL.get(self.usuario["rol"], [])
        for indice, (etiqueta, _fabrica) in enumerate(opciones):
            btn = QPushButton(etiqueta)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked, i=indice: self._mostrar(i))
            self.grupo_botones.addButton(btn)
            self.botones_menu.append(btn)
            lay.addWidget(btn)

        lay.addStretch()

        btn_salir = QPushButton("Cerrar sesión")
        btn_salir.setCursor(Qt.PointingHandCursor)
        btn_salir.clicked.connect(lambda: self.cerrar_sesion.emit(""))
        lay.addWidget(btn_salir)
        lay.addSpacing(10)

        return sidebar

    def _mostrar(self, indice: int):
        self.stack.setCurrentIndex(indice)
        vista_actual = self._vistas[indice]
        if hasattr(vista_actual, "actualizar"):
            vista_actual.actualizar()
