"""
Excel generator for Granulometría de Suelos (ASTM D6913/D6913M-17).

ZIP/XML strategy to preserve styles, merged cells and drawings from the
official template.
"""

from __future__ import annotations

import io
import logging
import zipfile
from copy import deepcopy
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


def _col_num_to_letter(num: int) -> str:
    result = ""
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def _build_merge_anchor_map(root: etree._Element) -> dict[str, str]:
    anchor_map: dict[str, str] = {}
    merge_cells = root.find(f".//{{{NS_SHEET}}}mergeCells")
    if merge_cells is None:
        return anchor_map

    for merge_cell in merge_cells.findall(f"{{{NS_SHEET}}}mergeCell"):
        ref = merge_cell.get("ref")
        if not ref:
            continue
        if ":" not in ref:
            anchor_map[ref] = ref
            continue

        start_ref, end_ref = ref.split(":", 1)
        start_col, start_row = _parse_cell_ref(start_ref)
        end_col, end_row = _parse_cell_ref(end_ref)
        start_col_num = _col_letter_to_num(start_col)
        end_col_num = _col_letter_to_num(end_col)
        anchor_ref = f"{start_col}{start_row}"

        for row_num in range(start_row, end_row + 1):
            for col_num in range(start_col_num, end_col_num + 1):
                anchor_map[f"{_col_num_to_letter(col_num)}{row_num}"] = anchor_ref

    return anchor_map


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


def _set_cell(
    sheet_data: etree._Element,
    ref: str,
    value: Any,
    is_number: bool = False,
    merge_anchor_map: dict[str, str] | None = None,
    style_id: int | None = None,
    font_size: float | None = None,
) -> None:
    if value is None:
        return

    target_ref = merge_anchor_map.get(ref, ref) if merge_anchor_map else ref

    _, row_num = _parse_cell_ref(target_ref)
    row = _find_or_create_row(sheet_data, row_num)
    cell = _find_or_create_cell(row, target_ref)

    if style_id is not None:
        cell.set("s", str(style_id))

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
    if font_size is not None:
        run_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}r")
        rpr_el = etree.SubElement(run_el, f"{{{NS_SHEET}}}rPr")
        font_el = etree.SubElement(rpr_el, f"{{{NS_SHEET}}}rFont")
        font_el.set("val", "Arial")
        sz_el = etree.SubElement(rpr_el, f"{{{NS_SHEET}}}sz")
        sz_el.set("val", str(font_size))
        t_el = etree.SubElement(run_el, f"{{{NS_SHEET}}}t")
    else:
        t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
    t_el.text = text


def _ensure_centered_weight_style(styles_xml: bytes, base_style_id: int = 112) -> tuple[bytes, int | None]:
    root = etree.fromstring(styles_xml)
    cell_xfs = root.find(f".//{{{NS_SHEET}}}cellXfs")
    if cell_xfs is None:
        return styles_xml, None

    xfs = cell_xfs.findall(f"{{{NS_SHEET}}}xf")
    if base_style_id >= len(xfs):
        return styles_xml, None

    base_xf = xfs[base_style_id]
    centered_xf = deepcopy(base_xf)

    for child in list(centered_xf):
        if child.tag == f"{{{NS_SHEET}}}alignment":
            centered_xf.remove(child)

    base_alignment = base_xf.find(f"{{{NS_SHEET}}}alignment")
    alignment_attrs = dict(base_alignment.attrib) if base_alignment is not None else {}
    alignment_attrs["horizontal"] = "center"
    if "vertical" not in alignment_attrs:
        alignment_attrs["vertical"] = "center"

    alignment_el = etree.SubElement(centered_xf, f"{{{NS_SHEET}}}alignment")
    for key, val in alignment_attrs.items():
        alignment_el.set(key, val)

    centered_xf.set("applyAlignment", "1")

    def _serialize_xf(xf: etree._Element) -> bytes:
        return etree.tostring(xf, encoding="utf-8")

    target_sig = _serialize_xf(centered_xf)
    for idx, xf in enumerate(xfs):
        if _serialize_xf(xf) == target_sig:
            return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), idx

    new_style_id = len(xfs)
    cell_xfs.append(centered_xf)
    cell_xfs.set("count", str(new_style_id + 1))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), new_style_id


def _fill_sheet(
    sheet_xml: bytes,
    data: GranSueloRequest,
    centered_weight_style_id: int | None = None,
) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    merge_anchor_map = _build_merge_anchor_map(root)

    def set_cell(
        ref: str,
        value: Any,
        is_number: bool = False,
        style_id: int | None = None,
        font_size: float | None = None,
    ) -> None:
        _set_cell(
            sd,
            ref,
            value,
            is_number=is_number,
            merge_anchor_map=merge_anchor_map,
            style_id=style_id,
            font_size=font_size,
        )

    # Encabezado
    set_cell("D11", data.muestra)
    set_cell("F11", data.numero_ot)
    set_cell("H11", data.fecha_ensayo)
    set_cell("J11", data.realizado_por)

    # Método / tipo / muestreo
    if data.metodo_prueba == "A":
        set_cell("B17", "X")
    if data.metodo_prueba == "B":
        set_cell("B18", "X")

    if data.tamizado_tipo == "FRACCIONADO":
        set_cell("B21", "X")
    if data.tamizado_tipo == "GLOBAL":
        set_cell("B22", "X")

    if data.metodo_muestreo == "HUMEDO":
        set_cell("C25", "X")
    if data.metodo_muestreo == "SECADO AL AIRE":
        set_cell("C26", "X")
    if data.metodo_muestreo == "SECADO AL HORNO":
        set_cell("C27", "X")

    # Descripción de muestra
    set_cell("J17", data.descripcion_turbo_organico)
    set_cell("H17", data.tipo_muestra)
    set_cell("H18", data.condicion_muestra if data.condicion_muestra != "-" else None)
    set_cell("H19", data.tamano_maximo_particula_in)
    set_cell("H20", data.forma_particula)
    set_cell("K20", data.tamiz_separador)

    # Tamizado compuesto/global
    set_cell("H23", data.masa_seca_porcion_gruesa_cp_md_g, is_number=True)
    set_cell("H24", data.masa_humeda_porcion_fina_fp_mm_g, is_number=True)
    set_cell("H25", data.masa_seca_porcion_fina_fp_md_g, is_number=True)
    set_cell("H26", data.masa_seca_muestra_s_md_g, is_number=True)

    set_cell("K23", data.masa_seca_global_g, is_number=True)
    set_cell("K25", data.subespecie_masa_humeda_g, is_number=True)
    set_cell("K26", data.subespecie_masa_seca_g, is_number=True)
    set_cell("K27", data.contenido_agua_wfp_pct, is_number=True)

    # Pérdida aceptable durante lavado/tamizado
    set_cell("K30", data.masa_porcion_gruesa_lavada_cpwmd_g, is_number=True)
    set_cell("K31", data.masa_retenida_plato_cpmrpan_g, is_number=True)
    set_cell("K32", data.perdida_cpl_pct, is_number=True)
    set_cell("K33", data.masa_subespecimen_lavado_fina_g, is_number=True)
    # K34 pertenece al texto de criterio de aceptabilidad (no debe llenarse con datos).

    # Clasificación / incidencias
    set_cell("B31", data.clasificacion_visual_simbolo)
    set_cell("B32", data.clasificacion_visual_nombre)
    set_cell("C35", data.excluyo_material_descripcion, font_size=8)
    set_cell("C38", data.problema_descripcion, font_size=8)

    if data.proceso_dispersion == "MANUAL":
        set_cell("E38", "Manual X")
    elif data.proceso_dispersion == "BAÑO ULTRASÓNICO":
        set_cell("F38", "Baño ultrasónico X")
    elif data.proceso_dispersion == "APARATO DE AGITACIÓN":
        set_cell("H38", "Aparato de agitación X")

    set_cell("K39", data.masa_retenida_primer_tamiz_g, is_number=True)

    # Pesos por tamiz
    for idx, row_num in enumerate(SIEVE_ROWS):
        set_cell(
            f"E{row_num}",
            data.masa_retenida_tamiz_g[idx],
            is_number=True,
            style_id=centered_weight_style_id,
        )

    # Equipos / observaciones
    set_cell("I51", data.balanza_01g_codigo)
    set_cell("I52", data.horno_110_codigo)
    set_cell("G55", data.observaciones)

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
                replacements["Fecha"] = data.revisado_fecha
        elif is_aprobado:
            if data.aprobado_por:
                replacements["Aprobado:"] = data.aprobado_por
            if data.aprobado_fecha:
                replacements["Fecha:"] = data.aprobado_fecha
                replacements["Fecha"] = data.aprobado_fecha

        for run in anchor.findall(".//a:r", ns):
            t_el = run.find("a:t", ns)
            if t_el is None or t_el.text is None:
                continue
            text = t_el.text.strip()
            if text in replacements and replacements[text]:
                t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if "Fecha" in text:
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
        centered_weight_style_id: int | None = None
        styles_xml = None
        if "xl/styles.xml" in zin.namelist():
            styles_original = zin.read("xl/styles.xml")
            styles_xml, centered_weight_style_id = _ensure_centered_weight_style(styles_original, base_style_id=112)

        sheet_original = zin.read("xl/worksheets/sheet1.xml")
        sheet_xml = _fill_sheet(sheet_original, data, centered_weight_style_id=centered_weight_style_id)

        for item in zin.infolist():
            if item.filename == "xl/worksheets/sheet1.xml":
                raw = sheet_xml
            elif item.filename == "xl/styles.xml" and styles_xml is not None:
                raw = styles_xml
            else:
                raw = zin.read(item.filename)

            if item.filename.startswith("xl/drawings/drawing") and item.filename.endswith(".xml"):
                raw = _fill_drawing(raw, data)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
