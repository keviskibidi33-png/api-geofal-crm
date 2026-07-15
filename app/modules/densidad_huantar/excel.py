from __future__ import annotations

import io
import logging
import zipfile
from datetime import date
from typing import Any
from lxml import etree

from app.modules.common.excel_xml import (
    NS_SHEET,
    build_merge_anchor_map,
    set_cell,
    enable_full_recalc_on_open,
    remove_calc_chain_relationships,
    remove_calc_chain_content_type,
    remove_external_link_relationships,
    remove_external_link_content_types,
    strip_external_references,
    fill_footer_drawing,
    find_template_path,
)
from .schemas import DensidadHuantarRequest

logger = logging.getLogger(__name__)

TEMPLATE_FILE = "informes/Proyecto Huantar/Densidad Huanta/1-INF.-N-001-26-SU06-DEN-V05.xlsx"


def _fill_sheet1(sheet_xml: bytes, payload: DensidadHuantarRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)
    data = payload.model_dump(mode="json")

    # Cabecera general (Lado derecho de la hoja F LEM1)
    set_cell(sheet_data, "M2", payload.cliente or data.get("cliente") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M3", data.get("direccion") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M4", data.get("proyecto") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M5", data.get("ubicacion") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M7", data.get("recepcion_n") or data.get("numero_recepcion") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M8", data.get("fecha_emision") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M9", payload.numero_ot, merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M11", data.get("codigo_muestra") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M12", data.get("fecha_recepcion") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M13", payload.fecha_ensayo or data.get("fecha_ejecucion") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M15", data.get("cantera_sondaje") or data.get("cantera") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M16", data.get("numero_muestra") or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "M17", data.get("tipo_muestra") or "", merge_anchor_map=merge_anchor_map)

    # Cabecera principal izquierda (OT, Fecha, Realizado por) — fila 7
    set_cell(sheet_data, "D7", payload.numero_ot, merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "F7", payload.fecha_ensayo, merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "G7", payload.realizado_por or "", merge_anchor_map=merge_anchor_map)

    # Calibraciones / Proctor
    set_cell(sheet_data, "D18", payload.cono_codigo or "", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "D19", payload.masa_arena_embudo, is_number=True, merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "D20", payload.densidad_arena, is_number=True, merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "D21", payload.volumen_cono, is_number=True, merge_anchor_map=merge_anchor_map)

    set_cell(sheet_data, "H18", payload.proctor_norma or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H19", payload.proctor_metodo or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H20", payload.peso_unitario_seco_lab, is_number=True, merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H21", payload.humedad_optima, is_number=True, merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H22", payload.gravedad_especifica, is_number=True, merge_anchor_map=merge_anchor_map)

    # Condiciones ambientales
    set_cell(sheet_data, "D24", payload.temperatura_inicial or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H24", payload.temperatura_final or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "D25", payload.humedad_relativa_inicial or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H25", payload.humedad_relativa_final or "-", merge_anchor_map=merge_anchor_map)

    # Códigos de equipos utilizados
    set_cell(sheet_data, "F41", payload.eq_balanza_30kg or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H41", payload.eq_pesa_patron_5kg or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "F42", payload.eq_cono_equipo or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H42", payload.eq_tamiz_3_4 or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "F43", payload.eq_termohigrometro or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H43", payload.eq_tamiz_4 or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "F44", payload.eq_pesa_patron_200g or "-", merge_anchor_map=merge_anchor_map)
    set_cell(sheet_data, "H44", payload.eq_tamiz_3_8 or "-", merge_anchor_map=merge_anchor_map)

    # Observaciones
    set_cell(sheet_data, "B46", payload.observaciones or "", merge_anchor_map=merge_anchor_map)

    # Puntos metadata (Punto 1: F, Punto 2: G, Punto 3: H, Punto 4: I)
    cols = ["F", "G", "H", "I"]
    for idx, col in enumerate(cols):
        if idx < len(payload.puntos):
            punto = payload.puntos[idx]
            set_cell(sheet_data, f"{col}30", punto.ubicacion or "", merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}31", punto.progresiva or "", merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}32", punto.tipo_muestra or "", merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}33", punto.espesor_capa, is_number=True, merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}34", punto.tamano_maximo or "", merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}35", punto.tamiz_sobretamano or "", merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}36", punto.descripcion_visual or "", merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}37", punto.condiciones_entorno or "", merge_anchor_map=merge_anchor_map)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_sheet2(sheet_xml: bytes, payload: DensidadHuantarRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)

    # Puntos mediciones en F LEM2 (Punto 1: E, Punto 2: F, Punto 3: G, Punto 4: H)
    cols = ["E", "F", "G", "H"]
    for idx, col in enumerate(cols):
        if idx < len(payload.puntos):
            punto = payload.puntos[idx]
            set_cell(sheet_data, f"{col}12", punto.masa_inicial_cono, is_number=True, merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}13", punto.masa_residual_cono, is_number=True, merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}18", punto.masa_humeda_orificio, is_number=True, merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}20", punto.masa_sobretamano, is_number=True, merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}30", punto.criterio_aceptacion, is_number=True, merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}33", punto.humedad_speedy, is_number=True, merge_anchor_map=merge_anchor_map)
            set_cell(sheet_data, f"{col}34", punto.humedad_astm, is_number=True, merge_anchor_map=merge_anchor_map)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _fill_sheet3(sheet_xml: bytes, payload: DensidadHuantarRequest) -> bytes:
    root = etree.fromstring(sheet_xml)
    sheet_data = root.find(f".//{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        return sheet_xml

    merge_anchor_map = build_merge_anchor_map(root)

    # Tamiz del sobretamaño en DENSIDAD sheet (Punto 1: G, Punto 2: H, Punto 3: I, Punto 4: J)
    cols = ["G", "H", "I", "J"]
    for idx, col in enumerate(cols):
        if idx < len(payload.puntos):
            punto = payload.puntos[idx]
            set_cell(sheet_data, f"{col}31", punto.tamiz_sobretamano or "", merge_anchor_map=merge_anchor_map)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def generate_densidad_huantar_excel(payload: DensidadHuantarRequest) -> bytes:
    template_path = find_template_path(TEMPLATE_FILE)
    if not template_path.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_path}")

    with open(template_path, "rb") as f:
        template_bytes = f.read()

    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            # Omitir calcChain y enlaces externos para evitar advertencias de fórmulas rotas
            if item.filename == "xl/calcChain.xml":
                continue
            if item.filename.startswith("xl/externalLinks/"):
                continue

            raw = zin.read(item.filename)

            # Inyectar datos en las hojas correspondientes
            if item.filename == "xl/worksheets/sheet1.xml":
                raw = _fill_sheet1(raw, payload)
            elif item.filename == "xl/worksheets/sheet2.xml":
                raw = _fill_sheet2(raw, payload)
            elif item.filename == "xl/worksheets/sheet3.xml":
                raw = _fill_sheet3(raw, payload)

            # Inyectar firmas/firmas de footer en drawings
            elif item.filename == "xl/drawings/drawing1.xml":
                raw = fill_footer_drawing(
                    raw,
                    revisado_por=payload.revisado_por,
                    revisado_fecha=payload.revisado_fecha or payload.fecha_ensayo,
                    aprobado_por=payload.aprobado_por,
                    aprobado_fecha=payload.aprobado_fecha or payload.fecha_ensayo,
                )
            elif item.filename == "xl/drawings/drawing2.xml":
                raw = fill_footer_drawing(
                    raw,
                    revisado_por=payload.revisado_por,
                    revisado_fecha=payload.revisado_fecha or payload.fecha_ensayo,
                    aprobado_por=payload.aprobado_por,
                    aprobado_fecha=payload.aprobado_fecha or payload.fecha_ensayo,
                )

            # Forzar recálculo completo de fórmulas al abrir el archivo
            elif item.filename == "xl/workbook.xml":
                raw = enable_full_recalc_on_open(raw)
                raw = strip_external_references(raw)
            elif item.filename == "xl/_rels/workbook.xml.rels":
                raw = remove_calc_chain_relationships(raw)
                raw = remove_external_link_relationships(raw)
            elif item.filename == "[Content_Types].xml":
                raw = remove_calc_chain_content_type(raw)
                raw = remove_external_link_content_types(raw)

            zout.writestr(item, raw)

    output.seek(0)
    return output.read()
