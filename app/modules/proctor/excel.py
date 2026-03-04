"""
Excel generator for Proctor test - ASTM D1557-12(2021).

ZIP/XML strategy (without openpyxl writes) to preserve shapes, merged cells,
styles and formulas of the official template.
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .schemas import ProctorRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _find_template() -> str:
    filename = "Template_Proctor.xlsx"
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
POINT_COLS = ["D", "F", "G", "H", "I"]
SIEVE_ROWS = [37, 38, 39, 40, 41]


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
    ns = NS_SHEET
    for row in sheet_data.findall(f"{{{ns}}}row"):
        if row.get("r") == str(row_num):
            return row

    new_row = etree.SubElement(sheet_data, f"{{{ns}}}row")
    new_row.set("r", str(row_num))
    return new_row


def _find_or_create_cell(row: etree._Element, cell_ref: str) -> etree._Element:
    ns = NS_SHEET
    for cell in row.findall(f"{{{ns}}}c"):
        if cell.get("r") == cell_ref:
            return cell

    col, _ = _parse_cell_ref(cell_ref)
    col_num = _col_letter_to_num(col)

    insert_pos = None
    existing = row.findall(f"{{{ns}}}c")
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

    ns = NS_SHEET
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    for child in list(cell):
        cell.remove(child)

    if is_number:
        cell.attrib.pop("t", None)
        val = etree.SubElement(cell, f"{{{ns}}}v")
        val.text = str(value)
        return

    text = str(value)
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{ns}}}is")
    t_el = etree.SubElement(is_el, f"{{{ns}}}t")
    t_el.text = text


def _set_cell_formula(sheet_data: etree._Element, ref: str, formula: str) -> None:
    if not formula:
        return

    ns = NS_SHEET
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    for child in list(cell):
        cell.remove(child)

    cell.attrib.pop("t", None)
    f_el = etree.SubElement(cell, f"{{{ns}}}f")
    f_el.text = formula.lstrip("=")


def _set_cell_formula_with_cached_value(
    sheet_data: etree._Element,
    ref: str,
    formula: str,
    cached_value: float | int | None,
) -> None:
    if not formula:
        return

    ns = NS_SHEET
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    for child in list(cell):
        cell.remove(child)

    cell.attrib.pop("t", None)
    f_el = etree.SubElement(cell, f"{{{ns}}}f")
    f_el.text = formula.lstrip("=")
    if cached_value is not None:
        v_el = etree.SubElement(cell, f"{{{ns}}}v")
        v_el.text = str(cached_value)


def _set_cell_style(sheet_data: etree._Element, ref: str, style_id: int | None) -> None:
    if style_id is None:
        return

    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    cell.set("s", str(style_id))


def _get_cell_style_id(sheet_root: etree._Element, ref: str) -> int | None:
    for cell in sheet_root.findall(f".//{{{NS_SHEET}}}c"):
        if cell.get("r") != ref:
            continue
        style = cell.get("s")
        if style is None:
            return None
        try:
            return int(style)
        except ValueError:
            return None
    return None


def _resolve_centered_styles(sheet_xml: bytes) -> dict[str, int]:
    sheet_root = etree.fromstring(sheet_xml)
    style_by_ref: dict[str, int] = {}

    # Reuse existing style ids from template instead of rewriting xl/styles.xml.
    i41_style = _get_cell_style_id(sheet_root, "H41") or _get_cell_style_id(sheet_root, "I41")
    if i41_style is not None:
        style_by_ref["I41"] = i41_style

    h44_style = _get_cell_style_id(sheet_root, "H44")
    if h44_style is not None:
        style_by_ref["H44"] = h44_style

    h45_style = _get_cell_style_id(sheet_root, "H45")
    if h45_style is not None:
        style_by_ref["H45"] = h45_style

    return style_by_ref


def _round(value: float | None, decimals: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, decimals)


def _force_full_calc_on_open(workbook_xml: bytes) -> bytes:
    root = etree.fromstring(workbook_xml)
    calc = root.find(f".//{{{NS_SHEET}}}calcPr")
    if calc is None:
        calc = etree.SubElement(root, f"{{{NS_SHEET}}}calcPr")
    calc.set("fullCalcOnLoad", "1")
    calc.set("calcOnSave", "1")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_proctor_excel(data: ProctorRequest) -> bytes:
    """Generates the Proctor Excel file from the template."""
    logger.info("Generating Proctor Excel - ASTM D1557-12(2021)")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as file_handle:
        template_bytes = file_handle.read()

    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        sheet_original = zin.read("xl/worksheets/sheet1.xml")
        centered_style_map = _resolve_centered_styles(sheet_original)
        sheet_xml = _fill_sheet(sheet_original, data, centered_style_map)

        for item in zin.infolist():
            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet_xml
            else:
                raw = zin.read(item.filename)

            if item.filename == "xl/workbook.xml":
                raw = _force_full_calc_on_open(raw)

            if item.filename == "xl/drawings/drawing1.xml":
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()


def _fill_sheet(sheet_xml: bytes, data: ProctorRequest, centered_style_map: dict[str, int] | None = None) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Header
    _set_cell(sd, "B9", data.muestra)
    _set_cell(sd, "C9", data.numero_ot)
    _set_cell(sd, "F9", data.fecha_ensayo)
    _set_cell(sd, "H9", data.realizado_por)

    # Densidad humeda + contenido humedad/densidad seca (5 puntos)
    densidad_humeda_por_punto: list[float | None] = []

    for idx, col in enumerate(POINT_COLS):
        punto = data.puntos[idx]

        masa_compactado_c = punto.masa_suelo_compactado_c
        if masa_compactado_c is None and punto.masa_suelo_humedo_molde_a is not None and punto.masa_molde_compactacion_b is not None:
            masa_compactado_c = _round(punto.masa_suelo_humedo_molde_a - punto.masa_molde_compactacion_b, 2)

        densidad_humeda_x = punto.densidad_humeda_x
        if densidad_humeda_x is None and masa_compactado_c is not None and punto.volumen_molde_compactacion_d not in (None, 0):
            densidad_humeda_x = _round(masa_compactado_c / punto.volumen_molde_compactacion_d, 3)

        masa_agua_y = punto.masa_agua_y
        if (
            masa_agua_y is None
            and punto.masa_recipiente_suelo_humedo_e is not None
            and punto.masa_recipiente_suelo_seco_3_f is not None
        ):
            masa_agua_y = _round(punto.masa_recipiente_suelo_humedo_e - punto.masa_recipiente_suelo_seco_3_f, 2)

        masa_suelo_seco_z = punto.masa_suelo_seco_z
        if masa_suelo_seco_z is None and punto.masa_recipiente_suelo_seco_3_f is not None and punto.masa_recipiente_g is not None:
            masa_suelo_seco_z = _round(punto.masa_recipiente_suelo_seco_3_f - punto.masa_recipiente_g, 2)

        contenido_humedad_w = punto.contenido_humedad_moldeo_w
        if contenido_humedad_w is None and masa_agua_y is not None and masa_suelo_seco_z not in (None, 0):
            contenido_humedad_w = _round((masa_agua_y / masa_suelo_seco_z) * 100, 2)

        densidad_seca = punto.densidad_seca
        if densidad_seca is None and densidad_humeda_x is not None and contenido_humedad_w is not None:
            divisor = 1 + (contenido_humedad_w / 100)
            if divisor != 0:
                densidad_seca = _round(densidad_humeda_x / divisor, 3)

        densidad_humeda_por_punto.append(densidad_humeda_x)

        # Rows 15-22
        _set_cell(sd, f"{col}15", punto.prueba_numero, is_number=True)
        _set_cell(sd, f"{col}16", punto.numero_capas, is_number=True)
        _set_cell(sd, f"{col}17", punto.numero_golpes, is_number=True)
        _set_cell(sd, f"{col}18", punto.masa_suelo_humedo_molde_a, is_number=True)
        _set_cell(sd, f"{col}19", punto.masa_molde_compactacion_b, is_number=True)
        _set_cell(sd, f"{col}20", masa_compactado_c, is_number=True)
        _set_cell(sd, f"{col}21", punto.volumen_molde_compactacion_d, is_number=True)
        _set_cell(sd, f"{col}22", densidad_humeda_x, is_number=True)

        # Rows 24-33
        _set_cell(sd, f"{col}24", punto.tara_numero)
        _set_cell(sd, f"{col}25", punto.masa_recipiente_suelo_humedo_e, is_number=True)
        _set_cell(sd, f"{col}26", punto.masa_recipiente_suelo_seco_1, is_number=True)
        _set_cell(sd, f"{col}27", punto.masa_recipiente_suelo_seco_2, is_number=True)
        _set_cell(sd, f"{col}28", punto.masa_recipiente_suelo_seco_3_f, is_number=True)
        _set_cell(sd, f"{col}29", masa_agua_y, is_number=True)
        _set_cell(sd, f"{col}30", punto.masa_recipiente_g, is_number=True)
        _set_cell(sd, f"{col}31", masa_suelo_seco_z, is_number=True)
        _set_cell(sd, f"{col}32", contenido_humedad_w, is_number=True)
        _set_cell(sd, f"{col}33", densidad_seca, is_number=True)

    # Sample description and test conditions
    _set_cell(sd, "C35", data.tipo_muestra)
    _set_cell(sd, "C36", data.condicion_muestra)
    _set_cell(sd, "C37", data.tamano_maximo_particula_in)
    _set_cell(sd, "C38", data.forma_particula)
    _set_cell(sd, "C39", data.clasificacion_sucs_visual)

    _set_cell(sd, "C41", data.metodo_ensayo)
    _set_cell(sd, "C42", data.metodo_preparacion)
    _set_cell(sd, "C43", data.tipo_apisonador)
    _set_cell(sd, "C44", data.contenido_humedad_natural_pct, is_number=True)
    _set_cell(sd, "C45", data.excluyo_material_muestra)
    _set_cell(sd, "C46", data.observaciones)

    # Sieves
    sieve_mass = list(data.tamiz_masa_retenida_g)
    if sieve_mass[4] is None and all(value is not None for value in sieve_mass[:4]):
        sieve_mass[4] = _round(sum(value for value in sieve_mass[:4] if value is not None), 2)

    for idx, row_num in enumerate(SIEVE_ROWS[:4]):
        _set_cell(sd, f"G{row_num}", sieve_mass[idx], is_number=True)
    total_sieve = _round(sum(value for value in sieve_mass[:4] if value is not None), 2)
    _set_cell_formula_with_cached_value(sd, "G41", "SUM(G37:G40)", total_sieve)

    # Formula-driven sieve table (rows 37-41), aligned to the official sheet:
    # H37:H40 = Gx/G41*100, H41 = SUM(H37:H40)
    # I37 = H37, I38 = I37+H38, I39 = I38+H39, I40 = I39+H40, I41 = I40
    h_values: list[float] = []
    for row_num in SIEVE_ROWS[:4]:
        mass = sieve_mass[row_num - SIEVE_ROWS[0]]
        cached_pct = 0.0
        if total_sieve not in (None, 0) and mass is not None:
            cached_pct = _round((mass / total_sieve) * 100, 2) or 0.0
        h_values.append(cached_pct)
        _set_cell_formula_with_cached_value(sd, f"H{row_num}", f"IF(G41=0,0,G{row_num}/G41*100)", cached_pct)

    h_total = _round(sum(h_values), 2) or 0.0
    _set_cell_formula_with_cached_value(sd, "H41", "SUM(H37:H40)", h_total)

    i37 = h_values[0] if len(h_values) > 0 else 0.0
    i38 = _round(i37 + (h_values[1] if len(h_values) > 1 else 0.0), 2) or 0.0
    i39 = _round(i38 + (h_values[2] if len(h_values) > 2 else 0.0), 2) or 0.0
    i40 = _round(i39 + (h_values[3] if len(h_values) > 3 else 0.0), 2) or 0.0
    _set_cell_formula_with_cached_value(sd, "I37", "H37", i37)
    _set_cell_formula_with_cached_value(sd, "I38", "I37+H38", i38)
    _set_cell_formula_with_cached_value(sd, "I39", "I38+H39", i39)
    _set_cell_formula_with_cached_value(sd, "I40", "I39+H40", i40)
    _set_cell_formula_with_cached_value(sd, "I41", "I40", i40)

    # Equipment used (codes)
    tamiz_rows: list[str] = []
    if data.tamiz_metodo_c_codigo and data.tamiz_metodo_c_codigo != "-":
        tamiz_rows.append(f"{data.tamiz_metodo_c_codigo} - METODO C")
    if data.tamiz_metodo_a_codigo and data.tamiz_metodo_a_codigo != "-":
        tamiz_rows.append(f"{data.tamiz_metodo_a_codigo} - METODO A")
    if data.tamiz_metodo_b_codigo and data.tamiz_metodo_b_codigo != "-":
        tamiz_rows.append(f"{data.tamiz_metodo_b_codigo} - METODO B")
    tamiz_display = " | ".join(tamiz_rows) if tamiz_rows else data.tamiz_utilizado_metodo_codigo
    _set_cell(sd, "H44", tamiz_display)
    _set_cell(sd, "H45", data.balanza_1g_codigo)
    _set_cell(sd, "H46", data.balanza_codigo)
    _set_cell(sd, "H47", data.horno_110_codigo)
    _set_cell(sd, "H48", data.molde_codigo)
    _set_cell(sd, "H49", data.pison_codigo)

    # Keep critical output cells centered even when template merges/alignments vary.
    if centered_style_map:
        _set_cell_style(sd, "I41", centered_style_map.get("I41"))
        _set_cell_style(sd, "H44", centered_style_map.get("H44"))
        _set_cell_style(sd, "H45", centered_style_map.get("H45"))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: ProctorRequest) -> bytes:
    """Injects text in footer shapes (Revisado/Aprobado)."""
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
                    # Keep the date on the same line to avoid dropping too low in the signature box.
                    t_el.text = f"{text} {replacements[text]}"
                else:
                    t_el.text = f"{text}\n{replacements[text]}"

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
