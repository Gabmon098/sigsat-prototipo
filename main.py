import argparse
import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

import correo
import persistencia
from estilos import QSS_APP, paleta_clara
from ventana_login import VentanaLogin
from ventana_principal import VentanaPrincipal


class AplicacionSigsat:
    """Controla el flujo entre la ventana de login y la ventana principal,
    permitiendo cerrar sesión y volver a entrar con otro rol/usuario para
    poder demostrar los tres flujos (Representante de Área, Técnico, Administrador)
    dentro de una sola ejecución del prototipo."""

    def __init__(self):
        self.ventana_login = None
        self.ventana_principal = None
        self._mostrar_login()

    # Siempre se abre la ventana nueva ANTES de cerrar la anterior: así nunca
    # hay un instante sin ventanas visibles (Qt cierra la app al cerrar la última).
    def _mostrar_login(self, aviso: str = ""):
        self.ventana_login = VentanaLogin(aviso)
        self.ventana_login.acceso_concedido.connect(self._entrar)
        self.ventana_login.show()

    def _entrar(self, usuario: dict):
        login = self.ventana_login
        self.ventana_principal = VentanaPrincipal(usuario)
        self.ventana_principal.cerrar_sesion.connect(self._salir)
        self.ventana_principal.show()
        login.close()

    def _salir(self, motivo: str = ""):
        principal = self.ventana_principal
        self.ventana_principal = None
        self._mostrar_login(motivo)
        principal.close()


_HORA_MS = 60 * 60 * 1000


def _iniciar_persistencia(app: QApplication, reiniciar: bool) -> None:
    """Carga los datos guardados (o crea los de ejemplo), activa el guardado automático y programa el
    respaldo diario: uno al abrir, uno cada día si la aplicación queda abierta y uno al cerrar."""
    try:
        resultado = persistencia.activar(reiniciar=reiniciar)
    except OSError as error:
        QMessageBox.warning(None, "No se pueden guardar los datos",
                            f"No se pudo usar la carpeta de datos ({error}).\n\n"
                            "SIGSAT se abrirá SIN guardar: al cerrarlo se perderán los cambios.")
        return
    if resultado == "actualizado":
        QMessageBox.information(
            None, "Aplicación actualizada",
            "Los datos guardados eran de una versión anterior de SIGSAT y no son compatibles con esta.\n\n"
            "Se guardó una copia en la carpeta «respaldos» y la aplicación se abrió con los datos de ejemplo "
            "nuevos (con las cuentas de demostración actualizadas).")
    elif resultado == "recuperado":
        QMessageBox.warning(None, "Datos recuperados",
                            "El archivo de datos estaba dañado. Se conservó una copia (estado_danado_*.json) "
                            "y se restauró el último respaldo.")
    elif resultado == "nuevo" and (persistencia.carpeta() / "estado.json").exists() and any(
            persistencia.carpeta().glob("estado_danado_*.json")):
        QMessageBox.warning(None, "Datos reiniciados",
                            "El archivo de datos estaba dañado y no había un respaldo utilizable. "
                            "Se abrieron los datos de ejemplo (el archivo dañado se conservó).")

    def respaldar():
        try:
            persistencia.respaldo_diario()
        except Exception:
            logging.getLogger("sigsat").exception("No se pudo crear el respaldo diario")

    respaldar()
    reloj = QTimer(app)
    reloj.setInterval(_HORA_MS)
    reloj.timeout.connect(respaldar)
    reloj.start()
    app.aboutToQuit.connect(lambda: (persistencia.guardar(), respaldar()))


def main():
    parser = argparse.ArgumentParser(description="SIGSAT — prototipo de escritorio")
    parser.add_argument("--reiniciar", action="store_true",
                        help="descarta los datos guardados y vuelve a los datos de ejemplo (antes hace un respaldo)")
    parser.add_argument("--sin-guardar", action="store_true",
                        help="no guarda nada en disco: se parte de los datos de ejemplo y se pierden al cerrar")
    args, resto = parser.parse_known_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    app = QApplication([sys.argv[0]] + resto)
    app.setStyle("Fusion")
    # Paleta clara explícita: evita que el modo oscuro de Windows deje
    # menús, tooltips o cuadros de diálogo con fondo negro y texto oscuro.
    app.setPalette(paleta_clara())
    app.setStyleSheet(QSS_APP)

    correo.configurar(asincrono=True)          # el correo se envía en segundo plano: la ventana nunca espera
    if not args.sin_guardar:
        _iniciar_persistencia(app, args.reiniciar)

    controlador = AplicacionSigsat()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
