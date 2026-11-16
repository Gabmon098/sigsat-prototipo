"""RF-11 (correo de asignación) y RF-12 (correo de cambio de estatus), y el servicio de correo."""

import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from pruebas.base import Base, cuenta
import correo
import datos


class PruebasCorreoAsignacion(Base):
    def test_al_crear_la_solicitud_solo_se_avisa_a_los_administradores(self):
        self.buzon.clear()
        s = self.nueva(tipo="Incidencia de software", tecnico=False)
        self.assertEqual([m["To"] for m in self.buzon], [self.admin["correo"]])
        self.assertIsNone(s["agente_asignado"])

    def test_al_asignar_se_avisa_al_tecnico_y_al_representante(self):
        s = self.nueva(tipo="Incidencia de software", tecnico=False)
        self.buzon.clear()
        datos.asignar_solicitud(s["folio"], self.admin, self.gabriel["id"])
        destinos = {m["To"]: m for m in self.buzon}
        self.assertEqual(set(destinos), {self.gabriel["correo"], self.ana["correo"]})
        self.assertIn(f"Se te asignó la solicitud {s['folio']}", destinos[self.gabriel["correo"]]["Subject"])
        cuerpo_tecnico = self.cuerpo(destinos[self.gabriel["correo"]])
        for dato in (s["folio"], "Incidencia de software", "Alta", "Ana Reyes", "No abre el sistema", "Fecha límite", "Matriz CDMX", "Mis reportes"):
            self.assertIn(dato, cuerpo_tecnico)
        self.assertIn(f"Tu solicitud {s['folio']} fue asignada", destinos[self.ana["correo"]]["Subject"])
        self.assertIn("Gabriel Santiago", self.cuerpo(destinos[self.ana["correo"]]))

    def test_la_asignacion_del_administrador_incluye_su_nombre_y_el_motivo(self):
        self.buzon.clear()
        datos.asignar_solicitud("SIGSAT-0003", self.admin, self.zyanya["id"], "Es tu especialidad")
        destinos = {m["To"]: m for m in self.buzon}
        self.assertEqual(set(destinos), {self.zyanya["correo"], self.ana["correo"]})
        cuerpo = self.cuerpo(destinos[self.zyanya["correo"]])
        self.assertIn("Dirección General", cuerpo)
        self.assertIn("Es tu especialidad", cuerpo)

    def test_la_reasignacion_avisa_tambien_al_tecnico_anterior(self):
        self.buzon.clear()
        datos.asignar_solicitud("SIGSAT-0002", self.admin, self.gabriel["id"], "Carga de trabajo")
        destinos = {m["To"]: m for m in self.buzon}
        self.assertEqual(set(destinos), {self.gabriel["correo"], self.carlos["correo"], self.sebastian["correo"]})
        self.assertIn("reasignó", destinos[self.gabriel["correo"]]["Subject"])
        self.assertIn("reasignada", destinos[self.carlos["correo"]]["Subject"])
        self.assertIn("ya no está a tu cargo", destinos[self.sebastian["correo"]]["Subject"])

    def test_no_se_envia_correo_si_no_hubo_cambio(self):
        self.buzon.clear()
        datos.asignar_solicitud("SIGSAT-0002", self.admin, self.sebastian["id"])          # ya era suyo
        datos.asignar_solicitud("SIGSAT-0001", self.admin, self.gabriel["id"])            # finalizada
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "En proceso", "")     # sin cambios
        self.assertEqual(self.buzon, [])


class PruebasCorreoEstatus(Base):
    def test_un_cambio_de_estatus_avisa_al_representante(self):
        self.buzon.clear()
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "Finalizado", "Esperando al proveedor, se instaló")
        self.assertEqual(len(self.buzon), 1)
        m = self.buzon[0]
        self.assertEqual(m["To"], self.carlos["correo"])                    # SIGSAT-0002 es de Carlos
        self.assertIn("SIGSAT-0002", m["Subject"])
        self.assertIn("Finalizado", m["Subject"])
        cuerpo = self.cuerpo(m)
        self.assertIn("«En proceso» a «Finalizado»", cuerpo)
        self.assertIn("se instaló", cuerpo)
        self.assertIn("Sebastián Estrada", cuerpo)

    def test_al_visualizar_tambien_se_avisa(self):
        s = self.nueva(tipo="Incidencia de software")
        self.buzon.clear()
        datos.registrar_visualizacion(s["folio"], self.sebastian)
        self.assertEqual([m["To"] for m in self.buzon], [self.ana["correo"]])
        self.assertIn("«Visualizado»", self.buzon[0]["Subject"])

    def test_al_finalizar_se_invita_a_calificar(self):
        self.buzon.clear()
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "Finalizado", "Se reinició el servicio")
        cuerpo = self.cuerpo(self.buzon[0])
        self.assertIn("calificar el servicio recibido", cuerpo)
        self.assertNotIn("cerrada", cuerpo.lower())

    def test_un_simple_comentario_no_envia_correo(self):
        self.buzon.clear()
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "En proceso", "Avance: revisando logs")
        self.assertEqual(self.buzon, [])

    def test_el_correo_de_estatus_no_incluye_datos_de_otras_personas(self):
        self.buzon.clear()
        datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "Finalizado", "Listo")
        cuerpo = self.cuerpo(self.buzon[0])
        self.assertNotIn(self.ana["correo"], cuerpo)
        self.assertNotIn("contrasena", cuerpo.lower())


class PruebasServicioDeCorreo(Base):
    def test_un_fallo_de_correo_no_interrumpe_la_operacion(self):
        def roto(msg):
            raise RuntimeError("servidor caído")
        correo.configurar(transporte=roto)
        self.assertEqual(datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "Finalizado", "x"), "ok")
        self.assertEqual(datos.buscar_por_folio("SIGSAT-0002")["estado"], "Finalizado")     # el cambio se guardó
        reg = correo.bandeja()[0]
        self.assertEqual(reg["estado"], "error")
        self.assertIn("servidor caído", reg["detalle"])

    def test_una_excepcion_al_armar_la_notificacion_tampoco_rompe_nada(self):
        with mock.patch("notificaciones.estatus_cambiado", side_effect=RuntimeError("boom")):
            self.assertEqual(datos.actualizar_por_tecnico("SIGSAT-0002", self.sebastian, "Finalizado", "x"), "ok")

    def test_direcciones_invalidas_no_se_envian(self):
        for mala in (None, "", "sin-arroba", "a@b", "a b@c.mx", "a@b.mx\nBcc: x@y.mx", "a@b.mx,c@d.mx"):
            with self.subTest(direccion=mala):
                self.assertIsNone(correo.enviar(mala, "Asunto", "Cuerpo"))
        self.assertEqual(self.buzon, [])

    def test_no_se_pueden_inyectar_cabeceras_por_el_asunto(self):
        correo.enviar("a@b.mx", "Hola\r\nBcc: espia@x.mx", "Cuerpo con ñ y acentos")
        m = self.buzon[0]
        self.assertIsNone(m["Bcc"])
        self.assertNotIn("\n", m["Subject"])
        self.assertIn("ñ", self.cuerpo(m))

    def test_la_bandeja_guarda_los_mensajes_y_se_limita(self):
        for i in range(correo.MAX_BANDEJA + 20):
            correo.enviar("a@b.mx", f"Mensaje {i}", "x")
        b = correo.bandeja()
        self.assertEqual(len(b), correo.MAX_BANDEJA)
        self.assertEqual(b[0]["asunto"], f"Mensaje {correo.MAX_BANDEJA + 19}")            # el más reciente primero

    def test_modos_de_envio(self):
        correo.configurar(transporte=None)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SIGSAT_SMTP_HOST", None)
            self.assertEqual(correo.modo(), "desarrollo")
        with mock.patch.dict(os.environ, {"SIGSAT_SMTP_HOST": "smtp.ejemplo.mx"}):
            self.assertEqual(correo.modo(), "smtp")

    def test_en_modo_desarrollo_se_guarda_un_eml_y_nada_sale_a_internet(self):
        correo.configurar(transporte=None)
        os.environ.pop("SIGSAT_SMTP_HOST", None)
        with tempfile.TemporaryDirectory() as d, mock.patch("smtplib.SMTP") as smtp, mock.patch("smtplib.SMTP_SSL") as smtp_ssl:
            correo.configurar(carpeta=d)
            r = correo.enviar("alguien@ipn.mx", "Hola", "Texto con acentos: áéíóú")
            archivos = os.listdir(d)
            self.assertEqual(r["estado"], "enviado")
            self.assertEqual(len(archivos), 1)
            self.assertTrue(archivos[0].endswith(".eml"))
            contenido = open(os.path.join(d, archivos[0]), "rb").read().decode("utf-8", "replace")
            self.assertIn("alguien@ipn.mx", contenido)
            smtp.assert_not_called()
            smtp_ssl.assert_not_called()

    def test_smtp_cifra_valida_certificado_y_autentica(self):
        correo.configurar(transporte=None)
        entorno = {"SIGSAT_SMTP_HOST": "smtp.ejemplo.mx", "SIGSAT_SMTP_PORT": "587", "SIGSAT_SMTP_SECURE": "tls",
                   "SIGSAT_SMTP_USER": "usuario", "SIGSAT_SMTP_PASSWORD": "secreta", "SIGSAT_MAIL_FROM": "sigsat@ejemplo.mx"}
        with mock.patch.dict(os.environ, entorno), mock.patch("smtplib.SMTP") as smtp:
            r = correo.enviar("a@b.mx", "Hola", "x")
        servidor = smtp.return_value          # (smtplib devuelve el mismo objeto en «with»)
        smtp.assert_called_once_with("smtp.ejemplo.mx", 587, timeout=10)
        servidor.starttls.assert_called_once()
        contexto = servidor.starttls.call_args.kwargs["context"]
        self.assertTrue(contexto.check_hostname)                                          # se valida el certificado
        servidor.login.assert_called_once_with("usuario", "secreta")
        servidor.send_message.assert_called_once()
        self.assertEqual(r["estado"], "enviado")
        self.assertIn("sigsat@ejemplo.mx", servidor.send_message.call_args[0][0]["From"])

    def test_no_se_envian_credenciales_sin_cifrar_a_un_servidor_remoto(self):
        correo.configurar(transporte=None)
        entorno = {"SIGSAT_SMTP_HOST": "smtp.ejemplo.mx", "SIGSAT_SMTP_SECURE": "none",
                   "SIGSAT_SMTP_USER": "usuario", "SIGSAT_SMTP_PASSWORD": "secreta"}
        with mock.patch.dict(os.environ, entorno), mock.patch("smtplib.SMTP") as smtp:
            r = correo.enviar("a@b.mx", "Hola", "x")
        smtp.assert_not_called()
        self.assertEqual(r["estado"], "error")
        self.assertIn("sin cifrar", r["detalle"])

    def test_el_envio_asincrono_no_bloquea_y_se_completa_despues(self):
        liberar, enviados = threading.Event(), []

        def lento(msg):
            liberar.wait(5)
            enviados.append(msg)
        correo.configurar(asincrono=True, transporte=lento)
        inicio = time.monotonic()
        r = correo.enviar("a@b.mx", "Hola", "x")
        self.assertLess(time.monotonic() - inicio, 1.0, "enviar() no debe esperar al servidor")
        self.assertEqual(r["estado"], "en cola")
        liberar.set()
        for _ in range(100):
            if correo.bandeja()[0]["estado"] == "enviado":
                break
            time.sleep(0.05)
        self.assertEqual(correo.bandeja()[0]["estado"], "enviado")
        self.assertEqual(len(enviados), 1)

    def test_los_correos_de_ejemplo_no_se_envian_al_reiniciar(self):
        self.buzon.clear()
        datos.reiniciar()
        self.assertEqual(self.buzon, [])


class PruebasCorreoCalificacion(Base):
    """Al calificar el servicio se avisa por correo al técnico que lo atendió."""

    def finalizada(self):
        s = self.nueva(tipo="Incidencia de software")
        datos.actualizar_por_tecnico(s["folio"], self.sebastian, "Finalizado", "Listo")
        self.buzon.clear()
        return s["folio"]

    def test_al_calificar_se_avisa_al_tecnico(self):
        folio = self.finalizada()
        datos.calificar_servicio(folio, self.ana, 4)
        self.assertEqual([m["To"] for m in self.buzon], [self.sebastian["correo"]])
        m = self.buzon[0]
        self.assertIn("4/5", m["Subject"])
        self.assertIn(folio, m["Subject"])
        self.assertIn("Ana Reyes", self.cuerpo(m))

    def test_no_se_envia_nada_si_no_se_pudo_calificar(self):
        folio = self.finalizada()
        datos.calificar_servicio(folio, self.carlos, 5)            # no es suya
        s = self.nueva()
        self.buzon.clear()
        datos.calificar_servicio(s["folio"], self.ana, 5)          # aún no está finalizada
        with self.assertRaises(ValueError):
            datos.calificar_servicio(folio, self.ana, 9)           # calificación inválida
        self.assertEqual(self.buzon, [])

    def test_no_se_califica_dos_veces_ni_se_repite_el_correo(self):
        folio = self.finalizada()
        datos.calificar_servicio(folio, self.ana, 4)
        antes = len(self.buzon)
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 1), "no_aplica")
        self.assertEqual(len(self.buzon), antes)

    def test_un_fallo_de_correo_no_impide_calificar(self):
        folio = self.finalizada()
        correo.configurar(transporte=lambda m: (_ for _ in ()).throw(RuntimeError("servidor caído")))
        self.assertEqual(datos.calificar_servicio(folio, self.ana, 3), "ok")
        self.assertEqual(datos.buscar_por_folio(folio)["calificacion"], 3)

    def test_la_demo_de_ana_envia_el_correo_al_calificar(self):
        self.buzon.clear()
        datos.calificar_servicio("SIGSAT-0005", self.ana, 5)
        self.assertEqual({m["To"] for m in self.buzon}, {self.zyanya["correo"]})


class PruebasAvisoPorAsignar(Base):
    """Cada solicitud nueva avisa a los administradores que está por distribuirse."""

    def test_se_avisa_a_los_administradores(self):
        self.buzon.clear()
        s = self.nueva(tecnico=False)
        self.assertEqual([m["To"] for m in self.buzon], [self.admin["correo"]])
        m = self.buzon[0]
        self.assertIn(s["folio"], m["Subject"])
        self.assertIn("por asignar", m["Subject"])
        cuerpo = self.cuerpo(m)
        for dato in ("Contabilidad", "Matriz CDMX", "Alta", "Solicitudes"):
            self.assertIn(dato, cuerpo)

    def test_queda_anotado_en_la_bitacora(self):
        s = self.nueva(tecnico=False)
        eventos = [b["evento"] for b in s["bitacora"]]
        self.assertIn("Pendiente de asignación", eventos[-1])
        self.assertEqual(datos.verificar_bitacora(), [])

    def test_un_administrador_desactivado_no_recibe_el_aviso(self):
        datos._usuario_por_id(self.admin["id"])["activo"] = False
        self.buzon.clear()
        self.nueva(tecnico=False)
        self.assertEqual(self.buzon, [])

    def test_un_fallo_de_correo_no_impide_registrar_la_solicitud(self):
        correo.configurar(transporte=lambda m: (_ for _ in ()).throw(RuntimeError("servidor caído")))
        s = self.nueva(tecnico=False)
        self.assertIsNotNone(datos.buscar_por_folio(s["folio"]))


class PruebasMantenimientoCorrectivo(Base):
    def test_el_tipo_existe_con_su_prioridad_y_asigna_bien(self):
        self.assertIn("Mantenimiento correctivo", datos.tipos_activos())
        self.assertEqual(datos.prioridad_de_tipo("Mantenimiento correctivo"), "Media")
        s = self.nueva(tipo="Mantenimiento correctivo")
        self.assertEqual((s["prioridad"], s["sla_horas"]), ("Media", 60))
        self.assertIn("Mantenimiento preventivo", datos.tipos_activos())


if __name__ == "__main__":
    unittest.main()
