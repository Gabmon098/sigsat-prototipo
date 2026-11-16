from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QComboBox, QPushButton, QScrollArea, QTextEdit, QDialog, QLineEdit, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

import datos
from estilos import TONO_CONVERSACION, aplicar_badge
from permisos import puede
from widgets.utiles import ajustar_a_pantalla, crear_contador, limitar_texto, poner_con_scroll


class DialogoNuevaConversacion(QDialog):
    """Formulario para abrir una conversación con la Administración (Mesa de Servicio)."""

    def __init__(self, usuario: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva conversación con la Administración")
        ajustar_a_pantalla(self, 460, 420)
        self.asunto = ""
        self.folio = None
        self.mensaje = ""

        cuerpo = QWidget()
        poner_con_scroll(self, cuerpo)
        lay = QVBoxLayout(cuerpo)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Asunto"))
        self.txt_asunto = QLineEdit()
        self.txt_asunto.setMaxLength(datos.LIM_ASUNTO)
        self.txt_asunto.setPlaceholderText("Ej. Duda sobre el estatus de mi solicitud")
        lay.addWidget(self.txt_asunto)

        lay.addSpacing(6)
        lay.addWidget(QLabel("Solicitud relacionada (opcional)"))
        self.combo_folio = QComboBox()
        self.combo_folio.addItem("Ninguna", None)
        for s in (datos.solicitudes_de(usuario["id"]) if puede(usuario, "solicitud.crear")
                  else datos.listar_reportes(usuario, incluir_finalizados=True)):
            self.combo_folio.addItem(f"{s['folio']} — {s['tipo']}", s["folio"])
        lay.addWidget(self.combo_folio)

        lay.addSpacing(6)
        lay.addWidget(QLabel("Mensaje"))
        self.txt_mensaje = QTextEdit()
        self.txt_mensaje.setPlaceholderText("Escribe tu mensaje para la Administración…")
        contador = crear_contador()
        limitar_texto(self.txt_mensaje, datos.LIM_MENSAJE, contador)
        lay.addWidget(self.txt_mensaje)
        lay.addWidget(contador)

        fila = QHBoxLayout()
        fila.addStretch()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setObjectName("botonSecundario")
        btn_cancelar.clicked.connect(self.reject)
        btn_enviar = QPushButton("Enviar")
        btn_enviar.setObjectName("botonPrimario")
        btn_enviar.clicked.connect(self._aceptar)
        fila.addWidget(btn_cancelar)
        fila.addWidget(btn_enviar)
        lay.addSpacing(8)
        lay.addLayout(fila)

    def _aceptar(self):
        asunto = self.txt_asunto.text().strip()
        mensaje = self.txt_mensaje.toPlainText().strip()
        if not asunto or not mensaje:
            QMessageBox.warning(self, "Falta información", "Escribe un asunto y un mensaje.")
            return
        self.asunto, self.mensaje = asunto, mensaje
        self.folio = self.combo_folio.currentData()
        self.accept()


class VistaMesaTI(QWidget):
    """Mesa de Servicio: canal de comunicación entre la Administración y las áreas (representantes) y los
    técnicos. Representantes y técnicos ven sus propias conversaciones; el Administrador, todas."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self.conv_actual = None
        self._construir_ui()
        self.actualizar()

    # ------------------------------------------------------------------ UI
    def _construir_ui(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(30, 26, 30, 26)
        raiz.setSpacing(10)

        titulo = QLabel("Mesa de Servicio")
        titulo.setObjectName("tituloVista")
        textos = {
            "Representante de Área": "Canal directo con la Administración para dudas y seguimiento de tus solicitudes.",
            "Técnico": "Canal directo con la Administración para dudas, avisos y apoyo en tus reportes.",
            "Administrador": "Atiende las conversaciones de las áreas y de los técnicos.",
        }
        subtitulo = QLabel(textos.get(self.usuario["rol"], ""))
        subtitulo.setObjectName("subtituloVista")
        raiz.addWidget(titulo)
        raiz.addWidget(subtitulo)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(16)
        raiz.addLayout(cuerpo, 1)

        # Columna izquierda: filtro + lista
        izq = QVBoxLayout()
        fila_filtro = QHBoxLayout()
        self.combo_filtro = QComboBox()
        self.combo_filtro.addItems(["Todas"] + datos.ESTADOS_CONVERSACION)
        self.combo_filtro.currentTextChanged.connect(self.actualizar)
        fila_filtro.addWidget(self.combo_filtro, 1)
        if puede(self.usuario, "mesa.crear_conversacion"):
            btn_nueva = QPushButton("Nueva")
            btn_nueva.setObjectName("botonPrimario")
            btn_nueva.setCursor(Qt.PointingHandCursor)
            btn_nueva.clicked.connect(self._nueva)
            fila_filtro.addWidget(btn_nueva)
        izq.addLayout(fila_filtro)

        self.lista = QListWidget()
        self.lista.setObjectName("listaConversaciones")
        self.lista.itemClicked.connect(self._seleccionar)
        izq.addWidget(self.lista, 1)

        cont_izq = QWidget()
        cont_izq.setLayout(izq)
        cont_izq.setFixedWidth(320)
        cuerpo.addWidget(cont_izq)

        # Columna derecha: encabezado + chat + entrada + acciones
        der = QVBoxLayout()
        fila_cab = QHBoxLayout()
        self.lbl_asunto = QLabel("")
        self.lbl_asunto.setStyleSheet("font-size:16px; font-weight:700; color:#122C55;")
        self.lbl_estado = QLabel("")
        fila_cab.addWidget(self.lbl_asunto, 1)
        fila_cab.addWidget(self.lbl_estado)
        der.addLayout(fila_cab)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color:#64748B; font-size:12px;")
        der.addWidget(self.lbl_info)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("scrollChat")
        self.scroll.setWidgetResizable(True)
        self.contenedor_chat = QWidget()
        self.contenedor_chat.setObjectName("contenedorChat")
        self.lay_chat = QVBoxLayout(self.contenedor_chat)
        self.lay_chat.setContentsMargins(14, 14, 14, 14)
        self.lay_chat.setSpacing(10)
        self.scroll.setWidget(self.contenedor_chat)
        der.addWidget(self.scroll, 1)

        self.panel_entrada = QWidget()
        fila_entrada = QHBoxLayout(self.panel_entrada)
        fila_entrada.setContentsMargins(0, 0, 0, 0)
        self.txt_mensaje = QTextEdit()
        self.txt_mensaje.setPlaceholderText("Escribe un mensaje…  (Ctrl+Enter para enviar)")
        self.txt_mensaje.setFixedHeight(64)
        limitar_texto(self.txt_mensaje, datos.LIM_MENSAJE)
        atajo = QShortcut(QKeySequence("Ctrl+Return"), self.txt_mensaje)
        atajo.setContext(Qt.WidgetShortcut)
        atajo.activated.connect(self._enviar)
        btn_enviar = QPushButton("Enviar")
        btn_enviar.setObjectName("botonPrimario")
        btn_enviar.setCursor(Qt.PointingHandCursor)
        btn_enviar.setMinimumHeight(40)
        btn_enviar.clicked.connect(self._enviar)
        fila_entrada.addWidget(self.txt_mensaje, 1)
        fila_entrada.addWidget(btn_enviar)
        der.addWidget(self.panel_entrada)

        self.lbl_cerrada = QLabel("Esta conversación está cerrada.")
        self.lbl_cerrada.setStyleSheet("color:#64748B;")
        der.addWidget(self.lbl_cerrada)

        self.panel_acciones = QWidget()
        fila_acc = QHBoxLayout(self.panel_acciones)
        fila_acc.setContentsMargins(0, 0, 0, 0)
        self.btn_cerrar = QPushButton("Cerrar conversación")
        self.btn_cerrar.setObjectName("botonSecundario")
        self.btn_cerrar.clicked.connect(self._cerrar)
        fila_acc.addStretch()
        fila_acc.addWidget(self.btn_cerrar)
        der.addWidget(self.panel_acciones)

        cont_der = QWidget()
        cont_der.setLayout(der)
        cuerpo.addWidget(cont_der, 1)

    # ------------------------------------------------------------ datos/UI
    def actualizar(self):
        filtro = self.combo_filtro.currentText()
        visibles = datos.conversaciones_visibles(self.usuario, "" if filtro == "Todas" else filtro)

        self.lista.blockSignals(True)
        self.lista.clear()
        fila_actual = None
        for i, c in enumerate(visibles):
            contraparte = c["solicitante"] if puede(self.usuario, "mesa.ver_todas") else "Administración"
            item = QListWidgetItem(f"{c['id']} · {c['asunto']}\n{c['estado']} · {contraparte}")
            item.setData(Qt.UserRole, c["id"])
            self.lista.addItem(item)
            if c["id"] == self.conv_actual:
                fila_actual = i
        if fila_actual is not None:
            self.lista.setCurrentRow(fila_actual)
        else:
            self.conv_actual = None
        self.lista.blockSignals(False)
        self._render_chat()

    def _seleccionar(self, item):
        self.conv_actual = item.data(Qt.UserRole)
        self._render_chat()

    def _limpiar_chat(self):
        while self.lay_chat.count():
            it = self.lay_chat.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _render_chat(self):
        self._limpiar_chat()
        c = datos.buscar_conversacion(self.conv_actual) if self.conv_actual else None

        if c is None:
            self.lbl_asunto.setText("")
            self.lbl_estado.hide()
            self.lbl_info.setText("")
            vacio = QLabel("Selecciona una conversación de la lista para ver los mensajes.")
            vacio.setAlignment(Qt.AlignCenter)
            vacio.setStyleSheet("color:#94A3B8;")
            self.lay_chat.addWidget(vacio)
            self.lay_chat.addStretch()
            self.panel_entrada.hide()
            self.lbl_cerrada.hide()
            self.panel_acciones.hide()
            return

        self.lbl_asunto.setText(c["asunto"])
        aplicar_badge(self.lbl_estado, c["estado"], TONO_CONVERSACION[c["estado"]])
        self.lbl_estado.show()
        info = f"{c['id']} · {c['rol_solicitante'] or 'Usuario'}: {c['solicitante']}"
        if c["folio"]:
            info += f" · Solicitud {c['folio']}"
        self.lbl_info.setText(info)

        for m in c["mensajes"]:
            self.lay_chat.addWidget(self._fila_mensaje(m))
        self.lay_chat.addStretch()
        cerrada = c["estado"] == "Cerrada"
        puede_escribir = datos.puede_escribir_en(self.usuario, c)
        self.panel_entrada.setVisible(puede_escribir)
        self.lbl_cerrada.setVisible(cerrada)
        self.btn_cerrar.setVisible(puede(self.usuario, "mesa.cerrar") and not cerrada)
        self.panel_acciones.setVisible(self.btn_cerrar.isVisibleTo(self.panel_acciones))

        QTimer.singleShot(0, self._ir_al_final)
        QTimer.singleShot(0, self._ajustar_alturas_burbujas)

    def _ajustar_alturas_burbujas(self):
        """Corrige un problema de Qt: una QLabel con ajuste de palabras dentro
        de un QVBoxLayout anidado en un QHBoxLayout a veces recibe menos alto
        del que necesita su propio texto ya envuelto. Una vez que el layout ya
        asignó el ancho final, recalculamos y forzamos la altura correcta."""
        for burbuja in self.contenedor_chat.findChildren(QLabel):
            if burbuja.objectName() in ("burbujaPropia", "burbujaAjena"):
                alto_necesario = burbuja.heightForWidth(burbuja.width())
                if alto_necesario > burbuja.height():
                    burbuja.setMinimumHeight(alto_necesario)

    def _ir_al_final(self):
        barra = self.scroll.verticalScrollBar()
        barra.setValue(barra.maximum())

    def _fila_mensaje(self, m: dict) -> QWidget:
        fila = QWidget()
        lay = QHBoxLayout(fila)
        lay.setContentsMargins(0, 0, 0, 0)

        if m["rol"] == "Sistema":
            lbl = QLabel(f"{m['texto']} · {m['fecha']}")
            lbl.setObjectName("mensajeSistema")
            lbl.setAlignment(Qt.AlignCenter)
            lay.addWidget(lbl)
            return fila

        propio = m["autor_id"] is not None and m["autor_id"] == self.usuario["id"]
        alineacion = Qt.AlignRight if propio else Qt.AlignLeft

        col = QVBoxLayout()
        col.setSpacing(2)
        meta = QLabel(f"{m['autor']} · {m['rol']} · {m['fecha']}")
        meta.setObjectName("metaMensaje")
        burbuja = QLabel(m["texto"])
        burbuja.setObjectName("burbujaPropia" if propio else "burbujaAjena")
        burbuja.setTextFormat(Qt.PlainText)
        burbuja.setWordWrap(True)
        burbuja.setMaximumWidth(440)
        burbuja.setTextInteractionFlags(Qt.TextSelectableByMouse)
        col.addWidget(meta, alignment=alineacion)
        col.addWidget(burbuja, alignment=alineacion)

        if propio:
            lay.addStretch()
            lay.addLayout(col)
        else:
            lay.addLayout(col)
            lay.addStretch()
        return fila

    # ------------------------------------------------------------- acciones
    def _enviar(self):
        if not self.conv_actual:
            return
        texto = self.txt_mensaje.toPlainText().strip()
        if not texto:
            return
        if not datos.enviar_mensaje(self.conv_actual, self.usuario, texto):
            QMessageBox.warning(self, "No se pudo enviar", "No puedes enviar mensajes en esta conversación.")
            self.actualizar()
            return
        self.txt_mensaje.clear()
        self.actualizar()

    def _cerrar(self):
        if not self.conv_actual or not puede(self.usuario, "mesa.cerrar"):
            return
        r = QMessageBox.question(self, "Cerrar conversación",
                                 "¿Cerrar esta conversación? Ya no se podrán enviar más mensajes.",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            if not datos.cerrar_conversacion(self.conv_actual, self.usuario):
                QMessageBox.warning(self, "No se pudo cerrar", "No se pudo cerrar la conversación.")
            self.actualizar()

    def _nueva(self):
        if not puede(self.usuario, "mesa.crear_conversacion"):
            return
        dlg = DialogoNuevaConversacion(self.usuario, self)
        if dlg.exec() == QDialog.Accepted:
            try:
                c = datos.crear_conversacion(self.usuario, dlg.asunto, dlg.mensaje, dlg.folio)
            except ValueError as error:
                QMessageBox.warning(self, "Revisa los datos", str(error))
                return
            self.conv_actual = c["id"]
            self.combo_filtro.setCurrentText("Todas")
            self.actualizar()
