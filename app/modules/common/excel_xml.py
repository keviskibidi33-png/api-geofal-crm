"""Helpers to update template sheets without destroying original workbook layout."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Callable

from app.utils.http_client import http_get
from lxml import etree

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def find_template_path(filename: str) -> Path:
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


def fetch_template_from_storage(filename: str) -> bytes | None:
    bucket = os.getenv("SUPABASE_TEMPLATES_BUCKET")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not bucket or not supabase_url or not supabase_key:
        return None

    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{filename}"
    try:
        response = http_get(
            url,
            headers={"Authorization": f"Bearer {supabase_key}"},
            timeout=20,
            request_name=f"supabase.template_fetch.{filename}",
        )
        if response.status_code == 200:
            return response.content
        logger.warning("Template download failed for %s: %s", filename, response.status_code)
    except Exception:
        logger.exception("Template download error for %s", filename)
    return None


def get_template_bytes(filename: str) -> bytes:
    local_path = find_template_path(filename)
    if local_path.exists():
        return local_path.read_bytes()

    storage_bytes = fetch_template_from_storage(filename)
    if storage_bytes:
        return storage_bytes

    raise FileNotFoundError(f"Template {filename} not found")


def parse_cell_ref(ref: str) -> tuple[str, int]:
    col = "".join(char for char in ref if char.isalpha())
    row = int("".join(char for char in ref if char.isdigit()))
    return col, row


def col_letter_to_num(col: str) -> int:
    num = 0
    for char in col.upper():
        num = num * 26 + (ord(char) - ord("A") + 1)
    return num


def col_num_to_letter(num: int) -> str:
    result = ""
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def build_merge_anchor_map(root: etree._Element) -> dict[str, str]:
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
        start_col, start_row = parse_cell_ref(start_ref)
        end_col, end_row = parse_cell_ref(end_ref)
        start_col_num = col_letter_to_num(start_col)
        end_col_num = col_letter_to_num(end_col)
        anchor_ref = f"{start_col}{start_row}"

        for row_num in range(start_row, end_row + 1):
            for col_num in range(start_col_num, end_col_num + 1):
                anchor_map[f"{col_num_to_letter(col_num)}{row_num}"] = anchor_ref

    return anchor_map


def find_or_create_row(sheet_data: etree._Element, row_num: int) -> etree._Element:
    for row in sheet_data.findall(f"{{{NS_SHEET}}}row"):
        if row.get("r") == str(row_num):
            return row
    new_row = etree.SubElement(sheet_data, f"{{{NS_SHEET}}}row")
    new_row.set("r", str(row_num))
    return new_row


def find_or_create_cell(row: etree._Element, cell_ref: str) -> etree._Element:
    for cell in row.findall(f"{{{NS_SHEET}}}c"):
        if cell.get("r") == cell_ref:
            return cell

    target_col_num = col_letter_to_num(parse_cell_ref(cell_ref)[0])
    new_cell = etree.Element(f"{{{NS_SHEET}}}c")
    new_cell.set("r", cell_ref)

    insert_at = None
    for index, existing in enumerate(row.findall(f"{{{NS_SHEET}}}c")):
        existing_col_num = col_letter_to_num(parse_cell_ref(existing.get("r"))[0])
        if target_col_num < existing_col_num:
            insert_at = index
            break

    if insert_at is None:
        row.append(new_cell)
    else:
        row.insert(insert_at, new_cell)

    return new_cell


def set_cell(
    sheet_data: etree._Element,
    ref: str,
    value: Any,
    *,
    is_number: bool = False,
    merge_anchor_map: dict[str, str] | None = None,
    style_ref: str | None = None,
) -> None:
    if value is None:
        return

    if is_number and value == "":
        return

    target_ref = merge_anchor_map.get(ref, ref) if merge_anchor_map else ref
    _, row_num = parse_cell_ref(target_ref)
    row = find_or_create_row(sheet_data, row_num)
    cell = find_or_create_cell(row, target_ref)

    style = cell.get("s")
    if style_ref:
        style_row_num = parse_cell_ref(style_ref)[1]
        style_row = find_or_create_row(sheet_data, style_row_num)
        style_cell = find_or_create_cell(style_row, style_ref)
        style = style_cell.get("s") or style

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


def resolve_sheet_path(zin: zipfile.ZipFile, sheet_name: str) -> str | None:
    try:
        workbook_xml = zin.read("xl/workbook.xml")
        rels_xml = zin.read("xl/_rels/workbook.xml.rels")
    except KeyError:
        return None

    workbook_root = etree.fromstring(workbook_xml)
    ns = {
        "main": NS_SHEET,
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    rel_id: str | None = None
    for sheet in workbook_root.findall("main:sheets/main:sheet", ns):
        if sheet.get("name") == sheet_name:
            rel_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            break
    if not rel_id:
        return None

    rels_root = etree.fromstring(rels_xml)
    rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    target: str | None = None
    for rel in rels_root.findall("rel:Relationship", rel_ns):
        if rel.get("Id") == rel_id:
            target = rel.get("Target")
            break

    if not target:
        return None

    return f"xl/{target.lstrip('/')}"


def resolve_sheet_and_drawing_paths(zin: zipfile.ZipFile, sheet_name: str) -> tuple[str | None, str | None]:
    sheet_path = resolve_sheet_path(zin, sheet_name)
    if sheet_path is None:
        return None, None

    rels_path = sheet_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
    try:
        rels_xml = zin.read(rels_path)
    except KeyError:
        return sheet_path, None

    rels_root = etree.fromstring(rels_xml)
    rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    drawing_target: str | None = None

    for rel in rels_root.findall("rel:Relationship", rel_ns):
        rel_type = rel.get("Type", "")
        if rel_type.endswith("/drawing"):
            drawing_target = rel.get("Target")
            break

    if not drawing_target:
        return sheet_path, None

    clean_target = drawing_target.lstrip("/")
    if clean_target.startswith("../"):
        clean_target = clean_target[3:]
    drawing_path = f"xl/{clean_target}"
    return sheet_path, drawing_path


def _set_paragraph_text(paragraph: etree._Element, text: str) -> None:
    ns = {"a": NS_A}
    run_tag = f"{{{NS_A}}}r"
    field_tag = f"{{{NS_A}}}fld"
    break_tag = f"{{{NS_A}}}br"
    run_props_tag = f"{{{NS_A}}}rPr"
    text_tag = f"{{{NS_A}}}t"

    first_run_props = paragraph.find("a:r/a:rPr", ns)
    end_para_props = paragraph.find("a:endParaRPr", ns)

    for child in list(paragraph):
        if child.tag in (run_tag, field_tag, break_tag):
            paragraph.remove(child)

    if not text:
        return

    run = etree.Element(run_tag)
    run_props = etree.SubElement(run, run_props_tag)

    style_source = first_run_props if first_run_props is not None else end_para_props
    if style_source is not None:
        for attr, attr_val in style_source.attrib.items():
            run_props.set(attr, attr_val)
        for style_child in style_source:
            run_props.append(etree.fromstring(etree.tostring(style_child)))
    else:
        run_props.set("lang", "es-PE")
        run_props.set("sz", "1000")

    text_node = etree.SubElement(run, text_tag)
    if "\n" in text or text.endswith(" "):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text

    end_para_props = paragraph.find("a:endParaRPr", ns)
    if end_para_props is not None:
        paragraph.insert(list(paragraph).index(end_para_props), run)
    else:
        paragraph.append(run)


def fill_footer_drawing(
    drawing_xml: bytes,
    *,
    revisado_por: str | None,
    revisado_fecha: str | None,
    aprobado_por: str | None,
    aprobado_fecha: str | None,
) -> bytes:
    has_footer = any([revisado_por, revisado_fecha, aprobado_por, aprobado_fecha])
    if not has_footer:
        return drawing_xml

    ns = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    def _fill_footer_anchor(anchor: etree._Element, role_label: str, person: str | None, footer_date: str | None) -> bool:
        paragraphs = anchor.findall(".//xdr:txBody/a:p", ns)
        if len(paragraphs) < 2:
            return False

        _set_paragraph_text(paragraphs[0], f"{role_label}: {(person or '').strip()}".rstrip())
        _set_paragraph_text(paragraphs[1], f"Fecha: {(footer_date or '').strip()}".rstrip())
        for paragraph in paragraphs[2:]:
            _set_paragraph_text(paragraph, "")
        return True

    revisado_nombre = (revisado_por or "").strip()
    revisado_fecha_text = (revisado_fecha or "").strip()
    aprobado_nombre = (aprobado_por or "").strip()
    aprobado_fecha_text = (aprobado_fecha or "").strip()

    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        all_texts = [(t.text or "").strip() for t in anchor.findall(".//a:t", ns)]
        text_blob = " ".join(all_texts)

        is_revisado = "Revisado" in text_blob
        is_aprobado = "Aprobado" in text_blob

        if not is_revisado and not is_aprobado:
            continue

        if is_revisado:
            if _fill_footer_anchor(anchor, "Revisado", revisado_nombre, revisado_fecha_text):
                continue
            replacements = {"Revisado:": revisado_nombre, "Revisado": revisado_nombre, "Fecha:": revisado_fecha_text}
        else:
            if _fill_footer_anchor(anchor, "Aprobado", aprobado_nombre, aprobado_fecha_text):
                continue
            replacements = {"Aprobado:": aprobado_nombre, "Aprobado": aprobado_nombre, "Fecha:": aprobado_fecha_text}

        for run in anchor.findall(".//a:r", ns):
            text_node = run.find("a:t", ns)
            if text_node is None or text_node.text is None:
                continue
            raw_text = text_node.text.strip()
            if raw_text in replacements and replacements[raw_text]:
                text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if raw_text.startswith("Fecha"):
                    text_node.text = f"Fecha: {replacements[raw_text]}"
                else:
                    label = "Revisado:" if is_revisado else "Aprobado:"
                    text_node.text = f"{label} {replacements[raw_text]}"

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def transform_template_sheet(
    template_filename: str,
    sheet_name: str,
    transform: Callable[[bytes], bytes],
    *,
    drawing_transform: Callable[[bytes], bytes] | None = None,
) -> bytes:
    template_bytes = get_template_bytes(template_filename)
    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        sheet_path, drawing_path = resolve_sheet_and_drawing_paths(zin, sheet_name)
        if sheet_path is None:
            raise FileNotFoundError(f"Sheet {sheet_name} not found in {template_filename}")

        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue

            raw = zin.read(item.filename)
            if item.filename == sheet_path:
                raw = transform(raw)
            elif drawing_transform and drawing_path and item.filename == drawing_path:
                raw = drawing_transform(raw)
            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
