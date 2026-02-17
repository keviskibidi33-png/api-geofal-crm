"""
Servicio para generar archivos Excel de verificación de muestras cilíndricas.
Usa manipulación directa ZIP/XML para preservar logos y estilos.
"""

import os
import io
import logging
import zipfile
import copy
from datetime import datetime
from typing import List, Optional
from lxml import etree
from .models import VerificacionMuestras, MuestraVerificada

logger = logging.getLogger(__name__)

NAMESPACES = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
}

class ExcelLogic:
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

    # --- XML Helpers ---

    def _parse_cell_ref(self, ref: str) -> tuple[str, int]:
        col = ''.join(c for c in ref if c.isalpha())
        row = int(''.join(c for c in ref if c.isdigit()))
        return col, row

    def _get_row(self, sheet_data, row_num, ns):
        row = sheet_data.find(f'{{{ns}}}row[@r="{row_num}"]')
        if row is None:
            row = etree.SubElement(sheet_data, f'{{{ns}}}row')
            row.set('r', str(row_num))
        return row

    def _set_cell_value(self, row_el, ref, value, ns, is_number=False, get_string_idx=None):
        c = row_el.find(f'{{{ns}}}c[@r="{ref}"]')
        if c is None:
            c = etree.SubElement(row_el, f'{{{ns}}}c')
            c.set('r', ref)
        style = c.get('s')
        for child in list(c): c.remove(child)
        if value is None or value == '':
            if 't' in c.attrib: del c.attrib['t']
            if style: c.set('s', style)
            return
        if is_number:
            if 't' in c.attrib: del c.attrib['t']
            v = etree.SubElement(c, f'{{{ns}}}v')
            v.text = str(value)
        else:
            if get_string_idx:
                c.set('t', 's')
                v = etree.SubElement(c, f'{{{ns}}}v')
                v.text = str(get_string_idx(str(value)))
            else:
                c.set('t', 'inlineStr')
                is_elem = etree.SubElement(c, f'{{{ns}}}is')
                t = etree.SubElement(is_elem, f'{{{ns}}}t')
                t.text = str(value)
        if style: c.set('s', style)

    def _duplicate_row(self, sheet_data, source_row_num, target_row_num, ns):
        source_row = sheet_data.find(f'{{{ns}}}row[@r="{source_row_num}"]')
        if source_row is None: return
        new_row = copy.deepcopy(source_row)
        new_row.set('r', str(target_row_num))
        for cell in new_row.findall(f'{{{ns}}}c'):
            old_ref = cell.get('r')
            col, _ = self._parse_cell_ref(old_ref)
            cell.set('r', f'{col}{target_row_num}')
            for child in list(cell): cell.remove(child)
        sheet_data.append(new_row)

    def _shift_rows(self, sheet_data, from_row, shift, ns):
        if shift <= 0: return
        rows = list(sheet_data.findall(f'{{{ns}}}row'))
        rows.sort(key=lambda r: int(r.get('r')), reverse=True)
        for row in rows:
            rn = int(row.get('r'))
            if rn >= from_row:
                nn = rn + shift
                row.set('r', str(nn))
                for cell in row.findall(f'{{{ns}}}c'):
                    old_ref = cell.get('r')
                    col, _ = self._parse_cell_ref(old_ref)
                    cell.set('r', f'{col}{nn}')

    def _shift_merged(self, root, from_row, shift, ns):
        if shift <= 0: return
        mc_node = root.find(f'.//{{{ns}}}mergeCells')
        if mc_node is None: return
        for mc in mc_node.findall(f'{{{ns}}}mergeCell'):
            ref = mc.get('ref')
            if not ref or ':' not in ref: continue
            parts = ref.split(':')
            new_parts = []
            for p in parts:
                c, r = self._parse_cell_ref(p)
                if r >= from_row: new_parts.append(f"{c}{r + shift}")
                else: new_parts.append(p)
            mc.set('ref', ':'.join(new_parts))

    def _col_num_to_letter(self, n):
        string = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            string = chr(65 + remainder) + string
        return string

    # --- Main Logic ---

    def generar_excel_verificacion(self, verificacion: VerificacionMuestras) -> bytes:
        logger.info(f"Generando Excel Verificación (Direct XML) {verificacion.numero_verificacion}")
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"Template no encontrado: {self.template_path}")

        # 1. Shared Strings
        shared_strings = []
        ss_xml_original = None
        with zipfile.ZipFile(self.template_path, 'r') as z:
            if 'xl/sharedStrings.xml' in z.namelist():
                ss_root = etree.fromstring(z.read('xl/sharedStrings.xml'))
                ns_ss = ss_root.nsmap.get(None, NAMESPACES['main'])
                for si in ss_root.findall(f'{{{ns_ss}}}si'):
                    t = si.find(f'{{{ns_ss}}}t')
                    if t is not None: shared_strings.append((t.text or "").strip())
                    else: shared_strings.append(''.join([x.text or '' for x in si.findall(f'.//{{{ns_ss}}}t')]).strip())

        ss_map = {t: i for i, t in enumerate(shared_strings)}
        def get_ss_idx(text):
            text = str(text or "").strip()
            if text in ss_map: return ss_map[text]
            idx = len(shared_strings); shared_strings.append(text); ss_map[text] = idx; return idx

        # 2. Sheet XML
        sheet_file = 'xl/worksheets/sheet1.xml'
        with zipfile.ZipFile(self.template_path, 'r') as z:
            raw_sheet = z.read(sheet_file)
        
        root = etree.fromstring(raw_sheet)
        ns = NAMESPACES['main']
        sheet_data = root.find(f'.//{{{ns}}}sheetData')

        muestras = verificacion.muestras_verificadas
        n_muestras = len(muestras)
        base_rows = 8 # Template has 8 data rows (10-17)
        data_start_row = 10

        # Shift for extra samples
        if n_muestras > base_rows:
            shift = n_muestras - base_rows
            _from = 18 # Rows below samples start at 18
            self._shift_rows(sheet_data, _from, shift, ns)
            self._shift_merged(root, _from, shift, ns)
            # Duplicate template row (row 10)
            for i in range(base_rows, n_muestras):
                self._duplicate_row(sheet_data, 10, 10 + i, ns)

        rows_cache = {r.get('r'): r for r in sheet_data.findall(f'{{{ns}}}row')}
        def write(col, r_num, val, is_num=False, is_footer=False):
            actual_r = r_num
            if is_footer and n_muestras > base_rows: actual_r += (n_muestras - base_rows)
            row_el = rows_cache.get(str(actual_r))
            if row_el is None: row_el = self._get_row(sheet_data, actual_r, ns); rows_cache[str(actual_r)] = row_el
            c_ref = f"{col}{actual_r}"
            self._set_cell_value(row_el, c_ref, val, ns, is_num, get_ss_idx)

        # 3. Fill Header (using anchor-like search for robustness)
        header_vals = {
            "VERIFICADO POR:": verificacion.verificado_por,
            "FECHA VERIFIC.:": verificacion.fecha_verificacion,
            "CLIENTE:": verificacion.cliente
        }
        for r_el in sheet_data.findall(f'{{{ns}}}row'):
            rn = int(r_el.get('r'))
            if rn > 8: break # Header is in top 8 rows
            for c_el in r_el.findall(f'{{{ns}}}c'):
                v_el = c_el.find(f'{{{ns}}}v')
                if v_el is not None and c_el.get('t') == 's':
                    try:
                        t = shared_strings[int(v_el.text)].upper().strip()
                        for k, v in header_vals.items():
                            if k in t:
                                col_name, _ = self._parse_cell_ref(c_el.get('r'))
                                # offset typically 1 or 3 columns
                                offset = 3 if "VERIFICADO" in k else 1
                                target_col = self._col_num_to_letter(ord(col_name[-1]) - 64 + offset)
                                write(target_col, rn, v)
                    except: pass

        # 4. Samples Table
        def _fmt_bool(v):
            if v is True or str(v).upper() in ["TRUE", "CUMPLE"]: return "CUMPLE"
            if v is False or str(v).upper() in ["FALSE", "NO CUMPLE"]: return "NO CUMPLE"
            return str(v) if v is not None else ""

        for i, m in enumerate(muestras):
            curr_row = data_start_row + i
            write('A', curr_row, i + 1, True)
            write('B', curr_row, m.codigo_lem)
            write('C', curr_row, m.tipo_testigo)
            write('D', curr_row, m.diametro_1_mm, True)
            write('E', curr_row, m.diametro_2_mm, True)
            write('F', curr_row, (m.tolerancia_porcentaje / 100.0) if m.tolerancia_porcentaje else 0, True)
            write('G', curr_row, _fmt_bool(m.aceptacion_diametro))
            write('H', curr_row, _fmt_bool(m.perpendicularidad_sup1))
            write('I', curr_row, _fmt_bool(m.perpendicularidad_sup2))
            write('J', curr_row, _fmt_bool(m.perpendicularidad_inf1))
            write('K', curr_row, _fmt_bool(m.perpendicularidad_inf2))
            write('L', curr_row, _fmt_bool(m.perpendicularidad_medida))
            write('M', curr_row, _fmt_bool(m.planitud_superior_aceptacion))
            write('N', curr_row, _fmt_bool(m.planitud_inferior_aceptacion))
            write('O', curr_row, _fmt_bool(m.planitud_depresiones_aceptacion))
            write('P', curr_row, m.accion_realizar)
            write('Q', curr_row, m.conformidad)
            write('R', curr_row, m.longitud_1_mm, True)
            write('S', curr_row, m.longitud_2_mm, True)
            write('T', curr_row, m.longitud_3_mm, True)
            write('U', curr_row, m.masa_muestra_aire_g, True)
            write('V', curr_row, m.pesar)

        # 5. Equipos & Nota (Footer)
        write('C', 18, verificacion.equipo_bernier, is_footer=True)
        write('E', 18, verificacion.equipo_lainas_1, is_footer=True)
        write('G', 18, verificacion.equipo_lainas_2, is_footer=True)
        write('I', 18, verificacion.equipo_escuadra, is_footer=True)
        write('K', 18, verificacion.equipo_balanza, is_footer=True)
        if verificacion.nota: write('B', 19, verificacion.nota, is_footer=True)

        # 6. Serialization
        modified_sheet = etree.tostring(root, encoding='utf-8', xml_declaration=True)
        
        ss_root_new = etree.Element(f'{{{ns}}}sst', nsmap={None: ns})
        for text in shared_strings:
            si = etree.SubElement(ss_root_new, f'{{{ns}}}si')
            t = etree.SubElement(si, f'{{{ns}}}t')
            t.text = text
        ss_root_new.set('count', str(len(shared_strings)))
        ss_root_new.set('uniqueCount', str(len(shared_strings)))
        modified_ss = etree.tostring(ss_root_new, encoding='utf-8', xml_declaration=True)

        # 7. Drawing Shift (if extra samples)
        drawing_file = 'xl/drawings/drawing1.xml'
        modified_draw = None
        if n_muestras > base_rows:
            shift = n_muestras - base_rows
            with zipfile.ZipFile(self.template_path, 'r') as z:
                if drawing_file in z.namelist():
                    d_root = etree.fromstring(z.read(drawing_file))
                    d_ns = {'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'}
                    for anchor in d_root.xpath('//xdr:twoCellAnchor | //xdr:oneCellAnchor', namespaces=d_ns):
                        frow = anchor.find('.//xdr:from/xdr:row', namespaces=d_ns)
                        trow = anchor.find('.//xdr:to/xdr:row', namespaces=d_ns)
                        if frow is not None and int(frow.text) >= 17:
                            frow.text = str(int(frow.text) + shift)
                            if trow is not None: trow.text = str(int(trow.text) + shift)
                    modified_draw = etree.tostring(d_root, encoding='utf-8', xml_declaration=True)

        # 8. ZIP Construction
        output = io.BytesIO()
        with zipfile.ZipFile(self.template_path, 'r') as z_in:
            with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
                for item in z_in.namelist():
                    if item == sheet_file: z_out.writestr(item, modified_sheet)
                    elif item == 'xl/sharedStrings.xml': z_out.writestr(item, modified_ss)
                    elif item == drawing_file and modified_draw is not None: z_out.writestr(item, modified_draw)
                    else: z_out.writestr(item, z_in.read(item))
        
        output.seek(0)
        return output.read()
