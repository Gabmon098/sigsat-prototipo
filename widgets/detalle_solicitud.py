import os
from html import escape

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QLineEdit, QFileDialog,
    QTextEdit, QPushButton, QScrollArea, QWidget, QSpinBox, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer

import archivos
import datos
from estilos import AZUL_OSCURO, TONO_ESTADO, TONO_PRIORIDAD, crear_badge
from permisos import puede
from widgets.utiles import (
    ajustar_a_pantalla, crear_area_desplazable, crear_contador, limitar_texto, texto_filtro_archivos
)


def _h(texto) -> str:
    """Texto de usuario -> HTML seguro. Los QLabel interpretan HTML, así que sin
    esto un texto con '<' o '&' se vería mal (o inyectaría formato)."""
    return escape(str(texto)).replace("\n", "<br>")


class DialogoDetalleSolicitud(QDialog):
    """Muestra el detalle completo de una solicitud: datos generales,
    bitácora de seguimiento y, según el rol, acciones disponibles
    (asignar para el Administrador; avanzar el estatus y comentar para el Técnico; calificar el servicio
    para el Representante). Solo abre solicitudes que el usuario puede ver. Cuando un técnico abre un
    reporte nuevo, queda «Visualizado» automáticamente."""

    def __init__(self, folio: str, usuario: dict, al_guardar=None, parent=None):
        super().__init__(parent)
        self.folio = folio
        self.usuario = usuario
        self.al_guardar = al_guardar
        self.setWindowTitle(f"Detalle de solicitud — {folio}")
        ajustar_a_pantalla(self, 560, 680)      # nunca más grande que la pantalla

        # Contenido desplazable (si la pantalla es chica, se desplaza en vez de salirse)
        # y, debajo, el botón Cerrar fijo: siempre visible.
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self._ajustando = False
        self._scroll = crear_area_desplazable(QWidget())
        raiz.addWidget(self._scroll, 1)
        pie = QWidget()
        lay_pie = QVBoxLayout(pie)
        lay_pie.setContentsMargins(24, 8, 24, 16)
        lay_pie.addWidget(self._boton_cerrar())
        raiz.addWidget(pie)
        self._registrar_visualizacion()
        self._construir_ui()

    def _registrar_visualizacion(self):
        """El técnico asignado que abre un reporte «Sin visualizar» lo deja «Visualizado»."""
        if not puede(self.usuario, "solicitud.atender"):
            return
        try:
            if datos.registrar_visualizacion(self.folio, self.usuario) == "ok":
                self._notificar_cambio()
        except PermissionError:
            pass

    # El contenido vive en un widget propio para poder reconstruirlo (p. ej.
    # después de asignar o actualizar, que cambian las acciones).
    def _construir_ui(self):
        self._contenido = QWidget()
        self._scroll.setWidget(self._contenido)     # reemplaza (y borra) el contenido anterior
        self._contenido.setMinimumHeight(0)

        layout = QVBoxLayout(self._contenido)
        layout.setContentsMargins(24, 24, 24, 12)
        layout.setSpacing(10)

        s = datos.solicitud_visible(self.usuario, self.folio)
        if s is None:
            aviso = QLabel("No tienes acceso a esta solicitud o ya no existe.")
            aviso.setWordWrap(True)
            layout.addWidget(aviso)
            layout.addStretch()
            return

        cab = QHBoxLayout()
        titulo = QLabel(s["folio"])
        titulo.setStyleSheet(f"font-size:20px; font-weight:800; color:{AZUL_OSCURO};")
        cab.addWidget(titulo)
        cab.addStretch()
        cab.addWidget(crear_badge(s["estado"], TONO_ESTADO[s["estado"]]))
        cab.addWidget(crear_badge(f"Prioridad {s['prioridad']}", TONO_PRIORIDAD[s["prioridad"]]))
        layout.addLayout(cab)

        layout.addWidget(self._fila("Tipo de solicitud", s["tipo"]))
        layout.addWidget(self._fila("Área", s["area"] or "—"))
        layout.addWidget(self._fila("Sucursal", s["sucursal"] or "—"))
        layout.addWidget(self._fila("Descripción", s["descripcion"]))
        layout.addWidget(self._fila("Solicitante", s["solicitante"]))
        layout.addWidget(self._fila("Técnico asignado", s["agente_asignado"] or "Sin asignar"))
        layout.addWidget(self._fila("Fecha de creación", s["fecha_creacion"]))
        if s["fecha_finalizacion"]:
            layout.addWidget(self._fila("Fecha de finalización", s["fecha_finalizacion"]))
        # RF-16: plazo de atención (el tiempo estimado del tipo de solicitud) y si ya se venció
        if s["cumplio_sla"] is not None:
            marca = ("<span style='color:#14603A;'>(cumplido)</span>" if s["cumplio_sla"]
                     else "<span style='color:#B91C1C;'>(fuera de plazo)</span>")
        else:
            marca = "<span style='color:#B91C1C; font-weight:700;'>(VENCIDA)</span>" if s["vencida"] else ""
        layout.addWidget(self._fila("Fecha límite de atención", f"{s['vence']} ({s['sla_horas']} h)", marca))
        if s["calificacion"] is not None:
            layout.addWidget(self._fila("Calificación del servicio", f"{s['calificacion']} de 5"))

        if s["estado"] == "Finalizado":
            # Lo ven por igual el representante, el técnico y el administrador.
            quien = f" por {s['agente_asignado']}" if s["agente_asignado"] else ""
            cuando = f" el {s['fecha_finalizacion']}" if s["fecha_finalizacion"] else ""
            banner = QLabel(f"✔ Solicitud finalizada{quien}{cuando}.")
            banner.setObjectName("avisoFinalizada")
            banner.setTextFormat(Qt.PlainText)
            banner.setWordWrap(True)
            banner.setStyleSheet("background:#DDF3E6; color:#14603A; border-radius:6px; padding:8px 10px; font-weight:700;")
            layout.addWidget(banner)

        if s["vencida"] and (puede(self.usuario, "solicitud.atender") or puede(self.usuario, "solicitud.asignar")):
            aviso = QLabel("Esta solicitud superó su fecha límite de atención; se contará como fuera de tiempo.")
            aviso.setWordWrap(True)
            aviso.setStyleSheet("background:#FBE1DE; color:#9B2A1F; border-radius:6px; padding:8px 10px; font-weight:700;")
            layout.addWidget(aviso)

        layout.addWidget(self._separador())
        layout.addWidget(self._seccion_adjuntos(s))
        layout.addWidget(self._separador())

        lbl_bitacora = QLabel("Historial de atención")
        lbl_bitacora.setStyleSheet("font-weight:700; margin-top:4px;")
        layout.addWidget(lbl_bitacora)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scrollBitacora")
        contenedor = QWidget()
        lay_bit = QVBoxLayout(contenedor)
        lay_bit.setAlignment(Qt.AlignTop)
        for entrada in s["bitacora"]:
            item = QLabel(f"<b>{_h(entrada['fecha'])}</b> — {_h(entrada['autor'])}<br>{_h(entrada['evento'])}")
            item.setWordWrap(True)
            item.setStyleSheet("padding: 6px 8px; border-bottom: 1px solid #F1F5F9;")
            lay_bit.addWidget(item)
        scroll.setWidget(contenedor)
        scroll.setMinimumHeight(100)
        # Alto "ignorado": la bitácora no exige su tamaño ideal (que es grande) y solo
        # ocupa lo que sobre, para que el contenido no obligue a desplazar sin necesidad.
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        layout.addWidget(scroll, 1)             # la bitácora aprovecha el espacio sobrante

        # --- Acciones según permisos y estado ---
        sin_atencion = s["estado"] in datos.ESTADOS_SIN_ATENCION           # Finalizado
        if puede(self.usuario, "solicitud.asignar") and not sin_atencion:
            layout.addWidget(self._separador())
            layout.addWidget(self._panel_asignacion(s))
        if puede(self.usuario, "solicitud.atender") and not sin_atencion and s["agente_id"] == self.usuario["id"]:
            layout.addWidget(self._separador())
            layout.addWidget(self._panel_acciones_tecnico(s))
        elif (puede(self.usuario, "solicitud.calificar") and s["por_calificar"]
              and s["solicitante_id"] == self.usuario["id"]):
            layout.addWidget(self._separador())
            layout.addWidget(self._panel_calificacion(s))

    def _boton_cerrar(self):
        btn = QPushButton("Cerrar")
        btn.setObjectName("botonSecundario")
        btn.clicked.connect(self.accept)
        return btn

    # El texto que se ajusta a varias líneas no informa bien su alto mínimo: sin esto, cuando falta espacio las
    # etiquetas se comprimen y se recorta texto en vez de aparecer la barra de desplazamiento. Se fija el alto
    # real de cada etiqueta para su ancho actual y, con eso, el del contenido completo.
    def _ajustar_alto_minimo(self):
        contenido = getattr(self, "_contenido", None)
        lay = contenido.layout() if contenido is not None else None
        if lay is None or self._ajustando:
            return
        self._ajustando = True
        try:
            etiquetas = [w for w in contenido.findChildren(QLabel) if w.wordWrap()]
            for w in etiquetas:
                w.ensurePolished()                         # aplica negritas/estilos ANTES de medir el texto
            for _pasada in range(2):                       # el alto de unas puede cambiar el ancho/alto de otras
                for w in etiquetas:
                    w.setMinimumHeight(0)
                lay.activate()
                for w in etiquetas:
                    if w.width() > 0:
                        w.setMinimumHeight(w.heightForWidth(w.width()) + 6)    # + holgura: la fuente en negrita mide un poco más
                lay.activate()
            contenido.setMinimumHeight(lay.totalMinimumSize().height())
        finally:
            self._ajustando = False

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        QTimer.singleShot(0, self._ajustar_alto_minimo)

    def showEvent(self, evento):
        super().showEvent(evento)
        self._ajustar_alto_minimo()
        QTimer.singleShot(0, self._ajustar_alto_minimo)

    def _fila(self, etiqueta, valor, extra_html=""):
        w = QLabel(f"<span style='color:#64748B;'>{_h(etiqueta)}:</span> {_h(valor)} {extra_html}")
        w.setWordWrap(True)
        return w

    def _separador(self):
        linea = QFrame()
        linea.setFrameShape(QFrame.HLine)
        linea.setStyleSheet("color:#E2E8F0;")
        return linea

    def _notificar_cambio(self):
        if self.al_guardar:
            self.al_guardar()

    # ---------------------------------------------------------- adjuntos
    def _seccion_adjuntos(self, s):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        titulo = QLabel("Archivos adjuntos")
        titulo.setStyleSheet("font-weight:700;")
        lay.addWidget(titulo)

        lista = datos.adjuntos_de(self.folio, self.usuario)
        if not lista:
            vacio = QLabel("Esta solicitud no tiene archivos adjuntos (los archivos solo se adjuntan al registrarla).")
            vacio.setStyleSheet("color:#64748B;")
            vacio.setWordWrap(True)          # sin esto la frase ensancha el diálogo y recorta lo de la derecha
            lay.addWidget(vacio)
        for a in lista:
            fila = QHBoxLayout()
            etiqueta = QLabel(f"{_h(a['nombre'])}  <span style='color:#64748B;'>({archivos.formato_tamano(a['tamano'])} · "
                              f"{_h(a['subido_por'])}, {_h(a['fecha'])})</span>")
            etiqueta.setWordWrap(True)
            fila.addWidget(etiqueta, 1)
            btn_guardar = QPushButton("Guardar…")
            btn_guardar.setObjectName("botonSecundario")
            btn_guardar.clicked.connect(lambda _c=False, i=a["id"]: self._guardar_adjunto(i))
            fila.addWidget(btn_guardar)
            if a["subido_por_id"] == self.usuario["id"] and datos.puede_adjuntar(self.usuario, self.folio):
                btn_quitar = QPushButton("Quitar")
                btn_quitar.setObjectName("botonSecundario")
                btn_quitar.clicked.connect(lambda _c=False, i=a["id"]: self._quitar_adjunto(i))
                fila.addWidget(btn_quitar)
            lay.addLayout(fila)

        if datos.puede_adjuntar(self.usuario, self.folio):
            if len(lista) < archivos.MAX_ADJUNTOS_POR_SOLICITUD:
                btn = QPushButton("Adjuntar archivo…")
                btn.setObjectName("botonSecundario")
                btn.clicked.connect(self._elegir_archivos)
                lay.addWidget(btn)
        return panel

    def _guardar_adjunto(self, adjunto_id):
        encontrado = datos.obtener_adjunto(adjunto_id, self.usuario)
        if not encontrado:
            QMessageBox.warning(self, "No disponible", "No se encontró el archivo.")
            return
        meta, contenido = encontrado
        ruta, _filtro = QFileDialog.getSaveFileName(self, "Guardar archivo adjunto", meta["nombre"])
        self._escribir_archivo(ruta, contenido)

    def _escribir_archivo(self, ruta, contenido):
        if not ruta:
            return
        try:
            with open(ruta, "wb") as f:
                f.write(contenido)
        except OSError as error:
            QMessageBox.warning(self, "No se pudo guardar", f"No se pudo escribir el archivo: {error.strerror or error}")
            return
        QMessageBox.information(self, "Archivo guardado", f"El archivo se guardó en:\n{ruta}")

    def _elegir_archivos(self):
        rutas, _filtro = QFileDialog.getOpenFileNames(self, "Elegir archivos para adjuntar", "", texto_filtro_archivos())
        self._agregar_rutas(rutas)

    def _agregar_rutas(self, rutas):
        problemas, agregado = [], False
        for ruta in rutas:
            nombre = os.path.basename(ruta)
            try:
                if os.path.getsize(ruta) > archivos.MAX_TAMANO_ADJUNTO:
                    raise ValueError(f"«{nombre}» pesa más de {archivos.formato_tamano(archivos.MAX_TAMANO_ADJUNTO)}.")
                with open(ruta, "rb") as f:
                    datos.agregar_adjunto(self.folio, self.usuario, nombre, f.read())
                agregado = True
            except OSError:
                problemas.append(f"«{nombre}»: no se pudo leer el archivo.")
            except (ValueError, PermissionError) as error:
                problemas.append(str(error))
        if agregado:
            self._notificar_cambio()
            self._construir_ui()
        if problemas:
            QMessageBox.warning(self, "Algunos archivos no se agregaron", "\n".join(problemas))

    def _quitar_adjunto(self, adjunto_id):
        try:
            datos.quitar_adjunto(adjunto_id, self.usuario)
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "No se pudo quitar", str(error))
            return
        self._notificar_cambio()
        self._construir_ui()

    # ------------------------------------------------ asignación (RF-09)
    def _panel_asignacion(self, s):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 4, 0, 0)
        reasigna = s["agente_id"] is not None

        titulo = QLabel("Reasignar solicitud" if reasigna else "Asignar solicitud")
        titulo.setStyleSheet("font-weight:700;")
        lay.addWidget(titulo)
        ayuda = QLabel("Elige al técnico que la atenderá. Su reporte quedará «Sin visualizar» para él. "
                       "Se avisa por correo al técnico y al representante.")
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color:#64748B; font-size:11px;")
        lay.addWidget(ayuda)

        self.combo_agente = QComboBox()
        for c in datos.carga_trabajo():       # se muestra la carga de cada agente para repartir mejor el trabajo
            texto = f"{c['agente']} ({c['abiertas']} abiertas" + (f", {c['vencidas']} vencidas)" if c["vencidas"] else ")")
            self.combo_agente.addItem(texto, c["agente_id"])
        if reasigna:
            indice = self.combo_agente.findData(s["agente_id"])
            if indice >= 0:
                self.combo_agente.setCurrentIndex(indice)
        lay.addWidget(self.combo_agente)

        self.txt_motivo = QLineEdit()
        self.txt_motivo.setPlaceholderText("Motivo (opcional)")
        self.txt_motivo.setMaxLength(datos.LIM_COMENTARIO)
        lay.addWidget(self.txt_motivo)

        self.btn_asignar = QPushButton("Reasignar" if reasigna else "Asignar")
        self.btn_asignar.setObjectName("botonPrimario")
        self.btn_asignar.clicked.connect(self._asignar_agente)
        lay.addWidget(self.btn_asignar)
        return panel

    def _asignar_agente(self):
        try:
            resultado = datos.asignar_solicitud(self.folio, self.usuario, self.combo_agente.currentData(),
                                                self.txt_motivo.text())
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "No se pudo asignar", str(error))
            return
        if resultado == "ok":
            QMessageBox.information(self, "Solicitud asignada", "La asignación quedó registrada en la bitácora y se avisó por correo.")
        elif resultado == "sin_cambios":
            QMessageBox.information(self, "Sin cambios", "Esa solicitud ya está asignada a ese técnico.")
            return
        else:
            QMessageBox.warning(self, "No se pudo asignar", "La solicitud ya está finalizada o no existe.")
        self._notificar_cambio()
        self._construir_ui()

    # ----------------------------------------------------------- técnico
    def _panel_acciones_tecnico(self, s):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 4, 0, 0)

        lbl_estado = QLabel("Actualizar estatus del reporte")
        lbl_estado.setStyleSheet("font-weight:700;")
        self.combo_estado = QComboBox()
        # solo hacia adelante: el estatus actual y los siguientes
        self.combo_estado.addItems(datos.ESTADOS[datos.ESTADOS.index(s["estado"]):] if s["estado"] != "Sin visualizar"
                                   else datos.ESTADOS_TECNICO)
        self.combo_estado.setCurrentText(s["estado"] if s["estado"] != "Sin visualizar" else "Visualizado")

        lbl_comentario = QLabel("Comentario / avance (obligatorio para finalizar)")
        lbl_comentario.setStyleSheet("font-weight:700; margin-top:6px;")
        self.txt_comentario = QTextEdit()
        self.txt_comentario.setPlaceholderText("Describe el avance o la acción realizada…")
        self.txt_comentario.setFixedHeight(60)
        contador = crear_contador()
        limitar_texto(self.txt_comentario, datos.LIM_COMENTARIO, contador)

        btn_guardar = QPushButton("Guardar actualización")
        btn_guardar.setObjectName("botonPrimario")
        btn_guardar.clicked.connect(self._guardar_actualizacion_tecnico)

        lay.addWidget(lbl_estado)
        lay.addWidget(self.combo_estado)
        lay.addWidget(lbl_comentario)
        lay.addWidget(self.txt_comentario)
        lay.addWidget(contador)
        lay.addWidget(btn_guardar)
        return panel

    def _guardar_actualizacion_tecnico(self):
        try:
            resultado = datos.actualizar_por_tecnico(
                self.folio, self.usuario, self.combo_estado.currentText(), self.txt_comentario.toPlainText())
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "Revisa los datos", str(error))
            return
        if resultado == "ok":
            self._notificar_cambio()
            self.accept()
        elif resultado == "sin_cambios":
            QMessageBox.information(self, "Sin cambios",
                                    "No hay cambios que guardar: cambia el estatus o escribe un comentario.")
        else:  # 'finalizada' / 'no_existe'
            QMessageBox.warning(self, "No se pudo guardar",
                                "Esta solicitud ya está finalizada y no admite más cambios.")
            self._notificar_cambio()
            self._construir_ui()

    # ----------------------------------------------------- representante
    def _panel_calificacion(self, s):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 4, 0, 0)

        lbl = QLabel("El técnico marcó tu solicitud como FINALIZADA. Califica el servicio recibido.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-weight:700;")

        lbl_cal = QLabel("Calificación del servicio (1 a 5)")
        self.spin_calificacion = QSpinBox()
        self.spin_calificacion.setRange(1, 5)
        self.spin_calificacion.setValue(5)

        btn = QPushButton("Calificar el servicio")
        btn.setObjectName("botonPrimario")
        btn.clicked.connect(self._guardar_calificacion)

        lay.addWidget(lbl)
        lay.addWidget(lbl_cal)
        lay.addWidget(self.spin_calificacion)
        lay.addWidget(btn)
        return panel

    def _guardar_calificacion(self):
        try:
            resultado = datos.calificar_servicio(self.folio, self.usuario, self.spin_calificacion.value())
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "No se pudo calificar", str(error))
            return
        if resultado != "ok":
            QMessageBox.warning(self, "No se pudo calificar", "Esta solicitud no está esperando tu calificación.")
        else:
            QMessageBox.information(self, "Gracias", "Gracias por tu calificación; quedó registrada.")
        self._notificar_cambio()
        self.accept()
