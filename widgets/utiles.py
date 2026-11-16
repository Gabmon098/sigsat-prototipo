"""Utilidades pequeñas de interfaz compartidas por las vistas."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

# Espacio que se deja libre alrededor de una ventana, y reserva para su barra de
# título y bordes (el tamaño que se pide es el del contenido, sin el marco).
MARGEN_PANTALLA = 16
ALTO_MARCO_VENTANA = 40


def area_disponible(ventana) -> QRect:
    """Área útil de la pantalla donde aparecerá la ventana: la de su ventana padre
    (o la principal), sin contar la barra de tareas."""
    pantalla = None
    padre = ventana.parentWidget()
    if padre is not None:
        pantalla = padre.screen()
    if pantalla is None:
        pantalla = QGuiApplication.primaryScreen()
    return pantalla.availableGeometry()


def ajustar_a_pantalla(ventana, ancho: int, alto: int, centrar: bool = False, limitar: bool = True) -> None:
    """Da a la ventana el tamaño pedido, pero nunca mayor que la pantalla: se adapta
    a monitores pequeños y a la escala de Windows (125 %, 150 %…).

    - `limitar`: además impide que la ventana crezca más que la pantalla.
    - `centrar`: la coloca en el centro del área útil (para ventanas sin padre; los
      diálogos ya se centran solos sobre su ventana principal).
    """
    area = area_disponible(ventana)
    max_ancho = max(320, area.width() - 2 * MARGEN_PANTALLA)
    max_alto = max(240, area.height() - 2 * MARGEN_PANTALLA - ALTO_MARCO_VENTANA)
    ancho, alto = min(ancho, max_ancho), min(alto, max_alto)
    ventana.resize(ancho, alto)
    if limitar:
        ventana.setMaximumSize(max_ancho, max_alto)
    if centrar:
        ventana.move(area.x() + (area.width() - ancho) // 2,
                     area.y() + max(0, (area.height() - alto - ALTO_MARCO_VENTANA) // 2))


def crear_area_desplazable(cuerpo: QWidget) -> QScrollArea:
    """Envuelve `cuerpo` en un área con barra de desplazamiento sin marco. Así, si la
    pantalla es tan pequeña que el contenido no cabe, se desplaza en vez de salirse."""
    scroll = QScrollArea()
    scroll.setObjectName("scrollDialogo")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setStyleSheet("QScrollArea#scrollDialogo, QScrollArea#scrollDialogo > QWidget > QWidget { background: transparent; }")
    scroll.setWidget(cuerpo)
    return scroll


def poner_con_scroll(dialogo, cuerpo: QWidget) -> QScrollArea:
    """Instala `cuerpo` como único contenido (desplazable) de un diálogo."""
    raiz = QVBoxLayout(dialogo)
    raiz.setContentsMargins(0, 0, 0, 0)
    scroll = crear_area_desplazable(cuerpo)
    raiz.addWidget(scroll)
    return scroll


def item_vence(s: dict) -> QTableWidgetItem:
    """Celda «fecha límite» de una solicitud: en rojo y con aviso si ya se venció (el color nunca es
    lo único que informa: también dice «vencida» o «fuera de plazo»)."""
    if s["cumplio_sla"] is False:
        item = QTableWidgetItem(f"{s['vence']}  (fuera de plazo)")
    elif s["vencida"]:
        item = QTableWidgetItem(f"{s['vence']}  (vencida)")
    else:
        return QTableWidgetItem(s["vence"])
    item.setForeground(QColor("#B91C1C"))
    return item


def texto_filtro_archivos() -> str:
    """Filtro del cuadro «Abrir archivo» con las extensiones de adjuntos permitidas."""
    import archivos
    patrones = " ".join(f"*{e}" for e in archivos.EXTENSIONES_PERMITIDAS)
    return f"Archivos permitidos ({patrones});;Todos los archivos (*)"


def crear_contador() -> QLabel:
    """Etiqueta pequeña 'n / máximo' para colocar debajo de un cuadro de texto."""
    lbl = QLabel("")
    lbl.setAlignment(Qt.AlignRight)
    lbl.setStyleSheet("color:#94A3B8; font-size:11px; padding-top:3px;")
    return lbl


def limitar_texto(editor: QTextEdit, maximo: int, contador: QLabel = None) -> None:
    """Impide que el texto de un QTextEdit pase de `maximo` caracteres (QTextEdit
    no trae esa opción, a diferencia de QLineEdit.setMaxLength) y, si se da un
    contador, lo mantiene actualizado."""

    def revisar():
        texto = editor.toPlainText()
        if len(texto) > maximo:
            texto = texto[:maximo]
            editor.blockSignals(True)
            editor.setPlainText(texto)
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            editor.setTextCursor(cursor)
            editor.blockSignals(False)
        if contador is not None:
            contador.setText(f"{len(texto)} / {maximo}")

    editor.textChanged.connect(revisar)
    revisar()
