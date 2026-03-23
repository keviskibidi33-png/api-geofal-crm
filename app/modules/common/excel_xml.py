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


def transform_template_sheet(
    template_filename: str,
    sheet_name: str,
    transform: Callable[[bytes], bytes],
) -> bytes:
    template_bytes = get_template_bytes(template_filename)
    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        sheet_path = resolve_sheet_path(zin, sheet_name)
        if sheet_path is None:
            raise FileNotFoundError(f"Sheet {sheet_name} not found in {template_filename}")

        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue

            raw = zin.read(item.filename)
            if item.filename == sheet_path:
                raw = transform(raw)
            zout.writestr(item, raw)

    output.seek(0)
    return output.read()

