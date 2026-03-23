"""Excel generator for particulas livianas."""

from __future__ import annotations

from lxml import etree

from app.modules.common.excel_xml import NS_SHEET, build_merge_anchor_map, set_cell, transform_template_sheet

from .schemas import PartLivianasRequest

TEMPLATE_FILE = "Template_Part_Livinas_Fino_Grueso.xlsx"
SHEET_NAME = "PRT. LIVIANAS"


def _fill_sheet(sheet_xml: bytes, payload: PartLivianasRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)
    set_cell(sheet_data, "C11", payload.muestra, merge_anchor_map=merge_anchor_map, style_ref="C11")
    set_cell(sheet_data, "E11", payload.numero_ot, merge_anchor_map=merge_anchor_map, style_ref="E11")
    set_cell(sheet_data, "F11", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map, style_ref="F11")
    set_cell(sheet_data, "G11", payload.realizado_por or "", merge_anchor_map=merge_anchor_map, style_ref="G11")

    set_cell(sheet_data, "G16", payload.tamano_maximo_nominal or "", merge_anchor_map=merge_anchor_map, style_ref="G16")
    set_cell(sheet_data, "H19", payload.fino_masa_porcion_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="H19")
    set_cell(sheet_data, "H20", payload.fino_masa_flotan_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="H20")
    set_cell(sheet_data, "H21", payload.fino_particulas_livianas_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="H21")

    row_map = {
        25: (payload.grueso_a_masa_porcion_g, payload.grueso_a_masa_flotan_g),
        26: (payload.grueso_b_masa_porcion_g, payload.grueso_b_masa_flotan_g),
        27: (payload.grueso_c_masa_porcion_g, payload.grueso_c_masa_flotan_g),
        28: (payload.grueso_d_masa_porcion_g, payload.grueso_d_masa_flotan_g),
    }
    for row, (masa_porcion, masa_flotan) in row_map.items():
        set_cell(sheet_data, f"F{row}", masa_porcion, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"F{row}")
        set_cell(sheet_data, f"G{row}", masa_flotan, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=f"G{row}")

    set_cell(sheet_data, "F29", payload.grueso_suma_masa_porcion_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="F29")
    set_cell(sheet_data, "G29", payload.grueso_suma_masa_flotan_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G29")
    set_cell(sheet_data, "F30", payload.grueso_particulas_livianas_pct, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="F30")
    set_cell(sheet_data, "B49", f"Revisado: {payload.revisado_por or '-'}", merge_anchor_map=merge_anchor_map, style_ref="B49")
    set_cell(sheet_data, "B50", f"Fecha: {payload.revisado_fecha or payload.fecha_ensayo or '-'}", merge_anchor_map=merge_anchor_map, style_ref="B50")
    set_cell(sheet_data, "D49", f"Aprobado: {payload.aprobado_por or '-'}", merge_anchor_map=merge_anchor_map, style_ref="D49")
    set_cell(sheet_data, "D50", f"Fecha: {payload.aprobado_fecha or payload.fecha_ensayo or '-'}", merge_anchor_map=merge_anchor_map, style_ref="D50")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_part_livianas_excel(payload: PartLivianasRequest) -> bytes:
    return transform_template_sheet(TEMPLATE_FILE, SHEET_NAME, lambda xml: _fill_sheet(xml, payload))
