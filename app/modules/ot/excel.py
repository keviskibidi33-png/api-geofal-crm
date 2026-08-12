from __future__ import annotations

import io
import logging
from typing import Any
import openpyxl

from app.modules.common.excel_xml import find_template_path
from .models import OrdenTrabajo

logger = logging.getLogger(__name__)


def generar_excel_ot(ot: OrdenTrabajo) -> io.BytesIO:
    """
    Genera un archivo Excel inyectando los datos de la Orden de Trabajo
    en la plantilla oficial OT-001-Geofal.xlsx.
    Limpia previamente cualquier ítem remanente de la plantilla original.
    """
    template_path = find_template_path("OT/OT-001-Geofal.xlsx")
    if not template_path.exists():
        template_path = find_template_path("OT-001-Geofal.xlsx")

    wb = openpyxl.load_workbook(str(template_path))
    
    # Seleccionar la hoja principal CENS o la activa
    if "CENS" in wb.sheetnames:
        sheet = wb["CENS"]
        wb.active = sheet
    else:
        sheet = wb.active

    # Limpiar celdas de ítems previas de la fila 10 a la 30 para evitar texto heredado del template
    for row_num in range(10, 31):
        sheet[f'A{row_num}'] = None
        sheet[f'B{row_num}'] = None
        sheet[f'E{row_num}'] = None
        sheet[f'J{row_num}'] = None

    # --- Header Metadata ---
    sheet['B6'] = ot.numero_ot or ""
    sheet['G6'] = ot.numero_recepcion or ""
    sheet['J6'] = ot.referencia or "-"

    # --- Items Table (Rows 10 to 30) ---
    raw_items = ot.items if isinstance(ot.items, list) else []
    for idx, item in enumerate(raw_items[:21]):
        row_num = 10 + idx
        item_val = item.get("item", idx + 1) if isinstance(item, dict) else idx + 1
        codigo = item.get("codigo_muestra", "") if isinstance(item, dict) else ""
        desc = item.get("descripcion", "") if isinstance(item, dict) else ""
        cant = item.get("cantidad", 1) if isinstance(item, dict) else 1

        sheet[f'A{row_num}'] = item_val
        sheet[f'B{row_num}'] = codigo
        sheet[f'E{row_num}'] = desc
        sheet[f'J{row_num}'] = cant

    # --- Footer & Fechas ---
    sheet['C31'] = ot.fecha_recepcion or ""
    sheet['C32'] = ot.plazo_entrega_dias or ""
    sheet['F31'] = ot.inicio_programado or ""
    sheet['F32'] = ot.fin_programado or ""
    sheet['H31'] = ot.inicio_real or ""
    sheet['H32'] = ot.fin_real or ""
    sheet['J31'] = ot.variacion_inicio or ""
    sheet['J32'] = ot.variacion_fin or ""

    duracion_text = (
        f"DURACION REAL DE EJECUCION (DIAS): {ot.duracion_real_ejecucion_dias}"
        if ot.duracion_real_ejecucion_dias
        else "DURACION REAL DE EJECUCION (DIAS):"
    )
    obs_text = f"OBSERVACIONES: {ot.observaciones}" if ot.observaciones else "OBSERVACIONES:"

    sheet['A33'] = duracion_text
    sheet['A34'] = obs_text
    sheet['C38'] = ot.ot_aperturada_por or ""
    sheet['H38'] = ot.ot_designada_a or ""

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
