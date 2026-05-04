from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .schemas import HumedadCompleteDemoRequest

logger = logging.getLogger(__name__)

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _find_template() -> str:
    filename = "Template_Humedad_Complete.xlsx"
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]
    for path in (
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ):
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
    row = etree.SubElement(sheet_data, f"{{{NS_SHEET}}}row")
    row.set("r", str(row_num))
    return row


def _find_or_create_cell(row: etree._Element, cell_ref: str) -> etree._Element:
    for cell in row.findall(f"{{{NS_SHEET}}}c"):
        if cell.get("r") == cell_ref:
            return cell
    col, _ = _parse_cell_ref(cell_ref)
    col_num = _col_letter_to_num(col)
    insert_pos = None
    for idx, ex in enumerate(row.findall(f"{{{NS_SHEET}}}c")):
        ex_col, _ = _parse_cell_ref(ex.get("r"))
        if col_num < _col_letter_to_num(ex_col):
            insert_pos = idx
            break
    cell = etree.Element(f"{{{NS_SHEET}}}c")
    cell.set("r", cell_ref)
    if insert_pos is None:
        row.append(cell)
    else:
        row.insert(insert_pos, cell)
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
        v = etree.SubElement(cell, f"{{{NS_SHEET}}}v")
        v.text = str(value)
        return
    text = str(value)
    cell.set("t", "inlineStr")
    is_el = etree.SubElement(cell, f"{{{NS_SHEET}}}is")
    t_el = etree.SubElement(is_el, f"{{{NS_SHEET}}}t")
    if "\n" in text or text.endswith(" "):
        t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t_el.text = text


def _num(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_metodo(data: HumedadCompleteDemoRequest) -> str:
    metodo = (data.metodo_prueba or "-").strip().upper()
    if metodo in {"A", "B"}:
        return metodo
    if data.metodo_a and not data.metodo_b:
        return "A"
    if data.metodo_b and not data.metodo_a:
        return "B"
    if data.metodo_a and data.metodo_b:
        return "A"
    return "-"


def _compute_metrics(data: HumedadCompleteDemoRequest) -> tuple[float | None, float | None, float | None]:
    masa_humeda = _num(data.masa_recipiente_muestra_humeda)
    masa_seca = _num(data.masa_recipiente_muestra_seca)
    masa_constante = _num(data.masa_recipiente_muestra_seca_constante)
    recipiente = _num(data.masa_recipiente)
    masa_agua = _num(data.masa_agua)
    masa_muestra_seca = _num(data.masa_muestra_seca)
    humedad = _num(data.contenido_humedad)

    if masa_agua is None and masa_humeda is not None and masa_constante is not None:
        masa_agua = round(masa_humeda - masa_constante, 3)
    if masa_muestra_seca is None and masa_constante is not None and recipiente is not None:
        masa_muestra_seca = round(masa_constante - recipiente, 3)
    if humedad is None and masa_agua is not None and masa_muestra_seca not in (None, 0):
        humedad = round((masa_agua / masa_muestra_seca) * 100, 3)
    return masa_agua, masa_muestra_seca, humedad


def _fill_sheet(sheet_xml: bytes, data: HumedadCompleteDemoRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sd = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sd is None:
        return sheet_xml

    masa_agua, masa_muestra_seca, humedad = _compute_metrics(data)

    # Encabezado
    _set_cell(sd, "D11", data.codigo_muestra)
    _set_cell(sd, "E11", data.ot_n)
    _set_cell(sd, "G11", data.fecha_ejecucion)
    _set_cell(sd, "I11", data.realizado_por)

    # Lateral derecho
    _set_cell(sd, "P2", data.cliente)
    _set_cell(sd, "P3", data.direccion)
    _set_cell(sd, "P4", data.proyecto)
    _set_cell(sd, "P5", data.ubicacion)
    _set_cell(sd, "P7", data.recepcion_n)
    _set_cell(sd, "P8", data.f_emision)
    _set_cell(sd, "P9", data.ot_n)
    _set_cell(sd, "P12", data.fecha_recepcion)
    _set_cell(sd, "P13", data.fecha_ejecucion)
    _set_cell(sd, "P15", data.cantera_sondaje)
    _set_cell(sd, "P16", data.n_muestra)
    _set_cell(sd, "P17", data.tipo_muestra)

    # Condiciones / descripción / método
    _set_cell(sd, "J18", data.condicion_masa_menor)
    _set_cell(sd, "J19", data.condicion_capas)
    _set_cell(sd, "J20", data.condicion_temperatura)
    _set_cell(sd, "J21", data.condicion_excluido)
    if data.descripcion_material_excluido:
        _set_cell(sd, "A22", f"Descripción material excluido: {data.descripcion_material_excluido}")

    _set_cell(sd, "E25", data.tipo_muestra)
    _set_cell(sd, "E26", data.condicion_muestra)
    _set_cell(sd, "E27", data.tamano_maximo_particula)
    _set_cell(sd, "E28", data.forma_particula)
    _set_cell(sd, "J26", _resolve_metodo(data))

    # Tabla principal
    _set_cell(sd, "I31", data.numero_ensayo, is_number=True)
    _set_cell(sd, "I32", data.recipiente_numero)
    _set_cell(sd, "I33", data.masa_recipiente_muestra_humeda, is_number=True)
    _set_cell(sd, "I34", data.masa_recipiente_muestra_seca, is_number=True)
    _set_cell(sd, "I35", data.masa_recipiente_muestra_seca_constante, is_number=True)
    _set_cell(sd, "I36", data.masa_recipiente, is_number=True)
    _set_cell(sd, "I37", masa_agua, is_number=True)
    _set_cell(sd, "I38", masa_muestra_seca, is_number=True)
    _set_cell(sd, "I39", humedad, is_number=True)

    # Equipo / observaciones
    _set_cell(sd, "J42", data.equipo_balanza_01)
    _set_cell(sd, "J43", data.equipo_balanza_001)
    _set_cell(sd, "J45", data.equipo_horno)
    if data.observaciones:
        _set_cell(sd, "D52", data.observaciones)

    # Footer en celdas combinadas
    revisado_fecha = data.revisado_fecha or data.f_emision or ""
    aprobado_fecha = data.aprobado_fecha or data.f_emision or ""
    _set_cell(sd, "C55", f"Revisado:\n{data.revisado_por or '-'}\nFecha: {revisado_fecha}")
    _set_cell(sd, "G55", f"Aprobado:\n{data.aprobado_por or '-'}\nFecha: {aprobado_fecha}")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _force_recalc(workbook_xml: bytes) -> bytes:
    try:
        root = etree.fromstring(workbook_xml)
        calc_pr = root.find(f".//{{{NS_SHEET}}}calcPr")
        if calc_pr is None:
            calc_pr = etree.SubElement(root, f"{{{NS_SHEET}}}calcPr")
        calc_pr.set("fullCalcOnLoad", "1")
        calc_pr.set("forceFullCalc", "1")
        calc_pr.set("calcOnSave", "1")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    except Exception:
        logger.warning("No se pudo ajustar calcPr del workbook", exc_info=True)
        return workbook_xml


def generate_humedad_complete_demo_excel(data: HumedadCompleteDemoRequest) -> bytes:
    logger.info("Generando Excel Humedad Complete Demo")
    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template no encontrado: {TEMPLATE_PATH}")

    template_bytes = Path(TEMPLATE_PATH).read_bytes()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            raw = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet2.xml":
                raw = _fill_sheet(raw, data)
            elif item.filename == "xl/workbook.xml":
                raw = _force_recalc(raw)
            zout.writestr(item, raw)
    output.seek(0)
    return output.read()
