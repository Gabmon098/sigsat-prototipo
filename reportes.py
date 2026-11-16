"""
Reportes filtrables (RF-24) y su exportación a Excel y PDF (RF-25).

`generar()` aplica los filtros (fechas, área, tipo, estatus, prioridad, agente, solo vencidas) y
devuelve un diccionario con las filas y un resumen (totales, tiempos promedio por área / tipo /
agente, cumplimiento del plazo, satisfacción). Ese mismo diccionario alimenta la pantalla y las
dos exportaciones, así los tres siempre muestran lo mismo.

Excel (openpyxl) y PDF (reportlab) son dependencias opcionales: si faltan, la pantalla funciona y
solo se avisa de que hay que instalarlas (`pip install -r requirements.txt`).
"""

from datetime import datetime
from xml.sax.saxutils import escape

import datos

_FMT = "%Y-%m-%d %H:%M"

COLUMNAS = [  # (encabezado, clave de la fila)
    ("Folio", "folio"), ("Tipo", "tipo"), ("Área", "area"), ("Prioridad", "prioridad"), ("Estatus", "estado"),
    ("Solicitante", "solicitante"), ("Técnico", "agente"), ("Creada", "creada"), ("Vence", "vence"),
    ("Finalizada", "finalizacion"), ("Horas de atención", "horas"), ("Plazo", "plazo"),
    ("Calificación", "calificacion"),
    ("Descripción", "descripcion"),
]


class DependenciaFaltante(Exception):
    """Falta una biblioteca para exportar (mensaje listo para mostrar)."""


def _horas(s: dict):
    """Horas que tardó el equipo en finalizarla (de que se registró a que se marcó «Finalizado»)."""
    if not s["fecha_finalizacion"]:
        return None
    return round((datetime.strptime(s["fecha_finalizacion"], _FMT) - datetime.strptime(s["fecha_creacion"], _FMT)).total_seconds() / 3600, 1)


def _plazo(s: dict) -> str:
    if s["cumplio_sla"] is not None:
        return "Cumplido" if s["cumplio_sla"] else "Fuera de plazo"
    return "Vencida" if s["vencida"] else "Vigente"


def _promedio(valores):
    return round(sum(valores) / len(valores), 1) if valores else None


def _grupo(filas: list, clave: str) -> dict:
    """Totales por valor de `clave`: {valor: {'total', 'finalizadas', 'vencidas', 'promedio_h'}}, ordenado por total."""
    res = {}
    for f in filas:
        g = res.setdefault(f[clave] or "Sin asignar", {"total": 0, "finalizadas": 0, "vencidas": 0, "_h": []})
        g["total"] += 1
        if f["horas"] is not None:
            g["finalizadas"] += 1
            g["_h"].append(f["horas"])
        if f["plazo"] == "Vencida":
            g["vencidas"] += 1
    for g in res.values():
        g["promedio_h"] = _promedio(g.pop("_h"))
    return dict(sorted(res.items(), key=lambda kv: (-kv[1]["total"], kv[0])))


def etiquetas_filtros(filtros: dict) -> list:
    """Los filtros aplicados en texto ('Área: Soporte Técnico'); lista vacía si no hay ninguno."""
    nombres = {"area": "Área", "tipo": "Tipo", "estado": "Estatus", "prioridad": "Prioridad"}
    res = []
    if filtros.get("desde"):
        res.append(f"Desde: {filtros['desde']:%Y-%m-%d}")
    if filtros.get("hasta"):
        res.append(f"Hasta: {filtros['hasta']:%Y-%m-%d}")
    for clave, nombre in nombres.items():
        if filtros.get(clave):
            res.append(f"{nombre}: {filtros[clave]}")
    if filtros.get("agente_id") is not None:
        agente = datos.buscar_usuario(filtros["agente_id"])
        res.append(f"Técnico: {agente['nombre'] if agente else filtros['agente_id']}")
    if filtros.get("solo_vencidas"):
        res.append("Solo solicitudes vencidas")
    return res


def generar(actor: dict, **filtros) -> dict:
    """Genera el reporte. Lanza PermissionError si el rol no puede y ValueError si un filtro no es válido."""
    solicitudes = datos.solicitudes_reporte(actor, **filtros)
    filas = []
    for s in solicitudes:
        filas.append({"folio": s["folio"], "tipo": s["tipo"], "area": s["area"], "prioridad": s["prioridad"],
                      "estado": s["estado"], "solicitante": s["solicitante"], "agente": s["agente_asignado"] or "",
                      "creada": s["fecha_creacion"], "vence": s["vence"], "finalizacion": s["fecha_finalizacion"] or "",
                      "horas": _horas(s), "plazo": _plazo(s), "calificacion": s["calificacion"],
                      "descripcion": s["descripcion"]})
    finalizadas = [f for f in filas if f["horas"] is not None]
    en_plazo = sum(1 for f in finalizadas if f["plazo"] == "Cumplido")
    calificaciones = [f["calificacion"] for f in filas if f["calificacion"]]
    resumen = {
        "total": len(filas),
        "finalizadas": len(finalizadas),
        "vencidas": sum(1 for f in filas if f["plazo"] == "Vencida"),
        "tiempo_promedio_h": _promedio([f["horas"] for f in finalizadas]),
        "efectividad_pct": round(100 * en_plazo / len(finalizadas)) if finalizadas else None,
        "satisfaccion": _promedio(calificaciones),
        "por_estado": {e: sum(1 for f in filas if f["estado"] == e) for e in datos.ESTADOS},
        "por_prioridad": {p: sum(1 for f in filas if f["prioridad"] == p) for p in reversed(datos.PRIORIDADES)},
        "por_area": _grupo(filas, "area"),
        "por_tipo": _grupo(filas, "tipo"),
        "por_agente": _grupo(filas, "agente"),
    }
    return {"generado_en": datetime.now().replace(microsecond=0), "generado_por": actor["nombre"],
            "filtros": dict(filtros), "etiquetas_filtros": etiquetas_filtros(filtros), "filas": filas, "resumen": resumen}


def _fmt_num(valor, sufijo=""):
    return "—" if valor is None else f"{valor}{sufijo}"


def _tarjetas(resumen: dict) -> list:
    return [("Solicitudes", resumen["total"]), ("Finalizadas", resumen["finalizadas"]), ("Vencidas", resumen["vencidas"]),
            ("Tiempo promedio de atención", _fmt_num(resumen["tiempo_promedio_h"], " h")),
            ("Efectividad en tiempo", _fmt_num(resumen["efectividad_pct"], " %")),
            ("Satisfacción promedio", _fmt_num(resumen["satisfaccion"] or None, " / 5"))]


# --------------------------------------------------------------------------
# Excel (RF-25)
# --------------------------------------------------------------------------

def exportar_excel(reporte: dict, ruta) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as error:
        raise DependenciaFaltante("Para exportar a Excel instala openpyxl:  pip install openpyxl") from error

    azul = PatternFill("solid", fgColor="122C55")
    claro = PatternFill("solid", fgColor="EAF1FB")
    blanco = Font(bold=True, color="FFFFFF")

    def poner(ws, fila, col, valor, **estilo):
        c = ws.cell(row=fila, column=col, value=valor)
        if isinstance(valor, str):
            c.data_type = "s"          # el texto del usuario NUNCA se interpreta como fórmula (p. ej. "=1+1")
        for k, v in estilo.items():
            setattr(c, k, v)
        return c

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    resumen = reporte["resumen"]
    poner(ws, 1, 1, "SIGSAT — Reporte de solicitudes", font=Font(bold=True, size=16, color="122C55"))
    poner(ws, 2, 1, f"Generado el {reporte['generado_en']:%Y-%m-%d %H:%M} por {reporte['generado_por']}")
    poner(ws, 3, 1, "Filtros: " + ("; ".join(reporte["etiquetas_filtros"]) or "ninguno (todas las solicitudes)"))
    fila = 5
    for etiqueta, valor in _tarjetas(resumen):
        poner(ws, fila, 1, etiqueta, font=Font(bold=True), fill=claro)
        poner(ws, fila, 2, valor, alignment=Alignment(horizontal="right"))
        fila += 1

    def tabla(titulo, encabezados, filas):
        nonlocal fila
        fila += 1
        poner(ws, fila, 1, titulo, font=Font(bold=True, size=12, color="122C55"))
        fila += 1
        for j, h in enumerate(encabezados, start=1):
            poner(ws, fila, j, h, font=blanco, fill=azul)
        for datos_fila in filas:
            fila += 1
            for j, v in enumerate(datos_fila, start=1):
                poner(ws, fila, j, v)
        fila += 1

    tabla("Por estatus", ["Estatus", "Solicitudes"], list(resumen["por_estado"].items()))
    tabla("Por prioridad", ["Prioridad", "Solicitudes"], list(resumen["por_prioridad"].items()))
    for titulo, clave, primera in (("Por área", "por_area", "Área"), ("Por tipo de solicitud", "por_tipo", "Tipo"),
                                   ("Por técnico", "por_agente", "Técnico")):
        tabla(titulo, [primera, "Solicitudes", "Finalizadas", "Vencidas", "Tiempo promedio (h)"],
              [(k, v["total"], v["finalizadas"], v["vencidas"], v["promedio_h"]) for k, v in resumen[clave].items()])
    ws.column_dimensions["A"].width = 34
    for col in "BCDE":
        ws.column_dimensions[col].width = 18

    det = wb.create_sheet("Solicitudes")
    for j, (encabezado, _clave) in enumerate(COLUMNAS, start=1):
        poner(det, 1, j, encabezado, font=blanco, fill=azul, alignment=Alignment(vertical="center", wrap_text=True))
    for i, f in enumerate(reporte["filas"], start=2):
        for j, (_encabezado, clave) in enumerate(COLUMNAS, start=1):
            valor = f[clave]
            poner(det, i, j, valor, alignment=Alignment(vertical="top", wrap_text=(clave == "descripcion")))
    anchos = [13, 26, 24, 11, 12, 28, 22, 17, 17, 17, 17, 11, 15, 11, 60]
    for j, ancho in enumerate(anchos, start=1):
        det.column_dimensions[get_column_letter(j)].width = ancho
    det.freeze_panes = "B2"
    det.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNAS))}{max(1, len(reporte['filas']) + 1)}"
    wb.save(ruta)


# --------------------------------------------------------------------------
# PDF (RF-25)
# --------------------------------------------------------------------------

def _pdf(texto) -> str:
    """Texto seguro para el PDF: escapa marcas y cambia lo que la fuente estándar no puede dibujar."""
    texto = "" if texto is None else str(texto)
    return escape(texto.encode("cp1252", "replace").decode("cp1252"))


def exportar_pdf(reporte: dict, ruta) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as error:
        raise DependenciaFaltante("Para exportar a PDF instala reportlab:  pip install reportlab") from error

    azul = colors.HexColor("#122C55")
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=estilos["Normal"], fontSize=8, leading=10)
    celda = ParagraphStyle("c", parent=normal, fontSize=7, leading=8.5)
    valor_grande = ParagraphStyle("v", parent=normal, fontSize=13, leading=17)
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=azul, alignment=0, fontSize=18, spaceAfter=4)
    sub = ParagraphStyle("s", parent=estilos["Heading2"], textColor=azul, fontSize=11, spaceBefore=10, spaceAfter=4)

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(1.5 * cm, 0.9 * cm, f"SIGSAT — Reporte generado el {reporte['generado_en']:%Y-%m-%d %H:%M}")
        canvas.drawRightString(landscape(A4)[0] - 1.5 * cm, 0.9 * cm, f"Página {doc.page}")
        canvas.restoreState()

    def tabla(filas, anchos, encabezado=True, alinear_derecha=()):
        t = Table(filas, colWidths=anchos, repeatRows=1 if encabezado else 0)
        estilo = [("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8FD")]),
                  ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
        if encabezado:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), azul), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                       ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        for col in alinear_derecha:
            estilo.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
        t.setStyle(TableStyle(estilo))
        return t

    resumen = reporte["resumen"]
    doc = SimpleDocTemplate(str(ruta), pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.4 * cm, bottomMargin=1.6 * cm, title="SIGSAT — Reporte de solicitudes",
                            author="SIGSAT")
    historia = [Paragraph("SIGSAT — Reporte de solicitudes", titulo),
                Paragraph(_pdf(f"Generado el {reporte['generado_en']:%Y-%m-%d %H:%M} por {reporte['generado_por']}"), normal),
                Paragraph(_pdf("Filtros: " + ("; ".join(reporte["etiquetas_filtros"]) or "ninguno (todas las solicitudes)")), normal),
                Spacer(1, 6)]

    tarjetas = _tarjetas(resumen)
    historia.append(tabla([[Paragraph(f"<b>{_pdf(e)}</b>", normal) for e, _ in tarjetas],
                           [Paragraph(f"<font size=13 color='#122C55'><b>{_pdf(v)}</b></font>", valor_grande) for _, v in tarjetas]],
                          [4.3 * cm] * 6, encabezado=False))

    def bloque(titulo_texto, primera, clave):
        datos_g = resumen[clave]
        if not datos_g:
            return
        historia.append(Paragraph(_pdf(titulo_texto), sub))
        filas = [[primera, "Solicitudes", "Finalizadas", "Vencidas", "Tiempo prom. (h)"]]
        filas += [[Paragraph(_pdf(k), celda), v["total"], v["finalizadas"], v["vencidas"], _fmt_num(v["promedio_h"])]
                  for k, v in datos_g.items()]
        historia.append(tabla(filas, [9 * cm, 3.4 * cm, 3.4 * cm, 3.4 * cm, 3.8 * cm], alinear_derecha=(1, 2, 3, 4)))

    bloque("Por área", "Área", "por_area")
    bloque("Por tipo de solicitud", "Tipo", "por_tipo")
    bloque("Por técnico", "Técnico", "por_agente")

    historia.append(Paragraph(_pdf(f"Detalle de solicitudes ({resumen['total']})"), sub))
    if not reporte["filas"]:
        historia.append(Paragraph("No hay solicitudes con esos filtros.", normal))
    else:
        cols = [("Folio", "folio", 2.0), ("Tipo", "tipo", 3.6), ("Área", "area", 3.2), ("Prior.", "prioridad", 1.3),
                ("Estatus", "estado", 1.8), ("Solicitante", "solicitante", 3.4), ("Técnico", "agente", 2.8),
                ("Creada", "creada", 2.3), ("Plazo", "plazo", 1.9), ("Horas", "horas", 1.1), ("Descripción", "descripcion", 3.2)]
        filas = [[c[0] for c in cols]]
        for f in reporte["filas"]:
            fila = []
            for _t, clave, _a in cols:
                valor = f[clave]
                if clave == "descripcion" and valor and len(valor) > 90:
                    valor = valor[:89] + "…"
                fila.append(Paragraph(_pdf("—" if valor in (None, "") and clave == "horas" else valor), celda))
            filas.append(fila)
        historia.append(tabla(filas, [c[2] * cm for c in cols]))
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
