"""
Excel generator for Planas y Alargadas (ASTM D4791-19).

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

from .schemas import PlanasRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

TARGET_SHEET_NAME = "PLANAS Y ALARGADAS"


def _find_template() -> str:
    filename = "Template_Planas.xlsx"
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


def _set_cell(
    sheet_data: etree._Element,
    ref: str,
    value: Any,
    is_number: bool = False,
    force_black_bold: bool = False,
) -> None:
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
    if force_black_bold:
        r_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}r")
        rpr = etree.SubElement(r_el, f"{{{NS_SHEET}}}rPr")
        etree.SubElement(rpr, f"{{{NS_SHEET}}}b")
        color = etree.SubElement(rpr, f"{{{NS_SHEET}}}color")
        color.set("rgb", "FF000000")
        sz = etree.SubElement(rpr, f"{{{NS_SHEET}}}sz")
        sz.set("val", "11")
        rf = etree.SubElement(rpr, f"{{{NS_SHEET}}}rFont")
        rf.set("val", "Calibri")
        t_el = etree.SubElement(r_el, f"{{{NS_SHEET}}}t")
        t_el.text = text
    else:
        t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
        t_el.text = text


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


def _fill_sheet(sheet_xml: bytes, data: PlanasRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    # Encabezado (top-left de celdas mergeadas).
    _set_cell(sheet_data, "D11", data.muestra)
    _set_cell(sheet_data, "G11", data.numero_ot)
    _set_cell(sheet_data, "J11", data.fecha_ensayo)
    _set_cell(sheet_data, "M11", data.realizado_por)

    # Relacion dimensional (marca en fila 19).
    _set_cell(sheet_data, "B19", "X" if data.relacion_dimensional == "1:2" else "")
    _set_cell(sheet_data, "C19", "X" if data.relacion_dimensional == "1:3" else "")
    _set_cell(sheet_data, "D19", "X" if data.relacion_dimensional == "1:5" else "")

    # Metodo y tamiz requerido (marcas X).
    _set_cell(sheet_data, "G18", "X" if data.metodo_ensayo == "A" else "")
    _set_cell(sheet_data, "G19", "X" if data.metodo_ensayo == "B" else "")
    _set_cell(sheet_data, "K18", "X" if data.tamiz_requerido == "3/8 in." else "")
    _set_cell(sheet_data, "K19", "X" if data.tamiz_requerido == "No. 4" else "")

    # Masas del bloque derecho.
    _set_cell(sheet_data, "N21", data.masa_inicial_g, is_number=True)
    _set_cell(sheet_data, "N22", data.masa_seca_g, is_number=True)
    _set_cell(sheet_data, "N23", data.masa_seca_constante_g, is_number=True)

    # Tabla gradacion (filas 26..31).
    grad_rows = data.gradacion_rows[:6]
    for idx, row in enumerate(grad_rows):
        r = 26 + idx
        _set_cell(sheet_data, f"D{r}", row.masa_retenido_original_g, is_number=True)
        _set_cell(sheet_data, f"F{r}", row.porcentaje_retenido, is_number=True)
        _set_cell(sheet_data, f"H{r}", "X" if row.criterio_acepta else "", force_black_bold=True)
        _set_cell(sheet_data, f"I{r}", row.numero_particulas_aprox_100, is_number=True)
        _set_cell(sheet_data, f"K{r}", row.masa_retenido_g, is_number=True)

    total_original = sum((row.masa_retenido_original_g or 0.0) for row in grad_rows)
    total_pct = sum((row.porcentaje_retenido or 0.0) for row in grad_rows)
    total_reduccion = sum((row.masa_retenido_g or 0.0) for row in grad_rows)
    if total_original > 0:
        _set_cell(sheet_data, "D32", round(total_original, 4), is_number=True)
    if total_pct > 0:
        _set_cell(sheet_data, "F32", round(total_pct, 4), is_number=True)
    if total_reduccion > 0:
        _set_cell(sheet_data, "K32", round(total_reduccion, 4), is_number=True)

    # Tabla metodo A/B (filas 39..44)
    metodo_rows = data.metodo_rows[:6]
    for idx, row in enumerate(metodo_rows):
        r = 39 + idx
        _set_cell(sheet_data, f"C{r}", row.grupo1_numero_particulas, is_number=True)
        _set_cell(sheet_data, f"E{r}", row.grupo1_masa_g, is_number=True)
        _set_cell(sheet_data, f"G{r}", row.grupo2_numero_particulas, is_number=True)
        _set_cell(sheet_data, f"I{r}", row.grupo2_masa_g, is_number=True)
        _set_cell(sheet_data, f"K{r}", row.grupo3_numero_particulas, is_number=True)
        _set_cell(sheet_data, f"M{r}", row.grupo3_masa_g, is_number=True)
        _set_cell(sheet_data, f"O{r}", row.grupo4_numero_particulas, is_number=True)
        _set_cell(sheet_data, f"Q{r}", row.grupo4_masa_g, is_number=True)

    # Equipos.
    _set_cell(sheet_data, "G47", data.dispositivo_calibre_codigo, force_black_bold=True)
    _set_cell(sheet_data, "M47", data.balanza_01g_codigo, force_black_bold=True)
    _set_cell(sheet_data, "G48", data.horno_codigo, force_black_bold=True)

    # Nota.
    _set_cell(sheet_data, "D49", data.nota or "", force_black_bold=True)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: PlanasRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_planas_excel(data: PlanasRequest) -> bytes:
    """Generate Planas Excel file from template."""
    logger.info("Generating Planas Excel - ASTM D4791-19")

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
