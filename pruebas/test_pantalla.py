"""Las ventanas y diálogos se adaptan al tamaño de la pantalla (no se salen de ella)
y los botones importantes siguen a la vista. Se simulan pantallas de distintos
tamaños (ya descontada la barra de tareas) sustituyendo `area_disponible`.

Ejecutar:   python -m unittest discover -s pruebas -v
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QPushButton

import datos
from estilos import QSS_APP, paleta_clara
from ventana_login import VentanaLogin
from ventana_principal import VentanaPrincipal
from vistas.mesa_ti import DialogoNuevaConversacion
from widgets import utiles
from widgets.detalle_solicitud import DialogoDetalleSolicitud
from widgets.dialogo_usuario import DialogoUsuario

APP = QApplication.instance() or QApplication([])
APP.setStyle("Fusion")
APP.setPalette(paleta_clara())
APP.setStyleSheet(QSS_APP)

# (ancho, alto) del área útil: la captura del usuario (1920x1080 al 150 %), un portátil
# de 1366x768 al 125 % y al 150 %, y una pantalla muy pequeña.
PANTALLAS = [(1280, 686), (1093, 580), (910, 480), (800, 480)]


def cuenta(login):
    return next(u for u in datos.usuarios_todos() if u["usuario"] == login)


def pantalla(ancho, alto):
    return mock.patch.object(utiles, "area_disponible", lambda ventana: QRect(0, 0, ancho, alto))


class PruebasPantalla(unittest.TestCase):
    def setUp(self):
        datos.reiniciar()

    def _cabe(self, ventana, ancho, alto):
        self.assertLessEqual(ventana.width(), ancho - 2 * utiles.MARGEN_PANTALLA, "se sale a lo ancho")
        self.assertLessEqual(ventana.height() + utiles.ALTO_MARCO_VENTANA, alto - 2 * utiles.MARGEN_PANTALLA + utiles.ALTO_MARCO_VENTANA,
                             "se sale a lo alto")

    def test_pantalla_grande_conserva_el_tamano_original(self):
        with pantalla(2560, 1380):
            d = DialogoDetalleSolicitud("SIGSAT-0002", cuenta("sestrada"))
            self.assertEqual((d.width(), d.height()), (560, 680))
            self.assertEqual((DialogoUsuario().width(), DialogoUsuario().height()), (420, 530))

    def test_detalle_se_adapta_y_cerrar_siempre_se_ve(self):
        for ancho, alto in PANTALLAS:
            with self.subTest(pantalla=(ancho, alto)), pantalla(ancho, alto):
                # SIGSAT-0002 es la más alta: agente con el panel de acciones abierto
                d = DialogoDetalleSolicitud("SIGSAT-0002", cuenta("sestrada"))
                d.show()
                self._cabe(d, ancho, alto)
                self.assertLessEqual(d.height(), alto - 2 * utiles.MARGEN_PANTALLA - utiles.ALTO_MARCO_VENTANA)
                cerrar = next(b for b in d.findChildren(QPushButton) if b.text() == "Cerrar")
                self.assertTrue(cerrar.isVisible())
                abajo = cerrar.mapTo(d, cerrar.rect().bottomLeft()).y()
                self.assertLessEqual(abajo, d.height(), "el botón Cerrar queda fuera de la ventana")
                d.close()

    def test_el_contenido_del_detalle_no_se_desborda_hacia_la_derecha(self):
        """Ninguna etiqueta puede ser más ancha que el área visible (si no, el texto sale cortado)."""
        from PySide6.QtWidgets import QLabel
        casos = [("SIGSAT-0005", "areyes"), ("SIGSAT-0003", "areyes"), ("SIGSAT-0004", "dlopez"),
                 ("SIGSAT-0001", "areyes"), ("SIGSAT-0003", "direccion"), ("SIGSAT-0002", "sestrada")]
        with pantalla(1300, 900):
            for folio, login in casos:
                with self.subTest(folio=folio, usuario=login):
                    d = DialogoDetalleSolicitud(folio, cuenta(login))
                    d.show()
                    APP.processEvents()
                    visible = d._scroll.viewport().width()
                    self.assertLessEqual(d._contenido.width(), visible + 1, "el contenido es más ancho que la ventana")
                    for w in d._contenido.findChildren(QLabel):
                        if w.isVisible():
                            self.assertLessEqual(w.mapTo(d._contenido, w.rect().topRight()).x(), d._contenido.width() + 1,
                                                 f"«{w.text()[:40]}» se sale por la derecha")
                    # ninguna etiqueta con texto largo queda más baja que su texto (se recortaría una línea)
                    for w in d._contenido.findChildren(QLabel):
                        if w.isVisible() and w.wordWrap() and w.height() > 0:
                            self.assertGreaterEqual(w.height() + 2, w.heightForWidth(w.width()),
                                                    f"«{w.text()[:40]}» está comprimida: se recorta su texto")
                    d.close()

    def test_el_detalle_no_comprime_el_texto_en_pantallas_chicas(self):
        from PySide6.QtWidgets import QLabel
        for ancho, alto in PANTALLAS:
            for folio, login in (("SIGSAT-0005", "areyes"), ("SIGSAT-0002", "sestrada"), ("SIGSAT-0003", "direccion")):
                with self.subTest(pantalla=(ancho, alto), folio=folio), pantalla(ancho, alto):
                    d = DialogoDetalleSolicitud(folio, cuenta(login))
                    d.show()
                    APP.processEvents()
                    for w in d._contenido.findChildren(QLabel):
                        if w.isVisible() and w.wordWrap() and w.height() > 0:
                            self.assertGreaterEqual(w.height() + 2, w.heightForWidth(w.width()),
                                                    f"«{w.text()[:40]}» está comprimida")
                    d.close()

    def test_detalle_sigue_funcionando_tras_reconstruirse(self):
        with pantalla(910, 480):
            nueva = datos.crear_solicitud("Incidencia de hardware", "Mouse roto", cuenta("areyes"))
            d = DialogoDetalleSolicitud(nueva["folio"], cuenta("direccion"))     # sin técnico: aparece «Asignar»
            d.show()
            with mock.patch("widgets.detalle_solicitud.QMessageBox.information"):
                d.combo_agente.setCurrentIndex(0)
                d._asignar_agente()                          # reconstruye el contenido
            cerrar = [b for b in d.findChildren(QPushButton) if b.text() == "Cerrar"]
            self.assertEqual(len(cerrar), 1, "debe haber un único botón Cerrar")
            self.assertTrue(cerrar[0].isVisible())
            d.close()

    def test_dialogos_de_formulario_se_adaptan(self):
        ana = cuenta("areyes")
        for ancho, alto in PANTALLAS:
            with self.subTest(pantalla=(ancho, alto)), pantalla(ancho, alto):
                for dlg in (DialogoUsuario(), DialogoUsuario(usuario_existente=ana), DialogoNuevaConversacion(ana)):
                    dlg.show()
                    self._cabe(dlg, ancho, alto)
                    self.assertLessEqual(dlg.height(), alto - 2 * utiles.MARGEN_PANTALLA - utiles.ALTO_MARCO_VENTANA)
                    dlg.close()

    def test_login_y_ventana_principal_caben_en_pantallas_pequenas(self):
        for ancho, alto in PANTALLAS:
            with self.subTest(pantalla=(ancho, alto)), pantalla(ancho, alto):
                login = VentanaLogin()
                self.assertLessEqual(login.width(), ancho - 2 * utiles.MARGEN_PANTALLA)
                self.assertLessEqual(login.height(), alto - 2 * utiles.MARGEN_PANTALLA - utiles.ALTO_MARCO_VENTANA)
                for login in ("areyes", "sestrada", "direccion"):                   # los tres roles
                    principal = VentanaPrincipal(cuenta(login))
                    principal.show()
                    self.assertLessEqual(principal.width(), ancho - 2 * utiles.MARGEN_PANTALLA, login)
                    self.assertLessEqual(principal.height(), alto - 2 * utiles.MARGEN_PANTALLA - utiles.ALTO_MARCO_VENTANA, login)
                    # lo que la ventana EXIGE como mínimo también debe caber (si no, Qt la agrandaría)
                    self.assertLessEqual(principal.minimumSizeHint().width(), ancho - 2 * utiles.MARGEN_PANTALLA, login)
                    self.assertLessEqual(principal.minimumSizeHint().height(), alto - 2 * utiles.MARGEN_PANTALLA, login)
                    for i in range(len(principal.botones_menu)):
                        principal._mostrar(i)
                    principal._reloj.stop()
                    principal.close()

    def test_centrado(self):
        with pantalla(1280, 686):
            login = VentanaLogin()
            self.assertEqual(login.pos().x(), (1280 - login.width()) // 2)
            self.assertGreaterEqual(login.pos().y(), 0)


if __name__ == "__main__":
    unittest.main()
