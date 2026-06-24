"""
Excel generator for Caras Fracturadas (ASTM D5821-13).

ZIP/XML strategy to preserve styles, merged cells and drawings from template.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes
from app.modules.common.excel_xml import (
    enable_full_recalc_on_open,
    remove_calc_chain_content_type,
    remove_calc_chain_relationships,
    remove_external_link_content_types,
    remove_external_link_relationships,
    strip_external_references,
    find_template_path,
)

from .schemas import CarasRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

TEMPLATE_PATH = str(find_template_path("1-INF.-N-000-26-AG35-CARAS-ASTM-D5821-V04.xlsx"))


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


def _clear_cell(cell: etree._Element) -> None:
    cell.attrib.pop("t", None)
    for child in list(cell):
        cell.remove(child)


def _set_text(sheet_data: etree._Element, ref: str, value: Any) -> None:
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    _clear_cell(cell)

    text = str(value or "").strip()
    if not text:
        return

    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{NS_SHEET}}}is")
    t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
    t_el.text = text


def _set_number(sheet_data: etree._Element, ref: str, value: float | int | None) -> None:
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    _clear_cell(cell)

    if value is None or value == "":
        return

    val = etree.SubElement(cell, f"{{{NS_SHEET}}}v")
    val.text = str(value)


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
        logger.warning("Error fetching reception metadata for Caras: %s", exc)
    return metadata


def _fill_sheet(sheet_xml: bytes, data: CarasRequest, metadata: dict[str, str]) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    # Encabezado (top-left de celdas mergeadas).
    _set_text(sheet_data, "C8", data.muestra)
    _set_text(sheet_data, "D8", data.numero_ot)
    _set_text(sheet_data, "E8", data.fecha_ensayo)
    _set_text(sheet_data, "G8", data.realizado_por)

    # Inyectar en Columna K (Mapeo a sheet FORMATO para que el INFORME lo lea vía fórmulas)
    _set_text(sheet_data, "K2", metadata["cliente"])
    _set_text(sheet_data, "K3", metadata["direccion"])
    _set_text(sheet_data, "K4", metadata["proyecto"])
    _set_text(sheet_data, "K5", metadata["ubicacion"])
    _set_text(sheet_data, "K7", metadata["numero_recepcion"])
    _set_text(sheet_data, "K8", data.fecha_ensayo)  # Fecha Emisión
    _set_text(sheet_data, "K9", data.numero_ot)
    _set_text(sheet_data, "K11", metadata["muestra_nombre"] or data.muestra)
    _set_text(sheet_data, "K12", metadata["fecha_recepcion"])
    _set_text(sheet_data, "K13", data.fecha_ensayo)  # Fecha de Ejecución

    # Metodo de determinacion (marcado sobre la misma etiqueta).
    _set_text(sheet_data, "D15", "X MASA" if data.metodo_determinacion == "MASA" else "Masa")
    _set_text(sheet_data, "E15", "X RECUENTO" if data.metodo_determinacion == "RECUENTO" else "Recuento")

    # Informacion de ensayo.
    _set_text(sheet_data, "D16", data.tamano_maximo_nominal_in)
    _set_text(sheet_data, "D17", data.tamiz_especificado_in)

    _set_text(sheet_data, "D18", "X SI" if data.fraccionada is True else "SI")
    _set_text(sheet_data, "E18", "X NO" if data.fraccionada is False else "NO")

    # Muestra original de ensayo.
    _set_number(sheet_data, "E20", data.masa_muestra_retenida_g)
    _set_number(sheet_data, "E21", data.masa_particula_mas_grande_g)
    if data.porcentaje_particula_mas_grande_pct is not None:
        _set_number(sheet_data, "E22", data.porcentaje_particula_mas_grande_pct)
    _set_number(sheet_data, "E23", data.masa_muestra_seca_lavada_g)
    _set_number(sheet_data, "E24", data.masa_muestra_seca_lavada_constante_g)
    _set_number(sheet_data, "E25", data.masa_muestra_mayor_3_8_g)
    _set_number(sheet_data, "E26", data.masa_muestra_menor_3_8_g)

    # Muestra de prueba > 3/8 in o Global.
    _set_number(sheet_data, "E33", data.global_una_f_masa_fracturadas_g)
    _set_number(sheet_data, "E34", data.global_una_n_masa_no_cumple_g)
    _set_number(sheet_data, "E35", data.global_una_p_porcentaje_pct)

    _set_number(sheet_data, "G33", data.global_dos_f_masa_fracturadas_g)
    _set_number(sheet_data, "G34", data.global_dos_n_masa_no_cumple_g)
    _set_number(sheet_data, "G35", data.global_dos_p_porcentaje_pct)

    # Fraccion < 3/8 in.
    _set_number(sheet_data, "E37", data.fraccion_masa_menor_3_8_mayor_200g_una_g)
    _set_number(sheet_data, "G37", data.fraccion_masa_menor_3_8_mayor_200g_dos_g)

    _set_number(sheet_data, "E38", data.fraccion_una_f_masa_fracturadas_g)
    _set_number(sheet_data, "E39", data.fraccion_una_n_masa_no_cumple_g)
    _set_number(sheet_data, "E40", data.fraccion_una_p_porcentaje_pct)

    _set_number(sheet_data, "G38", data.fraccion_dos_f_masa_fracturadas_g)
    _set_number(sheet_data, "G39", data.fraccion_dos_n_masa_no_cumple_g)
    _set_number(sheet_data, "G40", data.fraccion_dos_p_porcentaje_pct)

    _set_number(sheet_data, "E41", data.promedio_ponderado_una_pct)
    _set_number(sheet_data, "G41", data.promedio_ponderado_dos_pct)

    # Equipos.
    _set_text(sheet_data, "H15", data.horno_codigo)
    _set_text(sheet_data, "H16", data.balanza_01g_codigo)
    _set_text(sheet_data, "H17", data.tamiz_especificado_codigo)

    # Nota.
    _set_text(sheet_data, "C44", data.nota)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_datos_sheet(sheet_xml: bytes, data: CarasRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    _set_text(sheet_data, "G3", data.realizado_por)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


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


def _fill_incertidumbre_sheet(sheet_xml: bytes, data: CarasRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    _set_text(sheet_data, "B90", data.revisado_por)
    _set_text(sheet_data, "G90", data.aprobado_por)

    revisado_serial = _excel_date_serial(data.revisado_fecha)
    aprobado_serial = _excel_date_serial(data.aprobado_fecha)

    if revisado_serial is not None:
        _set_number(sheet_data, "B92", revisado_serial)
    elif data.revisado_fecha:
        _set_text(sheet_data, "B92", data.revisado_fecha)

    if aprobado_serial is not None:
        _set_number(sheet_data, "G92", aprobado_serial)
    elif data.aprobado_fecha:
        _set_text(sheet_data, "G92", data.aprobado_fecha)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_sheet_protection(sheet_xml: bytes) -> bytes:
    root = etree.fromstring(sheet_xml)
    for protection in list(root.findall(f".//{{{NS_SHEET}}}sheetProtection")):
        parent = protection.getparent()
        if parent is not None:
            parent.remove(protection)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: CarasRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_caras_excel(data: CarasRequest, db: Any = None) -> bytes:
    """Generate Caras Excel file from template."""
    logger.info("Generating Caras Excel - ASTM D5821-13 (Multi-sheet)")

    metadata = _get_reception_metadata(db, data.muestra, data.numero_ot)

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        sheet1_xml = _fill_sheet(zin.read("xl/worksheets/sheet1.xml"), data, metadata)
        sheet2_xml = _strip_sheet_protection(zin.read("xl/worksheets/sheet2.xml"))
        sheet3_xml = _fill_datos_sheet(zin.read("xl/worksheets/sheet3.xml"), data)
        sheet4_xml = _fill_incertidumbre_sheet(zin.read("xl/worksheets/sheet4.xml"), data)

        for item in zin.infolist():
            if item.filename == "xl/calcChain.xml":
                continue
            if item.filename.startswith("xl/externalLinks/"):
                continue

            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet1_xml
            elif item.filename == "xl/worksheets/sheet2.xml":
                raw = sheet2_xml
            elif item.filename == "xl/worksheets/sheet3.xml":
                raw = sheet3_xml
            elif item.filename == "xl/worksheets/sheet4.xml":
                raw = sheet4_xml
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