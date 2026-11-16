from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget
)
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

import datos
from estilos import color_estado
from vistas.reportes_vista import VistaAnaliticaReportes


def _descartar(item) -> None:
    """Quita un widget de su layout YA (no «más tarde»): se oculta y se desvincula antes de borrarlo, para que
    nunca quede dibujado encima del contenido nuevo mientras Qt procesa el borrado diferido."""
    w = item.widget()
    if w is not None:
        w.hide()
        w.setParent(None)
        w.deleteLater()


INTERVALO_ACTUALIZACION_MS = 30_000        # RF-22 / RNF-04: el panel se actualiza solo, como máximo cada 30 s


class PanelIndicadores(QWidget):
    """Indicadores (KPIs) del Administrador: avance de los reportes por estatus, número de solicitudes, tiempo
    promedio de resolución, resueltas fuera de tiempo, % de efectividad en tiempo, satisfacción promedio de
    las áreas, solicitudes por área, tiempo promedio de atención por área (RF-23) y carga de cada técnico.

    Se **actualiza automáticamente cada 30 segundos** (mientras se está viendo) y cada vez que se abre la
    pantalla; no hace falta ningún botón."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self._construir_ui()
        self.actualizar()
        self._temporizador = QTimer(self)
        self._temporizador.setInterval(INTERVALO_ACTUALIZACION_MS)
        self._temporizador.timeout.connect(self._al_pasar_el_tiempo)
        self._temporizador.start()

    def _al_pasar_el_tiempo(self):
        """Solo se recalcula si el panel se está viendo (no se gasta trabajo con la pantalla oculta)."""
        if self.isVisible():
            self.actualizar()

    def _construir_ui(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        contenido = QWidget()
        scroll.setWidget(contenido)
        raiz.addWidget(scroll)

        self.layout_raiz = QVBoxLayout(contenido)
        self.layout_raiz.setContentsMargins(30, 26, 30, 26)
        self.layout_raiz.setSpacing(14)

        cab = QHBoxLayout()
        col_titulos = QVBoxLayout()
        titulo = QLabel("Panel de indicadores")
        titulo.setObjectName("tituloVista")
        subtitulo = QLabel("Avance de reportes e incidentes, tiempos de atención y satisfacción de las áreas.")
        subtitulo.setObjectName("subtituloVista")
        col_titulos.addWidget(titulo)
        col_titulos.addWidget(subtitulo)
        cab.addLayout(col_titulos)
        cab.addStretch()
        self.lbl_actualizado = QLabel("")
        self.lbl_actualizado.setObjectName("subtituloVista")
        self.lbl_actualizado.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cab.addWidget(self.lbl_actualizado)
        self.layout_raiz.addLayout(cab)

        self.grid_kpis = QGridLayout()
        self.grid_kpis.setSpacing(14)
        self.layout_raiz.addLayout(self.grid_kpis)

        fila_1 = QHBoxLayout()
        self.panel_estado = self._panel_desglose("Solicitudes por estatus")
        self.panel_area = self._panel_desglose("Solicitudes por área")
        fila_1.addWidget(self.panel_estado)
        fila_1.addWidget(self.panel_area)
        self.layout_raiz.addLayout(fila_1)

        fila_2 = QHBoxLayout()
        self.panel_tiempo_area = self._panel_desglose("Tiempo promedio de atención por área")
        self.panel_satisfaccion_area = self._panel_desglose("Satisfacción promedio por área")
        fila_2.addWidget(self.panel_tiempo_area)
        fila_2.addWidget(self.panel_satisfaccion_area)
        self.layout_raiz.addLayout(fila_2)

        fila_3 = QHBoxLayout()
        self.panel_tiempo_tipo = self._panel_desglose("Tiempo promedio de atención por tipo")
        self.panel_sucursal = self._panel_desglose("Solicitudes por sucursal")
        fila_3.addWidget(self.panel_tiempo_tipo)
        fila_3.addWidget(self.panel_sucursal)
        self.layout_raiz.addLayout(fila_3)

        self.panel_carga = QFrame()
        self.panel_carga.setObjectName("panelDesglose")
        lay_carga = QVBoxLayout(self.panel_carga)
        lay_carga.setContentsMargins(18, 16, 18, 16)
        t = QLabel("Carga de trabajo por técnico")
        t.setStyleSheet("font-weight:700; margin-bottom:6px;")
        lay_carga.addWidget(t)
        self.tabla_carga = QTableWidget(0, 7)
        self.tabla_carga.setHorizontalHeaderLabels(
            ["Técnico", "Abiertas", "Sin visualizar", "Visualizadas", "En proceso", "Vencidas", "Finalizadas"])
        self.tabla_carga.verticalHeader().setVisible(False)
        self.tabla_carga.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_carga.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabla_carga.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla_carga.horizontalHeader().setStretchLastSection(True)
        self.tabla_carga.setMinimumHeight(190)
        lay_carga.addWidget(self.tabla_carga)
        self.layout_raiz.addWidget(self.panel_carga)
        self.layout_raiz.addStretch()

    def _tarjeta_kpi(self, valor, etiqueta):
        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaKpi")
        tarjeta.setMinimumHeight(90)
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(18, 14, 18, 14)
        lbl_valor = QLabel(str(valor))
        lbl_valor.setObjectName("kpiValor")
        lbl_etiqueta = QLabel(etiqueta)
        lbl_etiqueta.setObjectName("kpiEtiqueta")
        lbl_etiqueta.setWordWrap(True)
        lay.addWidget(lbl_valor)
        lay.addWidget(lbl_etiqueta)
        return tarjeta

    def _panel_desglose(self, titulo_texto):
        panel = QFrame()
        panel.setObjectName("panelDesglose")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 16, 18, 16)
        titulo = QLabel(titulo_texto)
        titulo.setStyleSheet("font-weight:700; margin-bottom:6px;")
        lay.addWidget(titulo)
        panel._layout_filas = lay
        return panel

    def _llenar_filas(self, panel, filas, vacio="Aún no hay datos."):
        """filas: [(etiqueta, texto_derecha, color_del_punto)]."""
        lay = panel._layout_filas
        while lay.count() > 1:                      # limpiar filas previas (el título está en el índice 0)
            _descartar(lay.takeAt(1))
        if not filas:
            lbl = QLabel(vacio)
            lbl.setStyleSheet("color:#64748B;")
            lay.addWidget(lbl)
            return
        for etiqueta_texto, derecha, color in filas:
            fila = QHBoxLayout()
            punto = QLabel("●")
            punto.setStyleSheet(f"color:{color}; font-size:14px;")
            etiqueta = QLabel(etiqueta_texto)
            etiqueta.setStyleSheet("color:#33414F;")
            etiqueta.setWordWrap(True)
            cantidad = QLabel(derecha)
            cantidad.setStyleSheet("color:#64748B;")
            fila.addWidget(punto)
            fila.addWidget(etiqueta, 1)
            fila.addWidget(cantidad)
            lay.addWidget(QWidgetFila(fila))

    def _llenar_desglose(self, panel, datos_dict, usar_color_estado=False):
        total = sum(datos_dict.values()) or 1
        self._llenar_filas(panel, [
            (clave, f"{valor}  ({round(100 * valor / total)}%)", color_estado(clave) if usar_color_estado else "#2E86C1")
            for clave, valor in datos_dict.items()])

    def actualizar(self):
        kpis = datos.calcular_kpis()
        self.lbl_actualizado.setText(f"Se actualiza solo cada {INTERVALO_ACTUALIZACION_MS // 1000} s · "
                                     f"última actualización {datetime.now():%H:%M:%S}")

        while self.grid_kpis.count():
            _descartar(self.grid_kpis.takeAt(0))

        efectividad = "—" if kpis["efectividad_pct"] is None else f"{kpis['efectividad_pct']} %"
        tarjetas = [
            (kpis["total"], "Solicitudes totales"),
            (f"{kpis['tiempo_promedio_h']} h", "Tiempo promedio de resolución"),
            (kpis["fuera_de_tiempo"], "Resueltas fuera de tiempo"),
            (efectividad, "Efectividad en tiempo"),
            (f"{kpis['satisfaccion_prom']} / 5", "Satisfacción promedio de las áreas"),
            (kpis["sin_asignar"], "Por asignar a un técnico"),
            (kpis["vencidas"], "Abiertas fuera de su fecha límite"),
        ]
        for i, (valor, etiqueta) in enumerate(tarjetas):
            self.grid_kpis.addWidget(self._tarjeta_kpi(valor, etiqueta), i // 4, i % 4)

        self._llenar_desglose(self.panel_estado, kpis["por_estado"], usar_color_estado=True)
        self._llenar_desglose(self.panel_area, kpis["por_area"])
        self._llenar_desglose(self.panel_sucursal, kpis["por_sucursal"])

        def tiempos(d):
            return [(k, f"{v['promedio_h']} h  ·  {v['finalizadas']} finalizada{'s' if v['finalizadas'] != 1 else ''}", "#2E86C1")
                    for k, v in d.items()]
        self._llenar_filas(self.panel_tiempo_area, tiempos(kpis["tiempo_por_area"]), "Aún no hay solicitudes finalizadas.")
        self._llenar_filas(self.panel_tiempo_tipo, tiempos(kpis["tiempo_por_tipo"]), "Aún no hay solicitudes finalizadas.")
        self._llenar_filas(self.panel_satisfaccion_area,
                           [(k, f"{v['promedio']} / 5  ·  {v['calificadas']} calificada{'s' if v['calificadas'] != 1 else ''}", "#2E86C1")
                            for k, v in kpis["satisfaccion_por_area"].items()], "Aún no hay calificaciones.")

        carga = datos.carga_trabajo()
        self.tabla_carga.setRowCount(len(carga))
        for fila, c in enumerate(carga):
            valores = [c["agente"], c["abiertas"], c["sin_visualizar"], c["visualizadas"], c["en_proceso"],
                       c["vencidas"], c["finalizadas"]]
            for col, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor))
                if col >= 1:
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 5 and c["vencidas"]:
                    item.setForeground(QColor("#B91C1C"))
                self.tabla_carga.setItem(fila, col, item)


class VistaDashboardAdmin(QWidget):
    """Panel de indicadores con dos pestañas: los indicadores (se actualizan solos cada 30 s) y el
    análisis con filtros y exportación a Excel/PDF (RF-24/25)."""

    def __init__(self, usuario: dict):
        super().__init__()
        self.usuario = usuario
        self.indicadores = PanelIndicadores(usuario)
        self.analisis = VistaAnaliticaReportes(usuario)
        self.pestanas = QTabWidget()
        self.pestanas.addTab(self.indicadores, "Indicadores")
        self.pestanas.addTab(self.analisis, "Análisis y exportación")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.pestanas)

    def actualizar(self):
        self.indicadores.actualizar()
        self.analisis.actualizar()


from PySide6.QtWidgets import QWidget as _QWidget


class QWidgetFila(_QWidget):
    """Pequeño contenedor para poder insertar un QHBoxLayout ya armado dentro de otro layout."""

    def __init__(self, layout_interno):
        super().__init__()
        self.setLayout(layout_interno)
