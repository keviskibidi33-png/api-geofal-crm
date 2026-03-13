"""
Excel generator for Caras Fracturadas (ASTM D5821-13).

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

from .schemas import CarasRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

TARGET_SHEET_NAME = "Caras Fracturadas"


def _find_template() -> str:
    filename = "Template_Caras.xlsx"
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


def _clear_cell(cell: etree._Element) -> None:
    cell.attrib.pop("t", None)
    for child in list(cell):
        cell.remove(child)


def _set_text(sheet_data: etree._Element, ref: str, value: Any) -> None:
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    _clear_cell(cell)

    text = "" if value is None else str(value)
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{NS_SHEET}}}is")
    t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
    t_el.text = text


def _set_number(sheet_data: etree._Element, ref: str, value: float | int | None) -> None:
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    _clear_cell(cell)

    if value is None:
        return

    val = etree.SubElement(cell, f"{{{NS_SHEET}}}v")
    val.text = str(value)


def _normalize_xlsx_path(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("xl/"):
        return target

    parts = base_dir.split("/")
    remaining = target
    while remaining.startswith("../"):
        remaining = remaining[3:]
        if parts:
            parts.pop()
    if remaining.startswith("./"):
        remaining = remaining[2:]
    return "/".join([*parts, remaining]) if parts else remaining


def _resolve_sheet_xml_path(zin: zipfile.ZipFile, sheet_name: str) -> str:
    wb_root = etree.fromstring(zin.read("xl/workbook.xml"))
    sheet_rid: str | None = None
    for sheet in wb_root.findall(f".//{{{NS_SHEET}}}sheet"):
        if sheet.get("name") == sheet_name:
            sheet_rid = sheet.get(f"{{{NS_OFFICE_REL}}}id")
            break
    if not sheet_rid:
        raise ValueError(f"No se encontro la hoja '{sheet_name}' en el template.")

    rels_root = etree.fromstring(zin.read("xl/_rels/workbook.xml.rels"))
    sheet_target: str | None = None
    for rel in rels_root.findall(f".//{{{NS_PKG_REL}}}Relationship"):
        if rel.get("Id") == sheet_rid:
            sheet_target = rel.get("Target")
            break
    if not sheet_target:
        raise ValueError(f"No se encontro el target de la hoja '{sheet_name}'.")

    return _normalize_xlsx_path("xl", sheet_target)


def _fill_sheet(sheet_xml: bytes, data: CarasRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    # Encabezado (top-left de celdas mergeadas).
    _set_text(sheet_data, "C8", data.muestra)
    _set_text(sheet_data, "D8", data.numero_ot)
    _set_text(sheet_data, "E8", data.fecha_ensayo)
    _set_text(sheet_data, "G8", data.realizado_por)

    # Metodo de determinacion (marcado sobre la misma etiqueta).
    _set_text(sheet_data, "D15", "X MASA" if data.metodo_determinacion == "MASA" else "Masa")
    _set_text(sheet_data, "E15", "X RECUENTO" if data.metodo_determinacion == "RECUENTO" else "Recuento")

    # Informacion de ensayo.
    _set_text(sheet_data, "D16", data.tamano_maximo_nominal_in)
    _set_text(sheet_data, "D17", data.tamiz_especificado_in)

    _set_text(sheet_data, "D18", "X SI" if data.fraccionada is True else "SI")
    _set_text(sheet_data, "E18", "X NO" if data.fraccionada is False else "NO")

    # Muestra original de ensayo.
    _set_number(sheet_data, "E20", data.masa_muestra_retenida_g)
    _set_number(sheet_data, "E21", data.masa_particula_mas_grande_g)
    if data.porcentaje_particula_mas_grande_pct is not None:
        _set_number(sheet_data, "E22", data.porcentaje_particula_mas_grande_pct)
    _set_number(sheet_data, "E23", data.masa_muestra_seca_lavada_g)
    _set_number(sheet_data, "E24", data.masa_muestra_seca_lavada_constante_g)
    _set_number(sheet_data, "E25", data.masa_muestra_mayor_3_8_g)
    _set_number(sheet_data, "E26", data.masa_muestra_menor_3_8_g)

    # Muestra de prueba > 3/8 in o Global.
    _set_number(sheet_data, "E33", data.global_una_f_masa_fracturadas_g)
    _set_number(sheet_data, "E34", data.global_una_n_masa_no_cumple_g)
    _set_number(sheet_data, "E35", data.global_una_p_porcentaje_pct)

    _set_number(sheet_data, "G33", data.global_dos_f_masa_fracturadas_g)
    _set_number(sheet_data, "G34", data.global_dos_n_masa_no_cumple_g)
    _set_number(sheet_data, "G35", data.global_dos_p_porcentaje_pct)

    # Fraccion < 3/8 in.
    _set_number(sheet_data, "E37", data.fraccion_masa_menor_3_8_mayor_200g_una_g)
    _set_number(sheet_data, "G37", data.fraccion_masa_menor_3_8_mayor_200g_dos_g)

    _set_number(sheet_data, "E38", data.fraccion_una_f_masa_fracturadas_g)
    _set_number(sheet_data, "E39", data.fraccion_una_n_masa_no_cumple_g)
    _set_number(sheet_data, "E40", data.fraccion_una_p_porcentaje_pct)

    _set_number(sheet_data, "G38", data.fraccion_dos_f_masa_fracturadas_g)
    _set_number(sheet_data, "G39", data.fraccion_dos_n_masa_no_cumple_g)
    _set_number(sheet_data, "G40", data.fraccion_dos_p_porcentaje_pct)

    _set_number(sheet_data, "E41", data.promedio_ponderado_una_pct)
    _set_number(sheet_data, "G41", data.promedio_ponderado_dos_pct)

    # Equipos.
    _set_text(sheet_data, "H15", data.horno_codigo)
    _set_text(sheet_data, "H16", data.balanza_01g_codigo)
    _set_text(sheet_data, "H17", data.tamiz_especificado_codigo)

    # Nota.
    _set_text(sheet_data, "C44", data.nota)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: CarasRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_caras_excel(data: CarasRequest) -> bytes:
    """Generate Caras Excel file from template."""
    logger.info("Generating Caras Excel - ASTM D5821-13")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        sheet_path = _resolve_sheet_xml_path(zin, TARGET_SHEET_NAME)
        sheet_original = zin.read(sheet_path)
        sheet_xml = _fill_sheet(sheet_original, data)

        for item in zin.infolist():
            if item.filename == sheet_path:
                raw = sheet_xml
            else:
                raw = zin.read(item.filename)

            if item.filename.startswith("xl/drawings/drawing") and item.filename.endswith(".xml"):
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
