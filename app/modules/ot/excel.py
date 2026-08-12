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
    """
    template_path = find_template_path("OT/OT-001-Geofal.xlsx")
    if not template_path.exists():
        template_path = find_template_path("OT-001-Geofal.xlsx")

    wb = openpyxl.load_workbook(str(template_path))
    # Utilizar la primera hoja (o 'CENS' / '.')
    sheet = wb.active

    # --- Header Metadata ---
    if ot.numero_ot:
        sheet['B6'] = ot.numero_ot
    if ot.numero_recepcion:
        sheet['G6'] = ot.numero_recepcion
    if ot.referencia:
        sheet['J6'] = ot.referencia

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
    if ot.fecha_recepcion:
        sheet['C31'] = ot.fecha_recepcion
    if ot.plazo_entrega_dias is not None:
        sheet['C32'] = ot.plazo_entrega_dias
    if ot.inicio_programado:
        sheet['F31'] = ot.inicio_programado
    if ot.fin_programado:
        sheet['F32'] = ot.fin_programado
    if ot.inicio_real:
        sheet['H31'] = ot.inicio_real
    if ot.fin_real:
        sheet['H32'] = ot.fin_real
    if ot.variacion_inicio:
        sheet['J31'] = ot.variacion_inicio
    if ot.variacion_fin:
        sheet['J32'] = ot.variacion_fin

    if ot.duracion_real_ejecucion_dias:
        sheet['A33'] = f"DURACION REAL DE EJECUCION (DIAS): {ot.duracion_real_ejecucion_dias}"
    if ot.observaciones:
        sheet['A34'] = f"OBSERVACIONES: {ot.observaciones}"
    if ot.ot_aperturada_por:
        sheet['C38'] = ot.ot_aperturada_por
    if ot.ot_designada_a:
        sheet['H38'] = ot.ot_designada_a

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
