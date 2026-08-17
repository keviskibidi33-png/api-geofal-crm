from __future__ import annotations

import io
import logging
from typing import Any
from lxml import etree

from app.modules.common.excel_xml import (
    transform_template_sheet,
    set_cell,
    build_merge_anchor_map,
    NS_SHEET,
)
from .models import OrdenTrabajo

logger = logging.getLogger(__name__)

TEMPLATE_CONCRETO_FILENAME = "OT-0000-Geofal.xlsx"
SHEET_CONCRETO_NAME = "MYP"


def generar_excel_ot(ot: OrdenTrabajo) -> io.BytesIO:
    """
    Genera un archivo Excel inyectando los datos de la Orden de Trabajo
    en la plantilla oficial OT-001-Geofal.xlsx usando manipulación directa ZIP/XML.
    Preserva el 100% de las imágenes, logos, dibujos, celdas combinadas y estilos.
    """

    def _transform(sheet_xml: bytes) -> bytes:
        root = etree.fromstring(sheet_xml)
        merge_map = build_merge_anchor_map(root)
        sheet_data = root.find(f"{{{NS_SHEET}}}sheetData")

        if sheet_data is None:
            return sheet_xml

        # 1. Limpiar filas de ítems de la 10 a la 30 para borrar cualquier texto remanente de la plantilla
        for r in range(10, 31):
            set_cell(sheet_data, f"A{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"B{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"E{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"J{r}", "", merge_anchor_map=merge_map)

        # 2. Encabezado de la Orden de Trabajo
        set_cell(sheet_data, "B6", ot.numero_ot or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "G6", ot.numero_recepcion or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "J6", ot.referencia or "-", merge_anchor_map=merge_map)

        # 3. Tabla de Ítems / Muestras / Ensayos (Filas 10 a 30)
        raw_items = ot.items if isinstance(ot.items, list) else []
        for idx, item in enumerate(raw_items[:21]):
            row_num = 10 + idx
            item_val = item.get("item", idx + 1) if isinstance(item, dict) else idx + 1
            codigo = item.get("codigo_muestra", "") if isinstance(item, dict) else ""
            desc = item.get("descripcion", "") if isinstance(item, dict) else ""
            cant = item.get("cantidad", 1) if isinstance(item, dict) else 1

            set_cell(sheet_data, f"A{row_num}", item_val, is_number=True, merge_anchor_map=merge_map)
            set_cell(sheet_data, f"B{row_num}", codigo, merge_anchor_map=merge_map)
            set_cell(sheet_data, f"E{row_num}", desc, merge_anchor_map=merge_map)
            set_cell(sheet_data, f"J{row_num}", cant, is_number=True, merge_anchor_map=merge_map)

        # 4. Fechas y Control de Ejecución Real
        set_cell(sheet_data, "C31", ot.fecha_recepcion or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "C32", ot.plazo_entrega_dias or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "F31", ot.inicio_programado or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "F32", ot.fin_programado or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "H31", ot.inicio_real or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "H32", ot.fin_real or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "J31", ot.variacion_inicio or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "J32", ot.variacion_fin or "", merge_anchor_map=merge_map)

        duracion_text = (
            f"DURACION REAL DE EJECUCION (DIAS): {ot.duracion_real_ejecucion_dias}"
            if ot.duracion_real_ejecucion_dias
            else "DURACION REAL DE EJECUCION (DIAS):"
        )
        obs_text = f"OBSERVACIONES: {ot.observaciones}" if ot.observaciones else "OBSERVACIONES:"

        set_cell(sheet_data, "A33", duracion_text, merge_anchor_map=merge_map)
        set_cell(sheet_data, "A34", obs_text, merge_anchor_map=merge_map)
        set_cell(sheet_data, "C38", ot.ot_aperturada_por or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "H38", ot.ot_designada_a or "", merge_anchor_map=merge_map)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    excel_bytes = transform_template_sheet(TEMPLATE_FILENAME, SHEET_NAME, _transform)
    output = io.BytesIO(excel_bytes)
    output.seek(0)
    return output


def generar_excel_ot_concreto(ot: OrdenTrabajo) -> io.BytesIO:
    """
    Genera un archivo Excel especializado para Probetas de Concreto usando la plantilla
    OT-CONCRETO/OT-0000-Geofal.xlsx (hoja MYP) con manipulación directa ZIP/XML.
    Inyecta ITEM, CÓDIGO LEM, DESCRIPCIÓN fija, ELEMENTO, F. ROTURA, DENSIDAD, EDAD, F'C.
    """

    def _transform(sheet_xml: bytes) -> bytes:
        root = etree.fromstring(sheet_xml)
        merge_map = build_merge_anchor_map(root)
        sheet_data = root.find(f"{{{NS_SHEET}}}sheetData")

        if sheet_data is None:
            return sheet_xml

        # 1. Limpiar filas de probetas de la 9 a la 20
        for r in range(9, 21):
            set_cell(sheet_data, f"A{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"B{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"C{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"F{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"G{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"H{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"I{r}", "", merge_anchor_map=merge_map)
            set_cell(sheet_data, f"J{r}", "", merge_anchor_map=merge_map)

        # 2. Encabezado
        set_cell(sheet_data, "C6", ot.numero_ot or "", merge_anchor_map=merge_map)
        set_cell(sheet_data, "G6", ot.numero_recepcion or "", merge_anchor_map=merge_map)

        # 3. Filas de probetas (filas 9 a 20)
        raw_items = ot.items if isinstance(ot.items, list) else []
        fechas_rotura = []
        for idx, item in enumerate(raw_items[:12]):
            row_num = 9 + idx
            item_val = item.get("item", idx + 1) if isinstance(item, dict) else idx + 1
            codigo = item.get("codigo_muestra", "") if isinstance(item, dict) else ""
            elemento = item.get("elemento", "-") if isinstance(item, dict) else "-"
            fecha_rotura = item.get("fecha_rotura", "") if isinstance(item, dict) else ""
            densidad = item.get("densidad", "-") if isinstance(item, dict) else "-"
            edad = item.get("edad", "") if isinstance(item, dict) else ""
            fc = item.get("fc_kg_cm2", item.get("fc", "")) if isinstance(item, dict) else ""

            if fecha_rotura:
                fechas_rotura.append(str(fecha_rotura).replace("-", "/"))

            # Descripción siempre fija según estándar de calidad Geofal
            desc_fija = "COMPRESION PROBETAS ASTM C39/C39M"

            set_cell(sheet_data, f"A{row_num}", item_val, is_number=True, merge_anchor_map=merge_map)
            set_cell(sheet_data, f"B{row_num}", str(codigo), merge_anchor_map=merge_map)
            set_cell(sheet_data, f"C{row_num}", desc_fija, merge_anchor_map=merge_map)
            set_cell(sheet_data, f"F{row_num}", str(elemento or "-"), merge_anchor_map=merge_map)
            set_cell(sheet_data, f"G{row_num}", str(fecha_rotura).replace("-", "/"), merge_anchor_map=merge_map)
            set_cell(sheet_data, f"H{row_num}", str(densidad or "-"), merge_anchor_map=merge_map)
            if edad != "" and edad is not None:
                try:
                    edad_val = float(str(edad))
                    set_cell(sheet_data, f"I{row_num}", int(edad_val), is_number=True, merge_anchor_map=merge_map)
                except (ValueError, TypeError):
                    set_cell(sheet_data, f"I{row_num}", str(edad), merge_anchor_map=merge_map)
            if fc != "" and fc is not None:
                try:
                    fc_val = float(str(fc))
                    # Sin decimales: 210.0 → 210
                    set_cell(sheet_data, f"J{row_num}", int(fc_val), is_number=True, merge_anchor_map=merge_map)
                except (ValueError, TypeError):
                    set_cell(sheet_data, f"J{row_num}", str(fc), merge_anchor_map=merge_map)

        # 4. Pie de página y programación
        fecha_recep_str = (ot.fecha_recepcion or "").replace("-", "/")
        inicio_prog = (ot.inicio_programado or "").replace("-", "/")
        if not inicio_prog and fechas_rotura:
            inicio_prog = min(fechas_rotura)
        if not inicio_prog:
            inicio_prog = fecha_recep_str

        fin_prog = (ot.fin_programado or "").replace("-", "/")
        if not fin_prog and fechas_rotura:
            fin_prog = max(fechas_rotura)
        if not fin_prog:
            fin_prog = inicio_prog

        set_cell(sheet_data, "C24", fecha_recep_str, merge_anchor_map=merge_map)
        set_cell(sheet_data, "F24", inicio_prog, merge_anchor_map=merge_map)
        set_cell(sheet_data, "J24", fin_prog, merge_anchor_map=merge_map)

        # Observaciones
        if ot.observaciones:
            set_cell(sheet_data, "A26", f"OBSERVACIONES: {ot.observaciones}", merge_anchor_map=merge_map)

        # Responsables
        set_cell(sheet_data, "C33", ot.ot_aperturada_por or "BETZABETH ZARABIA", merge_anchor_map=merge_map)
        if ot.ot_designada_a:
            set_cell(sheet_data, "F33", f"OT DESIGNADA A:\n{ot.ot_designada_a}", merge_anchor_map=merge_map)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    excel_bytes = transform_template_sheet(TEMPLATE_CONCRETO_FILENAME, SHEET_CONCRETO_NAME, _transform)
    output = io.BytesIO(excel_bytes)
    output.seek(0)
    return output

