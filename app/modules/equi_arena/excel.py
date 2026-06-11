"""
Excel generator for Equivalente de Arena (ASTM D2419-22).

ZIP/XML strategy to preserve styles, merged cells and drawings from the
official template.
"""

from __future__ import annotations

import io
import logging
from app.modules.common.excel_xml import find_template_path
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes

from .schemas import EquiArenaRequest, _compute_equivalente_por_prueba

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
TRIAL_COLS = ["H", "I", "J"]


TEMPLATE_PATH = str(find_template_path("Template_EquiArena.xlsx"))


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


def _set_trial_row(sheet_data: etree._Element, row_num: int, values: list[Any | None], is_number: bool = True) -> None:
    for idx, col in enumerate(TRIAL_COLS):
        _set_cell(sheet_data, f"{col}{row_num}", values[idx], is_number=is_number)


def _remove_calc_chain_relationships(rels_xml: bytes) -> bytes:
    root = etree.fromstring(rels_xml)
    for rel in list(root):
        rel_type = rel.get("Type", "")
        target = rel.get("Target", "")
        if rel_type.endswith("/calcChain") or target.endswith("calcChain.xml"):
            root.remove(rel)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _remove_calc_chain_content_type(content_types_xml: bytes) -> bytes:
    root = etree.fromstring(content_types_xml)
    for override in list(root):
        part_name = override.get("PartName", "")
        if part_name == "/xl/calcChain.xml":
            root.remove(override)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_sheet(sheet_xml: bytes, data: EquiArenaRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado (row 10 en FORMATO)
    _set_cell(sd, "B10", data.muestra)
    _set_cell(sd, "D10", data.numero_ot)
    _set_cell(sd, "F10", data.fecha_ensayo)
    _set_cell(sd, "H10", data.realizado_por)

    # Condiciones
    if data.tipo_muestra != "-":
        _set_cell(sd, "B17", data.tipo_muestra)

    if data.metodo_agitacion != "-":
        _set_cell(sd, "F17", data.metodo_agitacion)

    if data.preparacion_muestra != "-":
        _set_cell(sd, "F21", data.preparacion_muestra)

    _set_cell(sd, "J16", data.temperatura_solucion_c, is_number=True)
    _set_cell(sd, "D20", data.masa_4_medidas_g, is_number=True)

    # Pruebas (columnas H, I, J)
    _set_trial_row(sd, 26, data.cronometro_entrada_saturacion_hmin, is_number=False)
    _set_trial_row(sd, 27, data.cronometro_salida_saturacion_hmin, is_number=False)
    _set_trial_row(sd, 28, data.tiempo_saturacion_min)
    _set_trial_row(sd, 29, data.tiempo_agitacion_seg)
    _set_trial_row(sd, 30, data.cronometro_entrada_decantacion_hmin, is_number=False)
    _set_trial_row(sd, 31, data.cronometro_salida_decantacion_hmin, is_number=False)
    _set_trial_row(sd, 32, data.tiempo_decantacion_min)
    _set_trial_row(sd, 33, data.lectura_arcilla_in)
    _set_trial_row(sd, 34, data.lectura_arena_in)
    _set_trial_row(sd, 35, _compute_equivalente_por_prueba(data.lectura_arcilla_in, data.lectura_arena_in))
    _set_cell(sd, "H36", data.equivalente_arena_promedio_pct, is_number=True)

    # Equipos y observaciones
    _set_cell(sd, "D39", data.equipo_balanza_01g_codigo)
    _set_cell(sd, "D40", data.equipo_horno_110_codigo)
    _set_cell(sd, "D41", data.equipo_equivalente_arena_codigo)
    _set_cell(sd, "D42", data.equipo_agitador_ea_codigo)
    _set_cell(sd, "D43", data.equipo_termometro_codigo)
    _set_cell(sd, "D44", data.equipo_tamiz_no4_codigo)
    if data.observaciones:
        _set_cell(sd, "F39", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: EquiArenaRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def _fill_datos_sheet(sheet_xml: bytes, data: EquiArenaRequest) -> bytes:
    """Llena la hoja 'Datos' con las lecturas y el operador."""
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Operador en L2 (columna de OPERADORES)
    _set_cell(sd, "L2", data.realizado_por)

    # Pruebas (columnas G, H, I)
    # Row 6-12: Cronómetros y tiempos
    _set_cell(sd, "G6", data.cronometro_entrada_saturacion_hmin[0], is_number=False)
    _set_cell(sd, "H6", data.cronometro_entrada_saturacion_hmin[1], is_number=False)
    _set_cell(sd, "I6", data.cronometro_entrada_saturacion_hmin[2], is_number=False)

    _set_cell(sd, "G7", data.cronometro_salida_saturacion_hmin[0], is_number=False)
    _set_cell(sd, "H7", data.cronometro_salida_saturacion_hmin[1], is_number=False)
    _set_cell(sd, "I7", data.cronometro_salida_saturacion_hmin[2], is_number=False)

    _set_cell(sd, "G8", data.tiempo_saturacion_min[0], is_number=True)
    _set_cell(sd, "H8", data.tiempo_saturacion_min[1], is_number=True)
    _set_cell(sd, "I8", data.tiempo_saturacion_min[2], is_number=True)

    _set_cell(sd, "G9", data.tiempo_agitacion_seg[0], is_number=True)
    _set_cell(sd, "H9", data.tiempo_agitacion_seg[1], is_number=True)
    _set_cell(sd, "I9", data.tiempo_agitacion_seg[2], is_number=True)

    _set_cell(sd, "G10", data.cronometro_entrada_decantacion_hmin[0], is_number=False)
    _set_cell(sd, "H10", data.cronometro_entrada_decantacion_hmin[1], is_number=False)
    _set_cell(sd, "I10", data.cronometro_entrada_decantacion_hmin[2], is_number=False)

    _set_cell(sd, "G11", data.cronometro_salida_decantacion_hmin[0], is_number=False)
    _set_cell(sd, "H11", data.cronometro_salida_decantacion_hmin[1], is_number=False)
    _set_cell(sd, "I11", data.cronometro_salida_decantacion_hmin[2], is_number=False)

    _set_cell(sd, "G12", data.tiempo_decantacion_min[0], is_number=True)
    _set_cell(sd, "H12", data.tiempo_decantacion_min[1], is_number=True)
    _set_cell(sd, "I12", data.tiempo_decantacion_min[2], is_number=True)

    # Row 13-16: Lecturas y equivalente (valores numéricos)
    _set_cell(sd, "G13", data.lectura_arcilla_in[0], is_number=True)
    _set_cell(sd, "H13", data.lectura_arcilla_in[1], is_number=True)
    _set_cell(sd, "I13", data.lectura_arcilla_in[2], is_number=True)

    _set_cell(sd, "G14", data.lectura_arena_in[0], is_number=True)
    _set_cell(sd, "H14", data.lectura_arena_in[1], is_number=True)
    _set_cell(sd, "I14", data.lectura_arena_in[2], is_number=True)

    equivalente = _compute_equivalente_por_prueba(data.lectura_arcilla_in, data.lectura_arena_in)
    _set_cell(sd, "G15", equivalente[0], is_number=True)
    _set_cell(sd, "H15", equivalente[1], is_number=True)
    _set_cell(sd, "I15", equivalente[2], is_number=True)

    _set_cell(sd, "G16", data.equivalente_arena_promedio_pct, is_number=True)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_informe_sheet(sheet_xml: bytes, data: EquiArenaRequest) -> bytes:
    """Llena la hoja 'INFORME' con las lecturas de arcilla, arena y equivalente."""
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    equivalente = _compute_equivalente_por_prueba(data.lectura_arcilla_in, data.lectura_arena_in)

    # Row 21: Lectura de la arcilla (I21, J21, K21)
    _set_cell(sd, "I21", data.lectura_arcilla_in[0], is_number=True)
    _set_cell(sd, "J21", data.lectura_arcilla_in[1], is_number=True)
    _set_cell(sd, "K21", data.lectura_arcilla_in[2], is_number=True)

    # Row 22: Lectura de la arena (I22, J22, K22)
    _set_cell(sd, "I22", data.lectura_arena_in[0], is_number=True)
    _set_cell(sd, "J22", data.lectura_arena_in[1], is_number=True)
    _set_cell(sd, "K22", data.lectura_arena_in[2], is_number=True)

    # Row 23: Equivalente arena % (I23, J23, K23)
    _set_cell(sd, "I23", equivalente[0], is_number=True)
    _set_cell(sd, "J23", equivalente[1], is_number=True)
    _set_cell(sd, "K23", equivalente[2], is_number=True)

    # Row 24: Equivalente de Arena promedio % (I24-K24 fusionado)
    _set_cell(sd, "I24", data.equivalente_arena_promedio_pct, is_number=True)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_balanza_sheet(sheet_xml: bytes, data: EquiArenaRequest) -> bytes:
    """Preserva la hoja 'Balanza' sin modificar datos (las fórmulas calculan desde DATOS)."""
    return sheet_xml


def _fill_incertidumbre(sheet_xml: bytes, data: EquiArenaRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    # remove sheetProtection if present
    for sp in list(root.findall(f".//{{{NS_SHEET}}}sheetProtection")):
        parent = sp.getparent()
        if parent is not None:
            parent.remove(sp)

    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    def _excel_date_serial(value: str | None) -> float | None:
        text = (value or "").strip()
        if not text:
            return None
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                return float((parsed - date(1899, 12, 30)).days)
            except ValueError:
                continue
        return None

    _set_cell(sd, "B55", data.revisado_por)
    _set_cell(sd, "G55", data.aprobado_por)
    revisado_serial = _excel_date_serial(data.revisado_fecha)
    aprobado_serial = _excel_date_serial(data.aprobado_fecha)
    if revisado_serial is not None:
        _set_cell(sd, "B57", revisado_serial, is_number=True)
    elif data.revisado_fecha:
        _set_cell(sd, "B57", data.revisado_fecha)
    if aprobado_serial is not None:
        _set_cell(sd, "G57", aprobado_serial, is_number=True)
    elif data.aprobado_fecha:
        _set_cell(sd, "G57", data.aprobado_fecha)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_equi_arena_excel(data: EquiArenaRequest) -> bytes:
    """Generates the EquiArena Excel file from template."""
    logger.info("Generating EquiArena Excel - ASTM D2419-22")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        # Pre-fill sheets
        sheet_original = zin.read("xl/worksheets/sheet1.xml")
        sheet_xml = _fill_sheet(sheet_original, data)

        informe_xml = None
        try:
            raw_informe = zin.read("xl/worksheets/sheet2.xml")
            informe_xml = _fill_informe_sheet(raw_informe, data)
        except KeyError:
            informe_xml = None

        datos_xml = None
        try:
            raw_datos = zin.read("xl/worksheets/sheet3.xml")
            datos_xml = _fill_datos_sheet(raw_datos, data)
        except KeyError:
            datos_xml = None

        balanza_xml = None
        try:
            raw_balanza = zin.read("xl/worksheets/sheet5.xml")
            balanza_xml = _fill_balanza_sheet(raw_balanza, data)
        except KeyError:
            balanza_xml = None

        incert_xml = None
        try:
            raw_incert = zin.read("xl/worksheets/sheet4.xml")
            incert_xml = _fill_incertidumbre(raw_incert, data)
        except KeyError:
            incert_xml = None

        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue

            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet_xml
            elif item.filename == "xl/worksheets/sheet2.xml" and informe_xml is not None:
                raw = informe_xml
            elif item.filename == "xl/worksheets/sheet3.xml" and datos_xml is not None:
                raw = datos_xml
            elif item.filename == "xl/worksheets/sheet4.xml" and incert_xml is not None:
                raw = incert_xml
            elif item.filename == "xl/worksheets/sheet5.xml" and balanza_xml is not None:
                raw = balanza_xml
            elif item.filename == "xl/_rels/workbook.xml.rels":
                raw = _remove_calc_chain_relationships(zin.read(item.filename))
            elif item.filename == "[Content_Types].xml":
                raw = _remove_calc_chain_content_type(zin.read(item.filename))
            else:
                raw = zin.read(item.filename)

            if item.filename.startswith("xl/drawings/drawing") and item.filename.endswith(".xml"):
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()