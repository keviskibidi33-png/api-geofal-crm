"""Excel generator for sulfato de magnesio."""

from __future__ import annotations

from lxml import etree

from app.modules.common.excel_xml import NS_SHEET, build_merge_anchor_map, fill_footer_drawing, set_cell, transform_template_sheet

from .schemas import SulMagnesioRequest

TEMPLATE_FILE = "Template_Sul_Magnesio.xlsx"
SHEET_NAME = "DURAB MAGNESIO"


def _fill_sheet(sheet_xml: bytes, payload: SulMagnesioRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)
    set_cell(sheet_data, "D12", payload.muestra, merge_anchor_map=merge_anchor_map, style_ref="D12")
    set_cell(sheet_data, "F12", payload.numero_ot, merge_anchor_map=merge_anchor_map, style_ref="F12")
    set_cell(sheet_data, "H12", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map, style_ref="H12")
    set_cell(sheet_data, "J12", payload.realizado_por or "", merge_anchor_map=merge_anchor_map, style_ref="J12")

    for index, row in enumerate(payload.fino_rows, start=20):
        set_cell(sheet_data, f"D{index}", row.gradacion_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"D{index}")
        set_cell(sheet_data, f"E{index}", row.masa_fraccion_ensayo_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"E{index}")
        set_cell(sheet_data, f"F{index}", row.masa_material_retenido_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"F{index}")
        set_cell(sheet_data, f"G{index}", row.masa_perdida_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"G{index}")
        set_cell(sheet_data, f"H{index}", row.pct_pasa_post_ensayo, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"H{index}")
        set_cell(sheet_data, f"I{index}", row.pct_perdida_ponderado, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"I{index}")
    set_cell(sheet_data, "I25", payload.fino_total_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="I25")

    for index, row in enumerate(payload.grueso_rows, start=31):
        set_cell(sheet_data, f"D{index}", row.gradacion_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"D{index}")
        set_cell(sheet_data, f"E{index}", row.masa_individual_tamiz_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"E{index}")
        set_cell(sheet_data, f"F{index}", row.masa_fraccion_ensayo_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"F{index}")
        set_cell(sheet_data, f"G{index}", row.masa_material_retenido_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"G{index}")
        set_cell(sheet_data, f"H{index}", row.masa_perdida_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"H{index}")
        set_cell(sheet_data, f"I{index}", row.pct_pasa_post_ensayo, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"I{index}")
        set_cell(sheet_data, f"J{index}", row.pct_perdida_ponderado, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"J{index}")
    set_cell(sheet_data, "J38", payload.grueso_total_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="J38")

    for row_index, row in enumerate(payload.cualitativo_rows, start=45):
        set_cell(sheet_data, f"D{row_index}", row.total_particulas, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"D{row_index}")
        set_cell(sheet_data, f"E{row_index}", row.rajadas_num, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"E{row_index}")
        set_cell(sheet_data, f"F{row_index}", row.rajadas_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"F{row_index}")
        set_cell(sheet_data, f"G{row_index}", row.desmoronadas_num, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"G{row_index}")
        set_cell(sheet_data, f"H{row_index}", row.desmoronadas_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"H{row_index}")
        set_cell(sheet_data, f"I{row_index}", row.fracturadas_num, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"I{row_index}")
        set_cell(sheet_data, f"J{row_index}", row.fracturadas_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"J{row_index}")
        set_cell(sheet_data, f"K{row_index}", row.astilladas_num, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"K{row_index}")
        set_cell(sheet_data, f"L{row_index}", row.astilladas_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"L{row_index}")

    set_cell(sheet_data, "J50", payload.horno_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="J50")
    set_cell(sheet_data, "J51", payload.balanza_01_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="J51")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_sul_magnesio_excel(payload: SulMagnesioRequest) -> bytes:
    return transform_template_sheet(
        TEMPLATE_FILE,
        SHEET_NAME,
        lambda xml: _fill_sheet(xml, payload),
        drawing_transform=lambda xml: fill_footer_drawing(
            xml,
            revisado_por=payload.revisado_por,
            revisado_fecha=payload.revisado_fecha or payload.fecha_ensayo,
            aprobado_por=payload.aprobado_por,
            aprobado_fecha=payload.aprobado_fecha or payload.fecha_ensayo,
        ),
    )
