"""
Excel generator for LLP (Liquid Limit / Plastic Limit) - ASTM D4318-17e1.

ZIP/XML strategy (without openpyxl writes) to preserve shapes, merged cells,
styles and formulas of the official template.
"""

from __future__ import annotations

import io
import logging
import math
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .schemas import LLPRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _find_template() -> str:
    filename = "Template_LLP.xlsx"
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
POINT_COLS = ["G", "I", "J", "K", "L"]
ELIMINACION_PARTICULAS_CELL_MAP = {
    "LAVADO POR EL TAMIZ NO. 40": "B25",
    "TAMIZADO EN SECO POR EL TAMIZ NO. 40": "B26",
    "MECANICAMENTE EMPUJADO A TRAVES DEL TAMIZ NO. 40": "H25",
    "MEZCLADO EN PLACA DE VIDRIO Y ELIMINACION DE PARTICULAS DE ARENA MEDIANAS": "H26",
}


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


def _set_formula_with_cached_value(
    sheet_data: etree._Element,
    ref: str,
    formula: str,
    cached_value: Any,
    result_type: str = "number",
) -> None:
    """
    Writes a formula cell preserving style and updating cached value.
    result_type: "number" | "error" | "string"
    """
    ns = NS_SHEET
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)

    for child in list(cell):
        cell.remove(child)

    formula_el = etree.SubElement(cell, f"{{{ns}}}f")
    formula_el.text = formula

    if result_type == "error":
        cell.set("t", "e")
    elif result_type == "string":
        cell.set("t", "str")
    else:
        cell.attrib.pop("t", None)

    value_el = etree.SubElement(cell, f"{{{ns}}}v")
    value_el.text = str(cached_value)


def _safe_round(value: float, digits: int) -> float:
    return round(float(value), digits)


def _compute_point_metrics(point: Any) -> tuple[float | None, float | None, float | None]:
    agua: float | None = None
    seco: float | None = None
    humedad: float | None = None

    if point.masa_recipiente_suelo_humedo is not None and point.masa_recipiente_suelo_seco_1 is not None:
        agua = _safe_round(point.masa_recipiente_suelo_humedo - point.masa_recipiente_suelo_seco_1, 2)

    if point.masa_recipiente_suelo_seco_1 is not None and point.masa_recipiente is not None:
        seco = _safe_round(point.masa_recipiente_suelo_seco_1 - point.masa_recipiente, 2)

    if agua is not None and seco is not None and seco != 0:
        humedad = _safe_round((agua / seco) * 100, 2)

    return agua, seco, humedad


def _avg(values: list[float | None], digits: int) -> float | None:
    valid = [v for v in values if v is not None and math.isfinite(v)]
    if not valid:
        return None
    return _safe_round(sum(valid) / len(valid), digits)


def _cache_main_table_formulas(sheet_data: etree._Element, data: LLPRequest) -> list[float | None]:
    humidities: list[float | None] = []

    for idx, col in enumerate(POINT_COLS):
        agua, seco, humedad = _compute_point_metrics(data.puntos[idx])
        humidities.append(humedad)

        formula_agua = f"+{col}39-{col}41"
        formula_seco = f"+{col}41-{col}42"
        formula_humedad = f"+{col}43/{col}44*100"

        _set_formula_with_cached_value(sheet_data, f"{col}43", formula_agua, agua if agua is not None else 0, "number")
        _set_formula_with_cached_value(sheet_data, f"{col}44", formula_seco, seco if seco is not None else 0, "number")

        if humedad is None:
            _set_formula_with_cached_value(sheet_data, f"{col}45", formula_humedad, "#DIV/0!", "error")
        else:
            _set_formula_with_cached_value(sheet_data, f"{col}45", formula_humedad, humedad, "number")

    return humidities


def _cache_limite_liquido_control(sheet_data: etree._Element, data: LLPRequest, humidities: list[float | None]) -> None:
    n_values = [data.puntos[idx].numero_golpes for idx in range(3)]
    source_cols = POINT_COLS[:3]  # G, I, J
    ln_values: list[float | None] = []
    ll_humedades = humidities[:3]

    for idx, row in enumerate((30, 31, 32)):
        n = n_values[idx]
        source_col = source_cols[idx]

        _set_formula_with_cached_value(
            sheet_data,
            f"P{row}",
            f"+{source_col}38",
            n if n is not None else 0,
            "number",
        )

        if n is not None and n > 0:
            ln_n = _safe_round(math.log(float(n)), 6)
            ln_values.append(ln_n)
            _set_formula_with_cached_value(sheet_data, f"O{row}", f"+LN(P{row})", ln_n, "number")
        else:
            ln_values.append(None)
            _set_formula_with_cached_value(sheet_data, f"O{row}", f"+LN(P{row})", "#NUM!", "error")

        humedad = ll_humedades[idx]
        if humedad is None:
            _set_formula_with_cached_value(sheet_data, f"Q{row}", f"+{source_col}45", "#DIV/0!", "error")
        else:
            _set_formula_with_cached_value(sheet_data, f"Q{row}", f"+{source_col}45", humedad, "number")

    ll_promedio = _avg(ll_humedades, 2)
    if ll_promedio is None:
        _set_formula_with_cached_value(sheet_data, "Q33", "AVERAGE(Q30:Q32)", "#DIV/0!", "error")
    else:
        _set_formula_with_cached_value(sheet_data, "Q33", "AVERAGE(Q30:Q32)", ll_promedio, "number")

    valid_pairs = [
        (ln_values[i], ll_humedades[i])
        for i in range(3)
        if ln_values[i] is not None and ll_humedades[i] is not None
    ]

    ll_r2: float | None = None
    if len(valid_pairs) >= 3:
        x = [float(pair[0]) for pair in valid_pairs]
        y = [float(pair[1]) for pair in valid_pairs]
        x_mean = sum(x) / len(x)
        y_mean = sum(y) / len(y)
        cov = sum((xv - x_mean) * (yv - y_mean) for xv, yv in zip(x, y))
        var_x = sum((xv - x_mean) ** 2 for xv in x)
        var_y = sum((yv - y_mean) ** 2 for yv in y)
        if var_x != 0 and var_y != 0:
            r = cov / math.sqrt(var_x * var_y)
            ll_r2 = _safe_round(r**2, 4)

    if ll_r2 is None:
        _set_formula_with_cached_value(sheet_data, "O37", "RSQ(Q30:Q32,O30:O32)", "#DIV/0!", "error")
        _set_formula_with_cached_value(sheet_data, "P37", 'IF(O37<=0.95,"NO CONFORME","CONFORME")', "PENDIENTE", "string")
    else:
        _set_formula_with_cached_value(sheet_data, "O37", "RSQ(Q30:Q32,O30:O32)", ll_r2, "number")
        conformidad = "NO CONFORME" if ll_r2 <= 0.95 else "CONFORME"
        _set_formula_with_cached_value(sheet_data, "P37", 'IF(O37<=0.95,"NO CONFORME","CONFORME")', conformidad, "string")


def _cache_limite_plastico_control(sheet_data: etree._Element, humidities: list[float | None]) -> None:
    lp_1 = humidities[3] if len(humidities) > 3 else None
    lp_2 = humidities[4] if len(humidities) > 4 else None

    std_1s: float | None = None
    d2s: int | None = None
    control: str | None = None

    if lp_1 is not None and lp_2 is not None:
        mean = (lp_1 + lp_2) / 2
        variance = ((lp_1 - mean) ** 2) + ((lp_2 - mean) ** 2)
        std_1s = _safe_round(math.sqrt(variance), 4)
        d2s = math.floor(std_1s * 2.8)
        control = "cumple" if d2s < 1 else "no cumple"

    if std_1s is None:
        _set_formula_with_cached_value(sheet_data, "O45", "+STDEV(K45,L45)", "#DIV/0!", "error")
        _set_formula_with_cached_value(sheet_data, "P45", "ROUNDDOWN(O45*2.8,0)", "#DIV/0!", "error")
        _set_formula_with_cached_value(sheet_data, "S45", 'IF(P45<R45, "cumple", "no cumple")', "PENDIENTE", "string")
    else:
        _set_formula_with_cached_value(sheet_data, "O45", "+STDEV(K45,L45)", std_1s, "number")
        _set_formula_with_cached_value(sheet_data, "P45", "ROUNDDOWN(O45*2.8,0)", d2s if d2s is not None else 0, "number")
        _set_formula_with_cached_value(sheet_data, "S45", 'IF(P45<R45, "cumple", "no cumple")', control or "PENDIENTE", "string")


def _enable_full_recalc_on_open(workbook_xml: bytes) -> bytes:
    root = etree.fromstring(workbook_xml)
    calc_pr = root.find(f".//{{{NS_SHEET}}}calcPr")
    if calc_pr is None:
        calc_pr = etree.SubElement(root, f"{{{NS_SHEET}}}calcPr")
    calc_pr.set("fullCalcOnLoad", "1")
    calc_pr.set("forceFullCalc", "1")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_eliminacion_particulas_marker(sheet_data: etree._Element, metodo: str) -> None:
    ref = ELIMINACION_PARTICULAS_CELL_MAP.get((metodo or "").strip())
    if not ref:
        return
    _set_cell(sheet_data, ref, "X")


def generate_llp_excel(data: LLPRequest) -> bytes:
    """Generates the LLP Excel file from template."""
    logger.info("Generating LLP Excel - ASTM D4318-17e1")

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

            if item.filename == "xl/drawings/drawing1.xml":
                raw = _fill_drawing(raw, data)
            elif item.filename == "xl/workbook.xml":
                raw = _enable_full_recalc_on_open(raw)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()


def _fill_sheet(sheet_xml: bytes, data: LLPRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Header
    _set_cell(sd, "C11", data.muestra)
    _set_cell(sd, "E11", data.numero_ot)
    _set_cell(sd, "H11", data.fecha_ensayo)
    _set_cell(sd, "J11", data.realizado_por)

    # Condiciones del ensayo
    _set_cell(sd, "J17", data.metodo_ensayo_limite_liquido)
    _set_cell(sd, "J18", data.herramienta_ranurado_limite_liquido)
    _set_cell(sd, "J19", data.dispositivo_limite_liquido)
    _set_cell(sd, "J20", data.metodo_laminacion_limite_plastico)
    _set_cell(sd, "J21", data.contenido_humedad_muestra_inicial_pct, is_number=True)
    _set_cell(sd, "J22", data.proceso_seleccion_muestra)
    _set_cell(sd, "J23", data.metodo_preparacion_muestra)
    _set_eliminacion_particulas_marker(sd, data.metodo_eliminacion_particulas_tamiz_40)

    # Descripcion de la muestra
    _set_cell(sd, "J29", data.tipo_muestra)
    _set_cell(sd, "J30", data.condicion_muestra)
    _set_cell(sd, "J31", data.tamano_maximo_visual_in)
    _set_cell(sd, "J32", data.porcentaje_retenido_tamiz_40_pct, is_number=True)
    _set_cell(sd, "J33", data.forma_particula)

    # Tabla principal (LL + LP)
    for idx, col in enumerate(POINT_COLS):
        punto = data.puntos[idx]
        _set_cell(sd, f"{col}37", punto.recipiente_numero)
        if idx < 3:
            _set_cell(sd, f"{col}38", punto.numero_golpes, is_number=True)
        _set_cell(sd, f"{col}39", punto.masa_recipiente_suelo_humedo, is_number=True)
        _set_cell(sd, f"{col}40", punto.masa_recipiente_suelo_seco, is_number=True)
        _set_cell(sd, f"{col}41", punto.masa_recipiente_suelo_seco_1, is_number=True)
        _set_cell(sd, f"{col}42", punto.masa_recipiente, is_number=True)

    humidities = _cache_main_table_formulas(sd, data)
    _cache_limite_liquido_control(sd, data, humidities)
    _cache_limite_plastico_control(sd, humidities)

    # Equipos
    _set_cell(sd, "D48", data.balanza_001g_codigo)
    _set_cell(sd, "D49", data.horno_110_codigo)
    _set_cell(sd, "D50", data.copa_casagrande_codigo)
    _set_cell(sd, "D51", data.ranurador_codigo)

    # Observaciones
    _set_cell(sd, "G48", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_drawing(drawing_xml: bytes, data: LLPRequest) -> bytes:
    """
    Injects footer text in signature shapes.
    Works with placeholders:
    - Revisado:
    - Aprobado:
    - Fecha:
    """
    has_footer = any([data.revisado_por, data.revisado_fecha, data.aprobado_por, data.aprobado_fecha])
    if not has_footer:
        return drawing_xml

    ns = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    def _set_or_create_paragraph_text(paragraph: etree._Element, text: str) -> None:
        # Keep paragraph-level styling and only replace textual runs.
        for child in list(paragraph):
            if etree.QName(child).localname in {"r", "fld", "br"}:
                paragraph.remove(child)

        run = etree.SubElement(paragraph, f"{{{NS_A}}}r")
        run_props = etree.SubElement(run, f"{{{NS_A}}}rPr")
        run_props.set("lang", "es-PE")
        t_el = etree.SubElement(run, f"{{{NS_A}}}t")
        t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t_el.text = text

    def _inject_footer_in_template_layout(anchor: etree._Element, nombre: str, fecha: str) -> bool:
        tx_body = anchor.find(".//xdr:txBody", ns)
        if tx_body is None:
            return False

        paragraphs = tx_body.findall("a:p", ns)
        if len(paragraphs) < 2:
            return False

        # Template structure:
        # p1: "Revisado:" / "Aprobado:"
        # p2: value line
        # p3: spacer (kept as-is)
        # p4: "Fecha:" line
        _set_or_create_paragraph_text(paragraphs[1], nombre)
        if len(paragraphs) >= 4:
            _set_or_create_paragraph_text(paragraphs[3], f"Fecha: {fecha}")
        return True

    for anchor in root.findall(".//xdr:twoCellAnchor", ns):
        all_texts = [(node.text or "").strip() for node in anchor.findall(".//a:t", ns)]
        text_blob = " ".join(all_texts)

        is_revisado = "Revisado:" in text_blob
        is_aprobado = "Aprobado:" in text_blob
        if not is_revisado and not is_aprobado:
            continue

        replacements: dict[str, str] = {}
        nombre = "-"
        fecha = data.fecha_ensayo or "-"
        if is_revisado:
            nombre = data.revisado_por or "-"
            fecha = data.revisado_fecha or data.fecha_ensayo or "-"
        elif is_aprobado:
            nombre = data.aprobado_por or "-"
            fecha = data.aprobado_fecha or data.fecha_ensayo or "-"

        if _inject_footer_in_template_layout(anchor, nombre, fecha):
            continue

        # Fallback for non-standard template shapes.
        if is_revisado:
            replacements["Revisado:"] = f"Revisado: {nombre}"
            replacements["Fecha:"] = f"Fecha: {fecha}"
        else:
            replacements["Aprobado:"] = f"Aprobado: {nombre}"
            replacements["Fecha:"] = f"Fecha: {fecha}"

        for run in anchor.findall(".//a:r", ns):
            t_el = run.find("a:t", ns)
            if t_el is None or t_el.text is None:
                continue
            text = t_el.text.strip()
            if text in replacements and replacements[text]:
                t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                t_el.text = replacements[text]

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
