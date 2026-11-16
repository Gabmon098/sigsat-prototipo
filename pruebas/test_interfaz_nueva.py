"""Pruebas de humo y de flujo de la interfaz nueva (Qt en modo «offscreen»): recuperación de contraseña,
adjuntos, asignación, catálogos, reportes, correos y respaldos."""

import os
import sys
import tempfile
from datetime import timedelta
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QPushButton, QWidget

import archivos
import correo
import datos
import persistencia
from estilos import QSS_APP, paleta_clara
from pruebas.base import cuenta
from ventana_login import VentanaLogin
from vistas.administracion import VistaAdministracion
from vistas.dashboard_admin import PanelIndicadores as VistaDashboardAdmin
from vistas.mis_solicitudes import VistaMisSolicitudes
from vistas.nueva_solicitud import VistaNuevaSolicitud
from vistas.reportes_vista import VistaAnaliticaReportes as VistaReportes
from vistas.solicitudes_admin import VistaSolicitudesAdmin
from widgets.detalle_solicitud import DialogoDetalleSolicitud
from widgets.dialogo_recuperacion import DialogoRecuperacion
from widgets.dialogos_catalogo import DialogoArea, DialogoSucursal, DialogoTipo

APP = QApplication.instance() or QApplication([])
APP.setStyle("Fusion")
APP.setPalette(paleta_clara())
APP.setStyleSheet(QSS_APP)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


class Base(unittest.TestCase):
    def setUp(self):
        persistencia.desactivar()
        correo.reiniciar()
        datos.reiniciar()
        self.buzon = []
        correo.configurar(transporte=lambda m: self.buzon.append(m))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.admin, self.ana = cuenta("direccion"), cuenta("areyes")
        self.sebastian, self.gabriel = cuenta("sestrada"), cuenta("gsantiago")

    def tearDown(self):
        persistencia.desactivar()
        correo.reiniciar()

    def archivo(self, nombre, contenido):
        ruta = Path(self.tmp.name) / nombre
        ruta.write_bytes(contenido)
        return str(ruta)

    @staticmethod
    def botones(widget, texto):
        return [b for b in widget.findChildren(QPushButton) if b.text() == texto]


class PruebasRecuperacionUI(Base):
    def test_el_login_tiene_el_enlace_de_recuperacion(self):
        v = VentanaLogin()
        self.assertEqual(v.btn_olvide.text(), "¿Olvidaste tu contraseña?")
        v.txt_usuario.setText("dlopez")
        with mock.patch("ventana_login.DialogoRecuperacion") as clase:
            clase.return_value.exec.return_value = QDialog.Accepted
            v.btn_olvide.click()
            self.assertEqual(clase.call_args[0][0], "dlopez")            # lleva lo que ya escribió
        self.assertFalse(v.lbl_aviso.isHidden())
        self.assertIn("se actualizó", v.lbl_aviso.text())

    def test_flujo_completo_de_recuperacion_en_tres_pantallas(self):
        from widgets.dialogo_recuperacion import PASO_USUARIO, PASO_CODIGO, PASO_CONTRASENA
        d = DialogoRecuperacion()
        self.assertEqual(d.paginas.count(), 3)
        self.assertEqual(d.paginas.currentIndex(), PASO_USUARIO)
        self.assertIn("Paso 1 de 3", d.lbl_paso.text())
        d.txt_usuario.setText("dlopez")
        d._enviar_codigo()
        self.assertEqual(d.paginas.currentIndex(), PASO_CODIGO)
        self.assertIn("Paso 2 de 3", d.lbl_paso.text())
        self.assertIn("Si existe una cuenta", d.lbl_envio.text())
        self.assertEqual(len(self.buzon), 1)
        import re
        codigo = re.search(r"[A-Z2-9]{4}-[A-Z2-9]{4}", self.buzon[0].get_content()).group(0)

        d.txt_codigo.setText("AAAA-BBBB")                       # código equivocado: no avanza
        d._verificar_codigo()
        self.assertEqual(d.paginas.currentIndex(), PASO_CODIGO)
        self.assertIn("no es válido", d.lbl_error.text())
        d.txt_codigo.setText(codigo)
        d._verificar_codigo()
        self.assertEqual(d.paginas.currentIndex(), PASO_CONTRASENA)
        self.assertIn("Paso 3 de 3", d.lbl_paso.text())
        self.assertTrue(d.lbl_error.isHidden())

        d.txt_nueva.setText("NuevaClave-99")
        d.txt_confirmar.setText("otra-distinta")
        d._cambiar()
        self.assertIn("no coinciden", d.lbl_error.text())
        d.txt_confirmar.setText("NuevaClave-99")
        with mock.patch.object(QMessageBox, "information"):
            d._cambiar()
        self.assertEqual(d.result(), QDialog.Accepted)
        self.assertIsNotNone(datos.autenticar("dlopez", "NuevaClave-99"))

    def test_verificar_el_codigo_no_lo_consume(self):
        datos.solicitar_recuperacion("dlopez")
        import re
        codigo = re.search(r"[A-Z2-9]{4}-[A-Z2-9]{4}", self.buzon[0].get_content()).group(0)
        datos.verificar_codigo("dlopez", codigo)
        datos.verificar_codigo("dlopez", codigo)                  # sigue siendo válido
        datos.restablecer_con_codigo("dlopez", codigo, "NuevaClave-99")
        with self.assertRaises(ValueError):                       # ya se usó
            datos.verificar_codigo("dlopez", codigo)

    def test_verificar_el_codigo_cuenta_los_intentos_equivocados(self):
        datos.solicitar_recuperacion("dlopez")
        for _ in range(datos.CODIGO_MAX_INTENTOS):
            with self.assertRaises(ValueError):
                datos.verificar_codigo("dlopez", "AAAA-BBBB")
        import re
        codigo = re.search(r"[A-Z2-9]{4}-[A-Z2-9]{4}", self.buzon[0].get_content()).group(0)
        with self.assertRaises(ValueError):                       # el código quedó anulado
            datos.verificar_codigo("dlopez", codigo)

    def test_atras_y_reenviar_en_la_recuperacion(self):
        from widgets.dialogo_recuperacion import PASO_USUARIO, PASO_CODIGO
        d = DialogoRecuperacion()
        d.txt_usuario.setText("dlopez")
        d._enviar_codigo()
        d.btn_atras.click()
        self.assertEqual(d.paginas.currentIndex(), PASO_USUARIO)
        d._enviar_codigo()
        d._reenviar_codigo()
        self.assertEqual(d.paginas.currentIndex(), PASO_CODIGO)
        self.assertEqual(len(self.buzon), 3)

    def test_el_mensaje_es_el_mismo_exista_o_no_la_cuenta(self):
        textos = []
        for ident in ("dlopez", "noexiste"):
            d = DialogoRecuperacion()
            d.txt_usuario.setText(ident)
            d._enviar_codigo()
            textos.append(d.lbl_envio.text())
        self.assertEqual(textos[0], textos[1])

    def test_errores_en_el_dialogo(self):
        from widgets.dialogo_recuperacion import PASO_USUARIO, PASO_CODIGO, PASO_CONTRASENA
        d = DialogoRecuperacion()
        d._enviar_codigo()
        self.assertIn("Escribe tu usuario", d.lbl_error.text())
        self.assertEqual(d.paginas.currentIndex(), PASO_USUARIO)
        d.txt_usuario.setText("dlopez")
        d._enviar_codigo()
        d._verificar_codigo()
        self.assertIn("Escribe el código", d.lbl_error.text())
        self.assertEqual(d.paginas.currentIndex(), PASO_CODIGO)
        import re
        codigo = re.search(r"[A-Z2-9]{4}-[A-Z2-9]{4}", self.buzon[0].get_content()).group(0)
        d.txt_codigo.setText(codigo)
        d._verificar_codigo()
        self.assertEqual(d.paginas.currentIndex(), PASO_CONTRASENA)
        d.txt_nueva.setText("corta")
        d.txt_confirmar.setText("corta")
        d._cambiar()
        self.assertIn("8 caracteres", d.lbl_error.text())
        self.assertNotEqual(d.result(), QDialog.Accepted)

    def test_en_modo_desarrollo_se_explica_donde_quedo_el_correo(self):
        correo.configurar(transporte=None)
        os.environ.pop("SIGSAT_SMTP_HOST", None)
        d = DialogoRecuperacion()
        d.txt_usuario.setText("dlopez")
        d._enviar_codigo()
        self.assertIn("Modo desarrollo", d.lbl_envio.text())
        self.assertIn("Correos enviados", d.lbl_envio.text())

    def test_mostrar_contrasenas(self):
        d = DialogoRecuperacion()
        d.chk_mostrar.setChecked(True)
        self.assertEqual(d.txt_nueva.echoMode(), d.txt_nueva.EchoMode.Normal)
        d.chk_mostrar.setChecked(False)
        self.assertEqual(d.txt_confirmar.echoMode(), d.txt_confirmar.EchoMode.Password)


class PruebasAdjuntosUI(Base):
    def test_nueva_solicitud_con_adjuntos(self):
        v = VistaNuevaSolicitud(self.ana)
        from PySide6.QtWidgets import QLabel
        self.assertTrue(any("solo se pueden agregar ahora" in w.text() for w in v.findChildren(QLabel)),
                        "el formulario explica que los archivos solo se adjuntan al registrar la solicitud")
        v._agregar_rutas([self.archivo("captura.png", PNG), self.archivo("error.log", b"Traceback")])
        self.assertEqual(v.lista_adjuntos.count(), 2)
        self.assertIn("2 de 5", v.lbl_ayuda_adjuntos.text())
        v.lista_adjuntos.setCurrentRow(0)
        v._quitar_adjunto()
        self.assertEqual(v.lista_adjuntos.count(), 1)
        v.txt_descripcion.setPlainText("Con adjunto")
        with mock.patch.object(QMessageBox, "information"):
            v._enviar()
        s = datos.solicitudes_de(self.ana["id"])[0]
        self.assertEqual(s["n_adjuntos"], 1)
        self.assertEqual(v.lista_adjuntos.count(), 0, "la lista se limpia al enviar")

    def test_archivos_invalidos_se_explican_y_no_se_agregan(self):
        v = VistaNuevaSolicitud(self.ana)
        with mock.patch.object(QMessageBox, "warning") as aviso:
            v._agregar_rutas([self.archivo("virus.exe", b"MZ"), self.archivo("falso.pdf", b"nada"),
                              self.archivo("bueno.png", PNG), "/ruta/que/no/existe.png"])
        self.assertEqual(v.lista_adjuntos.count(), 1)
        texto = aviso.call_args[0][2]
        self.assertIn("No se aceptan", texto)
        self.assertIn("no corresponde", texto)
        self.assertIn("no se pudo leer", texto)

    def test_no_se_pasa_del_maximo_ni_duplica(self):
        v = VistaNuevaSolicitud(self.ana)
        rutas = [self.archivo(f"a{i}.txt", f"contenido {i}".encode()) for i in range(archivos.MAX_ADJUNTOS_POR_SOLICITUD + 2)]
        with mock.patch.object(QMessageBox, "warning") as aviso:
            v._agregar_rutas(rutas)
        self.assertEqual(v.lista_adjuntos.count(), archivos.MAX_ADJUNTOS_POR_SOLICITUD)
        self.assertIn("máximo 5 archivos", aviso.call_args[0][2])
        self.assertFalse(v.btn_adjuntar.isEnabled())
        v2 = VistaNuevaSolicitud(self.ana)
        v2._agregar_rutas([rutas[0], rutas[0]])
        self.assertEqual(v2.lista_adjuntos.count(), 1)

    def test_el_dialogo_no_carga_a_memoria_un_archivo_enorme(self):
        v = VistaNuevaSolicitud(self.ana)
        grande = self.archivo("grande.txt", b"x")
        with mock.patch("os.path.getsize", return_value=archivos.MAX_TAMANO_ADJUNTO + 1), \
                mock.patch.object(QMessageBox, "warning") as aviso:
            v._agregar_rutas([grande])
        self.assertEqual(v.lista_adjuntos.count(), 0)
        self.assertIn("pesa más de", aviso.call_args[0][2])

    def test_detalle_lista_y_guarda_pero_no_permite_agregar_ni_quitar_archivos(self):
        s = datos.crear_solicitud("Incidencia de software", "Con archivo", self.ana, adjuntos=[("a.png", PNG)])
        d = DialogoDetalleSolicitud(s["folio"], self.ana)
        self.assertTrue(self.botones(d, "Guardar…"))
        self.assertFalse(self.botones(d, "Adjuntar archivo…"), "el representante ya no sube archivos a una solicitud creada")
        self.assertFalse(self.botones(d, "Quitar"))
        destino = str(Path(self.tmp.name) / "copia.png")
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(destino, "")), \
                mock.patch.object(QMessageBox, "information"):
            self.botones(d, "Guardar…")[0].click()
        self.assertEqual(Path(destino).read_bytes(), PNG)

    def test_el_tecnico_y_el_administrador_ven_y_descargan_pero_no_adjuntan(self):
        s = datos.crear_solicitud("Incidencia de software", "Con archivo", self.ana, adjuntos=[("a.png", PNG)])
        datos.asignar_solicitud(s["folio"], self.admin, self.gabriel["id"])
        for quien in (self.gabriel, self.admin):
            with self.subTest(rol=quien["rol"]):
                d = DialogoDetalleSolicitud(s["folio"], quien)
                self.assertTrue(self.botones(d, "Guardar…"))
                self.assertFalse(self.botones(d, "Adjuntar archivo…") or self.botones(d, "Quitar"))

    def test_una_solicitud_sin_archivos_explica_la_regla(self):
        from PySide6.QtWidgets import QLabel
        d = DialogoDetalleSolicitud("SIGSAT-0003", self.ana)
        self.assertIn("solo se adjuntan al registrarla", " ".join(w.text() for w in d.findChildren(QLabel)))

    def test_el_detalle_muestra_la_fecha_limite_y_avisa_si_esta_vencida(self):
        from PySide6.QtWidgets import QLabel
        d = DialogoDetalleSolicitud("SIGSAT-0004", cuenta("dlopez"))         # en plazo
        textos = " ".join(w.text() for w in d.findChildren(QLabel))
        self.assertIn("Fecha límite de atención", textos)
        self.assertNotIn("VENCIDA", textos)
        datos._solicitud_por_folio("SIGSAT-0004")["plazo_desde"] -= timedelta(days=30)          # ahora sí vencida
        d_vencida = DialogoDetalleSolicitud("SIGSAT-0004", cuenta("dlopez"))
        self.assertIn("VENCIDA", " ".join(w.text() for w in d_vencida.findChildren(QLabel)))
        d2 = DialogoDetalleSolicitud("SIGSAT-0001", self.ana)                # finalizada y calificada, a tiempo
        t2 = " ".join(w.text() for w in d2.findChildren(QLabel))
        self.assertIn("(cumplido)", t2)
        self.assertIn("Fecha de finalización", t2)
        d3 = DialogoDetalleSolicitud("SIGSAT-0005", self.ana)                # finalizada, aún sin calificar
        t3 = " ".join(w.text() for w in d3.findChildren(QLabel))
        self.assertIn("Fecha de finalización", t3)


class PruebasAsignacionUI(Base):
    def test_el_administrador_asigna_desde_el_detalle(self):
        d = DialogoDetalleSolicitud("SIGSAT-0003", self.admin)
        self.assertTrue(hasattr(d, "combo_agente"))
        self.assertEqual(d.btn_asignar.text(), "Asignar")
        textos = [d.combo_agente.itemText(i) for i in range(d.combo_agente.count())]
        self.assertTrue(any("Zyanya Arriaga" in t and "abiertas" in t for t in textos), "se muestra la carga de cada técnico")
        d.combo_agente.setCurrentIndex(d.combo_agente.findData(cuenta("zarriaga")["id"]))
        d.txt_motivo.setText("Tiene menos carga")
        with mock.patch.object(QMessageBox, "information"):
            d.btn_asignar.click()
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0003")["agente_asignado"], "Zyanya Arriaga")
        self.assertEqual(d.btn_asignar.text(), "Reasignar", "el panel se reconstruye")
        self.assertTrue(any(cuenta("zarriaga")["correo"] in m["To"] for m in self.buzon))

    def test_reasignar_a_quien_ya_la_tiene_avisa_sin_cambios(self):
        d = DialogoDetalleSolicitud("SIGSAT-0002", self.admin)
        self.assertEqual(d.combo_agente.currentData(), self.sebastian["id"])        # preseleccionado el actual
        with mock.patch.object(QMessageBox, "information") as info:
            d.btn_asignar.click()
        self.assertIn("ya está asignada", info.call_args[0][2])

    def test_los_demas_roles_no_ven_el_panel_de_asignacion(self):
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0003", cuenta("zarriaga")), "combo_agente"))
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0003", self.ana), "combo_agente"))
        self.assertFalse(hasattr(DialogoDetalleSolicitud("SIGSAT-0001", self.admin), "combo_agente"), "una finalizada no se asigna")

    def test_el_administrador_ve_el_detalle_de_cualquier_solicitud_sin_panel_de_agente(self):
        d = DialogoDetalleSolicitud("SIGSAT-0002", self.admin)
        self.assertFalse(hasattr(d, "combo_estado"))

    def test_vista_de_solicitudes_del_administrador(self):
        v = VistaSolicitudesAdmin(self.admin)
        self.assertEqual(v.tabla.rowCount(), 7)
        self.assertEqual([v.tabla.horizontalHeaderItem(i).text() for i in range(4)], ["Folio", "Tipo", "Área", "Solicitante"])
        v.chk_sin_asignar.setChecked(True)
        self.assertEqual(v.tabla.rowCount(), 2)
        self.assertEqual(v.tabla.item(0, 6).text(), "Sin asignar")
        v.chk_sin_asignar.setChecked(False)
        v.combo_area.setCurrentIndex(v.combo_area.findData("Contabilidad"))
        self.assertEqual(v.tabla.rowCount(), 3)
        v.combo_area.setCurrentIndex(0)
        v.chk_vencidas.setChecked(True)
        self.assertEqual(v.tabla.rowCount(), 0)
        datos._solicitud_por_folio("SIGSAT-0004")["plazo_desde"] -= timedelta(days=30)
        v.actualizar()
        self.assertEqual(v.tabla.rowCount(), 1)
        self.assertIn("vencida", v.tabla.item(0, 7).text())
        v.chk_vencidas.setChecked(False)
        v.combo_estado.setCurrentIndex(v.combo_estado.findData("Finalizado"))
        v.chk_sin_asignar.setChecked(True)
        self.assertEqual(v.tabla.rowCount(), 0)
        self.assertFalse(v.lbl_vacio.isHidden())
        v.grab()

    def test_las_tablas_muestran_la_fecha_limite(self):
        mis = VistaMisSolicitudes(self.ana)
        self.assertEqual(mis.tabla.horizontalHeaderItem(5).text(), "Fecha límite")
        self.assertTrue(mis.tabla.item(0, 5).text())


class PruebasPanelYReportesUI(Base):
    def test_el_dashboard_muestra_tiempos_por_area_y_tipo_y_la_carga(self):
        v = VistaDashboardAdmin(self.admin)
        self.assertEqual(v.tabla_carga.rowCount(), 5)
        primeros = {v.tabla_carga.item(i, 0).text() for i in range(3)}
        self.assertEqual(primeros, {"Daniel López", "Sebastián Estrada", "Gabriel Santiago"})      # los de más carga primero
        self.assertEqual(v.tabla_carga.item(4, 1).text(), "0")
        from PySide6.QtWidgets import QLabel
        textos = " ".join(w.text() for w in v.panel_tiempo_area.findChildren(QLabel))
        self.assertIn("Contabilidad", textos)
        self.assertIn("48.0 h", textos)
        textos_tipo = " ".join(w.text() for w in v.panel_tiempo_tipo.findChildren(QLabel))
        self.assertIn("Incidencia de hardware", textos_tipo)
        self.assertIn("Matriz CDMX", " ".join(w.text() for w in v.panel_sucursal.findChildren(QLabel)))
        v.actualizar()
        v.grab()

    def test_reportes_filtra_y_exporta_a_excel_y_pdf(self):
        v = VistaReportes(self.admin)
        self.assertEqual(v.tabla.rowCount(), 7)
        v.combo_area.setCurrentIndex(v.combo_area.findData("Contabilidad"))
        v.generar()
        self.assertEqual(v.tabla.rowCount(), 3)
        self.assertIn("3 solicitudes", v.lbl_resumen.text())

        xlsx = str(Path(self.tmp.name) / "r.xlsx")
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(xlsx, "")), mock.patch.object(QMessageBox, "information"):
            self.assertEqual(v.exportar("excel"), xlsx)
        self.assertGreater(os.path.getsize(xlsx), 1000)
        pdf = str(Path(self.tmp.name) / "r")                                              # sin extensión: se agrega sola
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(pdf, "")), mock.patch.object(QMessageBox, "information"):
            self.assertEqual(v.exportar("pdf"), pdf + ".pdf")
        self.assertTrue(Path(pdf + ".pdf").read_bytes().startswith(b"%PDF-"))

    def test_cancelar_el_dialogo_no_exporta_nada(self):
        v = VistaReportes(self.admin)
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.assertIsNone(v.exportar("excel"))

    def test_fechas_invertidas_muestran_un_error_claro(self):
        v = VistaReportes(self.admin)
        v.chk_desde.setChecked(True)
        v.chk_hasta.setChecked(True)
        v.date_desde.setDate(v.date_hasta.date().addDays(5))
        v.generar()
        self.assertFalse(v.lbl_error.isHidden())
        self.assertIn("fecha inicial", v.lbl_error.text())
        v.limpiar_filtros()
        self.assertTrue(v.lbl_error.isHidden())
        self.assertEqual(v.tabla.rowCount(), 7)

    def test_error_al_guardar_se_explica(self):
        v = VistaReportes(self.admin)
        with mock.patch("reportes.exportar_excel", side_effect=PermissionError(13, "Permission denied")), \
                mock.patch.object(QMessageBox, "warning") as aviso:
            self.assertIsNone(v.exportar("excel", ruta=str(Path(self.tmp.name) / "r.xlsx")))
        self.assertIn("abierto en otro programa", aviso.call_args[0][2])

    def test_falta_una_biblioteca(self):
        import reportes
        v = VistaReportes(self.admin)
        with mock.patch("reportes.exportar_pdf", side_effect=reportes.DependenciaFaltante("instala reportlab")), \
                mock.patch.object(QMessageBox, "warning") as aviso:
            self.assertIsNone(v.exportar("pdf", ruta=str(Path(self.tmp.name) / "r.pdf")))
        self.assertIn("reportlab", aviso.call_args[0][2])


class PruebasAdministracionUI(Base):
    def test_las_cuatro_pestanas(self):
        v = VistaAdministracion(self.admin)
        self.assertEqual([v.tabs.tabText(i) for i in range(v.tabs.count())],
                         ["Usuarios y roles", "Catálogos", "Correos enviados", "Respaldos"])
        for i in range(v.tabs.count()):
            v.tabs.setCurrentIndex(i)
        v.grab()

    def test_catalogos_solo_se_agregan_y_no_hay_plazos_ni_columna_de_solicitudes(self):
        cat = VistaAdministracion(self.admin).pestana_catalogos
        self.assertEqual(cat.tabla_areas.rowCount(), 5)
        self.assertEqual(cat.tabla_sucursales.rowCount(), 3)
        self.assertEqual(cat.tabla_tipos.rowCount(), 7)
        self.assertEqual([cat.tabla_areas.horizontalHeaderItem(i).text() for i in range(cat.tabla_areas.columnCount())],
                         ["Área", "Representantes activos"])
        self.assertEqual([cat.tabla_tipos.horizontalHeaderItem(i).text() for i in range(cat.tabla_tipos.columnCount())],
                         ["Tipo de solicitud", "Tiempo estimado", "Prioridad que se asigna"])
        for columna in ([cat.tabla_areas.horizontalHeaderItem(i).text() for i in range(cat.tabla_areas.columnCount())]
                        + [cat.tabla_tipos.horizontalHeaderItem(i).text() for i in range(cat.tabla_tipos.columnCount())]):
            self.assertNotIn("Solicitudes", columna, "se quitó el apartado de solicitudes")
            self.assertNotIn("Plazo", columna)
        self.assertFalse(hasattr(cat, "spin_sla"), "ya no hay catálogo de plazos por prioridad")
        self.assertFalse(hasattr(cat, "_guardar_sla"))
        # ni editar ni eliminar: los botones no se muestran
        for boton in (cat.btn_area_editar, cat.btn_area_eliminar, cat.btn_suc_editar, cat.btn_suc_eliminar,
                      cat.btn_tipo_editar, cat.btn_tipo_eliminar):
            self.assertTrue(boton.isHidden())
        self.assertFalse(cat.btn_area_nueva.isHidden() or cat.btn_suc_nueva.isHidden() or cat.btn_tipo_nuevo.isHidden())
        cat.tabla_areas.selectRow(0)
        cat._editar_area()                                                   # aunque se invoque, no hace nada
        cat._eliminar_area()
        self.assertEqual(datos.areas_activas()[0], "Contabilidad")

    def test_catalogo_de_clasificacion_por_prioridad(self):
        cat = VistaAdministracion(self.admin).pestana_catalogos
        self.assertEqual(cat.tabla_prioridades.rowCount(), 3)
        filas = {cat.tabla_prioridades.item(i, 0).text(): cat.tabla_prioridades.item(i, 1).text() for i in range(3)}
        self.assertEqual(filas["Alta"], "Incidencia de software")
        self.assertIn("Incidencia de hardware", filas["Media"])
        self.assertIn("Solicitud de nuevo acceso", filas["Baja"])
        from PySide6.QtWidgets import QLabel
        self.assertIn("Alta: hasta 24 horas · Media: de 25 a 72 horas · Baja: más de 72 horas",
                      " ".join(w.text() for w in cat.findChildren(QLabel)))

    def test_catalogos_agregar_area_y_tipo(self):
        cat = VistaAdministracion(self.admin).pestana_catalogos
        d = DialogoArea(self.admin)
        d.txt_nombre.setText("Seguridad")
        d._guardar()
        self.assertEqual(d.result(), QDialog.Accepted)
        cat.actualizar()
        self.assertEqual(cat.tabla_areas.rowCount(), 6)
        self.assertEqual(cat.tabla_areas.item(5, 1).text(), "0")             # sin representantes todavía

        sc = DialogoSucursal(self.admin)
        sc.txt_nombre.setText("Puebla")
        sc._guardar()
        self.assertEqual(sc.result(), QDialog.Accepted)
        cat.actualizar()
        self.assertEqual(cat.tabla_sucursales.rowCount(), 4)

        t = DialogoTipo(self.admin)
        t.txt_nombre.setText("Auditoría")
        t.spin_horas.setValue(10)
        t._guardar()
        self.assertEqual(t.result(), QDialog.Accepted)
        cat.actualizar()
        fila = next(i for i in range(cat.tabla_tipos.rowCount()) if cat.tabla_tipos.item(i, 0).text() == "Auditoría")
        self.assertEqual(cat.tabla_tipos.item(fila, 1).text(), "10 h")
        self.assertEqual(cat.tabla_tipos.item(fila, 2).text(), "Alta")
        clasif = {cat.tabla_prioridades.item(i, 0).text(): cat.tabla_prioridades.item(i, 1).text() for i in range(3)}
        self.assertIn("Auditoría", clasif["Alta"])

    def test_los_dialogos_de_catalogo_muestran_los_errores(self):
        d = DialogoArea(self.admin)
        d.txt_nombre.setText("Contabilidad")
        d._guardar()
        self.assertIn("Ya existe", d.lbl_error.text())
        self.assertNotEqual(d.result(), QDialog.Accepted)
        t = DialogoTipo(self.admin)
        t.txt_nombre.setText("X")
        t._guardar()
        self.assertIn("al menos 2", t.lbl_error.text())
        s = DialogoSucursal(self.admin)
        s.txt_nombre.setText("Monterrey")
        s._guardar()
        self.assertIn("Ya existe", s.lbl_error.text())

    def test_si_se_habilitara_editar_los_botones_aparecerian(self):
        from permisos import PERMISOS_POR_ROL
        with mock.patch.dict(PERMISOS_POR_ROL, {"Administrador": PERMISOS_POR_ROL["Administrador"] | {"catalogos.editar", "catalogos.eliminar"}}):
            cat = VistaAdministracion(self.admin).pestana_catalogos
            self.assertFalse(cat.btn_area_editar.isHidden() or cat.btn_tipo_eliminar.isHidden())
            cat.tabla_tipos.selectRow(0)
            self.assertTrue(cat.btn_tipo_editar.isEnabled())

    def test_correos_muestra_los_enviados_y_su_contenido(self):
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "Finalizado", "Esperando proveedor")
        pestana = VistaAdministracion(self.admin).pestana_correos
        self.assertEqual(pestana.tabla.rowCount(), 1)
        self.assertEqual(pestana.tabla.item(0, 1).text(), "cpena@clienteext.mx")
        self.assertEqual(pestana.tabla.item(0, 4).text(), "Enviado")
        pestana.tabla.selectRow(0)
        self.assertIn("Esperando proveedor", pestana.txt_cuerpo.toPlainText())
        self.assertTrue(pestana.lbl_vacio.isHidden())

    def test_correos_vacio_y_con_error(self):
        pestana = VistaAdministracion(self.admin).pestana_correos
        self.assertFalse(pestana.lbl_vacio.isHidden())
        correo.configurar(transporte=mock.Mock(side_effect=RuntimeError("servidor caído")))
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "Finalizado", "listo")
        pestana.actualizar()
        self.assertIn("servidor caído", pestana.tabla.item(0, 4).text())

    def test_respaldos_sin_persistencia(self):
        p = VistaAdministracion(self.admin).pestana_respaldos
        self.assertIn("NO se están guardando", p.lbl_estado.text())
        self.assertFalse(p.btn_crear.isEnabled())

    def test_respaldos_crear_y_restaurar(self):
        persistencia.activar(Path(self.tmp.name) / "datos")
        p = VistaAdministracion(self.admin).pestana_respaldos
        self.assertTrue(p.btn_crear.isEnabled())
        with mock.patch.object(QMessageBox, "information"):
            ruta = p.crear_respaldo()
        self.assertTrue(Path(ruta).exists())
        self.assertGreaterEqual(p.tabla.rowCount(), 1)

        datos.crear_area(self.admin, "Seguridad")
        p.actualizar()
        p.tabla.selectRow(0)
        self.assertTrue(p.btn_restaurar.isEnabled())
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), mock.patch.object(QMessageBox, "information"):
            p.restaurar_seleccionado()
        self.assertNotIn("Seguridad", datos.areas_activas())

    def test_restaurar_pide_confirmacion_y_cancelar_no_cambia_nada(self):
        persistencia.activar(Path(self.tmp.name) / "datos")
        p = VistaAdministracion(self.admin).pestana_respaldos
        with mock.patch.object(QMessageBox, "information"):
            p.crear_respaldo()
        datos.crear_area(self.admin, "Seguridad")
        p.actualizar()
        p.tabla.selectRow(0)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            p.restaurar_seleccionado()
        self.assertIn("Seguridad", datos.areas_activas())

    def test_restaurar_un_archivo_malo_avisa_y_no_toca_los_datos(self):
        persistencia.activar(Path(self.tmp.name) / "datos")
        p = VistaAdministracion(self.admin).pestana_respaldos
        falso = self.archivo("malo.zip", b"no es un zip")
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "warning") as aviso:
            self.assertFalse(p._restaurar(falso))
        self.assertIn("no se modificaron", aviso.call_args[0][2])
        self.assertEqual(len(datos.solicitudes_todas(self.admin)), 7)

    def test_la_pestana_de_respaldos_ya_no_mezcla_la_bitacora(self):
        p = VistaAdministracion(self.admin).pestana_respaldos
        self.assertFalse(hasattr(p, "btn_verificar"))
        self.assertFalse(hasattr(p, "verificar_bitacora"))
        from PySide6.QtWidgets import QLabel
        textos = " ".join(w.text() for w in p.findChildren(QLabel)).lower()
        self.assertNotIn("bitácora", textos.replace("(la bitácora de cada solicitud", ""))


class PruebasFiltrosSeActualizan(Base):
    def test_un_area_nueva_aparece_en_los_filtros_sin_reabrir_la_pantalla(self):
        reportes, solicitudes = VistaReportes(self.admin), VistaSolicitudesAdmin(self.admin)
        reportes.combo_area.setCurrentIndex(reportes.combo_area.findData("Contabilidad"))
        datos.crear_area(self.admin, "Seguridad")
        datos.crear_tipo(self.admin, "Auditoría", 10)
        reportes.actualizar()
        solicitudes.actualizar()
        self.assertNotEqual(reportes.combo_area.findData("Seguridad"), -1)
        self.assertNotEqual(reportes.combo_tipo.findData("Auditoría"), -1)
        self.assertNotEqual(solicitudes.combo_area.findData("Seguridad"), -1)
        self.assertEqual(reportes.combo_area.currentData(), "Contabilidad", "se conserva lo elegido")


class PruebasActualizarPanel(Base):
    def test_actualizar_el_panel_no_deja_tarjetas_viejas_encima(self):
        v = VistaDashboardAdmin(self.admin)
        v.show()
        for _ in range(3):
            v.actualizar()
        APP.processEvents()
        tarjetas = [w for w in v.findChildren(QWidget) if w.objectName() == "tarjetaKpi" and w.isVisible()]
        self.assertEqual(len(tarjetas), 7, "debe haber exactamente las 7 tarjetas actuales a la vista")


from vistas.bandeja_reportes import VistaBandejaReportes
from PySide6.QtWidgets import QAbstractItemView


class PruebasHistorialEnReportes(Base):
    """La bitácora ya no es una sección aparte: su historial se consulta desde Reportes."""

    def fila_de(self, v, folio):
        return next(i for i in range(v.tabla.rowCount()) if v.tabla.item(i, 0).text() == folio)

    def test_no_hay_seccion_de_bitacora_en_ningun_menu(self):
        from ventana_principal import MENU_POR_ROL
        for rol, opciones in MENU_POR_ROL.items():
            self.assertNotIn("Bitácora", [e for e, _f in opciones], rol)
        with self.assertRaises(ImportError):
            __import__("vistas.bitacora_vista")

    def test_el_historial_aparece_al_elegir_un_reporte(self):
        v = VistaBandejaReportes(self.admin)
        self.assertTrue(v.tabla_historial.isHidden())
        self.assertFalse(v.lbl_historial_vacio.isHidden())
        self.assertEqual(v.lbl_historial.text(), "Historial de atención")
        v.tabla.selectRow(self.fila_de(v, "SIGSAT-0002"))
        esperados = datos.historial_de_solicitud(self.admin, "SIGSAT-0002")
        self.assertGreaterEqual(len(esperados), 2)
        self.assertFalse(v.tabla_historial.isHidden())
        self.assertTrue(v.lbl_historial_vacio.isHidden())
        self.assertIn("SIGSAT-0002", v.lbl_historial.text())
        self.assertEqual(v.tabla_historial.rowCount(), len(esperados))
        self.assertEqual([v.tabla_historial.horizontalHeaderItem(i).text() for i in range(3)],
                         ["Fecha y hora", "Autor", "Evento"])
        self.assertEqual(v.tabla_historial.item(0, 2).text(), esperados[0]["evento"])
        v.grab()

    def test_el_historial_va_de_lo_mas_antiguo_a_lo_mas_reciente_y_es_solo_de_ese_reporte(self):
        h = datos.historial_de_solicitud(self.admin, "SIGSAT-0005")
        self.assertEqual([e["n"] for e in h], sorted(e["n"] for e in h))
        otros = datos.historial_de_solicitud(self.admin, "SIGSAT-0002")
        self.assertNotEqual(h, otros)
        self.assertEqual(datos.historial_de_solicitud(self.admin, "sigsat-0005"), h, "el folio no distingue mayúsculas")
        self.assertEqual(datos.historial_de_solicitud(self.admin, "0005"), [], "el folio debe ser exacto")
        self.assertEqual(datos.historial_de_solicitud(self.admin, "SIGSAT-9999"), [])

    def test_el_historial_incluye_los_reportes_finalizados(self):
        v = VistaBandejaReportes(self.admin)
        fila = self.fila_de(v, "SIGSAT-0001")
        self.assertEqual(v.tabla.item(fila, 5).text(), "Finalizado")
        v.tabla.selectRow(fila)
        textos = " ".join(v.tabla_historial.item(i, 2).text() for i in range(v.tabla_historial.rowCount()))
        self.assertIn("Finalizado", textos)

    def test_es_de_solo_lectura(self):
        v = VistaBandejaReportes(self.admin)
        self.assertEqual(v.tabla_historial.editTriggers(), QAbstractItemView.NoEditTriggers)
        v.tabla.selectRow(self.fila_de(v, "SIGSAT-0002"))
        antes = datos.exportar_estado()
        v.tabla_historial.item(0, 2).setText("intento de alterar la pantalla")      # solo cambia lo que se ve
        v.consultar()
        self.assertEqual(datos.exportar_estado(), antes)
        self.assertNotIn("intento de alterar", str(datos.historial_de_solicitud(self.admin, "SIGSAT-0002")))
        from PySide6.QtWidgets import QPushButton
        textos = [b.text().lower() for b in v.findChildren(QPushButton)]
        self.assertFalse([t for t in textos if any(x in t for x in ("borrar", "eliminar", "editar", "modificar"))])

    def test_el_administrador_ve_la_integridad_y_el_tecnico_no(self):
        v = VistaBandejaReportes(self.admin)
        self.assertFalse(v.lbl_integridad.isHidden())
        self.assertIn("Integridad verificada", v.lbl_integridad.text())
        del v
        tecnico = VistaBandejaReportes(self.sebastian)
        self.assertTrue(tecnico.lbl_integridad.isHidden())

    def test_avisa_si_el_historial_fue_alterado(self):
        datos._SOLICITUDES[1]["bitacora"] = ()
        v = VistaBandejaReportes(self.admin)
        self.assertIn("alteraciones", v.lbl_integridad.text())

    def test_el_tecnico_solo_consulta_el_historial_de_sus_reportes(self):
        v = VistaBandejaReportes(self.sebastian)
        folios = {v.tabla.item(i, 0).text() for i in range(v.tabla.rowCount())}
        self.assertEqual(folios, {"SIGSAT-0001", "SIGSAT-0002"})
        v.tabla.selectRow(self.fila_de(v, "SIGSAT-0001"))
        self.assertGreaterEqual(v.tabla_historial.rowCount(), 2)
        self.assertEqual(datos.historial_de_solicitud(self.sebastian, "SIGSAT-0005"), [], "no ve el de reportes ajenos")
        with self.assertRaises(PermissionError):
            datos.historial_de_solicitud(self.ana, "SIGSAT-0002")

    def test_el_representante_no_tiene_reportes(self):
        with self.assertRaises(PermissionError):
            VistaBandejaReportes(self.ana)

    def test_se_actualiza_con_los_eventos_nuevos_y_conserva_la_seleccion(self):
        v = VistaBandejaReportes(self.admin)
        v.tabla.selectRow(self.fila_de(v, "SIGSAT-0002"))
        antes = v.tabla_historial.rowCount()
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "En proceso", "Esperando proveedor")
        v.actualizar()
        self.assertEqual(v.folio_seleccionado(), "SIGSAT-0002")
        self.assertEqual(v.tabla_historial.rowCount(), antes + 1)
        self.assertTrue(any("Esperando proveedor" in v.tabla_historial.item(i, 2).text()
                            for i in range(v.tabla_historial.rowCount())))

    def test_si_el_reporte_seleccionado_sale_del_filtro_el_historial_se_oculta(self):
        v = VistaBandejaReportes(self.admin)
        v.tabla.selectRow(self.fila_de(v, "SIGSAT-0001"))
        self.assertFalse(v.tabla_historial.isHidden())
        v.combo_estado.setCurrentText("Sin visualizar")
        v.consultar()
        self.assertTrue(v.tabla_historial.isHidden())
        self.assertEqual(v.lbl_historial.text(), "Historial de atención")

    def test_fechas_invertidas_muestran_un_error_claro(self):
        v = VistaBandejaReportes(self.admin)
        v.chk_desde.setChecked(True)
        v.chk_hasta.setChecked(True)
        v.date_desde.setDate(v.date_hasta.date().addDays(3))
        v.consultar()
        self.assertFalse(v.lbl_error.isHidden())
        self.assertIn("fecha inicial", v.lbl_error.text())
        v.limpiar_filtros()
        self.assertTrue(v.lbl_error.isHidden())

    def test_doble_clic_abre_el_detalle(self):
        v = VistaBandejaReportes(self.admin)
        with mock.patch("vistas.bandeja_reportes.DialogoDetalleSolicitud") as dialogo:
            v._abrir_detalle(self.fila_de(v, "SIGSAT-0005"), 0)
        self.assertEqual(dialogo.call_args[0][0], "SIGSAT-0005")
        dialogo.return_value.exec.assert_called_once()

    def test_el_resumen_cuenta_los_finalizados(self):
        v = VistaBandejaReportes(self.admin)
        self.assertIn("7 reportes", v.lbl_resumen.text())
        self.assertIn("2 finalizados", v.lbl_resumen.text())


class PruebasFinalizadoVisible(Base):
    """«Finalizado» se ve en Reportes y lo ven tanto el representante como el técnico; solo el técnico avanza el estatus."""

    def nueva(self, tecnico):
        s = datos.crear_solicitud("Incidencia de software", "No abre el sistema", self.ana)
        datos.asignar_solicitud(s["folio"], self.admin, tecnico["id"])
        return datos.buscar_por_folio(s["folio"])

    def banner(self, usuario, folio):
        from PySide6.QtWidgets import QLabel
        from widgets.detalle_solicitud import DialogoDetalleSolicitud
        d = DialogoDetalleSolicitud(folio, usuario)
        return d, d.findChild(QLabel, "avisoFinalizada")

    def test_el_representante_el_tecnico_y_el_administrador_ven_que_ya_se_finalizo(self):
        s = datos.buscar_por_folio("SIGSAT-0005")
        tecnico = next(u for u in datos.usuarios_todos() if u["nombre"] == s["agente_asignado"])
        for usuario in (self.ana, tecnico, self.admin):
            with self.subTest(rol=usuario["rol"]):
                _d, aviso = self.banner(usuario, "SIGSAT-0005")
                self.assertIsNotNone(aviso)
                self.assertIn("Solicitud finalizada", aviso.text())
                self.assertIn(s["agente_asignado"], aviso.text())

    def test_una_solicitud_en_curso_no_muestra_el_aviso(self):
        _d, aviso = self.banner(self.admin, "SIGSAT-0002")
        self.assertIsNone(aviso)

    def test_flujo_completo_el_tecnico_actualiza_y_los_dos_ven_finalizado(self):
        s = self.nueva(self.gabriel)
        folio = s["folio"]
        self.assertEqual(s["estado"], "Sin visualizar")
        # El técnico abre el reporte: pasa solo a Visualizado
        from widgets.detalle_solicitud import DialogoDetalleSolicitud
        DialogoDetalleSolicitud(folio, self.gabriel)
        self.assertEqual(datos.buscar_por_folio(folio)["estado"], "Visualizado")
        # El técnico (y solo él) actualiza a En proceso y luego a Finalizado, con comentario
        datos.actualizar_por_tecnico(folio, self.gabriel, "En proceso", "Revisando el equipo")
        self.assertEqual(datos.buscar_por_folio(folio)["estado"], "En proceso")
        with self.assertRaises((PermissionError, ValueError)):
            datos.actualizar_por_tecnico(folio, self.admin, "Finalizado", "no debería poder")
        with self.assertRaises((PermissionError, ValueError)):
            datos.actualizar_por_tecnico(folio, self.ana, "Finalizado", "no debería poder")
        datos.actualizar_por_tecnico(folio, self.gabriel, "Finalizado", "Equipo reparado")
        self.assertEqual(datos.buscar_por_folio(folio)["estado"], "Finalizado")
        # Lo ve el representante en «Mis solicitudes»…
        from vistas.mis_solicitudes import VistaMisSolicitudes
        mis = VistaMisSolicitudes(self.ana)
        fila = next(i for i in range(mis.tabla.rowCount()) if mis.tabla.item(i, 0).text() == folio)
        self.assertIn("Finalizado", mis.tabla.item(fila, 3).text())
        # …y el técnico y el administrador en «Reportes», que ya incluye los Finalizados
        for usuario in (self.gabriel, self.admin):
            vista = VistaBandejaReportes(usuario)
            fila = next(i for i in range(vista.tabla.rowCount()) if vista.tabla.item(i, 0).text() == folio)
            self.assertEqual(vista.tabla.item(fila, 5).text(), "Finalizado")
        # y desde Reportes se consulta todo su historial de atención
        reportes = VistaBandejaReportes(self.gabriel)
        reportes.tabla.selectRow(next(i for i in range(reportes.tabla.rowCount()) if reportes.tabla.item(i, 0).text() == folio))
        textos = " | ".join(reportes.tabla_historial.item(i, 2).text() for i in range(reportes.tabla_historial.rowCount()))
        for esperado in ("Visualizado", "En proceso", "Finalizado", "Equipo reparado"):
            self.assertIn(esperado, textos)

    def test_el_filtro_de_estatus_de_reportes_ofrece_finalizado(self):
        for usuario in (self.admin, self.sebastian):
            v = VistaBandejaReportes(usuario)
            opciones = [v.combo_estado.itemText(i) for i in range(v.combo_estado.count())]
            self.assertEqual(opciones, ["Todos los estatus", "Sin visualizar", "Visualizado", "En proceso", "Finalizado"])
            v.combo_estado.setCurrentText("Finalizado")
            v.consultar()
            self.assertGreaterEqual(v.tabla.rowCount(), 1)
            self.assertTrue(all(v.tabla.item(i, 5).text() == "Finalizado" for i in range(v.tabla.rowCount())))
