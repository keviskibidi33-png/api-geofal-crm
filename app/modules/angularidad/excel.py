"""Excel generator for angularidad del agregado fino."""

from __future__ import annotations

from lxml import etree

from app.modules.common.excel_xml import NS_SHEET, build_merge_anchor_map, fill_footer_drawing, set_cell, transform_template_sheet

from .schemas import AngularidadRequest

TEMPLATE_FILE = "Template_Angularidad.xlsx"
SHEET_NAME = "Caras Fracturadas"


def _rewrite_formula_refs(root: etree._Element, replacements: dict[str, str]) -> None:
    for formula in root.findall(f".//{{{NS_SHEET}}}f"):
        if formula.text:
            updated = formula.text
            for old_ref, new_ref in replacements.items():
                updated = updated.replace(old_ref, new_ref)
            formula.text = updated


def _fill_sheet(sheet_xml: bytes, payload: AngularidadRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)

    set_cell(sheet_data, "C11", payload.muestra, merge_anchor_map=merge_anchor_map, style_ref="C11")
    set_cell(sheet_data, "D11", payload.numero_ot, merge_anchor_map=merge_anchor_map, style_ref="D11")
    set_cell(sheet_data, "E11", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map, style_ref="E11")
    set_cell(sheet_data, "F11", payload.realizado_por or "", merge_anchor_map=merge_anchor_map, style_ref="F11")

    set_cell(
        sheet_data,
        "C16",
        payload.procedimiento_medicion_vacios or "",
        merge_anchor_map=merge_anchor_map,
        style_ref="C16",
    )
    set_cell(
        sheet_data,
        "G16",
        payload.volumen_cilindro_medida_ml,
        is_number=True,
        merge_anchor_map=merge_anchor_map,
        style_ref="G16",
    )
    set_cell(
        sheet_data,
        "G17",
        payload.masa_cilindro_vacio_g,
        is_number=True,
        merge_anchor_map=merge_anchor_map,
        style_ref="G17",
    )
    set_cell(
        sheet_data,
        "G18",
        payload.gravedad_especifica_agregado_fino_gs,
        is_number=True,
        merge_anchor_map=merge_anchor_map,
        style_ref="G18",
    )

    # Keep workbook formulas working without leaking helper values into the visible header area.
    set_cell(sheet_data, "Z6", payload.volumen_cilindro_medida_ml, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G16")
    set_cell(sheet_data, "Z7", payload.masa_cilindro_vacio_g, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G17")
    set_cell(sheet_data, "Z8", payload.gravedad_especifica_agregado_fino_gs, is_number=True, merge_anchor_map=merge_anchor_map, style_ref="G18")
    _rewrite_formula_refs(root, {"$D$6": "$Z$6", "$D$7": "$Z$7", "$D$8": "$Z$8"})

    method_a_cells = {
        "D24": payload.metodo_a_n8_n16_masa_g,
        "D25": payload.metodo_a_n16_n30_masa_g,
        "D26": payload.metodo_a_n30_n50_masa_g,
        "D27": payload.metodo_a_n50_n100_masa_g,
        "D28": payload.metodo_a_total_masa_g,
        "D31": payload.metodo_a_prueba_1_masa_agregado_cilindro_g,
        "E31": payload.metodo_a_prueba_1_masa_neta_agregado_g,
        "F31": payload.metodo_a_prueba_1_vacio_pct,
        "D32": payload.metodo_a_prueba_2_masa_agregado_cilindro_g,
        "E32": payload.metodo_a_prueba_2_masa_neta_agregado_g,
        "F32": payload.metodo_a_prueba_2_vacio_pct,
        "G32": payload.metodo_a_angularidad_promedio_us_pct,
    }
    for ref, value in method_a_cells.items():
        set_cell(sheet_data, ref, value, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=ref)

    method_b_cells = {
        "D35": payload.metodo_b_n8_n16_masa_g,
        "D36": payload.metodo_b_n16_n30_masa_g,
        "D37": payload.metodo_b_n30_n50_masa_g,
        "D38": payload.metodo_b_total_masa_g,
        "D41": payload.metodo_b_n8_n16_prueba_1_masa_agregado_cilindro_g,
        "E41": payload.metodo_b_n8_n16_prueba_1_masa_neta_agregado_g,
        "F41": payload.metodo_b_n8_n16_prueba_1_vacio_pct,
        "D42": payload.metodo_b_n8_n16_prueba_2_masa_agregado_cilindro_g,
        "E42": payload.metodo_b_n8_n16_prueba_2_masa_neta_agregado_g,
        "F42": payload.metodo_b_n8_n16_prueba_2_vacio_pct,
        "D43": payload.metodo_b_n16_n30_prueba_1_masa_agregado_cilindro_g,
        "E43": payload.metodo_b_n16_n30_prueba_1_masa_neta_agregado_g,
        "F43": payload.metodo_b_n16_n30_prueba_1_vacio_pct,
        "D44": payload.metodo_b_n16_n30_prueba_2_masa_agregado_cilindro_g,
        "E44": payload.metodo_b_n16_n30_prueba_2_masa_neta_agregado_g,
        "F44": payload.metodo_b_n16_n30_prueba_2_vacio_pct,
        "D45": payload.metodo_b_n30_n50_prueba_1_masa_agregado_cilindro_g,
        "E45": payload.metodo_b_n30_n50_prueba_1_masa_neta_agregado_g,
        "F45": payload.metodo_b_n30_n50_prueba_1_vacio_pct,
        "D46": payload.metodo_b_n30_n50_prueba_2_masa_agregado_cilindro_g,
        "E46": payload.metodo_b_n30_n50_prueba_2_masa_neta_agregado_g,
        "F46": payload.metodo_b_n30_n50_prueba_2_vacio_pct,
        "G46": payload.metodo_b_angularidad_promedio_um_pct,
    }
    for ref, value in method_b_cells.items():
        set_cell(sheet_data, ref, value, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=ref)

    method_c_cells = {
        "D49": payload.metodo_c_n8_n200_masa_g,
        "D50": payload.metodo_c_total_masa_g,
        "D53": payload.metodo_c_prueba_1_masa_agregado_cilindro_g,
        "E53": payload.metodo_c_prueba_1_masa_neta_agregado_g,
        "F53": payload.metodo_c_prueba_1_vacio_pct,
        "D54": payload.metodo_c_prueba_2_masa_agregado_cilindro_g,
        "E54": payload.metodo_c_prueba_2_masa_neta_agregado_g,
        "F54": payload.metodo_c_prueba_2_vacio_pct,
        "G54": payload.metodo_c_angularidad_promedio_ur_pct,
    }
    for ref, value in method_c_cells.items():
        set_cell(sheet_data, ref, value, is_number=True, merge_anchor_map=merge_anchor_map, style_ref=ref)

    set_cell(sheet_data, "A58", payload.observaciones or "", merge_anchor_map=merge_anchor_map, style_ref="A58")
    set_cell(sheet_data, "G58", payload.horno_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="G58")
    set_cell(sheet_data, "G59", payload.balanza_01_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="G59")
    set_cell(sheet_data, "G60", payload.tamiz_codigo or "", merge_anchor_map=merge_anchor_map, style_ref="G60")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_angularidad_excel(payload: AngularidadRequest) -> bytes:
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
