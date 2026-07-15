from __future__ import annotations

import io
import re
import logging
import zipfile
from datetime import datetime, timedelta
from typing import Any
from lxml import etree

from app.modules.common.excel_xml import (
    NS_SHEET,
    build_merge_anchor_map,
    set_cell,
    enable_full_recalc_on_open,
    remove_calc_chain_relationships,
    remove_calc_chain_content_type,
    remove_external_link_relationships,
    remove_external_link_content_types,
    strip_external_references,
    find_template_path,
)
from app.modules.huanta_probetas.models import HuantaProbeta
from app.modules.huanta_compresion.models import HuantaCompresion

logger = logging.getLogger(__name__)


def _safe_float(val: Any) -> float | None:
    if val is None or str(val).strip() == "" or str(val).strip() == "-":
        return None
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None or str(val).strip() == "" or str(val).strip() == "-":
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def _parse_fc(codigo: str) -> int:
    """Extract f'c value from a LEM code string."""
    if not codigo:
        return 210
    # Try finding -210- or -280-
    match = re.search(r'-(\d{3})-', codigo)
    if match:
        return int(match.group(1))
    # Fallback to search any 3-digit number in string
    match_any = re.search(r'\b(\d{3})\b', codigo)
    if match_any:
        return int(match_any.group(1))
    return 210


def _get_fc_value(probeta: HuantaProbeta) -> int:
    """Get the f'c value preferring the direct f_c field over parsing the LEM code."""
    fc_raw = (probeta.f_c or "").strip().replace("-", "").strip()
    if fc_raw:
        try:
            return int(float(fc_raw))
        except (ValueError, TypeError):
            pass
    return _parse_fc(probeta.codigo_muestra_lem or "")


def _date_str_to_excel_serial(date_str: str) -> int | None:
    """Convert a date string (YYYY/MM/DD or YYYY-MM-DD) to an Excel serial number.
    Excel serial 1 = 1900-01-01, represented as days since 1899-12-30.
    """
    if not date_str:
        return None
    clean = date_str.split("T")[0].strip().replace("-", "/")
    for fmt in ("%Y/%m/%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(clean, fmt)
            delta = dt - datetime(1899, 12, 30)
            return delta.days
        except ValueError:
            continue
    return None


def _clear_row_data_cells(
    sheet_data: Any,
    row_number: int,
    columns: tuple[str, ...]
) -> None:
    """Remove the value element from specific cells in a template row to clear stale data."""
    ns = NS_SHEET
    for row_elem in sheet_data:
        if row_elem.get("r") == str(row_number):
            for cell in row_elem.findall(f"{{{ns}}}c"):
                col_ref = ''.join(ch for ch in (cell.get("r") or "") if ch.isalpha())
                if col_ref in columns:
                    v = cell.find(f"{{{ns}}}v")
                    if v is not None:
                        cell.remove(v)
                    # Reset type to avoid leftover shared-string index
                    if cell.get("t") in ("s", "n"):
                        cell.set("t", "str")
            break


def _parse_date_str(val: str) -> str:
    if not val:
        return ""
    # Remove time part if exists
    clean = val.split("T")[0].strip()
    # Normalize YYYY-MM-DD to YYYY/MM/DD
    clean = clean.replace("-", "/")
    return clean


def generate_huanta_probetas_list_excel(rows: list[HuantaProbeta]) -> bytes:
    """Generates excel for Huanta Probetas list using 1. Control de probetas Huanta.xlsx template."""
    template_path = find_template_path("Proyecto Huantar/Control Hunta/1. Control de probetas Huanta.xlsx")
    if not template_path.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_path}")

    with open(template_path, "rb") as f:
        template_bytes = f.read()

    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue
            if item.filename.startswith("xl/externalLinks/"):
                continue

            raw = zin.read(item.filename)

            if item.filename == "xl/worksheets/sheet1.xml":
                root = etree.fromstring(raw)
                sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
                if sheet_data is not None:
                    merge_anchor_map = build_merge_anchor_map(root)
                    for idx, row in enumerate(rows):
                        row_idx = 5 + idx
                        fc_val = _parse_fc(row.codigo_muestra_lem)
                        
                        set_cell(sheet_data, f"B{row_idx}", idx + 1, is_number=True, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"C{row_idx}", row.codigo_probeta, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"D{row_idx}", row.sigla or "HHTA", merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"E{row_idx}", row.elemento or "-", merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"F{row_idx}", row.detalle_elemento or "-", merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"G{row_idx}", fc_val, is_number=True, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"H{row_idx}", _parse_date_str(row.fecha_moldeo), merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"I{row_idx}", row.edad, is_number=True, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"J{row_idx}", _parse_date_str(row.fecha_rotura), merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"K{row_idx}", row.codigo_muestra_lem or "", merge_anchor_map=merge_anchor_map)
                raw = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

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


def generate_huanta_compresion_list_excel(rows: list[HuantaCompresion]) -> bytes:
    """Generates excel for Huanta Compresion list using 2. Formato compresion Huanta.xlsx template."""
    template_path = find_template_path("Proyecto Huantar/Compresion Huanta/2. Formato compresion Huanta.xlsx")
    if not template_path.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_path}")

    with open(template_path, "rb") as f:
        template_bytes = f.read()

    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue
            if item.filename.startswith("xl/externalLinks/"):
                continue

            raw = zin.read(item.filename)

            if item.filename == "xl/worksheets/sheet1.xml":
                root = etree.fromstring(raw)
                sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
                if sheet_data is not None:
                    merge_anchor_map = build_merge_anchor_map(root)
                    for idx, row in enumerate(rows):
                        row_idx = 5 + idx
                        d1 = _safe_float(row.diam_1)
                        d2 = _safe_float(row.diam_2)
                        l1 = _safe_float(row.long_1)
                        l2 = _safe_float(row.long_2)
                        l3 = _safe_float(row.long_3)
                        carga = _safe_float(row.carga_maxima)
                        fractura = _safe_int(row.tipo_fractura)

                        set_cell(sheet_data, f"B{row_idx}", idx + 1, is_number=True, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"C{row_idx}", row.codigo_probeta, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"D{row_idx}", _parse_date_str(row.fecha_rotura), merge_anchor_map=merge_anchor_map)
                        
                        if d1 is not None:
                            set_cell(sheet_data, f"E{row_idx}", d1, is_number=True, merge_anchor_map=merge_anchor_map)
                        if d2 is not None:
                            set_cell(sheet_data, f"F{row_idx}", d2, is_number=True, merge_anchor_map=merge_anchor_map)
                        if l1 is not None:
                            set_cell(sheet_data, f"G{row_idx}", l1, is_number=True, merge_anchor_map=merge_anchor_map)
                        if l2 is not None:
                            set_cell(sheet_data, f"H{row_idx}", l2, is_number=True, merge_anchor_map=merge_anchor_map)
                        if l3 is not None:
                            set_cell(sheet_data, f"I{row_idx}", l3, is_number=True, merge_anchor_map=merge_anchor_map)
                        if carga is not None:
                            set_cell(sheet_data, f"J{row_idx}", carga, is_number=True, merge_anchor_map=merge_anchor_map)
                        if fractura is not None:
                            set_cell(sheet_data, f"K{row_idx}", fractura, is_number=True, merge_anchor_map=merge_anchor_map)
                raw = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

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


def generate_huanta_report_excel(
    probetas: list[HuantaProbeta],
    compresiones: list[HuantaCompresion],
    realizado_por: str
) -> bytes:
    """Generates the unified final report (up to 3 probetas) using 1-Inf-N-000-26-CO12-COM-V04.xlsx template."""
    template_path = find_template_path("Proyecto Huantar/Probetas export Huanta/1-Inf-N-000-26-CO12-COM-V04.xlsx")
    if not template_path.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_path}")

    with open(template_path, "rb") as f:
        template_bytes = f.read()

    output = io.BytesIO()

    # Build a lookup dict for compression records
    comp_map = {c.probeta_id: c for c in compresiones}

    _RESUMEN_DATA_COLS = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L")
    _DATOS_DATA_ROWS = (20, 21, 22)
    _RESUMEN_DATA_ROWS = (14, 15, 16)

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue
            if item.filename.startswith("xl/externalLinks/"):
                continue

            raw = zin.read(item.filename)

            # ── Hoja RESUMEN (sheet1.xml) ───────────────────────────────────────
            if item.filename == "xl/worksheets/sheet1.xml":
                root = etree.fromstring(raw)
                sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
                if sheet_data is not None:
                    merge_anchor_map = build_merge_anchor_map(root)

                    # Clear ALL template data rows upfront (rows 14-16)
                    for rnum in _RESUMEN_DATA_ROWS:
                        _clear_row_data_cells(sheet_data, rnum, _RESUMEN_DATA_COLS)

                    # Inject one row per selected probeta (up to 3)
                    for idx, probeta in enumerate(probetas[:3]):
                        row_idx = 14 + idx
                        comp = comp_map.get(probeta.id)
                        fc_val = _get_fc_value(probeta)

                        set_cell(sheet_data, f"A{row_idx}", probeta.codigo_muestra_lem or "", merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"B{row_idx}", probeta.detalle_elemento or "-", merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, f"C{row_idx}", fc_val, is_number=True, merge_anchor_map=merge_anchor_map)

                        moldeo_serial = _date_str_to_excel_serial(probeta.fecha_moldeo)
                        rotura_serial = _date_str_to_excel_serial(probeta.fecha_rotura)
                        if moldeo_serial is not None:
                            set_cell(sheet_data, f"D{row_idx}", moldeo_serial, is_number=True, merge_anchor_map=merge_anchor_map)
                        if rotura_serial is not None:
                            set_cell(sheet_data, f"E{row_idx}", rotura_serial, is_number=True, merge_anchor_map=merge_anchor_map)

                        if comp:
                            d1 = _safe_float(comp.diam_1)
                            d2 = _safe_float(comp.diam_2)
                            l1 = _safe_float(comp.long_1)
                            l2 = _safe_float(comp.long_2)
                            l3 = _safe_float(comp.long_3)
                            carga = _safe_float(comp.carga_maxima)
                            fractura = _safe_int(comp.tipo_fractura)

                            if d1 is not None:
                                set_cell(sheet_data, f"F{row_idx}", d1, is_number=True, merge_anchor_map=merge_anchor_map)
                            if d2 is not None:
                                set_cell(sheet_data, f"G{row_idx}", d2, is_number=True, merge_anchor_map=merge_anchor_map)
                            if l1 is not None:
                                set_cell(sheet_data, f"H{row_idx}", l1, is_number=True, merge_anchor_map=merge_anchor_map)
                            if l2 is not None:
                                set_cell(sheet_data, f"I{row_idx}", l2, is_number=True, merge_anchor_map=merge_anchor_map)
                            if l3 is not None:
                                set_cell(sheet_data, f"J{row_idx}", l3, is_number=True, merge_anchor_map=merge_anchor_map)
                            if carga is not None:
                                set_cell(sheet_data, f"K{row_idx}", carga, is_number=True, merge_anchor_map=merge_anchor_map)
                            if fractura is not None:
                                set_cell(sheet_data, f"L{row_idx}", fractura, is_number=True, merge_anchor_map=merge_anchor_map)

                raw = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

            # ── Hoja DATOS (sheet4.xml) ─────────────────────────────────────────
            elif item.filename == "xl/worksheets/sheet4.xml":
                root = etree.fromstring(raw)
                sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
                if sheet_data is not None:
                    merge_anchor_map = build_merge_anchor_map(root)

                    # Cabecera DATOS: use the first probeta's data
                    if probetas:
                        first = probetas[0]
                        fc_val = _get_fc_value(first)
                        set_cell(sheet_data, "C9", first.detalle_elemento or "-", merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, "C10", fc_val, is_number=True, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, "C11", _parse_date_str(first.fecha_moldeo), merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, "C13", _parse_date_str(first.fecha_rotura), merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, "C15", first.edad, is_number=True, merge_anchor_map=merge_anchor_map)
                        set_cell(sheet_data, "L9", realizado_por or "-", merge_anchor_map=merge_anchor_map)

                    # Fill up to 3 probeta rows starting at row 20
                    for idx, probeta in enumerate(probetas[:3]):
                        row_idx = 20 + idx
                        comp = comp_map.get(probeta.id)

                        set_cell(sheet_data, f"B{row_idx}", probeta.codigo_muestra_lem or "", merge_anchor_map=merge_anchor_map)

                        if comp:
                            d1 = _safe_float(comp.diam_1)
                            d2 = _safe_float(comp.diam_2)
                            l1 = _safe_float(comp.long_1)
                            l2 = _safe_float(comp.long_2)
                            l3 = _safe_float(comp.long_3)
                            carga = _safe_float(comp.carga_maxima)
                            fractura = _safe_int(comp.tipo_fractura)

                            if d1 is not None:
                                set_cell(sheet_data, f"D{row_idx}", d1, is_number=True, merge_anchor_map=merge_anchor_map)
                            if d2 is not None:
                                set_cell(sheet_data, f"E{row_idx}", d2, is_number=True, merge_anchor_map=merge_anchor_map)
                            if l1 is not None:
                                set_cell(sheet_data, f"F{row_idx}", l1, is_number=True, merge_anchor_map=merge_anchor_map)
                            if l2 is not None:
                                set_cell(sheet_data, f"G{row_idx}", l2, is_number=True, merge_anchor_map=merge_anchor_map)
                            if l3 is not None:
                                set_cell(sheet_data, f"H{row_idx}", l3, is_number=True, merge_anchor_map=merge_anchor_map)
                            if carga is not None:
                                set_cell(sheet_data, f"I{row_idx}", carga, is_number=True, merge_anchor_map=merge_anchor_map)
                            if fractura is not None:
                                set_cell(sheet_data, f"J{row_idx}", fractura, is_number=True, merge_anchor_map=merge_anchor_map)

                raw = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

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
