
"""Excel generator for PH.

ZIP/XML strategy to preserve styles, merged cells and drawings from template.
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Any

import requests
from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes

from .schemas import PHRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _find_template_path(filename: str) -> Path:
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]

    candidates = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _fetch_template_from_storage(filename: str) -> bytes | None:
    bucket = os.getenv("SUPABASE_TEMPLATES_BUCKET")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not bucket or not supabase_url or not supabase_key:
        return None

    template_key = f"{filename}"
    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{template_key}"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {supabase_key}"}, timeout=20)
        if resp.status_code == 200:
            return resp.content
        logger.warning("Template download failed: %s (%s)", filename, resp.status_code)
    except Exception:
        logger.exception("Template download error: %s", filename)
    return None


def _get_template_bytes(filename: str) -> bytes:
    local_path = _find_template_path(filename)
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


def _fill_sheet(sheet_xml: bytes, data: PHRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado (row 11)
    _set_cell(sd, "B11", data.muestra)
    _set_cell(sd, "D11", data.numero_ot)
    _set_cell(sd, "E11", data.fecha_ensayo)
    _set_cell(sd, "G11", data.realizado_por)

    # Condiciones de secado (rows 17-18) - ahora se inyectan en shapes, no en celdas
    # Las condiciones se renderizarán en los shapes del drawing

    # Resultados principales (rows 24-25) - inyectar en F (celda fusionada F:G)
    _set_cell(sd, "F24", data.temperatura_ensayo_c, is_number=True)
    _set_cell(sd, "F25", data.ph_resultado, is_number=True)

    # Equipos (rows 36-38)
    _set_cell(sd, "E36", data.equipo_horno_codigo)
    _set_cell(sd, "E37", data.equipo_balanza_001_codigo)
    _set_cell(sd, "E38", data.equipo_ph_metro_codigo)

    # Observaciones (row 32)
    if data.observaciones:
        _set_cell(sd, "A32", data.observaciones)

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

    template_bytes = _get_template_bytes("Template_PH.xlsx")

    in_zip = zipfile.ZipFile(io.BytesIO(template_bytes), "r")
    out_buffer = io.BytesIO()
    out_zip = zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED)

    for item in in_zip.infolist():
        data_bytes = in_zip.read(item.filename)

        if item.filename == "xl/worksheets/sheet2.xml":
            data_bytes = _fill_sheet(data_bytes, payload)
        elif item.filename == "xl/drawings/drawing2.xml":
            data_bytes = _fill_drawing(data_bytes, payload)
        elif item.filename == "xl/calcChain.xml":
            continue

        out_zip.writestr(item, data_bytes)

    out_zip.close()
    in_zip.close()

    return out_buffer.getvalue()
