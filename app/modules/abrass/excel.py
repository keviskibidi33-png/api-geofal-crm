"""
Excel generator for ABRASS (ASTM C131/C131M-20).

ZIP/XML strategy to preserve styles, merged cells and drawings from the
official template.
"""

from __future__ import annotations

import io
import logging
from app.modules.common.excel_xml import (
    enable_full_recalc_on_open,
    remove_calc_chain_content_type,
    remove_calc_chain_relationships,
    remove_external_link_content_types,
    remove_external_link_relationships,
    strip_external_references,
    find_template_path,
)
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes

from .schemas import AbrassRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

TAMIZ_ROWS = [29, 30, 31, 32, 33, 34, 35]
ITEM_ROWS = [41, 42, 43, 44, 45, 46, 47]


TEMPLATE_PATH = str(find_template_path("Template_ABRA.xlsx"))


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


def _excel_date_serial(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime, date
            parsed = datetime.strptime(text, fmt).date()
            return float((parsed - date(1899, 12, 30)).days)
        except ValueError:
            continue
    return None


def _get_reception_metadata(db: Any, sample_code: str, ot_code: str) -> dict[str, str]:
    metadata = {
        "cliente": "",
        "direccion": "",
        "proyecto": "",
        "ubicacion": "",
        "numero_recepcion": "",
        "fecha_recepcion": "",
        "cantera": "",
        "muestra_nombre": "",
        "tipo_muestra": "",
    }
    if not db:
        return metadata
    try:
        from app.modules.recepcion.models import MuestraConcreto, RecepcionMuestra
        from sqlalchemy import or_
        sample_clean = sample_code.strip()
        muestra_db = db.query(MuestraConcreto).filter(
            or_(
                MuestraConcreto.codigo_muestra_lem == sample_clean,
                MuestraConcreto.codigo_muestra == sample_clean,
                MuestraConcreto.identificacion_muestra == sample_clean,
            )
        ).first()
        recepcion = None
        if muestra_db:
            recepcion = muestra_db.recepcion_parent
            metadata["muestra_nombre"] = muestra_db.identificacion_muestra or ""
            metadata["tipo_muestra"] = muestra_db.elemento or "AGREGADO"
        if not recepcion and ot_code:
            recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_ot == ot_code.strip()).first()
        if not recepcion:
            from app.modules.tracing.service import TracingService
            base_num = TracingService._extraer_numero_base(sample_clean)
            if base_num:
                res = TracingService._buscar_recepcion_flexible(db, base_num)
                if res:
                    recepcion, _ = res
        if recepcion:
            metadata["cliente"] = recepcion.cliente or ""
            metadata["direccion"] = recepcion.domicilio_legal or ""
            metadata["proyecto"] = recepcion.proyecto or ""
            metadata["ubicacion"] = recepcion.ubicacion or ""
            metadata["numero_recepcion"] = recepcion.numero_recepcion or ""
            if recepcion.fecha_recepcion:
                metadata["fecha_recepcion"] = recepcion.fecha_recepcion.strftime("%Y/%m/%d")
    except Exception as exc:
        logger.warning("Error fetching reception metadata: %s", exc)
    return metadata


def _fill_sheet(sheet_xml: bytes, data: AbrassRequest, metadata: dict[str, str]) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado
    _set_cell(sd, "C11", data.muestra)
    _set_cell(sd, "E11", data.numero_ot)
    _set_cell(sd, "F11", data.fecha_ensayo)
    _set_cell(sd, "G11", data.realizado_por)

    # Inyectar en Columna N (Mapeo a sheet FORMATO para que el INFORME lo lea vía fórmulas)
    _set_cell(sd, "N2", metadata["cliente"])
    _set_cell(sd, "N3", metadata["direccion"])
    _set_cell(sd, "N4", metadata["proyecto"])
    _set_cell(sd, "N5", metadata["ubicacion"])
    _set_cell(sd, "N7", metadata["numero_recepcion"])
    _set_cell(sd, "N8", data.fecha_ensayo)  # F. Emisión
    _set_cell(sd, "N9", data.numero_ot)
    _set_cell(sd, "N11", data.muestra)
    _set_cell(sd, "N12", metadata["fecha_recepcion"])
    _set_cell(sd, "N13", data.fecha_ensayo)
    _set_cell(sd, "N15", metadata["cantera"])
    _set_cell(sd, "N16", metadata["muestra_nombre"] or data.muestra)
    _set_cell(sd, "N17", metadata["tipo_muestra"] or "AGREGADO")

    # Muestra de prueba antes del fraccionamiento
    _set_cell(sd, "E17", data.masa_muestra_inicial_g, is_number=True)
    _set_cell(sd, "E18", data.masa_muestra_inicial_seca_despues_lavado_g, is_number=True)
    _set_cell(sd, "E19", data.masa_muestra_inicial_seca_constante_despues_lavado_g, is_number=True)
    _set_cell(sd, "H19", data.numero_revoluciones, is_number=True)

    # Marcado SI/NO en la fila de casilla (fila 18)
    _set_cell(sd, "G18", "")
    _set_cell(sd, "H18", "")
    if data.requiere_lavado == "SI":
        _set_cell(sd, "G18", "X")
    elif data.requiere_lavado == "NO":
        _set_cell(sd, "H18", "X")

    # Tabla TAMIZ (filas 29-35), gradaciones A/B/C/D (E/F/G/H)
    for idx, row_num in enumerate(TAMIZ_ROWS):
        _set_cell(sd, f"E{row_num}", data.gradacion_a_tamiz_g[idx], is_number=True)
        _set_cell(sd, f"F{row_num}", data.gradacion_b_tamiz_g[idx], is_number=True)
        _set_cell(sd, f"G{row_num}", data.gradacion_c_tamiz_g[idx], is_number=True)
        _set_cell(sd, f"H{row_num}", data.gradacion_d_tamiz_g[idx], is_number=True)

    # Tabla ITEM (filas 41-47), gradaciones A/B/C/D (E/F/G/H)
    item_matrix = [
        data.item_3_masa_esferas_conjunto_g,
        data.item_a_masa_original_g,
        data.item_b_masa_final_g,
        data.item_c_masa_final_lavada_seca_g,
        data.item_d_masa_final_lavada_seca_constante_g,
        data.item_e_perdida_abrasion_pct,
        data.item_f_perdida_lavado_pct,
    ]

    for row_num, row_values in zip(ITEM_ROWS, item_matrix):
        _set_cell(sd, f"E{row_num}", row_values[0], is_number=True)
        _set_cell(sd, f"F{row_num}", row_values[1], is_number=True)
        _set_cell(sd, f"G{row_num}", row_values[2], is_number=True)
        _set_cell(sd, f"H{row_num}", row_values[3], is_number=True)

    # Equipos
    _set_cell(sd, "D49", data.horno_codigo)
    _set_cell(sd, "D50", data.maquina_los_angeles_codigo)
    _set_cell(sd, "D51", data.balanza_1g_codigo)
    _set_cell(sd, "G49", data.malla_no_12_codigo)
    _set_cell(sd, "G50", data.malla_no_4_codigo)

    # Nota
    if data.observaciones:
        _set_cell(sd, "B52", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_incertidumbre_sheet(sheet_xml: bytes, data: AbrassRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    _set_cell(sd, "B47", data.revisado_por)
    _set_cell(sd, "G47", data.aprobado_por)

    rev_serial = _excel_date_serial(data.revisado_fecha)
    aprob_serial = _excel_date_serial(data.aprobado_fecha)
    if rev_serial is not None:
        _set_cell(sd, "B49", rev_serial, is_number=True)
    elif data.revisado_fecha:
        _set_cell(sd, "B49", data.revisado_fecha)

    if aprob_serial is not None:
        _set_cell(sd, "G49", aprob_serial, is_number=True)
    elif data.aprobado_fecha:
        _set_cell(sd, "G49", data.aprobado_fecha)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: AbrassRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_abrass_excel(data: AbrassRequest, db: Any = None) -> bytes:
    """Generate ABRASS Excel file from template."""
    logger.info("Generating ABRASS Excel - ASTM C131/C131M-20")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    metadata = _get_reception_metadata(db, data.muestra, data.numero_ot)

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        sheet_original = zin.read("xl/worksheets/sheet1.xml")
        sheet_xml = _fill_sheet(sheet_original, data, metadata)

        incertidumbre_original = zin.read("xl/worksheets/sheet4.xml")
        incertidumbre_xml = _fill_incertidumbre_sheet(incertidumbre_original, data)

        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue
            if item.filename.startswith("xl/externalLinks/"):
                continue

            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet_xml
            elif item.filename == "xl/worksheets/sheet4.xml":
                raw = incertidumbre_xml
            else:
                raw = zin.read(item.filename)

            if item.filename.startswith("xl/drawings/drawing") and item.filename.endswith(".xml"):
                raw = _fill_drawing(raw, data)
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