"""
Servicio para generar archivos Excel de verificación de muestras cilíndricas
"""

import os
import io
import shutil
import logging
import zipfile
import tempfile as tmp
from datetime import datetime
from typing import List, Optional

from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from .models import VerificacionMuestras, MuestraVerificada

logger = logging.getLogger(__name__)

def preservar_imagenes_excel(workbook_data, template_path):
    """
    Restaura las imágenes (media y drawings) del template original en el contenido del workbook generado.
    """
    try:
        if isinstance(workbook_data, io.BytesIO):
            workbook_data = workbook_data.getvalue()
            
        with tmp.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_modified:
            tmp_modified.write(workbook_data)
            temp_modified_path = tmp_modified.name
            
        with tmp.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_new:
            temp_new_path = tmp_new.name
            
        try:
            with zipfile.ZipFile(temp_modified_path, 'r') as modified_zip:
                with zipfile.ZipFile(temp_new_path, 'w', zipfile.ZIP_DEFLATED) as new_zip:
                    exclude_patterns = [
                        'xl/media/', 
                        'xl/drawings/', 
                        'xl/worksheets/_rels/', 
                        'xl/_rels/',
                        '[Content_Types].xml'
                    ]
                    for item in modified_zip.infolist():
                        if not any(item.filename.startswith(pattern) for pattern in exclude_patterns) and item.filename != '[Content_Types].xml':
                            data = modified_zip.read(item.filename)
                            new_zip.writestr(item, data)
            
            if os.path.exists(template_path):
                with zipfile.ZipFile(template_path, 'r') as template_zip:
                    with zipfile.ZipFile(temp_new_path, 'a', zipfile.ZIP_DEFLATED) as new_zip:
                        restore_patterns = [
                            'xl/media/', 
                            'xl/drawings/', 
                            'xl/worksheets/_rels/', 
                            'xl/_rels/',
                            '[Content_Types].xml'
                        ]
                        for file_name in template_zip.namelist():
                            if any(file_name.startswith(p) for p in restore_patterns) or file_name == '[Content_Types].xml':
                                new_zip.writestr(file_name, template_zip.read(file_name))
            
            with open(temp_new_path, 'rb') as f:
                final_data = f.read()
            return final_data
        finally:
            if os.path.exists(temp_modified_path): os.remove(temp_modified_path)
            if os.path.exists(temp_new_path): os.remove(temp_new_path)
    except Exception as e:
        logger.error(f"Error restaurando imágenes del Excel: {e}")
        return workbook_data

class ExcelLogic:
    """
    Lógica para generar archivos Excel de verificación.
    """
    
    COLUMNS = {
        'numero': 1, 'codigo_lem': 2, 'tipo_testigo': 3, 'diametro_1': 4, 'diametro_2': 5,
        'tolerancia_porcentaje': 6, 'aceptacion_diametro': 7, 'perpendicularidad_sup1': 8,
        'perpendicularidad_sup2': 9, 'perpendicularidad_inf1': 10, 'perpendicularidad_inf2': 11,
        'perpendicularidad_medida': 12, 'planitud_superior': 13, 'planitud_inferior': 14,
        'planitud_depresiones': 15, 'accion': 16, 'conformidad': 17, 'longitud_1': 18,
        'longitud_2': 19, 'longitud_3': 20, 'masa': 21, 'pesar': 22
    }
    
    def __init__(self):
        filename = "Template_Verificacion.xlsx"
        from pathlib import Path
        current_dir = Path(__file__).resolve().parent
        app_dir = current_dir.parents[1]
        self.template_path = str(app_dir / "templates" / filename)
        
        # Estilos
        self.font_normal = Font(name='Arial', size=10)
        self.align_center = Alignment(horizontal='center', vertical='center')
        self.border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), 
                                 top=Side(style='thin'), bottom=Side(style='thin'))

    def generar_excel_verificacion(self, verificacion: VerificacionMuestras) -> bytes:
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"Template no encontrado en {self.template_path}")

        # Usar BytesIO para no escribir archivos temporales en disco innecesariamente
        output = io.BytesIO()
        shutil.copy2(self.template_path, "temp_verif.xlsx") # openpyxl needs a file or stream
        
        wb = load_workbook("temp_verif.xlsx")
        ws = wb.active
        
        # Llenar datos
        self._llenar_datos(ws, verificacion)
        
        wb.save(output)
        wb.close()
        os.remove("temp_verif.xlsx")
        
        # Restaurar imágenes
        final_bytes = preservar_imagenes_excel(output.getvalue(), self.template_path)
        return final_bytes

    def _llenar_datos(self, ws, verificacion: VerificacionMuestras):
        # Info General
        self._buscar_y_llenar(ws, "VERIFICADO POR:", verificacion.verificado_por, col_offset=1)
        self._buscar_y_llenar(ws, "FECHA VERIFIC.:", verificacion.fecha_verificacion)
        self._buscar_y_llenar(ws, "CLIENTE:", verificacion.cliente)
        
        # Muestras
        start_row = 10
        for i, muestra in enumerate(verificacion.muestras_verificadas, 1):
            row = start_row + i - 1
            self._llenar_fila_muestra(ws, row, i, muestra)
            
        # Equipos (fila 18 aprox)
        self._llenar_equipos(ws, verificacion)
        
        if verificacion.nota:
            self._set_cell_value(ws, 19, 2, verificacion.nota)

    def _set_cell_value(self, ws, row, col, value):
        """
        Escribe un valor en una celda, manejando casos de celdas combinadas (MergedCells).
        Escribe siempre en la celda superior izquierda del rango combinado.
        """
        from openpyxl.cell.cell import MergedCell
        cell = ws.cell(row=row, column=col)
        
        if isinstance(cell, MergedCell):
            # Buscar el rango al que pertenece esta celda
            for merged_range in ws.merged_cells.ranges:
                if cell.coordinate in merged_range:
                    # Escribir en la celda superior izquierda del rango
                    ws.cell(row=merged_range.min_row, column=merged_range.min_col, value=value)
                    return
        else:
            cell.value = value

    def _buscar_y_llenar(self, ws, etiqueta, valor, col_offset=1):
        for r in range(1, 15):
            for c in range(1, 15):
                cell = ws.cell(row=r, column=c)
                if cell.value and etiqueta in str(cell.value).upper():
                    self._set_cell_value(ws, r, c + col_offset, valor)
                    return

    def _llenar_fila_muestra(self, ws, row, numero, muestra: MuestraVerificada):
        def _fmt(val):
            if val is True: return "✓"
            if val is False: return "✗"
            return str(val) if val is not None else ""

        self._set_cell_value(ws, row, self.COLUMNS['numero'], numero)
        self._set_cell_value(ws, row, self.COLUMNS['codigo_lem'], muestra.codigo_lem or "")
        self._set_cell_value(ws, row, self.COLUMNS['tipo_testigo'], muestra.tipo_testigo or "")
        self._set_cell_value(ws, row, self.COLUMNS['diametro_1'], muestra.diametro_1_mm)
        self._set_cell_value(ws, row, self.COLUMNS['diametro_2'], muestra.diametro_2_mm)
        self._set_cell_value(ws, row, self.COLUMNS['tolerancia_porcentaje'], muestra.tolerancia_porcentaje)
        self._set_cell_value(ws, row, self.COLUMNS['aceptacion_diametro'], muestra.aceptacion_diametro)
        
        self._set_cell_value(ws, row, self.COLUMNS['perpendicularidad_sup1'], _fmt(muestra.perpendicularidad_sup1))
        self._set_cell_value(ws, row, self.COLUMNS['perpendicularidad_sup2'], _fmt(muestra.perpendicularidad_sup2))
        self._set_cell_value(ws, row, self.COLUMNS['perpendicularidad_inf1'], _fmt(muestra.perpendicularidad_inf1))
        self._set_cell_value(ws, row, self.COLUMNS['perpendicularidad_inf2'], _fmt(muestra.perpendicularidad_inf2))
        self._set_cell_value(ws, row, self.COLUMNS['perpendicularidad_medida'], _fmt(muestra.perpendicularidad_medida))
        
        self._set_cell_value(ws, row, self.COLUMNS['planitud_superior'], muestra.planitud_superior_aceptacion)
        self._set_cell_value(ws, row, self.COLUMNS['planitud_inferior'], muestra.planitud_inferior_aceptacion)
        self._set_cell_value(ws, row, self.COLUMNS['planitud_depresiones'], muestra.planitud_depresiones_aceptacion)
        
        self._set_cell_value(ws, row, self.COLUMNS['accion'], muestra.accion_realizar)
        self._set_cell_value(ws, row, self.COLUMNS['conformidad'], muestra.conformidad)
        
        self._set_cell_value(ws, row, self.COLUMNS['longitud_1'], muestra.longitud_1_mm)
        self._set_cell_value(ws, row, self.COLUMNS['longitud_2'], muestra.longitud_2_mm)
        self._set_cell_value(ws, row, self.COLUMNS['longitud_3'], muestra.longitud_3_mm)
        self._set_cell_value(ws, row, self.COLUMNS['masa'], muestra.masa_muestra_aire_g)
        self._set_cell_value(ws, row, self.COLUMNS['pesar'], muestra.pesar)

    def _llenar_equipos(self, ws, v: VerificacionMuestras):
        row = 18
        equipos = [
            (3, v.equipo_bernier), (5, v.equipo_lainas_1), (7, v.equipo_lainas_2),
            (9, v.equipo_escuadra), (11, v.equipo_balanza)
        ]
        for col, val in equipos:
            if val: self._set_cell_value(ws, row, col + 1, val)
