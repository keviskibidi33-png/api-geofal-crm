"""Excel generator for azul de metileno."""

from __future__ import annotations

from lxml import etree

from app.modules.common.excel_xml import NS_SHEET, build_merge_anchor_map, set_cell, transform_template_sheet

from .schemas import AzulMetilenoRequest

TEMPLATE_FILE = "Template_Azul_Metileno.xlsx"
SHEET_NAME = "AZUL DE METILENO"


def _fill_sheet(sheet_xml: bytes, payload: AzulMetilenoRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)
    set_cell(sheet_data, "B11", payload.muestra, merge_anchor_map=merge_anchor_map, style_ref="B11")
    set_cell(sheet_data, "D11", payload.numero_ot, merge_anchor_map=merge_anchor_map, style_ref="D11")
    set_cell(sheet_data, "E11", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map, style_ref="E11")
    set_cell(sheet_data, "F11", payload.realizado_por or "", merge_anchor_map=merge_anchor_map, style_ref="F11")

    set_cell(sheet_data, "F17", payload.concentracion_solucion_mg_ml, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="F17")
    set_cell(sheet_data, "F18", payload.solucion_usada_ml, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="F18")
    set_cell(sheet_data, "F19", payload.material_seco_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="F19")
    set_cell(sheet_data, "F20", payload.material_seco_constante_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="F20")
    set_cell(sheet_data, "F21", payload.valor_azul_metileno_mg_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="F21")

    set_cell(sheet_data, "H29", payload.balanza_0001_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="H29")
    set_cell(sheet_data, "H30", payload.horno_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="H30")
    set_cell(sheet_data, "B34", payload.observaciones or "", merge_anchor_map=merge_anchor_map, style_ref="B34")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_azul_metileno_excel(payload: AzulMetilenoRequest) -> bytes:
    return transform_template_sheet(TEMPLATE_FILE, SHEET_NAME, lambda xml: _fill_sheet(xml, payload))

