
"""Excel generator for PH.

ZIP/XML strategy to preserve styles, merged cells and drawings from template.
"""

from __future__ import annotations

import io
import logging
from app.modules.common.excel_xml import find_template_path
import os
import zipfile
from pathlib import Path
from typing import Any

from app.utils.http_client import http_get
from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes

from .schemas import PHRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"





def _fetch_template_from_storage(filename: str) -> bytes | None:
    bucket = os.getenv("SUPABASE_TEMPLATES_BUCKET")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not bucket or not supabase_url or not supabase_key:
        return None

    template_key = f"{filename}"
    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{template_key}"
    try:
        resp = http_get(
            url,
            headers={"Authorization": f"Bearer {supabase_key}"},
            timeout=20,
            request_name="supabase.ph.template_fetch",
        )
        if resp.status_code == 200:
            return resp.content
        logger.warning("Template download failed: %s (%s)", filename, resp.status_code)
    except Exception:
        logger.exception("Template download error: %s", filename)
    return None


def _get_template_bytes(filename: str) -> bytes:
    local_path = find_template_path(filename)
    if local_path.exists():
        return local_path.read_bytes()

    storage_bytes = _fetch_template_from_storage(filename)
    if storage_bytes:
        return storage_bytes

    raise FileNotFoundError(f"Template {filename} not found")


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


def _resolve_sheet_and_drawing_paths(zin: zipfile.ZipFile, sheet_name: str) -> tuple[str | None, str | None]:
    try:
        workbook_xml = zin.read("xl/workbook.xml")
        rels_xml = zin.read("xl/_rels/workbook.xml.rels")
    except KeyError:
        return None, None

    wb_root = etree.fromstring(workbook_xml)
    ns = {
        "main": NS_SHEET,
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    rel_id: str | None = None
    for sheet in wb_root.findall("main:sheets/main:sheet", ns):
        if sheet.get("name") == sheet_name:
            rel_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            break
    if not rel_id:
        return None, None

    rel_root = etree.fromstring(rels_xml)
    rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    sheet_target: str | None = None
    for rel in rel_root.findall("rel:Relationship", rel_ns):
        if rel.get("Id") == rel_id:
            sheet_target = rel.get("Target")
            break
    if not sheet_target:
        return None, None

    sheet_path = f"xl/{sheet_target.lstrip('/')}"

    sheet_rels_name = Path(sheet_target).name + ".rels"
    sheet_rels_path = f"xl/worksheets/_rels/{sheet_rels_name}"
    if sheet_rels_path not in zin.namelist():
        return sheet_path, None

    try:
        sheet_rels_xml = zin.read(sheet_rels_path)
    except KeyError:
        return sheet_path, None

    sheet_rels_root = etree.fromstring(sheet_rels_xml)
    drawing_target: str | None = None
    for rel in sheet_rels_root.findall("rel:Relationship", rel_ns):
        rel_type = rel.get("Type", "")
        if rel_type.endswith("/drawing"):
            drawing_target = rel.get("Target")
            break

    if not drawing_target:
        return sheet_path, None

    clean_target = drawing_target.lstrip("/")
    while clean_target.startswith("../"):
        clean_target = clean_target[3:]
    drawing_path = f"xl/{clean_target}"
    return sheet_path, drawing_path


def _fill_sheet(sheet_xml: bytes, data: PHRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    payload_dict = data.model_dump(mode="json")

    # Encabezado (row 11)
    _set_cell(sd, "B11", data.muestra)
    _set_cell(sd, "D11", data.numero_ot)
    _set_cell(sd, "E11", data.fecha_ensayo)
    _set_cell(sd, "G11", data.realizado_por)

    # Set metadata cells on the right (Column L)
    _set_cell(sd, "L2", data.cliente or payload_dict.get("cliente") or "")
    _set_cell(sd, "L3", payload_dict.get("direccion") or "")
    _set_cell(sd, "L4", payload_dict.get("proyecto") or "")
    _set_cell(sd, "L5", payload_dict.get("ubicacion") or "")
    _set_cell(sd, "L7", payload_dict.get("recepcion_n") or payload_dict.get("numero_recepcion") or "")
    _set_cell(sd, "L8", payload_dict.get("fecha_emision") or "")
    _set_cell(sd, "L9", payload_dict.get("ot_n") or data.numero_ot or "")
    _set_cell(sd, "L11", payload_dict.get("codigo_muestra") or "")
    _set_cell(sd, "L12", payload_dict.get("fecha_recepcion") or "")
    _set_cell(sd, "L13", data.fecha_ensayo or payload_dict.get("fecha_ejecucion") or "")
    _set_cell(sd, "L15", payload_dict.get("cantera_sondaje") or payload_dict.get("cantera") or "")
    _set_cell(sd, "L16", payload_dict.get("numero_muestra") or "")
    _set_cell(sd, "L17", payload_dict.get("tipo_muestra") or "")

    # Resultados principales (rows 24-25) - inyectar en F (celda fusionada F:G)
    _set_cell(sd, "F24", data.temperatura_ensayo_c, is_number=True)
    _set_cell(sd, "F25", data.ph_resultado, is_number=True)

    # Equipos (rows 36-38)
    _set_cell(sd, "E36", data.equipo_horno_codigo)
    _set_cell(sd, "E37", data.equipo_balanza_001_codigo)
    _set_cell(sd, "E38", data.equipo_ph_metro_codigo)

    # Observaciones (row 31)
    if data.observaciones:
        _set_cell(sd, "A31", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _inject_shape_text(anchor: etree._Element, text: str, ns: dict[str, str]) -> None:
    """Inject text into a shape's txBody."""
    txBody = anchor.find(".//xdr:txBody", ns)
    if txBody is None:
        return
    
    # Clear existing paragraphs
    for p in list(txBody.findall(".//a:p", ns)):
        txBody.remove(p)
    
    # Create new paragraph with text
    p = etree.SubElement(txBody, f"{{{NS_A}}}p")
    r = etree.SubElement(p, f"{{{NS_A}}}r")
    rPr = etree.SubElement(r, f"{{{NS_A}}}rPr")
    rPr.set("lang", "es-PE")
    rPr.set("sz", "1100")
    
    t = etree.SubElement(r, f"{{{NS_A}}}t")
    t.text = text
    
    # Add end para props
    endParaRPr = etree.SubElement(p, f"{{{NS_A}}}endParaRPr")
    endParaRPr.set("lang", "es-PE")
    endParaRPr.set("sz", "1100")


def _fill_drawing(drawing_xml: bytes, data: PHRequest) -> bytes:
    ns = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)
    
    # Find shapes in condiciones area and inject text
    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        from_elem = anchor.find(".//xdr:from", ns)
        to_elem = anchor.find(".//xdr:to", ns)
        if from_elem is None or to_elem is None:
            continue
        
        from_row_elem = from_elem.find("xdr:row", ns)
        from_col_elem = from_elem.find("xdr:col", ns)
        to_row_elem = to_elem.find("xdr:row", ns)
        if from_row_elem is None or from_col_elem is None or to_row_elem is None:
            continue
        
        from_row = int(from_row_elem.text)
        from_col = int(from_col_elem.text)
        to_row = int(to_row_elem.text)
        
        # Shape row 15-16, col 4 (E-F) = valor SECADO AL AIRE
        if from_row == 15 and to_row == 16 and from_col == 4 and data.condicion_secado_aire:
            _inject_shape_text(anchor, data.condicion_secado_aire, ns)
        
        # Shape row 16-18, col 4 (E-F) = valor SECADO EN HORNO
        elif from_row == 16 and to_row == 18 and from_col == 4 and data.condicion_secado_horno:
            _inject_shape_text(anchor, data.condicion_secado_horno, ns)
    
    # Apply footer shapes (revisado/aprobado)
    modified_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return fill_standard_footer_shapes(
        modified_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_ph_excel(payload: PHRequest) -> bytes:
    """
    Generate PH Excel from template with data injection.
    """
    logger.info("Generating PH Excel - NTP 339.176")

    template_bytes = _get_template_bytes("1-INF.-N-001-26-SU03-PH-V01.xlsx")

    in_zip = zipfile.ZipFile(io.BytesIO(template_bytes), "r")
    out_buffer = io.BytesIO()
    out_zip = zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED)

    sheet_path, drawing_path = _resolve_sheet_and_drawing_paths(in_zip, "FORMATO")
    if sheet_path is None:
        logger.warning("Sheet FORMATO not found in template, falling back to sheet1.xml")
        sheet_path = "xl/worksheets/sheet1.xml"

    for item in in_zip.infolist():
        data_bytes = in_zip.read(item.filename)

        if item.filename == sheet_path:
            data_bytes = _fill_sheet(data_bytes, payload)
        elif drawing_path and item.filename == drawing_path:
            data_bytes = _fill_drawing(data_bytes, payload)
        elif item.filename == "xl/calcChain.xml":
            continue

        out_zip.writestr(item, data_bytes)

    out_zip.close()
    in_zip.close()

    return out_buffer.getvalue()