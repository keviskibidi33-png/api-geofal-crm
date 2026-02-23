"""
Excel generator for Proctor test - ASTM D1557-12(2021).

ZIP/XML strategy (without openpyxl writes) to preserve shapes, merged cells,
styles and formulas of the official template.
"""

import io
import logging
import zipfile
from copy import deepcopy
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


def _clone_centered_style(styles_root: etree._Element, source_style_id: int, cache: dict[int, int]) -> int:
    if source_style_id in cache:
        return cache[source_style_id]

    cell_xfs = styles_root.find(f".//{{{NS_SHEET}}}cellXfs")
    if cell_xfs is None:
        cache[source_style_id] = source_style_id
        return source_style_id

    if source_style_id < 0 or source_style_id >= len(cell_xfs):
        cache[source_style_id] = source_style_id
        return source_style_id

    source_xf = cell_xfs[source_style_id]
    alignment = source_xf.find(f"{{{NS_SHEET}}}alignment")
    if alignment is not None and alignment.get("horizontal") == "center" and alignment.get("vertical") == "center":
        cache[source_style_id] = source_style_id
        return source_style_id

    cloned_xf = deepcopy(source_xf)
    for child in list(cloned_xf):
        if child.tag == f"{{{NS_SHEET}}}alignment":
            cloned_xf.remove(child)

    aligned = etree.SubElement(cloned_xf, f"{{{NS_SHEET}}}alignment")
    aligned.set("horizontal", "center")
    aligned.set("vertical", "center")
    cloned_xf.set("applyAlignment", "1")

    cell_xfs.append(cloned_xf)
    new_style_id = len(cell_xfs) - 1
    cell_xfs.set("count", str(len(cell_xfs)))
    cache[source_style_id] = new_style_id
    return new_style_id


def _prepare_centered_styles(sheet_xml: bytes, styles_xml: bytes) -> tuple[bytes, dict[str, int]]:
    sheet_root = etree.fromstring(sheet_xml)
    styles_root = etree.fromstring(styles_xml)

    source_by_ref: dict[str, int | None] = {
        "I41": _get_cell_style_id(sheet_root, "I41") or _get_cell_style_id(sheet_root, "H41"),
        "H44": _get_cell_style_id(sheet_root, "H44"),
        "H45": _get_cell_style_id(sheet_root, "H45"),
    }

    style_cache: dict[int, int] = {}
    style_by_ref: dict[str, int] = {}
    for ref, source_style_id in source_by_ref.items():
        if source_style_id is None:
            continue
        style_by_ref[ref] = _clone_centered_style(styles_root, source_style_id, style_cache)

    styles_with_centering = etree.tostring(styles_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return styles_with_centering, style_by_ref


def _round(value: float | None, decimals: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, decimals)


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
        styles_original = zin.read("xl/styles.xml")
        styles_xml, centered_style_map = _prepare_centered_styles(sheet_original, styles_original)
        sheet_xml = _fill_sheet(sheet_original, data, centered_style_map)

        for item in zin.infolist():
            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet_xml
            elif item.filename == "xl/styles.xml":
                raw = styles_xml
            else:
                raw = zin.read(item.filename)

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
    sieve_pct = list(data.tamiz_porcentaje_retenido)
    sieve_pct_acc = list(data.tamiz_porcentaje_retenido_acumulado)

    if sieve_mass[4] is None and all(value is not None for value in sieve_mass[:4]):
        sieve_mass[4] = _round(sum(value for value in sieve_mass[:4] if value is not None), 2)

    total_index = len(sieve_mass) - 1
    total_mass = sieve_mass[total_index] if sieve_mass[total_index] not in (None, 0) else None
    if total_mass:
        running = 0.0
        for idx in range(total_index):
            value = sieve_mass[idx]
            if value is not None and sieve_pct[idx] is None:
                sieve_pct[idx] = _round((value / total_mass) * 100, 2)

            if sieve_pct[idx] is not None:
                running += sieve_pct[idx] or 0
                if sieve_pct_acc[idx] is None:
                    sieve_pct_acc[idx] = _round(running, 2)

        if sieve_pct[total_index] is None:
            sieve_pct[total_index] = 100.0
        if sieve_pct_acc[total_index] is None:
            sieve_pct_acc[total_index] = 100.0

    for idx, row_num in enumerate(SIEVE_ROWS):
        _set_cell(sd, f"G{row_num}", sieve_mass[idx], is_number=True)
        _set_cell(sd, f"H{row_num}", sieve_pct[idx], is_number=True)
        _set_cell(sd, f"I{row_num}", sieve_pct_acc[idx], is_number=True)

    # Equipment used (codes)
    _set_cell(sd, "H44", data.tamiz_utilizado_metodo_codigo)
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
