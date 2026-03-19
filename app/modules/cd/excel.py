
"""Excel generator for CD."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Any

import requests
from lxml import etree

from .schemas import CDRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
SHEET_PATH = "xl/worksheets/sheet1.xml"
WORKBOOK_PATH = "xl/workbook.xml"

HEADER_CELLS = {
    "muestra": "B11",
    "numero_ot": "D11",
    "fecha_ensayo": "F11",
}
PESO_CELLS = ("B16", "D16", "F16")
ESF_NORMAL_CELLS = ("B17", "D17", "F17")
DEF_HORIZONTAL_COLUMNS = ("B", "D", "F")
CARGA_COLUMNS = ("C", "E", "G")
HUMEDAD_COLUMNS = ("E", "F", "G")
HUMEDAD_FIELD_ROWS = {
    "recipiente_numero": 46,
    "peso_recipiente_g": 47,
    "peso_recipiente_suelo_humedo_g": 48,
    "peso_recipiente_suelo_seco_g": 49,
    "peso_agua_g": 50,
    "peso_suelo_g": 51,
    "contenido_humedad_pct": 52,
}
HORA_COLUMNS = (
    ("B", "C"),
    ("D", "E"),
    ("F", "G"),
)
FIRMA_CELLS = {
    "realizado_por": "B62",
    "revisado_por": "D62",
    "aprobado_por": "F62",
}


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
    col = "".join(char for char in ref if char.isalpha())
    row = int("".join(char for char in ref if char.isdigit()))
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
    existing = row.findall(f"{{{NS_SHEET}}}c")
    insert_pos = None
    for idx, cell in enumerate(existing):
        existing_col, _ = _parse_cell_ref(cell.get("r", ""))
        if col_num < _col_letter_to_num(existing_col):
            insert_pos = idx
            break

    cell = etree.Element(f"{{{NS_SHEET}}}c")
    cell.set("r", cell_ref)
    if insert_pos is None:
        row.append(cell)
    else:
        row.insert(insert_pos, cell)
    return cell


def _set_cell(sheet_data: etree._Element, ref: str, value: Any, is_number: bool = False) -> None:
    if value is None:
        return

    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    style = cell.get("s")

    for child in list(cell):
        cell.remove(child)

    text_value = str(value)
    if text_value == "":
        cell.attrib.pop("t", None)
        if style:
            cell.set("s", style)
        return

    if is_number:
        cell.attrib.pop("t", None)
        value_node = etree.SubElement(cell, f"{{{NS_SHEET}}}v")
        value_node.text = text_value
    else:
        cell.set("t", "inlineStr")
        inline_string = etree.SubElement(cell, f"{{{NS_SHEET}}}is")
        text_node = etree.SubElement(inline_string, f"{{{NS_SHEET}}}t")
        text_node.text = text_value

    if style:
        cell.set("s", style)


def _force_full_calc_on_open(workbook_xml: bytes) -> bytes:
    root = etree.fromstring(workbook_xml)
    calc = root.find(f".//{{{NS_SHEET}}}calcPr")
    if calc is None:
        calc = etree.SubElement(root, f"{{{NS_SHEET}}}calcPr")
    calc.set("fullCalcOnLoad", "1")
    calc.set("calcOnSave", "1")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _write_header(sheet_data: etree._Element, payload: CDRequest) -> None:
    _set_cell(sheet_data, HEADER_CELLS["muestra"], payload.muestra)
    _set_cell(sheet_data, HEADER_CELLS["numero_ot"], payload.numero_ot)
    _set_cell(sheet_data, HEADER_CELLS["fecha_ensayo"], payload.fecha_ensayo)


def _write_condiciones(sheet_data: etree._Element, payload: CDRequest) -> None:
    for idx, ref in enumerate(PESO_CELLS):
        value = payload.peso_kg[idx] if idx < len(payload.peso_kg) else None
        _set_cell(sheet_data, ref, value, is_number=True)

    for idx, ref in enumerate(ESF_NORMAL_CELLS):
        value = payload.esf_normal[idx] if idx < len(payload.esf_normal) else None
        _set_cell(sheet_data, ref, value, is_number=True)

    def_values = payload.def_horizontal or []
    carga_sets = [payload.carga_kg_1, payload.carga_kg_2, payload.carga_kg_3]
    for offset, row_num in enumerate(range(20, 45)):
        def_value = def_values[offset] if offset < len(def_values) else None
        for col in DEF_HORIZONTAL_COLUMNS:
            _set_cell(sheet_data, f"{col}{row_num}", def_value, is_number=True)

        for col_idx, col in enumerate(CARGA_COLUMNS):
            carga_values = carga_sets[col_idx]
            value = carga_values[offset] if offset < len(carga_values) else None
            _set_cell(sheet_data, f"{col}{row_num}", value, is_number=True)


def _write_humedad(sheet_data: etree._Element, payload: CDRequest) -> None:
    for point_idx, point in enumerate(payload.humedad_puntos[:3]):
        col = HUMEDAD_COLUMNS[point_idx]
        for field_name, row_num in HUMEDAD_FIELD_ROWS.items():
            value = getattr(point, field_name, None)
            is_number = field_name != "recipiente_numero"
            _set_cell(sheet_data, f"{col}{row_num}", value, is_number=is_number)


def _write_horas(sheet_data: etree._Element, payload: CDRequest) -> None:
    hora_sets = [payload.hora_1, payload.hora_2, payload.hora_3]
    deform_sets = [payload.deform_1, payload.deform_2, payload.deform_3]

    for row_offset, row_num in enumerate(range(55, 60)):
        for idx, (hora_col, deform_col) in enumerate(HORA_COLUMNS):
            horas = hora_sets[idx]
            deformaciones = deform_sets[idx]
            hora = horas[row_offset] if row_offset < len(horas) else None
            deformacion = deformaciones[row_offset] if row_offset < len(deformaciones) else None
            _set_cell(sheet_data, f"{hora_col}{row_num}", hora)
            _set_cell(sheet_data, f"{deform_col}{row_num}", deformacion, is_number=True)


def _write_firmas(sheet_data: etree._Element, payload: CDRequest) -> None:
    _set_cell(sheet_data, FIRMA_CELLS["realizado_por"], payload.realizado_por)
    _set_cell(sheet_data, FIRMA_CELLS["revisado_por"], payload.revisado_por)
    _set_cell(sheet_data, FIRMA_CELLS["aprobado_por"], payload.aprobado_por)


def _fill_sheet(sheet_xml: bytes, payload: CDRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    _write_header(sheet_data, payload)
    _write_condiciones(sheet_data, payload)
    _write_humedad(sheet_data, payload)
    _write_horas(sheet_data, payload)
    _write_firmas(sheet_data, payload)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_cd_excel(payload: CDRequest) -> bytes:
    """Generate Excel from template preserving layout and media assets."""

    template_bytes = _get_template_bytes("Template_CD.xlsx")
    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            raw = zin.read(item.filename)

            if item.filename == SHEET_PATH:
                raw = _fill_sheet(raw, payload)
            elif item.filename == WORKBOOK_PATH:
                raw = _force_full_calc_on_open(raw)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
