"""Excel generator for Compresion No Confinada (ZIP/XML strategy)."""

from __future__ import annotations

import io
import logging
import math
import os
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

import requests
from lxml import etree

from .schemas import CompresionNoConfinadaRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

SHEET_NAME = "CNC (2)"

SIG_REVISADO_BOUNDS = (1, 53, 3, 56)  # col,row,col,row (0-based) from drawing2.xml
SIG_APROBADO_BOUNDS = (3, 53, 5, 56)
ARIAL_SOURCE_STYLE_IDS = (25, 36, 42, 43, 52, 69, 90)


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


def _set_cell(
    sheet_data: etree._Element,
    ref: str,
    value: Any,
    is_number: bool = False,
    style_overrides: dict[int, int] | None = None,
) -> None:
    if value is None:
        return

    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    style = cell.get("s")
    if style and style_overrides:
        try:
            style_id = int(style)
        except ValueError:
            style_id = None
        if style_id is not None and style_id in style_overrides:
            style = str(style_overrides[style_id])
    for child in list(cell):
        cell.remove(child)

    text_value = str(value)
    if text_value == "":
        if "t" in cell.attrib:
            del cell.attrib["t"]
        if style:
            cell.set("s", style)
        return

    if is_number:
        cell.attrib.pop("t", None)
        val = etree.SubElement(cell, f"{{{NS_SHEET}}}v")
        val.text = text_value
    else:
        cell.set("t", "inlineStr")
        is_el = etree.SubElement(cell, f"{{{NS_SHEET}}}is")
        t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
        t_el.text = text_value

    if style:
        cell.set("s", style)


def _ensure_arial_styles(styles_xml: bytes, source_style_ids: Iterable[int]) -> tuple[bytes, dict[int, int]]:
    root = etree.fromstring(styles_xml)
    fonts_el = root.find(f".//{{{NS_SHEET}}}fonts")
    cell_xfs = root.find(f".//{{{NS_SHEET}}}cellXfs")
    if fonts_el is None or cell_xfs is None:
        return styles_xml, {}

    fonts = fonts_el.findall(f"{{{NS_SHEET}}}font")
    xfs = cell_xfs.findall(f"{{{NS_SHEET}}}xf")
    font_map: dict[int, int] = {}
    style_map: dict[int, int] = {}

    def _serialize(node: etree._Element) -> bytes:
        return etree.tostring(node, encoding="utf-8")

    font_lookup = {_serialize(font): idx for idx, font in enumerate(fonts)}
    xf_lookup = {_serialize(xf): idx for idx, xf in enumerate(xfs)}

    for source_style_id in source_style_ids:
        if source_style_id >= len(xfs):
            continue

        source_xf = xfs[source_style_id]
        try:
            source_font_id = int(source_xf.get("fontId", "0"))
        except ValueError:
            source_font_id = 0
        if source_font_id >= len(fonts):
            continue

        source_font = fonts[source_font_id]
        font_name_el = source_font.find(f"{{{NS_SHEET}}}name")
        if font_name_el is not None and font_name_el.get("val") == "Arial":
            style_map[source_style_id] = source_style_id
            continue

        if source_font_id in font_map:
            new_font_id = font_map[source_font_id]
        else:
            new_font = deepcopy(source_font)
            name_el = new_font.find(f"{{{NS_SHEET}}}name")
            if name_el is None:
                name_el = etree.SubElement(new_font, f"{{{NS_SHEET}}}name")
            name_el.set("val", "Arial")

            signature = _serialize(new_font)
            existing_font_id = font_lookup.get(signature)
            if existing_font_id is not None:
                new_font_id = existing_font_id
            else:
                new_font_id = len(fonts)
                fonts_el.append(new_font)
                fonts.append(new_font)
                fonts_el.set("count", str(len(fonts)))
                font_lookup[signature] = new_font_id
            font_map[source_font_id] = new_font_id

        new_xf = deepcopy(source_xf)
        new_xf.set("fontId", str(new_font_id))
        new_xf.set("applyFont", "1")
        xf_signature = _serialize(new_xf)
        existing_style_id = xf_lookup.get(xf_signature)
        if existing_style_id is not None:
            style_map[source_style_id] = existing_style_id
            continue

        new_style_id = len(xfs)
        cell_xfs.append(new_xf)
        xfs.append(new_xf)
        cell_xfs.set("count", str(len(xfs)))
        xf_lookup[xf_signature] = new_style_id
        style_map[source_style_id] = new_style_id

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), style_map


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float, decimals: int = 4) -> float:
    return round(value, decimals)


def _normalize_list(values: Iterable[Any] | None, length: int) -> list[float | None]:
    result: list[float | None] = [None] * length
    if not values:
        return result
    for idx, item in enumerate(list(values)[:length]):
        result[idx] = _to_float(item)
    return result


def _format_number_text(value: float | None, decimals: int = 4) -> str:
    if value is None:
        return ""
    rounded = round(float(value), decimals)
    text = f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def _build_signature_text(name: str | None, date_text: str | None) -> str:
    name_value = (name or "").strip()
    date_value = (date_text or "").strip()
    if name_value and date_value:
        return f"{name_value} / {date_value}"
    return name_value or date_value


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
    paragraph = anchor.find(".//xdr:txBody/a:p", ns)
    if paragraph is None:
        return False

    run_tag = f"{{{NS_A}}}r"
    field_tag = f"{{{NS_A}}}fld"
    break_tag = f"{{{NS_A}}}br"
    run_props_tag = f"{{{NS_A}}}rPr"
    text_tag = f"{{{NS_A}}}t"

    for child in list(paragraph):
        if child.tag in (run_tag, field_tag, break_tag):
            paragraph.remove(child)

    end_para = paragraph.find("a:endParaRPr", ns)
    run = etree.Element(run_tag)
    run_props = etree.SubElement(run, run_props_tag)

    if end_para is not None:
        for attr, attr_val in end_para.attrib.items():
            run_props.set(attr, attr_val)
        for style_child in end_para:
            run_props.append(etree.fromstring(etree.tostring(style_child)))
    else:
        run_props.set("lang", "es-PE")
        run_props.set("sz", "900")

    t_el = etree.SubElement(run, text_tag)
    if "\n" in text or text.endswith(" "):
        t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t_el.text = text

    if end_para is not None:
        paragraph.insert(list(paragraph).index(end_para), run)
    else:
        paragraph.append(run)
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


def _fill_sheet(
    sheet_xml: bytes,
    payload: CompresionNoConfinadaRequest,
    style_overrides: dict[int, int] | None = None,
) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    data = payload.model_dump(mode="json")

    merge_cells = root.find(f".//{{{NS_SHEET}}}mergeCells")
    if merge_cells is not None:
        existing = {mc.get("ref") for mc in merge_cells.findall(f"{{{NS_SHEET}}}mergeCell")}
        for row in range(18, 24):
            ref = f"F{row}:H{row}"
            if ref not in existing:
                mc = etree.SubElement(merge_cells, f"{{{NS_SHEET}}}mergeCell")
                mc.set("ref", ref)

    # Encabezado
    _set_cell(sheet_data, "B11", payload.muestra, style_overrides=style_overrides)
    _set_cell(sheet_data, "D11", payload.numero_ot, style_overrides=style_overrides)
    _set_cell(sheet_data, "E11", payload.fecha_ensayo, style_overrides=style_overrides)
    if payload.realizado_por:
        _set_cell(sheet_data, "F11", payload.realizado_por, style_overrides=style_overrides)

    tara_numero = data.get("tara_numero")
    tara_humedo = _to_float(data.get("tara_suelo_humedo_g"))
    tara_seco = _to_float(data.get("tara_suelo_seco_g"))
    peso_tara = _to_float(data.get("peso_tara_g"))

    peso_agua = _to_float(data.get("peso_agua_g"))
    if peso_agua is None and tara_humedo is not None and tara_seco is not None:
        peso_agua = _round(tara_humedo - tara_seco)

    peso_suelo_seco = _to_float(data.get("peso_suelo_seco_g"))
    if peso_suelo_seco is None and tara_seco is not None and peso_tara is not None:
        peso_suelo_seco = _round(tara_seco - peso_tara)

    humedad_pct = _to_float(data.get("humedad_pct"))
    if humedad_pct is None and peso_agua is not None and peso_suelo_seco:
        humedad_pct = _round((peso_agua / peso_suelo_seco) * 100, 3)

    # Contenido de humedad (col C)
    _set_cell(sheet_data, "C17", tara_numero, style_overrides=style_overrides)
    _set_cell(sheet_data, "C18", _format_number_text(tara_humedo, 3), style_overrides=style_overrides)
    _set_cell(sheet_data, "C19", _format_number_text(tara_seco, 3), style_overrides=style_overrides)
    _set_cell(sheet_data, "C20", _format_number_text(peso_agua, 3), style_overrides=style_overrides)
    _set_cell(sheet_data, "C21", _format_number_text(peso_tara, 3), style_overrides=style_overrides)
    _set_cell(sheet_data, "C22", _format_number_text(peso_suelo_seco, 3), style_overrides=style_overrides)
    _set_cell(sheet_data, "C23", _format_number_text(humedad_pct, 3), style_overrides=style_overrides)

    diametros = _normalize_list(data.get("diametro_cm"), 3)
    alturas = _normalize_list(data.get("altura_cm"), 3)
    areas = _normalize_list(data.get("area_cm2"), 3)
    volumenes = _normalize_list(data.get("volumen_cm3"), 3)
    pesos = _normalize_list(data.get("peso_gr"), 3)
    unit_humedo = _normalize_list(data.get("p_unitario_humedo"), 3)
    unit_seco = _normalize_list(data.get("p_unitario_seco"), 3)

    for idx in range(3):
        if areas[idx] is None and diametros[idx] is not None:
            areas[idx] = _round((math.pi * diametros[idx] ** 2) / 4)
        if volumenes[idx] is None and areas[idx] is not None and alturas[idx] is not None:
            volumenes[idx] = _round(areas[idx] * alturas[idx])
        if unit_humedo[idx] is None and pesos[idx] is not None and volumenes[idx]:
            unit_humedo[idx] = _round(pesos[idx] / volumenes[idx])
        if unit_seco[idx] is None and unit_humedo[idx] is not None and humedad_pct is not None:
            unit_seco[idx] = _round(unit_humedo[idx] / (1 + humedad_pct / 100))

    value_cols = ["F", "G", "H"]
    rows = {
        "diametro": 17,
        "altura": 18,
        "area": 19,
        "volumen": 20,
        "peso": 21,
        "unit_humedo": 22,
        "unit_seco": 23,
    }

    for idx, col in enumerate(value_cols):
        _set_cell(sheet_data, f"{col}{rows['diametro']}", _format_number_text(diametros[idx], 4), style_overrides=style_overrides)

    _set_cell(sheet_data, f"F{rows['altura']}", _format_number_text(alturas[0], 4), style_overrides=style_overrides)
    _set_cell(sheet_data, f"F{rows['area']}", _format_number_text(areas[0], 4), style_overrides=style_overrides)
    _set_cell(sheet_data, f"F{rows['volumen']}", _format_number_text(volumenes[0], 4), style_overrides=style_overrides)
    _set_cell(sheet_data, f"F{rows['peso']}", _format_number_text(pesos[0], 4), style_overrides=style_overrides)
    _set_cell(sheet_data, f"F{rows['unit_humedo']}", _format_number_text(unit_humedo[0], 4), style_overrides=style_overrides)
    _set_cell(sheet_data, f"F{rows['unit_seco']}", _format_number_text(unit_seco[0], 4), style_overrides=style_overrides)

    tiempos = list(data.get("deformacion_tiempo") or [])[:24]
    deformacion_pulg = _normalize_list(data.get("deformacion_pulg_001"), 24)
    deformacion_mm = _normalize_list(data.get("deformacion_mm"), 24)
    lectura = _normalize_list(data.get("lectura_carga_kg"), 24)
    for idx in range(24):
        row = 27 + idx
        tiempo = tiempos[idx] if idx < len(tiempos) else ""
        _set_cell(sheet_data, f"B{row}", tiempo, style_overrides=style_overrides)
        _set_cell(sheet_data, f"C{row}", _format_number_text(deformacion_pulg[idx], 3), style_overrides=style_overrides)
        _set_cell(sheet_data, f"D{row}", _format_number_text(deformacion_mm[idx], 3), style_overrides=style_overrides)
        _set_cell(sheet_data, f"E{row}", _format_number_text(lectura[idx], 3), style_overrides=style_overrides)

    if payload.observaciones:
        _set_cell(sheet_data, "B52", payload.observaciones, style_overrides=style_overrides)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, payload: CompresionNoConfinadaRequest) -> bytes:
    revisado_text = _build_signature_text(payload.revisado_por, payload.revisado_fecha)
    aprobado_text = _build_signature_text(payload.aprobado_por, payload.aprobado_fecha)
    if not revisado_text and not aprobado_text:
        return drawing_xml

    root = etree.fromstring(drawing_xml)
    ns = {"xdr": NS_DRAW}

    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        bounds = _get_anchor_bounds(anchor)
        if bounds == SIG_REVISADO_BOUNDS and revisado_text:
            _set_anchor_value_text(anchor, revisado_text)
        elif bounds == SIG_APROBADO_BOUNDS and aprobado_text:
            _set_anchor_value_text(anchor, aprobado_text)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_compresion_no_confinada_excel(payload: CompresionNoConfinadaRequest) -> bytes:
    """
    Generate Excel from template preserving shapes and merged cells.
    """
    template_bytes = _get_template_bytes("Template_Compresion_No_Confinada.xlsx")

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, \
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:

        sheet_path, drawing_path = _resolve_sheet_and_drawing_paths(zin, SHEET_NAME)
        if sheet_path is None:
            logger.warning("Sheet %s not found in template, falling back to sheet2.xml", SHEET_NAME)
            sheet_path = "xl/worksheets/sheet2.xml"

        try:
            styles_xml = zin.read("xl/styles.xml")
            modified_styles_xml, style_overrides = _ensure_arial_styles(styles_xml, ARIAL_SOURCE_STYLE_IDS)
        except KeyError:
            modified_styles_xml, style_overrides = None, {}

        for item in zin.infolist():
            raw = zin.read(item.filename)

            if item.filename == sheet_path:
                raw = _fill_sheet(raw, payload, style_overrides=style_overrides)

            if modified_styles_xml is not None and item.filename == "xl/styles.xml":
                raw = modified_styles_xml

            if drawing_path and item.filename == drawing_path:
                raw = _fill_drawing(raw, payload)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
