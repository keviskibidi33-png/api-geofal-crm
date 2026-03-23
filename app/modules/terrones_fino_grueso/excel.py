"""Excel generator for terrones fino/grueso."""

from __future__ import annotations

from lxml import etree

from app.modules.common.excel_xml import NS_SHEET, build_merge_anchor_map, fill_footer_drawing, set_cell, transform_template_sheet

from .schemas import TerronesFinoGruesoRequest

TEMPLATE_FILE = "Template_Terrones_Fino_Grueso.xlsx"
SHEET_NAME = "TERRONES DE ARCILLA"


def _fill_sheet(sheet_xml: bytes, payload: TerronesFinoGruesoRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)
    set_cell(sheet_data, "B11", payload.muestra, merge_anchor_map=merge_anchor_map, style_ref="B11")
    set_cell(sheet_data, "D11", payload.numero_ot, merge_anchor_map=merge_anchor_map, style_ref="D11")
    set_cell(sheet_data, "F11", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map, style_ref="F11")
    set_cell(sheet_data, "H11", payload.realizado_por or "", merge_anchor_map=merge_anchor_map, style_ref="H11")

    row_map = {
        19: "grueso_a",
        20: "grueso_b",
        21: "grueso_c",
        22: "grueso_d",
        28: "fino",
    }
    for row, prefix in row_map.items():
        set_cell(sheet_data, f"D{row}", getattr(payload, f"{prefix}_masa_antes_g"), is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"D{row}")
        set_cell(sheet_data, f"E{row}", getattr(payload, f"{prefix}_masa_seca_despues_g"), is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"E{row}")
        set_cell(sheet_data, f"F{row}", getattr(payload, f"{prefix}_masa_constante_g"), is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"F{row}")
        set_cell(sheet_data, f"G{row}", getattr(payload, f"{prefix}_perdida_g"), is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"G{row}")
        set_cell(sheet_data, f"H{row}", getattr(payload, f"{prefix}_pct"), is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"H{row}")

    set_cell(sheet_data, "H23", payload.grueso_total_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="H23")
    set_cell(sheet_data, "H29", payload.fino_total_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="H29")
    set_cell(sheet_data, "F31", payload.secado_horno or "", merge_anchor_map=merge_anchor_map, style_ref="F31")
    set_cell(sheet_data, "H34", payload.balanza_01_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="H34")
    set_cell(sheet_data, "H35", payload.horno_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="H35")
    set_cell(sheet_data, "D40", payload.observaciones or "", merge_anchor_map=merge_anchor_map, style_ref="D40")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_terrones_fino_grueso_excel(payload: TerronesFinoGruesoRequest) -> bytes:
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
