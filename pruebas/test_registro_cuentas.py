"""Registro de cuentas: la persona crea su propia cuenta desde el login (ya no la crea el Administrador).
Rol fijo, validaciones, límite por hora, avisos por correo, persistencia, compatibilidad con respaldos
anteriores y pantallas (login, diálogo de registro y administración de roles)."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

import correo
import datos
import persistencia
from estilos import QSS_APP, paleta_clara
from permisos import ROL_REPRESENTANTE, ROL_TECNICO, puede
from pruebas.base import Base, cuenta
from ventana_login import VentanaLogin
from vistas.administracion import VistaAdministracion
from widgets.dialogo_registro import DialogoRegistro
from widgets.dialogo_usuario import DialogoUsuario

APP = QApplication.instance() or QApplication([])
APP.setStyle("Fusion")
APP.setPalette(paleta_clara())
APP.setStyleSheet(QSS_APP)

NUEVO = dict(nombre="Laura Méndez Ortiz", usuario="lmendez", correo="laura.mendez@ipn.mx",
             contrasena="Clave-12345", area="Contabilidad", sucursal="Monterrey")


class DatosRegistro(Base):
    def registrar(self, **kw):
        d = {**NUEVO, **kw}
        return datos.registrar_cuenta(d["nombre"], d["usuario"], d["correo"], d["contrasena"], d["area"], d["sucursal"])

    # ---- la cuenta se crea sola
    def test_la_cuenta_queda_creada_y_activa_sin_intervencion_del_administrador(self):
        antes = len(datos.usuarios_todos())
        c = self.registrar()
        self.assertEqual(len(datos.usuarios_todos()), antes + 1)
        self.assertEqual((c["nombre"], c["usuario"], c["correo"], c["area"], c["sucursal"], c["activo"]),
                         ("Laura Méndez Ortiz", "lmendez", "laura.mendez@ipn.mx", "Contabilidad", "Monterrey", True))
        sesion = datos.autenticar("lmendez", "Clave-12345")
        self.assertIsNotNone(sesion, "puede iniciar sesión de inmediato")
        self.assertEqual(sesion["rol"], ROL_REPRESENTANTE)

    def test_siempre_entra_como_representante_de_area(self):
        c = self.registrar()
        self.assertEqual(c["rol"], ROL_REPRESENTANTE)
        self.assertTrue(puede(c, "solicitud.crear"))
        self.assertFalse(puede(c, "solicitud.asignar"))
        self.assertFalse(puede(c, "solicitud.atender"))
        self.assertFalse(puede(c, "usuarios.gestionar"))

    def test_no_se_puede_elegir_otro_rol_ni_hay_parametro_para_ello(self):
        import inspect
        self.assertNotIn("rol", inspect.signature(datos.registrar_cuenta).parameters)

    def test_la_contrasena_se_guarda_solo_como_hash(self):
        self.registrar()
        interna = next(u for u in datos._USUARIOS if u["usuario"] == "lmendez")
        self.assertNotIn("Clave-12345", json.dumps({k: str(v) for k, v in interna.items()}))
        self.assertNotEqual(interna["contrasena_hash"], "Clave-12345")

    def test_nombre_y_espacios_se_limpian(self):
        c = self.registrar(nombre="  Laura   Méndez  ", usuario="  lmendez  ", correo="  laura.mendez@ipn.mx ")
        self.assertEqual((c["nombre"], c["usuario"], c["correo"]), ("Laura Méndez", "lmendez", "laura.mendez@ipn.mx"))

    # ---- validaciones
    def test_datos_invalidos_se_rechazan_con_mensaje_y_no_crean_nada(self):
        casos = [(dict(nombre=""), "Completa"), (dict(usuario=""), "Completa"), (dict(correo=""), "Completa"),
                 (dict(nombre="Al"), "nombre completo"), (dict(correo="no-es-correo"), "correo válido"),
                 (dict(usuario="con espacios"), "espacios"), (dict(contrasena=""), "contraseña"),
                 (dict(contrasena="corta"), "8 caracteres"), (dict(area="Inventada"), "área"), (dict(area=""), "área"),
                 (dict(sucursal="Inventada"), "sucursal"), (dict(sucursal=""), "sucursal"),
                 (dict(nombre="x" * 101), "demasiado largo")]
        cuentas = len(datos.usuarios_todos())
        for kw, texto in casos:
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, texto):
                self.registrar(**kw)
        self.assertEqual(len(datos.usuarios_todos()), cuentas)

    def test_usuario_y_correo_no_se_pueden_repetir(self):
        self.registrar()
        with self.assertRaisesRegex(ValueError, "ya está en uso"):
            self.registrar(correo="otro@ipn.mx")                     # mismo usuario
        with self.assertRaisesRegex(ValueError, "ya está registrado"):
            self.registrar(usuario="otro", correo="LAURA.MENDEZ@IPN.MX")   # mismo correo (sin distinguir mayúsculas)
        with self.assertRaisesRegex(ValueError, "ya está en uso"):
            self.registrar(usuario="DIRECCION", correo="x@ipn.mx")   # usuario de una cuenta existente

    def test_un_area_o_sucursal_inactiva_no_se_puede_elegir(self):
        datos._area_por_nombre("Compras")["activa"] = False
        with self.assertRaisesRegex(ValueError, "área"):
            self.registrar(area="Compras")
        datos._sucursal_por_nombre("Monterrey")["activa"] = False
        with self.assertRaisesRegex(ValueError, "sucursal"):
            self.registrar()

    def test_limite_global_de_registros_por_hora(self):
        for i in range(datos.CUENTAS_MAX_POR_HORA):
            self.registrar(usuario=f"persona{i}", correo=f"persona{i}@ipn.mx")
        with self.assertRaisesRegex(ValueError, "demasiadas"):
            self.registrar(usuario="otra", correo="otra@ipn.mx")

    def test_los_intentos_con_datos_invalidos_no_gastan_el_limite(self):
        for _ in range(datos.CUENTAS_MAX_POR_HORA + 5):
            with self.assertRaises(ValueError):
                self.registrar(contrasena="corta")
        self.registrar()                                            # sigue pudiendo registrarse

    # ---- correos
    def test_se_da_la_bienvenida_sin_enviar_la_contrasena_y_se_avisa_a_los_administradores(self):
        self.registrar()
        (bienvenida,) = self.correos("laura.mendez@ipn.mx")
        self.assertIn("Tu cuenta fue creada", bienvenida["Subject"])
        self.assertIn("lmendez", self.cuerpo(bienvenida))
        self.assertNotIn("Clave-12345", self.cuerpo(bienvenida), "la contraseña nunca viaja por correo")
        (aviso,) = self.correos(self.admin["correo"])
        self.assertIn("Laura Méndez Ortiz", self.cuerpo(aviso))
        self.assertIn("Usuarios y roles", self.cuerpo(aviso))

    def test_el_fallo_del_correo_no_impide_registrar(self):
        def falla(_msg):
            raise OSError("sin red")
        correo.configurar(transporte=falla)
        c = self.registrar()
        self.assertIsNotNone(datos.autenticar(c["usuario"], "Clave-12345"))

    # ---- el administrador ya no crea ni aprueba cuentas; solo cambia roles
    def test_ya_no_existe_el_flujo_de_solicitudes_de_cuenta(self):
        for nombre in ("solicitar_cuenta", "solicitudes_cuenta", "aprobar_solicitud_cuenta",
                       "rechazar_solicitud_cuenta", "contar_solicitudes_cuenta_pendientes"):
            self.assertFalse(hasattr(datos, nombre), nombre)
        self.assertFalse(puede(self.admin, "cuentas.revisar"))

    def test_el_administrador_puede_pasar_a_un_registrado_a_tecnico(self):
        c = self.registrar()
        datos.actualizar_usuario(c["id"], c["nombre"], c["usuario"], "", ROL_TECNICO, None, c["correo"])
        nuevo = datos.autenticar("lmendez", "Clave-12345")
        self.assertEqual(nuevo["rol"], ROL_TECNICO)
        self.assertIsNone(nuevo["area"])
        self.assertTrue(puede(nuevo, "solicitud.atender"))

    def test_la_cuenta_registrada_puede_levantar_una_solicitud(self):
        c = datos.autenticar(self.registrar()["usuario"], "Clave-12345")
        s = datos.crear_solicitud("Incidencia de software", "No abre", c)
        self.assertEqual(s["area"], "Contabilidad")
        self.assertEqual(s["sucursal"], "Monterrey")


class PersistenciaRegistro(Base):
    def test_la_cuenta_sobrevive_a_guardar_y_cargar(self):
        datos.registrar_cuenta(**{"nombre": "Laura Méndez", "usuario": "lmendez", "correo": "l@ipn.mx",
                                  "contrasena": "Clave-12345", "area": "Contabilidad", "sucursal": "Monterrey"})
        estado = datos.exportar_estado()
        self.assertNotIn("solicitudes_cuenta", estado)
        datos.reiniciar()
        self.assertIsNone(datos.autenticar("lmendez", "Clave-12345"))
        datos.importar_estado(estado, datos.contenidos_adjuntos())
        self.assertIsNotNone(datos.autenticar("lmendez", "Clave-12345"))

    def test_un_respaldo_anterior_con_solicitudes_de_cuenta_se_puede_restaurar(self):
        estado = datos.exportar_estado()
        estado["solicitudes_cuenta"] = [{"id": 1, "nombre": "X", "estado": "Pendiente"}]     # clave de la versión anterior
        estado["contadores"]["solicitud_cuenta"] = 1
        datos.importar_estado(estado, datos.contenidos_adjuntos())
        self.assertIsNotNone(datos.autenticar("direccion", "Dir_000"))

    def test_se_guarda_en_disco_al_registrarse(self):
        with tempfile.TemporaryDirectory() as carpeta:
            persistencia.activar(carpeta)
            datos.registrar_cuenta("Laura Méndez", "lmendez", "l@ipn.mx", "Clave-12345", "Contabilidad", "Monterrey")
            with open(os.path.join(carpeta, "estado.json"), encoding="utf-8") as f:
                en_disco = json.load(f)
            self.assertIn("lmendez", [u["usuario"] for u in en_disco["usuarios"]])
            persistencia.desactivar()


class InterfazRegistro(Base):
    def llenar(self, d, **kw):
        v = {**NUEVO, "confirmar": NUEVO["contrasena"], **kw}
        d.txt_nombre.setText(v["nombre"])
        d.txt_correo.setText(v["correo"])
        d.txt_usuario.setText(v["usuario"])
        d.txt_contrasena.setText(v["contrasena"])
        d.txt_confirmar.setText(v["confirmar"])
        d.combo_area.setCurrentText(v["area"])
        d.combo_sucursal.setCurrentText(v["sucursal"])

    def test_el_login_abre_el_registro_y_deja_el_usuario_listo(self):
        v = VentanaLogin()
        self.assertEqual(v.btn_registro.text(), "Creación de cuenta")
        with mock.patch("ventana_login.DialogoRegistro") as clase:
            clase.return_value.exec.return_value = QDialog.Accepted
            clase.return_value.usuario_creado = "lmendez"
            v.btn_registro.click()
            clase.assert_called_once()
        self.assertFalse(v.lbl_aviso.isHidden())
        self.assertIn("Tu cuenta fue creada", v.lbl_aviso.text())
        self.assertEqual(v.txt_usuario.text(), "lmendez")

    def test_cancelar_el_registro_no_muestra_aviso(self):
        v = VentanaLogin()
        with mock.patch("ventana_login.DialogoRegistro") as clase:
            clase.return_value.exec.return_value = QDialog.Rejected
            clase.return_value.usuario_creado = None
            v.btn_registro.click()
        self.assertTrue(v.lbl_aviso.isHidden())
        self.assertEqual(v.txt_usuario.text(), "")

    def test_el_dialogo_crea_la_cuenta(self):
        d = DialogoRegistro()
        self.llenar(d)
        d.btn_crear.click()
        self.assertTrue(d.lbl_error.isHidden())
        self.assertFalse(d.lbl_exito.isHidden())
        self.assertIn("fue creada", d.lbl_exito.text())
        self.assertEqual(d.usuario_creado, "lmendez")
        self.assertEqual(d.btn_crear.text(), "Ir a iniciar sesión")
        self.assertIsNotNone(datos.autenticar("lmendez", "Clave-12345"))
        total = len(datos.usuarios_todos())
        d.btn_crear.click()                                          # el segundo clic solo cierra
        self.assertEqual(len(datos.usuarios_todos()), total)
        self.assertEqual(d.result(), QDialog.Accepted)

    def test_el_dialogo_muestra_los_errores_sin_crear_nada(self):
        d = DialogoRegistro()
        total = len(datos.usuarios_todos())
        self.llenar(d, confirmar="otra-distinta")
        d.btn_crear.click()
        self.assertIn("no coinciden", d.lbl_error.text())
        self.llenar(d, contrasena="corta", confirmar="corta")
        d.btn_crear.click()
        self.assertIn("8 caracteres", d.lbl_error.text())
        self.llenar(d, usuario="direccion")
        d.btn_crear.click()
        self.assertIn("ya está en uso", d.lbl_error.text())
        self.assertEqual(len(datos.usuarios_todos()), total)
        self.assertIsNone(d.usuario_creado)

    def test_se_sugiere_un_usuario_a_partir_del_correo(self):
        d = DialogoRegistro()
        d.txt_correo.setText("laura.mendez@ipn.mx")
        d._sugerir_usuario()
        self.assertEqual(d.txt_usuario.text(), "laura.mendez")
        d.txt_usuario.setText("miusuario")
        d.txt_correo.setText("otro@ipn.mx")
        d._sugerir_usuario()
        self.assertEqual(d.txt_usuario.text(), "miusuario", "no pisa lo que la persona escribió")

    def test_mostrar_contrasenas(self):
        d = DialogoRegistro()
        d.chk_mostrar.setChecked(True)
        self.assertEqual(d.txt_contrasena.echoMode(), d.txt_contrasena.EchoMode.Normal)
        d.chk_mostrar.setChecked(False)
        self.assertEqual(d.txt_confirmar.echoMode(), d.txt_confirmar.EchoMode.Password)

    def test_el_registro_no_ofrece_elegir_rol(self):
        d = DialogoRegistro()
        self.assertFalse(hasattr(d, "combo_rol"))

    def test_administracion_ya_no_tiene_solicitudes_de_cuenta_ni_boton_nueva_cuenta(self):
        v = VistaAdministracion(self.admin)
        pestanas = [v.tabs.tabText(i) for i in range(v.tabs.count())]
        self.assertEqual(pestanas, ["Usuarios y roles", "Catálogos", "Correos enviados", "Respaldos"])
        textos = [b.text() for b in v.findChildren(QPushButton)]
        self.assertNotIn("Nueva cuenta", textos)
        self.assertIn("Editar", textos)
        self.assertIn("Eliminar", textos)

    def test_el_administrador_cambia_el_rol_de_un_registrado_desde_editar(self):
        c = datos.registrar_cuenta("Laura Méndez", "lmendez", "l@ipn.mx", "Clave-12345", "Contabilidad", "Monterrey")
        v = VistaAdministracion(self.admin)
        fila = next(i for i in range(v.tabla.rowCount()) if v.tabla.item(i, 1).text() == "lmendez")
        v.tabla.selectRow(fila)
        self.assertTrue(v.btn_editar.isEnabled())
        d = DialogoUsuario(usuario_existente=datos.buscar_usuario(c["id"]))
        d.combo_rol.setCurrentText(ROL_TECNICO)
        d._guardar()
        self.assertEqual(datos.buscar_usuario(c["id"])["rol"], ROL_TECNICO)


if __name__ == "__main__":
    unittest.main()
