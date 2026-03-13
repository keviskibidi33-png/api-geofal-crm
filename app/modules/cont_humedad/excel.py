"""
Excel generator for Contenido de Humedad de agregados (ASTM C566-25).

ZIP/XML strategy to preserve styles, merged cells and drawings from template.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes

from .schemas import ContHumedadRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _find_template() -> str:
    filename = "Template_ContHumedad.xlsx"
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
    for row in sheet_data.findall(f"{{{NS_SHEET}}}row"):
        if row.get("r") == str(row_num):
            return row

    new_row = etree.SubElement(sheet_data, f"{{{NS_SHEET}}}row")
    new_row.set("r", str(row_num))
    return new_row


def _find_or_create_cell(row: etree._Element, cell_ref: str) -> etree._Element:
    for cell in row.findall(f"{{{NS_SHEET}}}c"):
        if cell.get("r") == cell_ref:
            return cell

    col, _ = _parse_cell_ref(cell_ref)
    col_num = _col_letter_to_num(col)

    insert_pos = None
    existing = row.findall(f"{{{NS_SHEET}}}c")
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

    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    for child in list(cell):
        cell.remove(child)

    if is_number:
        cell.attrib.pop("t", None)
        val = etree.SubElement(cell, f"{{{NS_SHEET}}}v")
        val.text = str(value)
        return

    text = str(value)
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{NS_SHEET}}}is")
    t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
    t_el.text = text


def _fill_sheet(sheet_xml: bytes, data: ContHumedadRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado
    _set_cell(sd, "E11", data.muestra)
    _set_cell(sd, "G11", data.numero_ot)
    _set_cell(sd, "H11", data.fecha_ensayo)
    _set_cell(sd, "K11", data.realizado_por)

    # Tabla principal (columna G)
    _set_cell(sd, "G19", data.numero_ensayo, is_number=True)
    _set_cell(sd, "G20", data.recipiente_numero)
    _set_cell(sd, "G21", data.masa_recipiente_muestra_humedo_g, is_number=True)
    _set_cell(sd, "G22", data.masa_recipiente_muestra_seco_g, is_number=True)
    _set_cell(sd, "G23", data.masa_recipiente_muestra_seco_constante_g, is_number=True)
    _set_cell(sd, "G24", data.masa_agua_g, is_number=True)
    _set_cell(sd, "G25", data.masa_recipiente_g, is_number=True)
    _set_cell(sd, "G26", data.masa_muestra_seco_g, is_number=True)
    _set_cell(sd, "G27", data.contenido_humedad_pct, is_number=True)

    # Descripcion de muestra
    _set_cell(sd, "F30", data.tipo_muestra)
    _set_cell(sd, "F31", data.tamano_maximo_muestra_visual_in)
    _set_cell(sd, "F32", data.cumple_masa_minima_norma)
    _set_cell(sd, "F33", data.se_excluyo_material)
    _set_cell(sd, "G34", data.descripcion_material_excluido or "")

    # Equipos
    _set_cell(sd, "K31", data.balanza_01g_codigo)
    _set_cell(sd, "K32", data.horno_110c_codigo)

    # Observaciones
    if data.observaciones:
        lines = [line.strip() for line in str(data.observaciones).splitlines() if line.strip()]
        if lines:
            _set_cell(sd, "E37", lines[0])
            if len(lines) > 1:
                _set_cell(sd, "A38", " ".join(lines[1:]))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: ContHumedadRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_cont_humedad_excel(data: ContHumedadRequest) -> bytes:
    """Generate Contenido de Humedad Excel file from template."""
    logger.info("Generating Contenido Humedad Excel - ASTM C566-25")

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

            if item.filename.startswith("xl/drawings/drawing") and item.filename.endswith(".xml"):
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
