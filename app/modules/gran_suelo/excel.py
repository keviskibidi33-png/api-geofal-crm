"""
Excel generator for Granulometría de Suelos (ASTM D6913/D6913M-17).

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

from .schemas import GranSueloRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
SIEVE_ROWS = [42, 43, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 56, 57]


def _find_template() -> str:
    filename = "Template_GranSuelo.xlsx"
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


def _fill_sheet(sheet_xml: bytes, data: GranSueloRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado
    _set_cell(sd, "D11", data.muestra)
    _set_cell(sd, "F11", data.numero_ot)
    _set_cell(sd, "H11", data.fecha_ensayo)
    _set_cell(sd, "J11", data.realizado_por)

    # Método / tipo / muestreo
    if data.metodo_prueba == "A":
        _set_cell(sd, "D17", "X")
    if data.metodo_prueba == "B":
        _set_cell(sd, "D18", "X")

    if data.tamizado_tipo == "FRACCIONADO":
        _set_cell(sd, "D21", "X")
    if data.tamizado_tipo == "GLOBAL":
        _set_cell(sd, "D22", "X")

    if data.metodo_muestreo == "HUMEDO":
        _set_cell(sd, "D25", "X")
    if data.metodo_muestreo == "SECADO AL AIRE":
        _set_cell(sd, "D26", "X")
    if data.metodo_muestreo == "SECADO AL HORNO":
        _set_cell(sd, "D27", "X")

    # Descripción de muestra
    _set_cell(sd, "J17", data.descripcion_turbo_organico)
    _set_cell(sd, "I17", data.tipo_muestra)
    _set_cell(sd, "I18", data.condicion_muestra if data.condicion_muestra != "-" else None)
    _set_cell(sd, "I19", data.tamano_maximo_particula_in)
    _set_cell(sd, "I20", data.forma_particula)
    _set_cell(sd, "K20", data.tamiz_separador)

    # Tamizado compuesto/global
    _set_cell(sd, "I23", data.masa_seca_porcion_gruesa_cp_md_g, is_number=True)
    _set_cell(sd, "I24", data.masa_humeda_porcion_fina_fp_mm_g, is_number=True)
    _set_cell(sd, "I25", data.masa_seca_porcion_fina_fp_md_g, is_number=True)
    _set_cell(sd, "I26", data.masa_seca_muestra_s_md_g, is_number=True)

    _set_cell(sd, "K23", data.masa_seca_global_g, is_number=True)
    _set_cell(sd, "K25", data.subespecie_masa_humeda_g, is_number=True)
    _set_cell(sd, "K26", data.subespecie_masa_seca_g, is_number=True)
    _set_cell(sd, "K27", data.contenido_agua_wfp_pct, is_number=True)

    # Pérdida aceptable durante lavado/tamizado
    _set_cell(sd, "K30", data.masa_porcion_gruesa_lavada_cpwmd_g, is_number=True)
    _set_cell(sd, "K31", data.masa_retenida_plato_cpmrpan_g, is_number=True)
    _set_cell(sd, "K32", data.perdida_cpl_pct, is_number=True)
    _set_cell(sd, "K33", data.masa_subespecimen_lavado_fina_g, is_number=True)
    _set_cell(sd, "K34", data.masa_seca_muestra_perdida_smd_g, is_number=True)

    # Clasificación / incidencias
    _set_cell(sd, "D31", data.clasificacion_visual_simbolo)
    _set_cell(sd, "D32", data.clasificacion_visual_nombre)
    _set_cell(sd, "D34", data.excluyo_material if data.excluyo_material != "-" else None)
    _set_cell(sd, "D35", data.excluyo_material_descripcion)
    _set_cell(sd, "D37", data.problema_muestra if data.problema_muestra != "-" else None)
    _set_cell(sd, "D38", data.problema_descripcion)
    _set_cell(sd, "J37", data.proceso_dispersion if data.proceso_dispersion != "-" else None)
    _set_cell(sd, "J38", data.masa_retenida_primer_tamiz_g, is_number=True)

    # Pesos por tamiz
    for idx, row_num in enumerate(SIEVE_ROWS):
        _set_cell(sd, f"D{row_num}", data.masa_retenida_tamiz_g[idx], is_number=True)

    # Equipos / observaciones
    _set_cell(sd, "I51", data.balanza_01g_codigo)
    _set_cell(sd, "I52", data.horno_110_codigo)
    _set_cell(sd, "G55", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: GranSueloRequest) -> bytes:
    has_footer = any([data.revisado_por, data.revisado_fecha, data.aprobado_por, data.aprobado_fecha])
    if not has_footer:
        return drawing_xml

    ns = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        all_texts = [(node.text or "").strip() for node in anchor.findall(".//a:t", ns)]
        text_blob = " ".join(all_texts)

        is_revisado = "Revisado:" in text_blob
        is_aprobado = "Aprobado:" in text_blob
        if not is_revisado and not is_aprobado:
            continue

        replacements: dict[str, str] = {}
        if is_revisado:
            if data.revisado_por:
                replacements["Revisado:"] = data.revisado_por
            if data.revisado_fecha:
                replacements["Fecha:"] = data.revisado_fecha
        elif is_aprobado:
            if data.aprobado_por:
                replacements["Aprobado:"] = data.aprobado_por
            if data.aprobado_fecha:
                replacements["Fecha:"] = data.aprobado_fecha

        for run in anchor.findall(".//a:r", ns):
            t_el = run.find("a:t", ns)
            if t_el is None or t_el.text is None:
                continue
            text = t_el.text.strip()
            if text in replacements and replacements[text]:
                t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if text == "Fecha:":
                    t_el.text = f"{text} {replacements[text]}"
                else:
                    t_el.text = f"{text}\n{replacements[text]}"

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_gran_suelo_excel(data: GranSueloRequest) -> bytes:
    """Generates the Gran Suelo Excel file from template."""
    logger.info("Generating Gran Suelo Excel - ASTM D6913/D6913M-17")

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
