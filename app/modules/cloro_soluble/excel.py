"""Excel generator for Cloro Soluble (ZIP/XML strategy)."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Iterable

import requests
from lxml import etree

from .schemas import CloroSolubleRequest, CloroSolubleResultado

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

SHEET_NAME = "CLOR"
SECADO_AIRE_BOUNDS = (4, 15, 5, 16)
SECADO_HORNO_BOUNDS = (4, 16, 5, 18)
SIG_REVISADO_BOUNDS = (1, 43, 4, 47)
SIG_APROBADO_BOUNDS = (4, 43, 7, 47)


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


def _col_num_to_letter(num: int) -> str:
    result = ""
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def _build_merge_anchor_map(root: etree._Element) -> dict[str, str]:
    anchor_map: dict[str, str] = {}
    merge_cells = root.find(f".//{{{NS_SHEET}}}mergeCells")
    if merge_cells is None:
        return anchor_map

    for merge_cell in merge_cells.findall(f"{{{NS_SHEET}}}mergeCell"):
        ref = merge_cell.get("ref")
        if not ref:
            continue
        if ":" not in ref:
            anchor_map[ref] = ref
            continue

        start_ref, end_ref = ref.split(":", 1)
        start_col, start_row = _parse_cell_ref(start_ref)
        end_col, end_row = _parse_cell_ref(end_ref)
        start_col_num = _col_letter_to_num(start_col)
        end_col_num = _col_letter_to_num(end_col)
        anchor_ref = f"{start_col}{start_row}"

        for row_num in range(start_row, end_row + 1):
            for col_num in range(start_col_num, end_col_num + 1):
                anchor_map[f"{_col_num_to_letter(col_num)}{row_num}"] = anchor_ref

    return anchor_map


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
    *,
    is_number: bool = False,
    merge_anchor_map: dict[str, str] | None = None,
) -> None:
    if value is None:
        return

    target_ref = merge_anchor_map.get(ref, ref) if merge_anchor_map else ref
    _, row_num = _parse_cell_ref(target_ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, target_ref)

    style = cell.get("s")
    for child in list(cell):
        cell.remove(child)

    if is_number:
        cell.attrib.pop("t", None)
        val = etree.SubElement(cell, f"{{{NS_SHEET}}}v")
        val.text = str(value)
    else:
        text_value = str(value)
        if text_value == "":
            cell.attrib.pop("t", None)
            if style:
                cell.set("s", style)
            return
        cell.set("t", "inlineStr")
        is_el = etree.SubElement(cell, f"{{{NS_SHEET}}}is")
        t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
        if "\n" in text_value or text_value.startswith(" ") or text_value.endswith(" "):
            t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t_el.text = text_value

    if style:
        cell.set("s", style)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_number_list(values: Iterable[Any] | None, length: int) -> list[float | None]:
    result: list[float | None] = [None] * length
    if not values:
        return result
    for idx, item in enumerate(list(values)[:length]):
        result[idx] = _to_float(item)
    return result


def _build_labeled_footer_text(label: str, name: str | None, date_text: str | None) -> str:
    name_value = (name or "").strip()
    date_value = (date_text or "").strip()
    if not name_value and not date_value:
        return ""
    return f"{label}: {name_value}\nFecha: {date_value}"


def _get_anchor_bounds(anchor: etree._Element) -> tuple[int, int, int, int] | None:
    ns = {"xdr": NS_DRAW}
    from_el = anchor.find("xdr:from", ns)
    to_el = anchor.find("xdr:to", ns)
    if from_el is None or to_el is None:
        return None

    def _read_int(parent: etree._Element, tag: str) -> int | None:
        value_el = parent.find(f"xdr:{tag}", ns)
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


def _set_anchor_value_text(anchor: etree._Element, value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False

    ns = {"xdr": NS_DRAW, "a": NS_A}
    tx_body = anchor.find(".//xdr:txBody", ns)
    if tx_body is None:
        return False

    run_tag = f"{{{NS_A}}}r"
    run_props_tag = f"{{{NS_A}}}rPr"
    text_tag = f"{{{NS_A}}}t"
    end_para_tag = f"{{{NS_A}}}endParaRPr"
    paragraph_tag = f"{{{NS_A}}}p"

    template_end_para: etree._Element | None = None
    for paragraph in tx_body.findall("a:p", ns):
        end_para = paragraph.find("a:endParaRPr", ns)
        if end_para is not None:
            template_end_para = etree.fromstring(etree.tostring(end_para))
            break

    for paragraph in list(tx_body.findall("a:p", ns)):
        tx_body.remove(paragraph)

    for line in text.split("\n"):
        paragraph = etree.SubElement(tx_body, paragraph_tag)
        run = etree.SubElement(paragraph, run_tag)
        run_props = etree.SubElement(run, run_props_tag)

        if template_end_para is not None:
            for attr, attr_val in template_end_para.attrib.items():
                run_props.set(attr, attr_val)
            for style_child in template_end_para:
                run_props.append(etree.fromstring(etree.tostring(style_child)))
        else:
            run_props.set("lang", "es-PE")
            run_props.set("sz", "900")

        t_el = etree.SubElement(run, text_tag)
        if line.startswith(" ") or line.endswith(" "):
            t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t_el.text = line

        if template_end_para is not None:
            paragraph.append(etree.fromstring(etree.tostring(template_end_para)))
        else:
            end_para = etree.SubElement(paragraph, end_para_tag)
            end_para.set("lang", "es-PE")
            end_para.set("sz", "900")
    return True


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


def _fill_sheet(sheet_xml: bytes, payload: CloroSolubleRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = _build_merge_anchor_map(root)
    data = payload.model_dump(mode="json")

    _set_cell(sheet_data, "B10", payload.muestra, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "D10", payload.numero_ot, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "E10", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G10", payload.realizado_por or "", merge_anchor_map=merge_anchor_map)

    _set_cell(sheet_data, "G22", _to_float(data.get("volumen_agua_ml")), is_number=True, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G23", _to_float(data.get("peso_suelo_seco_g")), is_number=True, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G24", _to_float(data.get("alicuota_tomada_ml")), is_number=True, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G25", _to_float(data.get("titulacion_suelo_g")), is_number=True, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G26", _to_float(data.get("titulacion_nitrato_plata")), is_number=True, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G27", _to_float(data.get("ph_ensayo")), is_number=True, merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G28", _to_float(data.get("factor_dilucion")), is_number=True, merge_anchor_map=merge_anchor_map)

    resultados = list(payload.resultados or [])
    while len(resultados) < 2:
        resultados.append(CloroSolubleResultado())

    resultado_refs = (("G29", "G30"), ("H29", "H30"))
    for idx, refs in enumerate(resultado_refs):
        resultado = resultados[idx] if idx < len(resultados) else None
        if resultado is None:
            continue
        _set_cell(sheet_data, refs[0], resultado.mililitros_solucion_usada, is_number=True, merge_anchor_map=merge_anchor_map)
        _set_cell(sheet_data, refs[1], resultado.contenido_cloruros_ppm, is_number=True, merge_anchor_map=merge_anchor_map)

    if payload.observaciones:
        _set_cell(sheet_data, "A35", payload.observaciones, merge_anchor_map=merge_anchor_map)

    _set_cell(sheet_data, "G40", data.get("equipo_horno_codigo") or "", merge_anchor_map=merge_anchor_map)
    _set_cell(sheet_data, "G41", data.get("equipo_balanza_001_codigo") or "", merge_anchor_map=merge_anchor_map)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, payload: CloroSolubleRequest) -> bytes:
    data = payload.model_dump(mode="json")
    secado_aire = (data.get("condicion_secado_aire") or "").strip()
    secado_horno = (data.get("condicion_secado_horno") or "").strip()
    revisado_text = _build_labeled_footer_text("Revisado", payload.revisado_por, payload.revisado_fecha)
    aprobado_text = _build_labeled_footer_text("Aprobado", payload.aprobado_por, payload.aprobado_fecha)

    if not any([secado_aire, secado_horno, revisado_text, aprobado_text]):
        return drawing_xml

    root = etree.fromstring(drawing_xml)
    ns = {"xdr": NS_DRAW}

    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        bounds = _get_anchor_bounds(anchor)
        if bounds == SECADO_AIRE_BOUNDS and secado_aire:
            _set_anchor_value_text(anchor, secado_aire)
        elif bounds == SECADO_HORNO_BOUNDS and secado_horno:
            _set_anchor_value_text(anchor, secado_horno)
        elif bounds == SIG_REVISADO_BOUNDS and revisado_text:
            _set_anchor_value_text(anchor, revisado_text)
        elif bounds == SIG_APROBADO_BOUNDS and aprobado_text:
            _set_anchor_value_text(anchor, aprobado_text)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_cloro_soluble_excel(payload: CloroSolubleRequest) -> bytes:
    """Generate Excel from template preserving styles, merges and drawings."""
    template_bytes = _get_template_bytes("Template_Cloro_Soluble.xlsx")

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, \
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:

        sheet_path, drawing_path = _resolve_sheet_and_drawing_paths(zin, SHEET_NAME)
        if sheet_path is None:
            logger.warning("Sheet %s not found in template, falling back to sheet2.xml", SHEET_NAME)
            sheet_path = "xl/worksheets/sheet2.xml"

        for item in zin.infolist():
            raw = zin.read(item.filename)

            if item.filename == sheet_path:
                raw = _fill_sheet(raw, payload)

            if drawing_path and item.filename == drawing_path:
                raw = _fill_drawing(raw, payload)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
