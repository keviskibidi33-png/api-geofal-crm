"""
Generador Excel para ensayo de Contenido de Humedad — ASTM D2216-19.

Estrategia 100% ZIP/XML (sin openpyxl) para preservar TODOS los shapes,
logos, merged cells, estilos y formato del template original.

Patrón idéntico a xlsx_direct_v2.py usado en recepción.
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Any, Optional

from lxml import etree

from .schemas import HumedadRequest

logger = logging.getLogger(__name__)

# ── Namespaces ─────────────────────────────────────────────────────────────────
NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


# ── Template path ──────────────────────────────────────────────────────────────

def _find_template() -> str:
    filename = "Template_Humedad.xlsx"
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]  # app/

    possible = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]
    for p in possible:
        if p.exists():
            return str(p)
    return str(app_dir / "templates" / filename)


TEMPLATE_PATH = _find_template()


# ── XML helpers (misma lógica que xlsx_direct_v2) ──────────────────────────────

def _parse_cell_ref(ref: str) -> tuple[str, int]:
    """Parse 'D5' -> ('D', 5)"""
    col = "".join(c for c in ref if c.isalpha())
    row = int("".join(c for c in ref if c.isdigit()))
    return col, row


def _col_letter_to_num(col: str) -> int:
    """A=1, B=2, ..., Z=26, AA=27"""
    num = 0
    for c in col.upper():
        num = num * 26 + (ord(c) - ord("A") + 1)
    return num


def _find_or_create_row(sheet_data: etree._Element, row_num: int) -> etree._Element:
    """Encuentra o crea una <row> dentro de <sheetData>."""
    ns = NS_SHEET
    for row in sheet_data.findall(f"{{{ns}}}row"):
        if row.get("r") == str(row_num):
            return row
    new_row = etree.SubElement(sheet_data, f"{{{ns}}}row")
    new_row.set("r", str(row_num))
    return new_row


def _find_or_create_cell(row: etree._Element, cell_ref: str) -> etree._Element:
    """Encuentra o crea una <c> dentro de una <row>, insertada en orden."""
    ns = NS_SHEET
    for cell in row.findall(f"{{{ns}}}c"):
        if cell.get("r") == cell_ref:
            return cell

    col, _ = _parse_cell_ref(cell_ref)
    col_num = _col_letter_to_num(col)

    insert_pos = None
    existing = row.findall(f"{{{ns}}}c")
    for i, ex in enumerate(existing):
        ex_col, _ = _parse_cell_ref(ex.get("r"))
        if col_num < _col_letter_to_num(ex_col):
            insert_pos = i
            break

    cell = etree.Element(f"{{{ns}}}c")
    cell.set("r", cell_ref)
    if insert_pos is not None:
        row.insert(insert_pos, cell)
    else:
        row.append(cell)
    return cell


def _set_cell(
    sheet_data: etree._Element,
    ref: str,
    value: Any,
    is_number: bool = False,
):
    """
    Escribe un valor en una celda del sheet XML.
    Usa inlineStr para texto (no necesita sharedStrings).
    """
    if value is None:
        return

    ns = NS_SHEET
    col, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    # Preservar estilo existente
    style = cell.get("s")

    # Limpiar contenido previo
    for child in list(cell):
        cell.remove(child)

    str_val = str(value)
    if str_val == "":
        if "t" in cell.attrib:
            del cell.attrib["t"]
        if style:
            cell.set("s", style)
        return

    if is_number:
        if "t" in cell.attrib:
            del cell.attrib["t"]
        v = etree.SubElement(cell, f"{{{ns}}}v")
        v.text = str_val
    else:
        cell.set("t", "inlineStr")
        is_elem = etree.SubElement(cell, f"{{{ns}}}is")
        t_elem = etree.SubElement(is_elem, f"{{{ns}}}t")
        t_elem.text = str_val

    if style:
        cell.set("s", style)


def _get_cell_style(sheet_data: etree._Element, ref: str) -> str | None:
    """Obtiene style id (atributo s) de una celda existente."""
    ns = NS_SHEET
    col, row_num = _parse_cell_ref(ref)
    for row in sheet_data.findall(f"{{{ns}}}row"):
        if row.get("r") != str(row_num):
            continue
        for cell in row.findall(f"{{{ns}}}c"):
            if cell.get("r") == ref:
                return cell.get("s")
    return None


def _set_cell_style(sheet_data: etree._Element, ref: str, style_id: str | None) -> None:
    """Aplica style id a una celda (la crea si no existe)."""
    if not style_id:
        return
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    cell.set("s", style_id)


# ── Shape text injection ──────────────────────────────────────────────────────

def _inject_shape_text(drawing_xml: bytes, labels: dict[str, str]) -> bytes:
    """
    Busca shapes por contenido de texto (no por índice) e inyecta valores.

    ``labels`` es un dict label→valor, ej:
        {"Revisado:": "Ing. Pérez", "Fecha:": "14/02/2026"}

    Busca TODOS los anchors; en cada anchor, si un <a:t> contiene el label,
    reemplaza el texto con "label valor".
    """
    NS = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    for anchor in root.findall(".//xdr:twoCellAnchor", NS):
        for run in anchor.findall(".//a:r", NS):
            t_el = run.find("a:t", NS)
            if t_el is None or t_el.text is None:
                continue
            text = t_el.text.strip()
            if text in labels and labels[text]:
                t_el.text = f"{text} {labels[text]}"

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _get_anchor_bounds(anchor: etree._Element) -> tuple[int, int, int, int] | None:
    """Obtiene los límites (col,row) del anchor para ubicar shapes por posición."""
    NS = {"xdr": NS_DRAW}
    from_el = anchor.find("xdr:from", NS)
    to_el = anchor.find("xdr:to", NS)
    if from_el is None or to_el is None:
        return None

    def _read_int(parent: etree._Element, tag: str) -> int | None:
        value_el = parent.find(f"xdr:{tag}", NS)
        if value_el is None or value_el.text is None:
            return None
        try:
            return int(value_el.text)
        except ValueError:
            return None

    from_col = _read_int(from_el, "col")
    from_row = _read_int(from_el, "row")
    to_col = _read_int(to_el, "col")
    to_row = _read_int(to_el, "row")

    if None in (from_col, from_row, to_col, to_row):
        return None
    return from_col, from_row, to_col, to_row


def _set_anchor_value_text(anchor: etree._Element, value: Any) -> bool:
    """
    Inserta texto en el txBody del shape.
    Se usa para los rectángulos de entrada del encabezado (MUESTRA/OT/FECHA/REALIZADO).
    """
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False

    NS = {"xdr": NS_DRAW, "a": NS_A}
    paragraph = anchor.find(".//xdr:txBody/a:p", NS)
    if paragraph is None:
        return False

    # Limpiar runs previos para dejar un único valor.
    run_tag = f"{{{NS_A}}}r"
    field_tag = f"{{{NS_A}}}fld"
    for child in list(paragraph):
        if child.tag in (run_tag, field_tag):
            paragraph.remove(child)

    end_para = paragraph.find("a:endParaRPr", NS)

    run = etree.Element(run_tag)
    run_props = etree.SubElement(run, f"{{{NS_A}}}rPr")

    # Reusar estilo tipográfico del párrafo para mantener consistencia visual.
    if end_para is not None:
        for attr, attr_val in end_para.attrib.items():
            run_props.set(attr, attr_val)
        for style_child in end_para:
            run_props.append(etree.fromstring(etree.tostring(style_child)))
    else:
        run_props.set("lang", "es-PE")
        run_props.set("sz", "900")

    t_el = etree.SubElement(run, f"{{{NS_A}}}t")
    t_el.text = text

    if end_para is not None:
        paragraph.insert(list(paragraph).index(end_para), run)
    else:
        paragraph.append(run)

    return True


# ── Generador principal ───────────────────────────────────────────────────────

def generate_humedad_excel(data: HumedadRequest) -> bytes:
    """
    Genera el Excel de Contenido de Humedad a partir de los datos proporcionados.
    Opera 100% a nivel ZIP/XML para preservar todos los shapes del template.

    Returns:
        bytes del archivo .xlsx listo para descarga.
    """
    logger.info("Generando Excel de Humedad — ASTM D2216-19")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template no encontrado: {TEMPLATE_PATH}")

    # ── Leer template como ZIP ─────────────────────────────────────────
    with open(TEMPLATE_PATH, "rb") as f:
        template_bytes = f.read()

    # ── Calcular fórmulas ──────────────────────────────────────────────
    masa_agua = data.masa_agua
    masa_seca = data.masa_muestra_seca
    humedad = data.contenido_humedad

    # masa_agua = húmeda - seca_constante  (ASTM D2216: I33 - I35)
    if masa_agua is None and data.masa_recipiente_muestra_humeda and data.masa_recipiente_muestra_seca_constante:
        masa_agua = round(data.masa_recipiente_muestra_humeda - data.masa_recipiente_muestra_seca_constante, 2)

    # masa_seca = seca_constante - recipiente  (I35 - I36)
    if masa_seca is None and data.masa_recipiente_muestra_seca_constante and data.masa_recipiente:
        masa_seca = round(data.masa_recipiente_muestra_seca_constante - data.masa_recipiente, 2)

    # contenido_humedad = (masa_agua / masa_seca) * 100
    if humedad is None and masa_agua is not None and masa_seca and masa_seca != 0:
        humedad = round((masa_agua / masa_seca) * 100, 2)

    # ── Procesar ZIP ───────────────────────────────────────────────────
    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, \
         zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:

        for item in zin.infolist():
            raw = zin.read(item.filename)

            # ── Modificar sheet1.xml (hoja principal) ──────────────────
            if item.filename == "xl/worksheets/sheet1.xml":
                raw = _fill_sheet(raw, data, masa_agua, masa_seca, humedad)

            # ── Modificar drawing1.xml (shapes del footer) ─────────────
            if item.filename == "xl/drawings/drawing1.xml":
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()


# ── Rellenado de celdas ───────────────────────────────────────────────────────

def _fill_sheet(
    sheet_xml: bytes,
    data: HumedadRequest,
    masa_agua: Optional[float],
    masa_seca: Optional[float],
    humedad: Optional[float],
) -> bytes:
    """Inyecta todos los valores de celdas en el XML de la hoja."""
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Tomar estilos centrados del template para reutilizarlos sin hardcode.
    # I31 suele ser centro para N° de ensayo y I37 centro para valores numéricos.
    centered_style_general = _get_cell_style(sd, "I31")
    centered_style_numeric = _get_cell_style(sd, "I37") or centered_style_general
    # E10/G10/I10 son labels del encabezado con alineación centrada (sin bordes).
    header_centered_style = (
        _get_cell_style(sd, "E10")
        or _get_cell_style(sd, "G10")
        or _get_cell_style(sd, "I10")
        or centered_style_general
    )

    # ── Encabezado principal (fila 12) ──────────────────────────────────
    # Nuevo mapeo sin rectángulos/shapes:
    #   Muestra -> D12, N° OT -> E12, Fecha ensayo -> G12, Realizado -> I12
    _set_cell(sd, "D12", data.muestra)
    _set_cell(sd, "E12", data.numero_ot)
    _set_cell(sd, "G12", data.fecha_ensayo)
    _set_cell(sd, "I12", data.realizado_por)
    for ref in ("D12", "E12", "G12", "I12"):
        _set_cell_style(sd, ref, header_centered_style)

    # ── Condiciones del ensayo (rows 18-21, col J) ─────────────────────
    _set_cell(sd, "J18", data.condicion_masa_menor)
    _set_cell(sd, "J19", data.condicion_capas)
    _set_cell(sd, "J20", data.condicion_temperatura)
    _set_cell(sd, "J21", data.condicion_excluido)
    if data.descripcion_material_excluido:
        _set_cell(sd, "A22", f"Descripción material excluido: {data.descripcion_material_excluido}")

    # ── Descripción muestra (rows 25-27, merged E-F) ──────────────────
    _set_cell(sd, "E25", data.tipo_muestra)
    _set_cell(sd, "E26", data.condicion_muestra)
    _set_cell(sd, "E27", data.tamano_maximo_particula)

    # ── Método — Marque X (rows 26-27, col J) ─────────────────────────
    _set_cell(sd, "J26", "X" if data.metodo_a else "")
    _set_cell(sd, "J27", "X" if data.metodo_b else "")

    # ── Datos de ensayo (rows 31-39, col I) ────────────────────────────
    # Reforzar columna UND para evitar pérdidas por cambios visuales de plantilla.
    _set_cell(sd, "H30", "UND")
    _set_cell(sd, "H31", "N°")
    _set_cell(sd, "H32", "N°")
    _set_cell(sd, "H33", "g")
    _set_cell(sd, "H34", "g")
    _set_cell(sd, "H35", "g")
    _set_cell(sd, "H36", "g")
    _set_cell(sd, "H37", "g")
    _set_cell(sd, "H38", "g")
    _set_cell(sd, "H39", "%")

    _set_cell(sd, "I31", data.numero_ensayo, is_number=True)
    _set_cell(sd, "I32", data.recipiente_numero)
    _set_cell(sd, "I33", data.masa_recipiente_muestra_humeda, is_number=True)
    _set_cell(sd, "I34", data.masa_recipiente_muestra_seca, is_number=True)
    _set_cell(sd, "I35", data.masa_recipiente_muestra_seca_constante, is_number=True)
    _set_cell(sd, "I36", data.masa_recipiente, is_number=True)

    # Fórmulas calculadas (rows 37-39)
    if masa_agua is not None:
        _set_cell(sd, "I37", masa_agua, is_number=True)
    else:
        _set_cell(sd, "I37", "-")

    if masa_seca is not None:
        _set_cell(sd, "I38", masa_seca, is_number=True)
    else:
        _set_cell(sd, "I38", "-")

    if humedad is not None:
        _set_cell(sd, "I39", humedad, is_number=True)
    else:
        _set_cell(sd, "I39", "-")

    # Forzar centrado visual en la columna ENSAYO (I31:I39).
    # El template trae I32:I36 con alineación derecha; aquí los homogeneizamos.
    _set_cell_style(sd, "I31", centered_style_general)
    for ref in ("I32", "I33", "I34", "I35", "I36", "I37", "I38", "I39"):
        _set_cell_style(sd, ref, centered_style_numeric)

    # ── Método A — Tamaños (rows 43-45) ────────────────────────────────
    _set_cell(sd, "B43", data.metodo_a_tamano_1)
    _set_cell(sd, "B44", data.metodo_a_tamano_2)
    _set_cell(sd, "B45", data.metodo_a_tamano_3)
    _set_cell(sd, "E43", data.metodo_a_masa_1)
    _set_cell(sd, "E44", data.metodo_a_masa_2)
    _set_cell(sd, "E45", data.metodo_a_masa_3)
    _set_cell(sd, "F43", data.metodo_a_legibilidad_1)
    _set_cell(sd, "F44", data.metodo_a_legibilidad_2)
    _set_cell(sd, "F45", data.metodo_a_legibilidad_3)

    # ── Método B — Tamaños (rows 47-49) ────────────────────────────────
    _set_cell(sd, "B47", data.metodo_b_tamano_1)
    _set_cell(sd, "B48", data.metodo_b_tamano_2)
    _set_cell(sd, "B49", data.metodo_b_tamano_3)
    _set_cell(sd, "E47", data.metodo_b_masa_1)
    _set_cell(sd, "E48", data.metodo_b_masa_2)
    _set_cell(sd, "E49", data.metodo_b_masa_3)
    _set_cell(sd, "F47", data.metodo_b_legibilidad_1)
    _set_cell(sd, "F48", data.metodo_b_legibilidad_2)
    _set_cell(sd, "F49", data.metodo_b_legibilidad_3)

    # ── Equipo utilizado (J42, J43, J45 — merged J-L) ─────────────────
    _set_cell(sd, "J42", data.equipo_balanza_01)
    _set_cell(sd, "J43", data.equipo_balanza_001)
    _set_cell(sd, "J45", data.equipo_horno)

    # ── Observaciones (D52) ────────────────────────────────────────────
    _set_cell(sd, "D52", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: HumedadRequest) -> bytes:
    """
    Inyecta texto en los shapes del footer (Revisado / Aprobado).

    Usa inyección por-anchor para distinguir correctamente las fechas
    de Revisado vs Aprobado (ambos tienen un label "Fecha:").
    """
    has_footer = any([data.revisado_por, data.revisado_fecha, data.aprobado_por, data.aprobado_fecha])
    if not has_footer:
        return drawing_xml

    NS = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    for anchor in root.findall(".//xdr:twoCellAnchor", NS):
        # Recopilar todos los textos del anchor para identificarlo
        all_texts = [
            (t.text or "").strip()
            for t in anchor.findall(".//a:t", NS)
        ]
        text_blob = " ".join(all_texts)

        # Determinar si es el shape de Revisado o Aprobado
        is_revisado = "Revisado:" in text_blob
        is_aprobado = "Aprobado:" in text_blob

        if not is_revisado and not is_aprobado:
            continue

        # Preparar los reemplazos para este anchor específico
        replacements: dict[str, str] = {}
        if is_revisado:
            if data.revisado_por:
                replacements["Revisado:"] = data.revisado_por
            if data.revisado_fecha:
                replacements["Fecha:"] = data.revisado_fecha
        elif is_aprobado:
            if data.aprobado_por:
                replacements["Aprobado:"] = data.aprobado_por
            if data.aprobado_fecha:
                replacements["Fecha:"] = data.aprobado_fecha

        # Aplicar reemplazos dentro de este anchor solamente
        for run in anchor.findall(".//a:r", NS):
            t_el = run.find("a:t", NS)
            if t_el is None or t_el.text is None:
                continue
            text = t_el.text.strip()
            if text in replacements and replacements[text]:
                t_el.text = f"{text} {replacements[text]}"

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
