"""
Excel generator for Tamiz (ASTM C117-23).

ZIP/XML strategy to preserve styles, merged cells and drawings from template.
"""

from __future__ import annotations

import io
import logging
from app.modules.common.excel_xml import (
    enable_full_recalc_on_open,
    remove_calc_chain_content_type,
    remove_calc_chain_relationships,
    remove_external_link_content_types,
    remove_external_link_relationships,
    strip_external_references,
    find_template_path,
)
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes

from .schemas import TamizRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


TEMPLATE_PATH = str(find_template_path("1-INF.-N-000-26-AG23-MALLA-200-V08.xlsx"))


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


def _fill_sheet(sheet_xml: bytes, data: TamizRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado
    _set_cell(sd, "C11", data.muestra)
    _set_cell(sd, "E11", data.numero_ot)
    _set_cell(sd, "G11", data.fecha_ensayo)
    _set_cell(sd, "I11", data.realizado_por)

    # Procedimiento y TMN
    if data.procedimiento == "A":
        _set_cell(sd, "C18", "X")
    elif data.procedimiento == "B":
        _set_cell(sd, "C19", "X")
    _set_cell(sd, "L18", data.tamano_maximo_nominal_visual_in)

    # Tabla A-H (DATOS columna J)
    _set_cell(sd, "J22", data.a_masa_recipiente_g, is_number=True)
    _set_cell(sd, "J23", data.b_masa_recipiente_muestra_seca_g, is_number=True)
    _set_cell(sd, "J24", data.c_masa_recipiente_muestra_seca_constante_g, is_number=True)
    _set_cell(sd, "J25", data.d_masa_seca_original_muestra_g, is_number=True)
    _set_cell(sd, "J26", data.e_masa_recipiente_muestra_seca_despues_lavado_g, is_number=True)
    _set_cell(sd, "J27", data.f_masa_recipiente_muestra_seca_despues_lavado_constante_g, is_number=True)
    _set_cell(sd, "J28", data.g_masa_seca_muestra_despues_lavado_g, is_number=True)
    _set_cell(sd, "J29", data.h_porcentaje_material_fino_pct, is_number=True)

    # Equipos (codigos)
    _set_cell(sd, "E33", data.balanza_01g_codigo)
    _set_cell(sd, "E34", data.horno_110c_codigo)
    _set_cell(sd, "E35", data.tamiz_no_200_codigo)
    _set_cell(sd, "E36", data.tamiz_no_16_codigo)

    # Observaciones
    if data.observaciones:
        _set_cell(sd, "B39", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_datos_ens_sheet(sheet_xml: bytes, data: TamizRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    _set_cell(sd, "H6", data.realizado_por)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_incertidumbre_sheet(sheet_xml: bytes, data: TamizRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    _set_cell(sd, "B58", data.revisado_por)
    _set_cell(sd, "B60", data.revisado_fecha)
    _set_cell(sd, "G58", data.aprobado_por)
    _set_cell(sd, "G60", data.aprobado_fecha)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: TamizRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_tamiz_excel(data: TamizRequest) -> bytes:
    """Generate Tamiz Excel file from template."""
    logger.info("Generating Tamiz Excel - ASTM C117-23")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        sheet_original = zin.read("xl/worksheets/sheet8.xml")
        sheet_xml = _fill_sheet(sheet_original, data)

        datos_ensayo_original = zin.read("xl/worksheets/sheet10.xml")
        datos_ensayo_xml = _fill_datos_ens_sheet(datos_ensayo_original, data)

        incertidumbre_original = zin.read("xl/worksheets/sheet11.xml")
        incertidumbre_xml = _fill_incertidumbre_sheet(incertidumbre_original, data)

        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue
            if item.filename.startswith("xl/externalLinks/"):
                continue

            if item.filename == "xl/worksheets/sheet8.xml":
                raw = sheet_xml
            elif item.filename == "xl/worksheets/sheet10.xml":
                raw = datos_ensayo_xml
            elif item.filename == "xl/worksheets/sheet11.xml":
                raw = incertidumbre_xml
            else:
                raw = zin.read(item.filename)

            if item.filename.startswith("xl/drawings/drawing") and item.filename.endswith(".xml"):
                raw = _fill_drawing(raw, data)
            elif item.filename == "xl/workbook.xml":
                raw = enable_full_recalc_on_open(raw)
                raw = strip_external_references(raw)
            elif item.filename == "xl/_rels/workbook.xml.rels":
                raw = remove_calc_chain_relationships(raw)
                raw = remove_external_link_relationships(raw)
            elif item.filename == "[Content_Types].xml":
                raw = remove_calc_chain_content_type(raw)
                raw = remove_external_link_content_types(raw)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()