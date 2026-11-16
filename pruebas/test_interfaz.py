"""Pruebas de humo de la interfaz: abre cada pantalla de cada rol sin mostrar
ventanas (Qt en modo "offscreen") y recorre los flujos principales.

Ejecutar:   python -m unittest discover -s pruebas -v      (requiere PySide6)
"""

import os
from datetime import timedelta
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QLabel

import datos
from estilos import QSS_APP, paleta_clara
from ventana_login import VentanaLogin
from ventana_principal import VentanaPrincipal
from vistas.bandeja_reportes import VistaBandejaReportes
from vistas.mesa_ti import VistaMesaTI
from vistas.nueva_solicitud import VistaNuevaSolicitud
from vistas.mis_solicitudes import VistaMisSolicitudes
from vistas.administracion import VistaAdministracion
from widgets.detalle_solicitud import DialogoDetalleSolicitud
from widgets.dialogo_usuario import DialogoUsuario

APP = QApplication.instance() or QApplication([])
APP.setStyle("Fusion")
APP.setPalette(paleta_clara())
APP.setStyleSheet(QSS_APP)


def cuenta(login):
    return next(u for u in datos.usuarios_todos() if u["usuario"] == login)


def sin_cuadros():
    """Evita que los QMessageBox bloqueen la prueba; devuelve el mock para revisarlos."""
    return mock.patch.multiple(QMessageBox, information=mock.DEFAULT, warning=mock.DEFAULT,
                               question=mock.DEFAULT, create=False)


class PruebasInterfaz(unittest.TestCase):
    def setUp(self):
        datos.reiniciar()

    def _textos(self, w):
        return " ".join(l.text() for l in w.findChildren(QLabel))

    # ----------------------------------------------------------------- login
    def test_login(self):
        v = VentanaLogin("Tu sesión expiró por inactividad.")
        self.assertFalse(v.lbl_aviso.isHidden())
        recibido = []
        v.acceso_concedido.connect(recibido.append)
        v.txt_usuario.setText("areyes")
        v.txt_contrasena.setText("mala")
        v._entrar()
        self.assertFalse(v.lbl_error.isHidden())
        self.assertEqual(recibido, [])
        v.txt_contrasena.setText("Rey_006")
        v._entrar()
        self.assertEqual(recibido[0]["rol"], "Representante de Área")
        self.assertNotIn("contrasena_hash", recibido[0])

    def test_login_bloqueado(self):
        v = VentanaLogin()
        for _ in range(5):
            v.txt_usuario.setText("areyes")
            v.txt_contrasena.setText("mala")
            v._entrar()
        self.assertIn("Demasiados intentos", v.lbl_error.text())
        v.txt_contrasena.setText("Rey_006")
        recibido = []
        v.acceso_concedido.connect(recibido.append)
        v._entrar()
        self.assertEqual(recibido, [])

    # ------------------------------------------------- ventana por rol/vistas
    def test_cada_rol_abre_todas_sus_pantallas(self):
        esperados = {"areyes": ["Nueva solicitud", "Mis solicitudes", "Mesa de Servicio"],
                     "sestrada": ["Mis reportes", "Mesa de Servicio"],
                     "direccion": ["Panel de indicadores", "Solicitudes", "Reportes", "Administración",
                                   "Mesa de Servicio"]}
        for login, nombres in esperados.items():
            with self.subTest(login):
                ventana = VentanaPrincipal(cuenta(login))
                self.assertEqual([b.text().strip() for b in ventana.botones_menu], nombres)
                for i in range(len(nombres)):
                    ventana._mostrar(i)
                ventana.grab()
                ventana.close()

    def test_cierre_por_inactividad(self):
        ventana = VentanaPrincipal(cuenta("areyes"), inactividad_s=-1)
        motivos = []
        ventana.cerrar_sesion.connect(motivos.append)
        ventana._revisar_inactividad()
        self.assertEqual(len(motivos), 1)
        self.assertIn("inactividad", motivos[0])
        ventana.close()
        activa = VentanaPrincipal(cuenta("areyes"))
        motivos = []
        activa.cerrar_sesion.connect(motivos.append)
        activa._revisar_inactividad()
        self.assertEqual(motivos, [])
        activa.close()

    # ---------------------------------------------------------- representante
    def test_nueva_solicitud(self):
        ana = cuenta("areyes")
        vista = VistaNuevaSolicitud(ana)
        self.assertFalse(hasattr(vista, "combo_prioridad"))
        self.assertFalse(hasattr(vista, "combo_area"), "el área es la del representante")
        self.assertIn("Contabilidad", vista.lbl_origen.text())
        self.assertIn("Matriz CDMX", vista.lbl_origen.text())
        vista.combo_tipo.setCurrentText("Solicitud de nuevo acceso")
        self.assertIn("Baja", vista.lbl_prioridad.text())
        vista.combo_tipo.setCurrentText("Incidencia de software")
        self.assertIn("Alta", vista.lbl_prioridad.text())

        antes = len(datos.solicitudes_de(ana["id"]))
        with mock.patch.object(QMessageBox, "warning") as aviso:
            vista._enviar()
            self.assertTrue(aviso.called)
        self.assertEqual(len(datos.solicitudes_de(ana["id"])), antes)

        vista.txt_descripcion.setPlainText("x" * 2500)
        self.assertEqual(len(vista.txt_descripcion.toPlainText()), datos.LIM_DESCRIPCION)

        vista.txt_descripcion.setPlainText("Necesito acceso a la VPN")
        recibidos = []
        vista.solicitud_creada.connect(recibidos.append)
        with mock.patch.object(QMessageBox, "information") as ok:
            vista._enviar()
            texto = ok.call_args[0][2]
            self.assertIn("SIGSAT-0008", texto)
            self.assertIn("Prioridad: Alta", texto)
            self.assertIn("administrador", texto.lower())
        self.assertEqual(recibidos, ["SIGSAT-0008"])
        self.assertEqual(len(datos.solicitudes_de(ana["id"])), antes + 1)
        self.assertEqual(vista.txt_descripcion.toPlainText(), "")
        nueva = datos.buscar_por_folio("SIGSAT-0008")
        self.assertEqual((nueva["estado"], nueva["asignada"], nueva["area"], nueva["sucursal"]),
                         ("Sin visualizar", False, "Contabilidad", "Matriz CDMX"))

    def test_mis_solicitudes_filtro_y_mensaje_vacio(self):
        vista = VistaMisSolicitudes(cuenta("areyes"))
        self.assertEqual(vista.tabla.rowCount(), 3)
        textos = [vista.tabla.item(f, 3).text() for f in range(3)]
        self.assertIn("Finalizado · califica el servicio", textos)        # la 0005 espera su calificación
        self.assertIn("Finalizado", textos)                              # la 0001 ya calificada
        self.assertIn("Sin visualizar", textos)                          # la 0003 sin asignar
        vista.combo_filtro.setCurrentText("En proceso")
        self.assertEqual(vista.tabla.rowCount(), 0)
        self.assertFalse(vista.lbl_vacio.isHidden())
        self.assertIn("En proceso", vista.lbl_vacio.text())

    def test_detalle_califica_solo_una_vez_y_solo_el_dueno(self):
        ana = cuenta("areyes")
        cambios = []
        d = DialogoDetalleSolicitud("SIGSAT-0005", ana, al_guardar=lambda: cambios.append(1))
        self.assertTrue(hasattr(d, "spin_calificacion"))
        d.spin_calificacion.setValue(3)
        with mock.patch.object(QMessageBox, "information") as ok:
            d._guardar_calificacion()
            self.assertIn("Gracias", ok.call_args[0][2])
        s = datos.buscar_por_folio("SIGSAT-0005")
        self.assertEqual((s["calificacion"], s["estado"]), (3, "Finalizado"))
        self.assertEqual(cambios, [1])
        # ya calificada / ajenas / no finalizadas: sin panel
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0005", ana), "spin_calificacion"))
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0001", ana), "spin_calificacion"))
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0003", ana), "spin_calificacion"))
        datos.reiniciar()
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0005", cuenta("cpena")), "spin_calificacion"))
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0005", cuenta("zarriaga")), "spin_calificacion"))

    def test_detalle_niega_solicitudes_ajenas(self):
        d = DialogoDetalleSolicitud("SIGSAT-0002", cuenta("areyes"))
        self.assertFalse(hasattr(d, "combo_estado"))
        self.assertIn("No tienes acceso", self._textos(d))

    def test_detalle_escapa_html(self):
        ana = cuenta("areyes")
        s = datos.crear_solicitud("Incidencia de software", "<b>negrita</b> & <script>", ana)
        d = DialogoDetalleSolicitud(s["folio"], ana)
        textos = self._textos(d)
        self.assertIn("&lt;b&gt;negrita&lt;/b&gt;", textos)
        self.assertNotIn("<script>", textos)

    # ---------------------------------------------------------- administrador
    def test_admin_asigna_y_reasigna_desde_el_detalle(self):
        admin = cuenta("direccion")
        cambios = []
        d = DialogoDetalleSolicitud("SIGSAT-0003", admin, al_guardar=lambda: cambios.append(1))
        self.assertTrue(hasattr(d, "combo_agente"))
        self.assertFalse(hasattr(d, "combo_estado"), "el administrador no cambia el estatus del técnico")
        d.combo_agente.setCurrentIndex(d.combo_agente.findData(cuenta("jmontes")["id"]))
        d.txt_motivo.setText("Carga ligera")
        with mock.patch.object(QMessageBox, "information") as info:
            d._asignar_agente()
            self.assertTrue(info.called)
        s = datos.buscar_por_folio("SIGSAT-0003")
        self.assertTrue(s["asignada"])
        self.assertEqual(s["agente_asignado"], cuenta("jmontes")["nombre"])
        self.assertEqual(s["estado"], "Sin visualizar")
        self.assertEqual(cambios, [1])
        self.assertEqual(d.btn_asignar.text(), "Reasignar")
        with mock.patch.object(QMessageBox, "information") as info:      # mismo técnico: sin cambios
            d._asignar_agente()
            self.assertIn("ya está asignada", info.call_args[0][2])
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0001", admin), "combo_agente"), "finalizada")

    # ---------------------------------------------------------------- técnico
    def test_tecnico_visualiza_al_abrir_y_avanza_solo_hacia_adelante(self):
        gabriel = cuenta("gsantiago")
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0007")["estado"], "Sin visualizar")
        refrescos = []
        d = DialogoDetalleSolicitud("SIGSAT-0007", gabriel, al_guardar=lambda: refrescos.append(1))
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0007")["estado"], "Visualizado")
        self.assertEqual(refrescos, [1])
        self.assertEqual([d.combo_estado.itemText(i) for i in range(d.combo_estado.count())],
                         ["Visualizado", "En proceso", "Finalizado"])
        with mock.patch.object(QMessageBox, "information") as info:      # sin cambios
            d._guardar_actualizacion_tecnico()
            self.assertTrue(info.called)
        d.combo_estado.setCurrentText("Finalizado")
        with mock.patch.object(QMessageBox, "warning") as aviso:         # finalizar exige comentario
            d._guardar_actualizacion_tecnico()
            self.assertTrue(aviso.called)
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0007")["estado"], "Visualizado")
        d.combo_estado.setCurrentText("En proceso")
        d.txt_comentario.setPlainText("Voy en camino")
        d._guardar_actualizacion_tecnico()
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0007")["estado"], "En proceso")
        d2 = DialogoDetalleSolicitud("SIGSAT-0007", gabriel)
        self.assertEqual([d2.combo_estado.itemText(i) for i in range(d2.combo_estado.count())],
                         ["En proceso", "Finalizado"])
        d2.combo_estado.setCurrentText("Finalizado")
        d2.txt_comentario.setPlainText("Listo")
        d2._guardar_actualizacion_tecnico()
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0007")["estado"], "Finalizado")
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0007", gabriel), "combo_estado"))

    def test_tecnico_no_ve_reportes_ajenos(self):
        d = DialogoDetalleSolicitud("SIGSAT-0004", cuenta("gsantiago"))      # es de dlopez
        self.assertFalse(hasattr(d, "combo_estado"))
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0004")["estado"], "Visualizado")
        self.assertIn("No tienes acceso", self._textos(d))

    def test_bandeja_del_tecnico_y_del_admin(self):
        vista = VistaBandejaReportes(cuenta("sestrada"))
        self.assertEqual(vista.tabla.rowCount(), 2)                      # la 0002 en curso y la 0001 ya Finalizada
        estados = {vista.tabla.item(i, 5).text() for i in range(vista.tabla.rowCount())}
        self.assertIn("Finalizado", estados)
        admin = VistaBandejaReportes(cuenta("direccion"))
        self.assertEqual(admin.tabla.rowCount(), 7)                      # incluye las 2 finalizadas
        admin.combo_estado.setCurrentText("Finalizado")
        admin.consultar()
        self.assertEqual(admin.tabla.rowCount(), 2)
        admin.limpiar_filtros()
        self.assertEqual(admin.tabla.rowCount(), 7)
        vista.grab()

    # ------------------------------------------------------- administración
    def test_administracion_baja_logica(self):
        vista = VistaAdministracion(cuenta("direccion"))
        total = vista.tabla.rowCount()
        self.assertEqual(total, 9)
        fila = next(f for f in range(total) if vista.tabla.item(f, 1).text() == "areyes")
        vista.tabla.selectRow(fila)
        self.assertTrue(vista.btn_editar.isEnabled() and vista.btn_eliminar.isEnabled())
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information") as info:
            vista._eliminar_cuenta()
            self.assertIn("desactivada", info.call_args[0][2])
        vista.tabla.selectRow(fila)
        self.assertTrue(vista.btn_editar.isEnabled())
        self.assertFalse(vista.btn_eliminar.isEnabled())
        fila_admin = next(f for f in range(total) if vista.tabla.item(f, 1).text() == "direccion")
        vista.tabla.selectRow(fila_admin)
        self.assertFalse(vista.btn_editar.isEnabled())

    def test_dialogo_usuario_validaciones_y_reactivar(self):
        d = DialogoUsuario()
        d.txt_nombre.setText("Luis Mora")
        d.txt_usuario.setText("lmora")
        d.txt_correo.setText("lmora@techsolve.mx")
        d.txt_contrasena.setText("corta")
        d._guardar()
        self.assertFalse(d.lbl_error.isHidden())
        self.assertIn("8 caracteres", d.lbl_error.text())
        d.txt_contrasena.setText("Clave-1234")
        d._guardar()
        self.assertEqual(d.result(), QDialog.Accepted)
        self.assertEqual(len(datos.usuarios_todos()), 10)
        nuevo = cuenta("lmora")
        self.assertEqual((nuevo["rol"], nuevo["area"], nuevo["sucursal"]), ("Representante de Área", "Contabilidad", "Matriz CDMX"))

        datos.eliminar_usuario(cuenta("areyes")["id"])
        editar = DialogoUsuario(usuario_existente=cuenta("areyes"))
        self.assertFalse(editar.chk_activa.isChecked())
        editar.chk_activa.setChecked(True)
        editar._guardar()
        self.assertTrue(cuenta("areyes")["activo"])

    # ------------------------------------------------------------------ mesa
    def test_mesa_de_servicio_representante_y_administracion(self):
        ana, admin = cuenta("areyes"), cuenta("direccion")
        vista_ana = VistaMesaTI(ana)
        self.assertEqual(vista_ana.lista.count(), 1)

        class FalsoDialogo:
            asunto, mensaje, folio = "Pregunta", "¿Cómo va?", "SIGSAT-0003"

            def __init__(self, *a, **k):
                pass

            def exec(self):
                return QDialog.Accepted

        with mock.patch("vistas.mesa_ti.DialogoNuevaConversacion", FalsoDialogo):
            vista_ana._nueva()
        self.assertEqual(vista_ana.conv_actual, "MESA-0004")
        self.assertEqual(vista_ana.lista.count(), 2)

        vista_a = VistaMesaTI(admin)
        self.assertEqual(vista_a.lista.count(), 4)
        vista_a.conv_actual = "MESA-0004"
        vista_a.actualizar()
        vista_a.txt_mensaje.setPlainText("Ya lo reviso")
        vista_a._enviar()
        self.assertEqual(datos.buscar_conversacion("MESA-0004")["mensajes"][-1]["texto"], "Ya lo reviso")
        vista_a.grab()
        vista_ana.actualizar()
        vista_ana.grab()
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            vista_a._cerrar()
        self.assertEqual(datos.buscar_conversacion("MESA-0004")["estado"], "Cerrada")
        self.assertFalse(vista_a.panel_entrada.isVisibleTo(vista_a))

    def test_mesa_de_servicio_tecnico_ve_solo_las_suyas(self):
        vista = VistaMesaTI(cuenta("sestrada"))
        self.assertEqual(vista.lista.count(), len(datos.conversaciones_visibles(cuenta("sestrada"))))
        vista.grab()


if __name__ == "__main__":
    unittest.main()
