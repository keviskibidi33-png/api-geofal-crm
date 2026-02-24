"""
Excel generator for LLP (Liquid Limit / Plastic Limit) - ASTM D4318-17e1.

ZIP/XML strategy (without openpyxl writes) to preserve shapes, merged cells,
styles and formulas of the official template.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .schemas import LLPRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _find_template() -> str:
    filename = "Template_LLP.xlsx"
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]  # app/

    possible = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]
    for path in possible:
        if path.exists():
            return str(path)
    return str(app_dir / "templates" / filename)


TEMPLATE_PATH = _find_template()
POINT_COLS = ["G", "I", "J", "K", "L"]


def _parse_cell_ref(ref: str) -> tuple[str, int]:
    col = "".join(c for c in ref if c.isalpha())
    row = int("".join(c for c in ref if c.isdigit()))
    return col, row


def _col_letter_to_num(col: str) -> int:
    num = 0
    for char in col.upper():
        num = num * 26 + (ord(char) - ord("A") + 1)
    return num


def _find_or_create_row(sheet_data: etree._Element, row_num: int) -> etree._Element:
    ns = NS_SHEET
    for row in sheet_data.findall(f"{{{ns}}}row"):
        if row.get("r") == str(row_num):
            return row

    new_row = etree.SubElement(sheet_data, f"{{{ns}}}row")
    new_row.set("r", str(row_num))
    return new_row


def _find_or_create_cell(row: etree._Element, cell_ref: str) -> etree._Element:
    ns = NS_SHEET
    for cell in row.findall(f"{{{ns}}}c"):
        if cell.get("r") == cell_ref:
            return cell

    col, _ = _parse_cell_ref(cell_ref)
    col_num = _col_letter_to_num(col)

    insert_pos = None
    existing = row.findall(f"{{{ns}}}c")
    for idx, ex in enumerate(existing):
        ex_col, _ = _parse_cell_ref(ex.get("r"))
        if col_num < _col_letter_to_num(ex_col):
            insert_pos = idx
            break

    cell = etree.Element(f"{{{NS_SHEET}}}c")
    cell.set("r", cell_ref)

    if insert_pos is not None:
        row.insert(insert_pos, cell)
    else:
        row.append(cell)

    return cell


def _set_cell(sheet_data: etree._Element, ref: str, value: Any, is_number: bool = False) -> None:
    if value is None:
        return

    ns = NS_SHEET
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    for child in list(cell):
        cell.remove(child)

    if is_number:
        cell.attrib.pop("t", None)
        val = etree.SubElement(cell, f"{{{ns}}}v")
        val.text = str(value)
        return

    text = str(value)
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{ns}}}is")
    t_el = etree.SubElement(is_el, f"{{{ns}}}t")
    t_el.text = text


def generate_llp_excel(data: LLPRequest) -> bytes:
    """Generates the LLP Excel file from template."""
    logger.info("Generating LLP Excel - ASTM D4318-17e1")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        sheet_original = zin.read("xl/worksheets/sheet1.xml")
        sheet_xml = _fill_sheet(sheet_original, data)

        for item in zin.infolist():
            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet_xml
            else:
                raw = zin.read(item.filename)

            if item.filename == "xl/drawings/drawing1.xml":
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()


def _fill_sheet(sheet_xml: bytes, data: LLPRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Header
    _set_cell(sd, "C11", data.muestra)
    _set_cell(sd, "E11", data.numero_ot)
    _set_cell(sd, "H11", data.fecha_ensayo)
    _set_cell(sd, "J11", data.realizado_por)

    # Condiciones del ensayo
    _set_cell(sd, "J17", data.metodo_ensayo_limite_liquido)
    _set_cell(sd, "J18", data.herramienta_ranurado_limite_liquido)
    _set_cell(sd, "J19", data.dispositivo_limite_liquido)
    _set_cell(sd, "J20", data.metodo_laminacion_limite_plastico)
    _set_cell(sd, "J21", data.contenido_humedad_muestra_inicial_pct, is_number=True)
    _set_cell(sd, "J22", data.proceso_seleccion_muestra)
    _set_cell(sd, "J23", data.metodo_preparacion_muestra)

    # Descripcion de la muestra
    _set_cell(sd, "J29", data.tipo_muestra)
    _set_cell(sd, "J30", data.condicion_muestra)
    _set_cell(sd, "J31", data.tamano_maximo_visual_in)
    _set_cell(sd, "J32", data.porcentaje_retenido_tamiz_40_pct, is_number=True)
    _set_cell(sd, "J33", data.forma_particula)

    # Tabla principal (LL + LP)
    for idx, col in enumerate(POINT_COLS):
        punto = data.puntos[idx]
        _set_cell(sd, f"{col}37", punto.recipiente_numero)
        if idx < 3:
            _set_cell(sd, f"{col}38", punto.numero_golpes, is_number=True)
        _set_cell(sd, f"{col}39", punto.masa_recipiente_suelo_humedo, is_number=True)
        _set_cell(sd, f"{col}40", punto.masa_recipiente_suelo_seco, is_number=True)
        _set_cell(sd, f"{col}41", punto.masa_recipiente_suelo_seco_1, is_number=True)
        _set_cell(sd, f"{col}42", punto.masa_recipiente, is_number=True)

    # Equipos
    _set_cell(sd, "D48", data.balanza_001g_codigo)
    _set_cell(sd, "D49", data.horno_110_codigo)
    _set_cell(sd, "D50", data.copa_casagrande_codigo)
    _set_cell(sd, "D51", data.ranurador_codigo)

    # Observaciones
    _set_cell(sd, "G48", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: LLPRequest) -> bytes:
    """
    Injects footer text in signature shapes.
    Works with placeholders:
    - Revisado:
    - Aprobado:
    - Fecha:
    """
    has_footer = any([data.revisado_por, data.revisado_fecha, data.aprobado_por, data.aprobado_fecha])
    if not has_footer:
        return drawing_xml

    ns = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        all_texts = [(node.text or "").strip() for node in anchor.findall(".//a:t", ns)]
        text_blob = " ".join(all_texts)

        is_revisado = "Revisado:" in text_blob
        is_aprobado = "Aprobado:" in text_blob
        if not is_revisado and not is_aprobado:
            continue

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

        for run in anchor.findall(".//a:r", ns):
            t_el = run.find("a:t", ns)
            if t_el is None or t_el.text is None:
                continue
            text = t_el.text.strip()
            if text in replacements and replacements[text]:
                t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if text == "Fecha:":
                    t_el.text = f"{text} {replacements[text]}"
                else:
                    t_el.text = f"{text}\n{replacements[text]}"

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

