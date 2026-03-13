"""
Excel generator for GE Grueso (ASTM C127-25).

ZIP/XML strategy to preserve styles, merged cells and drawings from the
official template.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from app.utils.excel_footer import fill_standard_footer_shapes

from .schemas import GeGruesoRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _find_template() -> str:
    filename = "Template_GE_GRUESO.xlsx"
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]  # app/

    possible = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]
    for path in possible:
        if path.exists():
            return str(path)
    return str(app_dir / "templates" / filename)


TEMPLATE_PATH = _find_template()


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


def _si_no_text(value: str | None) -> str:
    if value == "SI":
        return "    SI [X]                NO [ ]"
    if value == "NO":
        return "    SI [ ]                NO [X]"
    return "    SI [ ]                NO [ ]"


def _fill_sheet(sheet_xml: bytes, data: GeGruesoRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado
    _set_cell(sd, "E11", data.muestra)
    _set_cell(sd, "F11", data.numero_ot)
    _set_cell(sd, "H11", data.fecha_ensayo)
    _set_cell(sd, "I11", data.realizado_por)

    # Descripción de muestra
    _set_cell(sd, "E17", data.tamano_maximo_nominal)
    _set_cell(sd, "E18", _si_no_text(data.agregado_grupo_ligero_si_no))
    _set_cell(sd, "E19", _si_no_text(data.retenido_malla_no4_si_no))
    _set_cell(sd, "E20", _si_no_text(data.retenido_malla_1_1_2_si_no))
    _set_cell(sd, "E22", data.fecha_hora_inmersion_inicial)
    _set_cell(sd, "E23", data.fecha_hora_inmersion_final)

    # Equipos (tabla H-K)
    _set_cell(sd, "K17", data.equipo_balanza_1g_codigo)
    _set_cell(sd, "K18", data.equipo_horno_110_codigo)
    _set_cell(sd, "K19", data.equipo_termometro_01c_codigo)
    _set_cell(sd, "K20", data.equipo_canastilla_codigo)
    _set_cell(sd, "K22", data.equipo_tamiz_codigo)
    _set_cell(sd, "K23", data.equipo_gravedad_especifica_codigo)

    # Condiciones + masas
    _set_cell(sd, "H27", data.seco_horno_110_si_no)
    _set_cell(sd, "H28", data.ensayada_en_fracciones_si_no)
    _set_cell(sd, "H29", data.malla_fraccion)
    _set_cell(sd, "O26", data.masa_retenida_malla_1_1_2_pct, is_number=True)
    _set_cell(sd, "O27", data.masa_muestra_inicial_total_kg, is_number=True)
    _set_cell(sd, "O28", data.masa_fraccion_01_kg, is_number=True)
    _set_cell(sd, "O29", data.masa_fraccion_02_kg, is_number=True)

    # Reporte de datos 1° fracción
    _set_cell(sd, "M34", data.fr1_a_g, is_number=True)
    _set_cell(sd, "M35", data.fr1_b_g, is_number=True)
    _set_cell(sd, "M36", data.fr1_c_g, is_number=True)
    _set_cell(sd, "M37", data.fr1_d_g, is_number=True)
    _set_cell(sd, "O38", data.fr1_masa_total_g, is_number=True)

    # Reporte de datos 2° fracción
    _set_cell(sd, "M41", data.fr2_a_g, is_number=True)
    _set_cell(sd, "M42", data.fr2_b_g, is_number=True)
    _set_cell(sd, "M43", data.fr2_c_g, is_number=True)
    _set_cell(sd, "M44", data.fr2_d_g, is_number=True)
    _set_cell(sd, "O45", data.fr2_masa_total_g, is_number=True)

    # Observaciones
    if data.observaciones:
        _set_cell(sd, "D48", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: GeGruesoRequest) -> bytes:
    return fill_standard_footer_shapes(
        drawing_xml,
        revisado_por=data.revisado_por,
        revisado_fecha=data.revisado_fecha,
        aprobado_por=data.aprobado_por,
        aprobado_fecha=data.aprobado_fecha,
    )


def generate_ge_grueso_excel(data: GeGruesoRequest) -> bytes:
    """Generates the GE Grueso Excel file from template."""
    logger.info("Generating GE Grueso Excel - ASTM C127-25")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        sheet_original = zin.read("xl/worksheets/sheet1.xml")
        sheet_xml = _fill_sheet(sheet_original, data)

        for item in zin.infolist():
            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet_xml
            else:
                raw = zin.read(item.filename)

            if item.filename.startswith("xl/drawings/drawing") and item.filename.endswith(".xml"):
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
