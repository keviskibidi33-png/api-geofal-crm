"""Excel generator for impurezas organicas."""

from __future__ import annotations

from lxml import etree

from app.modules.common.excel_xml import NS_SHEET, build_merge_anchor_map, fill_footer_drawing, set_cell, transform_template_sheet

from .schemas import COLOR_GARDNER_MAP, ImpOrganicasRequest

TEMPLATE_FILE = "Template_Imp_Organicas.xlsx"
SHEET_NAME = "PRT. LIVIANAS"


def _fill_sheet(sheet_xml: bytes, payload: ImpOrganicasRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)
    set_cell(sheet_data, "B12", payload.muestra, merge_anchor_map=merge_anchor_map, style_ref="B12")
    set_cell(sheet_data, "D12", payload.numero_ot, merge_anchor_map=merge_anchor_map, style_ref="D12")
    set_cell(sheet_data, "F12", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map, style_ref="F12")
    set_cell(sheet_data, "H12", payload.realizado_por or "", merge_anchor_map=merge_anchor_map, style_ref="H12")

    set_cell(sheet_data, "G17", payload.tamano_particula or "", merge_anchor_map=merge_anchor_map, style_ref="G17")
    set_cell(sheet_data, "G18", payload.fecha_inicio_ensayo or "", merge_anchor_map=merge_anchor_map, style_ref="G18")
    set_cell(sheet_data, "G19", payload.fecha_fin_ensayo or "", merge_anchor_map=merge_anchor_map, style_ref="G19")
    set_cell(sheet_data, "G20", payload.temperatura_solucion_c, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G20")

    for color_num, row in {1: 24, 2: 25, 3: 26, 4: 27, 5: 28}.items():
        marker = "X" if payload.color_placa_organica == color_num else ""
        set_cell(sheet_data, f"H{row}", marker, merge_anchor_map=merge_anchor_map, style_ref=f"H{row}")
        if payload.color_placa_organica == color_num:
            set_cell(sheet_data, "K23", COLOR_GARDNER_MAP[color_num], is_number=True, merge_anchor_map=merge_anchor_map, style_ref="K23")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_imp_organicas_excel(payload: ImpOrganicasRequest) -> bytes:
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
