"""
Paleta y estilos (QSS) del prototipo SIGSAT.
Paleta institucional azul, consistente con materiales académicos de UPIICSA-IPN.
"""

from PySide6.QtCore import Qt

AZUL_OSCURO = "#122C55"      # sidebar / headers
AZUL_MEDIO = "#1F4E8C"       # botones primarios
AZUL_CLARO = "#EAF1FB"       # fondos suaves
AZUL_ACENTO = "#2E86C1"      # hover / links
GRIS_TEXTO = "#33414F"
BLANCO = "#FFFFFF"

# Tonos de las etiquetas (badges): (fondo, texto, punto). Fondo claro con texto
# oscuro para que se lean bien (contraste >= 4.5:1); el color vivo va solo en el
# puntito. Son los mismos tonos de la versión web.
TONOS = {
    "neutro":  ("#EDF0F4", "#3F4C5A", "#5B6B7C"),
    "ambar":   ("#FCF0D4", "#7A4E00", "#D98E04"),
    "naranja": ("#FBE6D3", "#8A3A05", "#B45309"),
    "verde":   ("#DDF1E5", "#14603A", "#1E7A46"),
    "rojo":    ("#FBE1DE", "#9B2A1F", "#C0392B"),
    "azul":    ("#E1ECFA", "#12407A", "#2E6FBF"),     # «Resuelta»: terminó el agente, falta la validación del cliente
}

TONO_ESTADO = {"Sin visualizar": "neutro", "Visualizado": "azul", "En proceso": "ambar", "Finalizado": "verde"}
TONO_PRIORIDAD = {"Baja": "neutro", "Media": "ambar", "Alta": "rojo"}
TONO_CONVERSACION = {"Abierta": "neutro", "En atención": "ambar", "Cerrada": "verde"}

QSS_APP = f"""
QWidget {{
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    color: {GRIS_TEXTO};
}}
QMainWindow, QDialog {{
    background-color: {BLANCO};
}}
#sidebar {{
    background-color: {AZUL_OSCURO};
}}
#sidebar QPushButton {{
    color: {BLANCO};
    background-color: transparent;
    text-align: left;
    padding: 12px 18px;
    border: none;
    font-size: 14px;
}}
#sidebar QPushButton:hover {{
    background-color: {AZUL_MEDIO};
}}
#sidebar QPushButton:checked {{
    background-color: {AZUL_ACENTO};
    font-weight: 600;
}}
#sidebarTitulo {{
    color: {BLANCO};
    font-size: 17px;
    font-weight: 700;
    padding: 20px 18px 4px 18px;
}}
#sidebarSubtitulo {{
    color: #B7C6DD;
    font-size: 12px;
    padding: 0 18px 16px 18px;
}}
QPushButton#botonPrimario {{
    background-color: {AZUL_MEDIO};
    color: {BLANCO};
    border: none;
    border-radius: 6px;
    padding: 9px 18px;
    font-weight: 600;
}}
QPushButton#botonPrimario:hover {{
    background-color: {AZUL_ACENTO};
}}
QPushButton#botonSecundario {{
    background-color: {BLANCO};
    color: {AZUL_MEDIO};
    border: 1px solid {AZUL_MEDIO};
    border-radius: 6px;
    padding: 9px 18px;
}}
QPushButton#botonSecundario:hover {{
    background-color: {AZUL_CLARO};
}}
QPushButton#botonEnlace {{
    background: transparent; border: none; color: {AZUL_MEDIO}; text-decoration: underline;
    padding: 4px 0px; text-align: left;
}}
QPushButton#botonEnlace:hover {{ color: {AZUL_ACENTO}; }}
QPushButton#botonEnlace:focus {{ outline: 1px dotted {AZUL_ACENTO}; }}
QLabel#tituloVista {{
    font-size: 20px;
    font-weight: 700;
    color: {AZUL_OSCURO};
}}
QLabel#subtituloVista {{
    font-size: 13px;
    color: #64748B;
}}
QTableWidget {{
    background-color: {BLANCO};
    gridline-color: #E2E8F0;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
}}
QHeaderView::section {{
    background-color: {AZUL_CLARO};
    color: {AZUL_OSCURO};
    padding: 6px;
    border: none;
    font-weight: 600;
}}
QLineEdit, QComboBox, QTextEdit, QSpinBox {{
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 6px 8px;
    background-color: {BLANCO};
}}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
    border: 1px solid {AZUL_ACENTO};
}}
QComboBox QAbstractItemView {{
    background-color: {BLANCO};
    color: {GRIS_TEXTO};
    border: 1px solid #CBD5E1;
    outline: none;
    selection-background-color: {AZUL_CLARO};
    selection-color: {AZUL_OSCURO};
}}
QMenu {{
    background-color: {BLANCO};
    color: {GRIS_TEXTO};
    border: 1px solid #CBD5E1;
}}
QMenu::item:selected {{
    background-color: {AZUL_CLARO};
    color: {AZUL_OSCURO};
}}
QToolTip {{
    background-color: {BLANCO};
    color: {GRIS_TEXTO};
    border: 1px solid #CBD5E1;
    padding: 4px 6px;
}}
QMessageBox {{
    background-color: {BLANCO};
}}
QMessageBox QLabel {{
    color: {GRIS_TEXTO};
    background-color: transparent;
}}
#tarjetaKpi {{
    background-color: {AZUL_CLARO};
    border-radius: 10px;
}}
#errorLogin {{
    color: #B91C1C;
    background-color: #FEE2E2;
    border-radius: 6px;
    padding: 8px 10px;
    margin-top: 6px;
}}
#avisoLogin {{
    color: #1F4E8C;
    background-color: {AZUL_CLARO};
    border-radius: 6px;
    padding: 8px 10px;
    margin-top: 6px;
}}
QLabel#burbujaPropia {{
    background-color: {AZUL_MEDIO};
    color: {BLANCO};
    border-radius: 10px;
    padding: 8px 12px;
}}
QLabel#burbujaAjena {{
    background-color: #E8EEF6;
    color: {GRIS_TEXTO};
    border-radius: 10px;
    padding: 8px 12px;
}}
QLabel#mensajeSistema {{
    color: #64748B;
    font-size: 11px;
    font-style: italic;
}}
QLabel#metaMensaje {{
    color: #94A3B8;
    font-size: 11px;
}}
QScrollArea#scrollChat {{
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    background-color: #F8FAFC;
}}
QWidget#contenedorChat {{
    background-color: #F8FAFC;
}}
QListWidget#listaConversaciones {{
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    background-color: {BLANCO};
}}
QListWidget#listaConversaciones::item {{
    padding: 10px 8px;
    border-bottom: 1px solid #F1F5F9;
}}
QListWidget#listaConversaciones::item:selected {{
    background-color: {AZUL_CLARO};
    color: {AZUL_OSCURO};
}}
#panelLoginIzq {{
    background-color: {AZUL_OSCURO};
}}
#panelLoginDer {{
    background-color: {BLANCO};
}}
#tarjetaFormulario {{
    background-color: {BLANCO};
    border: 1px solid #E2E8F0;
    border-radius: 10px;
}}
#panelDesglose {{
    background-color: {BLANCO};
    border: 1px solid #E2E8F0;
    border-radius: 10px;
}}
#scrollBitacora {{
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    background-color: {BLANCO};
}}
#kpiValor {{
    font-size: 30px;
    font-weight: 800;
    color: {AZUL_OSCURO};
}}
#kpiEtiqueta {{
    font-size: 12px;
    color: #52627A;
}}
"""


def _tono(tono: str):
    return TONOS.get(tono, TONOS["neutro"])


def color_estado(estado: str) -> str:
    """Color vivo del estatus (para puntos y barras)."""
    return _tono(TONO_ESTADO.get(estado, "neutro"))[2]


def color_prioridad(prioridad: str) -> str:
    return _tono(TONO_PRIORIDAD.get(prioridad, "neutro"))[2]


def color_texto(tono: str) -> str:
    """Color de texto oscuro de un tono; legible sobre fondo blanco (para tablas)."""
    return _tono(tono)[1]


def aplicar_badge(etiqueta, texto: str, tono: str) -> None:
    """Da formato de 'pastilla' con punto de color a una QLabel existente."""
    from html import escape

    fondo, texto_color, punto = _tono(tono)
    etiqueta.setTextFormat(Qt.RichText)
    etiqueta.setText(f"<span style='color:{punto};'>●</span>&nbsp;{escape(texto)}")
    etiqueta.setStyleSheet(
        f"background-color:{fondo}; color:{texto_color}; border-radius:9px; "
        "padding:3px 10px; font-weight:600; font-size:11px;")


def crear_badge(texto: str, tono: str):
    """QLabel nueva con formato de 'pastilla' (igual a la versión web)."""
    from PySide6.QtWidgets import QLabel

    badge = QLabel()
    aplicar_badge(badge, texto, tono)
    return badge


def paleta_clara():
    """Paleta explícita en tonos claros. Necesaria además del QSS: en Windows
    con modo oscuro activado, Qt aplica automáticamente una paleta oscura a
    elementos como los menús desplegables de los combos, tooltips o cuadros
    de diálogo que el QSS no cubre explícitamente por tipo/objectName, lo que
    dejaba texto oscuro sobre fondo negro (ilegible). Fijar la paleta evita
    que el prototipo cambie de apariencia según la configuración del sistema."""
    from PySide6.QtGui import QPalette, QColor

    p = QPalette()
    texto = QColor(GRIS_TEXTO)
    deshabilitado = QColor("#94A3B8")

    p.setColor(QPalette.Window, QColor(BLANCO))
    p.setColor(QPalette.WindowText, texto)
    p.setColor(QPalette.Base, QColor(BLANCO))
    p.setColor(QPalette.AlternateBase, QColor("#F8FAFC"))
    p.setColor(QPalette.ToolTipBase, QColor(BLANCO))
    p.setColor(QPalette.ToolTipText, texto)
    p.setColor(QPalette.Text, texto)
    p.setColor(QPalette.Button, QColor(BLANCO))
    p.setColor(QPalette.ButtonText, texto)
    p.setColor(QPalette.BrightText, QColor("#C0392B"))
    p.setColor(QPalette.Highlight, QColor(AZUL_ACENTO))
    p.setColor(QPalette.HighlightedText, QColor(BLANCO))
    p.setColor(QPalette.Link, QColor(AZUL_ACENTO))
    p.setColor(QPalette.PlaceholderText, QColor("#94A3B8"))
    p.setColor(QPalette.Disabled, QPalette.Text, deshabilitado)
    p.setColor(QPalette.Disabled, QPalette.WindowText, deshabilitado)
    p.setColor(QPalette.Disabled, QPalette.ButtonText, deshabilitado)
    return p
