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

TEMPLATE_FILENAME = "OT-001-Geofal.xlsx"
SHEET_NAME = "CENS"


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
