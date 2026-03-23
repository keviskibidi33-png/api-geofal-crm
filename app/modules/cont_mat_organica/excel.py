"""Excel generator for contenido de materia organica."""

from __future__ import annotations

from lxml import etree

from app.modules.common.excel_xml import NS_SHEET, build_merge_anchor_map, set_cell, transform_template_sheet

from .schemas import ContMatOrganicaRequest

TEMPLATE_FILE = "Template_Cont_Mat_Organica.xlsx"
SHEET_NAME = "PRT. LIVIANAS"


def _fill_sheet(sheet_xml: bytes, payload: ContMatOrganicaRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)
    set_cell(sheet_data, "B13", payload.muestra, merge_anchor_map=merge_anchor_map, style_ref="B13")
    set_cell(sheet_data, "D13", payload.numero_ot, merge_anchor_map=merge_anchor_map, style_ref="D13")
    set_cell(sheet_data, "E13", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map, style_ref="E13")
    set_cell(sheet_data, "F13", payload.realizado_por or "", merge_anchor_map=merge_anchor_map, style_ref="F13")

    set_cell(sheet_data, "F19", payload.crisol_numero or "", merge_anchor_map=merge_anchor_map, style_ref="F19")
    set_cell(sheet_data, "G20", payload.peso_especimen_seco_crisol_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G20")
    set_cell(sheet_data, "G21", payload.peso_especimen_calcinado_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G21")
    set_cell(sheet_data, "G22", payload.peso_crisol_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G22")
    set_cell(sheet_data, "G23", payload.contenido_materia_organica_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G23")

    set_cell(sheet_data, "D30", payload.balanza_0001_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="D30")
    set_cell(sheet_data, "D31", payload.horno_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="D31")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_cont_mat_organica_excel(payload: ContMatOrganicaRequest) -> bytes:
    return transform_template_sheet(TEMPLATE_FILE, SHEET_NAME, lambda xml: _fill_sheet(xml, payload))

