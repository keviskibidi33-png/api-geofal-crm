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
            ws.cell(row=19, column=2, value=verificacion.nota)

    def _buscar_y_llenar(self, ws, etiqueta, valor, col_offset=1):
        for r in range(1, 15):
            for c in range(1, 15):
                cell = ws.cell(row=r, column=c)
                if cell.value and etiqueta in str(cell.value).upper():
                    ws.cell(row=r, column=c + col_offset, value=valor)
                    return

    def _llenar_fila_muestra(self, ws, row, numero, muestra: MuestraVerificada):
        def _fmt(val):
            if val is True: return "✓"
            if val is False: return "✗"
            return str(val) if val is not None else ""

        ws.cell(row=row, column=self.COLUMNS['numero'], value=numero)
        ws.cell(row=row, column=self.COLUMNS['codigo_lem'], value=muestra.codigo_lem or "")
        ws.cell(row=row, column=self.COLUMNS['tipo_testigo'], value=muestra.tipo_testigo or "")
        ws.cell(row=row, column=self.COLUMNS['diametro_1'], value=muestra.diametro_1_mm)
        ws.cell(row=row, column=self.COLUMNS['diametro_2'], value=muestra.diametro_2_mm)
        ws.cell(row=row, column=self.COLUMNS['tolerancia_porcentaje'], value=muestra.tolerancia_porcentaje)
        ws.cell(row=row, column=self.COLUMNS['aceptacion_diametro'], value=muestra.aceptacion_diametro)
        
        ws.cell(row=row, column=self.COLUMNS['perpendicularidad_sup1'], value=_fmt(muestra.perpendicularidad_sup1))
        ws.cell(row=row, column=self.COLUMNS['perpendicularidad_sup2'], value=_fmt(muestra.perpendicularidad_sup2))
        ws.cell(row=row, column=self.COLUMNS['perpendicularidad_inf1'], value=_fmt(muestra.perpendicularidad_inf1))
        ws.cell(row=row, column=self.COLUMNS['perpendicularidad_inf2'], value=_fmt(muestra.perpendicularidad_inf2))
        ws.cell(row=row, column=self.COLUMNS['perpendicularidad_medida'], value=_fmt(muestra.perpendicularidad_medida))
        
        ws.cell(row=row, column=self.COLUMNS['planitud_superior'], value=muestra.planitud_superior_aceptacion)
        ws.cell(row=row, column=self.COLUMNS['planitud_inferior'], value=muestra.planitud_inferior_aceptacion)
        ws.cell(row=row, column=self.COLUMNS['planitud_depresiones'], value=muestra.planitud_depresiones_aceptacion)
        
        ws.cell(row=row, column=self.COLUMNS['accion'], value=muestra.accion_realizar)
        ws.cell(row=row, column=self.COLUMNS['conformidad'], value=muestra.conformidad)
        
        ws.cell(row=row, column=self.COLUMNS['longitud_1'], value=muestra.longitud_1_mm)
        ws.cell(row=row, column=self.COLUMNS['longitud_2'], value=muestra.longitud_2_mm)
        ws.cell(row=row, column=self.COLUMNS['longitud_3'], value=muestra.longitud_3_mm)
        ws.cell(row=row, column=self.COLUMNS['masa'], value=muestra.masa_muestra_aire_g)
        ws.cell(row=row, column=self.COLUMNS['pesar'], value=muestra.pesar)

    def _llenar_equipos(self, ws, v: VerificacionMuestras):
        row = 18
        equipos = [
            (3, v.equipo_bernier), (5, v.equipo_lainas_1), (7, v.equipo_lainas_2),
            (9, v.equipo_escuadra), (11, v.equipo_balanza)
        ]
        for col, val in equipos:
            if val: ws.cell(row=row, column=col+1, value=val)
