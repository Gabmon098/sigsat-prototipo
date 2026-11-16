import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTextEdit, QPushButton, QFrame, QMessageBox,
    QListWidget, QFileDialog
)
from PySide6.QtCore import Qt, Signal

import archivos
import datos
from widgets.utiles import crear_contador, limitar_texto, texto_filtro_archivos


class VistaNuevaSolicitud(QWidget):
    """Formulario de registro (check-in) de una nueva solicitud. El área y la sucursal salen de la cuenta del
    representante; la prioridad, del tiempo estimado de solución del tipo de solicitud."""

    solicitud_creada = Signal(str)  # emite el folio generado

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._adjuntos = []          # [(nombre, bytes)] listos para enviarse con la solicitud
        self._construir_ui()

    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(10)

        titulo = QLabel("Nueva solicitud")
        titulo.setObjectName("tituloVista")
        subtitulo = QLabel("Registra tu solicitud de incidente y recibe un folio único para darle seguimiento.")
        subtitulo.setObjectName("subtituloVista")

        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addSpacing(10)

        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaFormulario")
        lay_t = QVBoxLayout(tarjeta)
        lay_t.setContentsMargins(24, 24, 24, 24)
        lay_t.setSpacing(6)

        lay_t.addWidget(QLabel("Tipo de solicitud"))
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(datos.tipos_activos())
        self.combo_tipo.currentTextChanged.connect(self._actualizar_prioridad)
        lay_t.addWidget(self.combo_tipo)

        # La prioridad no la elige quien solicita: sale del tiempo estimado del tipo. Se muestra para que se vea.
        self.lbl_prioridad = QLabel("")
        self.lbl_prioridad.setStyleSheet("color:#64748B; font-size:11px;")
        self.lbl_prioridad.setWordWrap(True)
        lay_t.addWidget(self.lbl_prioridad)

        # El área y la sucursal son las de la cuenta del representante.
        self.lbl_origen = QLabel(f"Área: {self.usuario.get('area') or '—'}   ·   Sucursal: {self.usuario.get('sucursal') or '—'}")
        self.lbl_origen.setStyleSheet("color:#64748B; font-size:11px;")
        lay_t.addWidget(self.lbl_origen)

        lay_t.addSpacing(8)
        lay_t.addWidget(QLabel("Descripción"))
        self.txt_descripcion = QTextEdit()
        self.txt_descripcion.setPlaceholderText("Describe brevemente el problema o la solicitud…")
        self.txt_descripcion.setFixedHeight(120)
        self.contador = crear_contador()
        limitar_texto(self.txt_descripcion, datos.LIM_DESCRIPCION, self.contador)
        lay_t.addWidget(self.txt_descripcion)
        lay_t.addWidget(self.contador)

        lay_t.addSpacing(8)
        lay_t.addWidget(QLabel("Archivos adjuntos (opcional — solo se pueden agregar ahora, al registrar la solicitud)"))
        fila_adj = QHBoxLayout()
        self.btn_adjuntar = QPushButton("Agregar archivos…")
        self.btn_adjuntar.setObjectName("botonSecundario")
        self.btn_adjuntar.clicked.connect(self._elegir_archivos)
        self.btn_quitar_adjunto = QPushButton("Quitar seleccionado")
        self.btn_quitar_adjunto.setObjectName("botonSecundario")
        self.btn_quitar_adjunto.setEnabled(False)
        self.btn_quitar_adjunto.clicked.connect(self._quitar_adjunto)
        fila_adj.addWidget(self.btn_adjuntar)
        fila_adj.addWidget(self.btn_quitar_adjunto)
        fila_adj.addStretch()
        lay_t.addLayout(fila_adj)
        self.lista_adjuntos = QListWidget()
        self.lista_adjuntos.setMaximumHeight(84)
        self.lista_adjuntos.itemSelectionChanged.connect(
            lambda: self.btn_quitar_adjunto.setEnabled(bool(self.lista_adjuntos.selectedItems())))
        lay_t.addWidget(self.lista_adjuntos)
        self.lbl_ayuda_adjuntos = QLabel("")
        self.lbl_ayuda_adjuntos.setStyleSheet("color:#64748B; font-size:11px;")
        lay_t.addWidget(self.lbl_ayuda_adjuntos)
        self._actualizar_adjuntos()

        lay_t.addSpacing(14)
        btn_enviar = QPushButton("Enviar solicitud")
        btn_enviar.setObjectName("botonPrimario")
        btn_enviar.setCursor(Qt.PointingHandCursor)
        btn_enviar.setMinimumHeight(38)
        btn_enviar.clicked.connect(self._enviar)
        lay_t.addWidget(btn_enviar)

        layout.addWidget(tarjeta)
        layout.addStretch()
        self._actualizar_prioridad()

    def _actualizar_prioridad(self):
        prioridad = datos.prioridad_de_tipo(self.combo_tipo.currentText())
        horas = datos.horas_de_tipo(self.combo_tipo.currentText())
        if prioridad:
            self.lbl_prioridad.setText(f"Tiempo estimado de solución: {horas} h → prioridad {prioridad} "
                                       "(a menor tiempo, mayor prioridad).")
        else:
            self.lbl_prioridad.setText("")

    # ------------------------------------------------------------ adjuntos
    def _actualizar_adjuntos(self):
        self.lista_adjuntos.clear()
        for nombre, contenido in self._adjuntos:
            self.lista_adjuntos.addItem(f"{nombre}  ({archivos.formato_tamano(len(contenido))})")
        self.lbl_ayuda_adjuntos.setText(
            f"{len(self._adjuntos)} de {archivos.MAX_ADJUNTOS_POR_SOLICITUD} archivos · máximo "
            f"{archivos.formato_tamano(archivos.MAX_TAMANO_ADJUNTO)} cada uno · "
            f"{', '.join(archivos.EXTENSIONES_PERMITIDAS)}")
        self.btn_adjuntar.setEnabled(len(self._adjuntos) < archivos.MAX_ADJUNTOS_POR_SOLICITUD)

    def _elegir_archivos(self):
        rutas, _filtro = QFileDialog.getOpenFileNames(self, "Elegir archivos adjuntos", "", texto_filtro_archivos())
        self._agregar_rutas(rutas)

    def _agregar_rutas(self, rutas):
        """Lee y valida cada archivo elegido; los que no sirven se explican en un solo aviso."""
        problemas = []
        for ruta in rutas:
            nombre = os.path.basename(ruta)
            if len(self._adjuntos) >= archivos.MAX_ADJUNTOS_POR_SOLICITUD:
                problemas.append(f"«{nombre}»: máximo {archivos.MAX_ADJUNTOS_POR_SOLICITUD} archivos por solicitud.")
                continue
            try:
                if os.path.getsize(ruta) > archivos.MAX_TAMANO_ADJUNTO:      # no se carga a memoria si ya es muy grande
                    raise ValueError(f"«{nombre}» pesa más de {archivos.formato_tamano(archivos.MAX_TAMANO_ADJUNTO)}.")
                with open(ruta, "rb") as f:
                    contenido = f.read()
                archivos.validar_adjunto(nombre, contenido)
            except OSError:
                problemas.append(f"«{nombre}»: no se pudo leer el archivo.")
                continue
            except ValueError as error:
                problemas.append(str(error))
                continue
            if any(n == nombre and c == contenido for n, c in self._adjuntos):
                continue                                                      # el mismo archivo dos veces
            self._adjuntos.append((nombre, contenido))
        self._actualizar_adjuntos()
        if problemas:
            QMessageBox.warning(self, "Algunos archivos no se agregaron", "\n".join(problemas))

    def _quitar_adjunto(self):
        fila = self.lista_adjuntos.currentRow()
        if 0 <= fila < len(self._adjuntos):
            del self._adjuntos[fila]
            self._actualizar_adjuntos()

    def _enviar(self):
        try:
            s = datos.crear_solicitud(self.combo_tipo.currentText(), self.txt_descripcion.toPlainText(),
                                      self.usuario, adjuntos=self._adjuntos)
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "Falta información", str(error))
            return
        QMessageBox.information(self, "Solicitud registrada",
                                 f"Tu solicitud fue registrada con el folio {s['folio']}.\n"
                                 f"Prioridad: {s['prioridad']} · Fecha límite de atención: {s['vence']}.\n"
                                 "El administrador la asignará a un técnico.\n"
                                 "Podrás dar seguimiento a su estatus en 'Mis solicitudes'.")
        self.txt_descripcion.clear()
        self._adjuntos = []
        self._actualizar_adjuntos()
        self.solicitud_creada.emit(s["folio"])
