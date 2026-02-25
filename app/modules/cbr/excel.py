"""
Generador Excel para ensayo CBR — ASTM D1883-21.

Estrategia 100% ZIP/XML (sin openpyxl) para preservar shapes,
logos, merged cells, estilos y formulas del template original.
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .schemas import CBRRequest

logger = logging.getLogger(__name__)

# Namespaces
NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _find_template() -> str:
    filename = "Temp_CBR_ASTM.xlsx"
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]  # app/

    possible = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]
    for p in possible:
        if p.exists():
            return str(p)
    return str(app_dir / "templates" / filename)


TEMPLATE_PATH = _find_template()


def _parse_cell_ref(ref: str) -> tuple[str, int]:
    col = "".join(c for c in ref if c.isalpha())
    row = int("".join(c for c in ref if c.isdigit()))
    return col, row


def _col_letter_to_num(col: str) -> int:
    num = 0
    for c in col.upper():
        num = num * 26 + (ord(c) - ord("A") + 1)
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
    for i, ex in enumerate(existing):
        ex_col, _ = _parse_cell_ref(ex.get("r"))
        if col_num < _col_letter_to_num(ex_col):
            insert_pos = i
            break

    cell = etree.Element(f"{{{ns}}}c")
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


def _set_formula_cached_value(sheet_data: etree._Element, ref: str, value: Any) -> None:
    """Actualiza el valor cacheado de una celda con fórmula, sin eliminar la fórmula."""
    if value is None:
        return

    ns = NS_SHEET
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    formula = cell.find(f"{{{ns}}}f")
    if formula is None:
        _set_cell(sheet_data, ref, value, is_number=True)
        return

    cell.attrib.pop("t", None)
    val = cell.find(f"{{{ns}}}v")
    if val is None:
        val = etree.SubElement(cell, f"{{{ns}}}v")
    val.text = str(value)


def _clear_formula_cached_value(sheet_data: etree._Element, ref: str) -> None:
    """Limpia valor cacheado de celda con fórmula para evitar mostrar 0 desactualizado."""
    ns = NS_SHEET
    _, row_num = _parse_cell_ref(ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, ref)
    formula = cell.find(f"{{{ns}}}f")
    if formula is None:
        return
    val = cell.find(f"{{{ns}}}v")
    if val is not None:
        cell.remove(val)


def _force_full_calc_on_open(workbook_xml: bytes) -> bytes:
    """Fuerza recálculo completo al abrir el archivo para evitar caches #DIV/0 heredados."""
    root = etree.fromstring(workbook_xml)
    calc = root.find(f".//{{{NS_SHEET}}}calcPr")
    if calc is None:
        calc = etree.SubElement(root, f"{{{NS_SHEET}}}calcPr")
    calc.set("fullCalcOnLoad", "1")
    calc.set("calcOnSave", "1")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_cbr_excel(data: CBRRequest) -> bytes:
    """
    Genera el Excel de CBR desde el template Temp_CBR_ASTM.xlsx.
    """
    logger.info("Generando Excel CBR — ASTM D1883-21")

    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template no encontrado: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, "rb") as f:
        template_bytes = f.read()

    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            raw = zin.read(item.filename)

            if item.filename == "xl/worksheets/sheet1.xml":
                raw = _fill_sheet(raw, data)

            if item.filename == "xl/workbook.xml":
                raw = _force_full_calc_on_open(raw)

            if item.filename == "xl/drawings/drawing1.xml":
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()


def _fill_sheet(sheet_xml: bytes, data: CBRRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    # Encabezado principal (fila 9)
    _set_cell(sd, "D9", data.muestra)
    _set_cell(sd, "F9", data.numero_ot)
    _set_cell(sd, "H9", data.fecha_ensayo)
    _set_cell(sd, "K9", data.realizado_por)

    # Condiciones generales
    _set_cell(sd, "E14", data.sobretamano_porcentaje, is_number=True)
    _set_cell(sd, "E15", data.masa_grava_adicionada_g, is_number=True)
    _set_cell(sd, "E16", data.condicion_muestra_saturado)
    _set_cell(sd, "E17", data.condicion_muestra_sin_saturar)

    _set_cell(sd, "O14", data.maxima_densidad_seca, is_number=True)
    _set_cell(sd, "O15", data.optimo_contenido_humedad, is_number=True)
    _set_cell(sd, "O16", data.temperatura_inicial_c, is_number=True)
    _set_cell(sd, "O17", data.temperatura_final_c, is_number=True)

    _set_cell(sd, "G19", data.tamano_maximo_visual_in)
    _set_cell(sd, "E20", data.descripcion_muestra_astm)

    # Ensayo (3 especimenes)
    specimen_cols = ["D", "H", "L"]
    for idx, col in enumerate(specimen_cols):
        _set_cell(sd, f"{col}23", data.golpes_por_especimen[idx], is_number=True)
        _set_cell(sd, f"{col}24", data.codigo_molde_por_especimen[idx])

    # Secciones por columna (6 columnas)
    cols_6 = ["D", "F", "H", "J", "L", "O"]
    for idx, col in enumerate(cols_6):
        _set_cell(sd, f"{col}25", data.temperatura_inicio_c_por_columna[idx], is_number=True)
        _set_cell(sd, f"{col}26", data.temperatura_final_c_por_columna[idx], is_number=True)
        _set_cell(sd, f"{col}27", data.masa_molde_suelo_g_por_columna[idx], is_number=True)

        _set_cell(sd, f"{col}29", data.codigo_tara_por_columna[idx])
        _set_cell(sd, f"{col}30", data.masa_tara_g_por_columna[idx], is_number=True)
        _set_cell(sd, f"{col}31", data.masa_suelo_humedo_tara_g_por_columna[idx], is_number=True)
        # Row 32 conserva fórmula en template; actualizamos solo el valor cacheado.
        tara = data.masa_tara_g_por_columna[idx]
        masa_humeda = data.masa_suelo_humedo_tara_g_por_columna[idx]
        if tara is not None and masa_humeda is not None:
            _set_formula_cached_value(sd, f"{col}32", round(masa_humeda - tara, 6))
        else:
            _clear_formula_cached_value(sd, f"{col}32")
        _set_cell(sd, f"{col}33", data.masa_suelo_seco_tara_g_por_columna[idx], is_number=True)
        _set_cell(sd, f"{col}34", data.masa_suelo_seco_tara_constante_g_por_columna[idx], is_number=True)

    # Lectura de penetracion (rows 40-51)
    for idx, row_num in enumerate(range(40, 52)):
        row = data.lecturas_penetracion[idx]
        _set_cell(sd, f"D{row_num}", row.tension_standard, is_number=True)
        _set_cell(sd, f"E{row_num}", row.lectura_dial_esp_01, is_number=True)
        _set_cell(sd, f"G{row_num}", row.lectura_dial_esp_02, is_number=True)
        _set_cell(sd, f"I{row_num}", row.lectura_dial_esp_03, is_number=True)

    # Hinchamiento (rows 40-44)
    for idx, row_num in enumerate(range(40, 45)):
        row = data.hinchamiento[idx]
        _set_cell(sd, f"L{row_num}", row.fecha)
        _set_cell(sd, f"N{row_num}", row.hora)
        _set_cell(sd, f"O{row_num}", row.esp_01, is_number=True)
        _set_cell(sd, f"P{row_num}", row.esp_02, is_number=True)
        _set_cell(sd, f"Q{row_num}", row.esp_03, is_number=True)

    hendidura = [*data.profundidad_hendidura_mm_por_celda[:3], *([None] * (3 - len(data.profundidad_hendidura_mm_por_celda)))]
    if all(v is None for v in hendidura):
        hendidura[0] = data.profundidad_hendidura_mm
    # Fila 53: tres celdas de hendidura en top-left de celdas fusionadas.
    _set_cell(sd, "E53", hendidura[0], is_number=True)
    _set_cell(sd, "G53", hendidura[1], is_number=True)
    _set_cell(sd, "I53", hendidura[2], is_number=True)

    # Equipo utilizado (codes)
    _set_cell(sd, "O47", data.equipo_cbr)
    _set_cell(sd, "O48", data.equipo_dial_deformacion)
    _set_cell(sd, "O49", data.equipo_dial_expansion)
    _set_cell(sd, "O50", data.equipo_horno_110)
    _set_cell(sd, "O51", data.equipo_pison)
    _set_cell(sd, "O52", data.equipo_balanza_1g)
    _set_cell(sd, "O53", data.equipo_balanza_01g)

    _set_cell(sd, "D56", data.observaciones)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _build_footer_value_run(text: str, font_size: int = 800) -> etree._Element:
    run = etree.Element(f"{{{NS_A}}}r")
    rpr = etree.SubElement(run, f"{{{NS_A}}}rPr")
    rpr.set("lang", "es-PE")
    rpr.set("sz", str(font_size))
    rpr.set("b", "0")

    latin = etree.SubElement(rpr, f"{{{NS_A}}}latin")
    latin.set("typeface", "Arial")
    latin.set("pitchFamily", "34")
    latin.set("charset", "0")

    cs = etree.SubElement(rpr, f"{{{NS_A}}}cs")
    cs.set("typeface", "Arial")
    cs.set("pitchFamily", "34")
    cs.set("charset", "0")

    t_el = etree.SubElement(run, f"{{{NS_A}}}t")
    t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t_el.text = text
    return run


def _set_footer_value_paragraph(paragraph: etree._Element, value: str, font_size: int = 800) -> None:
    ns = NS_A
    ppr = paragraph.find(f"{{{ns}}}pPr")
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)

    text_value = (value or "").strip()
    if text_value:
        paragraph.append(_build_footer_value_run(text_value, font_size=font_size))
        return

    end_rpr = etree.SubElement(paragraph, f"{{{ns}}}endParaRPr")
    end_rpr.set("lang", "es-PE")
    end_rpr.set("sz", str(font_size))
    end_rpr.set("b", "0")


def _set_footer_fecha_inline(paragraph: etree._Element, value: str) -> None:
    ns = NS_A
    ppr = paragraph.find(f"{{{ns}}}pPr")
    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)

    paragraph.append(_build_footer_value_run("Fecha:", font_size=1000))
    date_text = (value or "").strip()
    if date_text:
        paragraph.append(_build_footer_value_run(f" {date_text}", font_size=800))


def _paragraph_text(paragraph: etree._Element) -> str:
    texts = [(t.text or "").strip() for t in paragraph.findall(f".//{{{NS_A}}}t")]
    return " ".join(part for part in texts if part).strip()


def _fill_drawing(drawing_xml: bytes, data: CBRRequest) -> bytes:
    """Inyecta texto solo en shapes del footer (Revisado/Aprobado)."""
    has_footer = any([data.revisado_por, data.revisado_fecha, data.aprobado_por, data.aprobado_fecha])
    if not has_footer:
        return drawing_xml

    NS = {"xdr": NS_DRAW, "a": NS_A}
    root = etree.fromstring(drawing_xml)

    for anchor in root.findall(".//xdr:twoCellAnchor", NS):
        all_texts = [(t.text or "").strip() for t in anchor.findall(".//a:t", NS)]
        text_blob = " ".join(all_texts)

        is_revisado = "Revisado:" in text_blob
        is_aprobado = "Aprobado:" in text_blob
        if not is_revisado and not is_aprobado:
            continue

        tx_body = anchor.find(".//xdr:txBody", NS)
        if tx_body is None:
            continue

        paragraphs = tx_body.findall("a:p", NS)
        if not paragraphs:
            continue

        label_principal = "Revisado:" if is_revisado else "Aprobado:"
        value_principal = data.revisado_por if is_revisado else data.aprobado_por
        value_fecha = data.revisado_fecha if is_revisado else data.aprobado_fecha

        idx_label_principal: int | None = None
        idx_label_fecha: int | None = None
        for idx, paragraph in enumerate(paragraphs):
            text = _paragraph_text(paragraph)
            if idx_label_principal is None and label_principal in text:
                idx_label_principal = idx
            if idx_label_fecha is None and "Fecha:" in text:
                idx_label_fecha = idx

        if idx_label_principal is not None:
            idx_value_principal = idx_label_principal + 1
            if idx_value_principal >= len(paragraphs):
                new_paragraph = etree.SubElement(tx_body, f"{{{NS_A}}}p")
                ppr = etree.SubElement(new_paragraph, f"{{{NS_A}}}pPr")
                ppr.set("algn", "l")
                paragraphs = tx_body.findall("a:p", NS)
            _set_footer_value_paragraph(paragraphs[idx_value_principal], value_principal or "-", font_size=800)

        if idx_label_fecha is not None:
            _set_footer_fecha_inline(paragraphs[idx_label_fecha], value_fecha or "")
            idx_value_fecha = idx_label_fecha + 1
            if idx_value_fecha < len(paragraphs):
                _set_footer_value_paragraph(paragraphs[idx_value_fecha], "", font_size=800)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
