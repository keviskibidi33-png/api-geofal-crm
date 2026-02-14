import io
import zipfile
from datetime import date
from typing import Any, List, Optional
from pathlib import Path
from lxml import etree
from .schemas import CompressionExportRequest

NAMESPACES = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
}

def _parse_cell_ref(ref: str) -> tuple[str, int]:
    col = ''.join(c for c in ref if c.isalpha())
    row = int(''.join(c for c in ref if c.isdigit()))
    return col, row

def _col_letter_to_num(col: str) -> int:
    num = 0
    for c in col.upper():
        num = num * 26 + (ord(c) - ord('A') + 1)
    return num

def _num_to_col_letter(n: int) -> str:
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

def _find_or_create_row(sheet_data: etree._Element, row_num: int, ns: str) -> etree._Element:
    for row in sheet_data.findall(f'{{{ns}}}row'):
        if row.get('r') == str(row_num):
            return row
    row = etree.SubElement(sheet_data, f'{{{ns}}}row')
    row.set('r', str(row_num))
    return row

def _find_or_create_cell(row: etree._Element, cell_ref: str, ns: str) -> etree._Element:
    for cell in row.findall(f'{{{ns}}}c'):
        if cell.get('r') == cell_ref:
            return cell
    
    col, _ = _parse_cell_ref(cell_ref)
    col_num = _col_letter_to_num(col)
    
    insert_pos = None
    existing_cells = row.findall(f'{{{ns}}}c')
    for i, existing in enumerate(existing_cells):
        exist_col, _ = _parse_cell_ref(existing.get('r'))
        if col_num < _col_letter_to_num(exist_col):
            insert_pos = i
            break
    
    cell = etree.Element(f'{{{ns}}}c')
    cell.set('r', cell_ref)
    if insert_pos is not None:
        row.insert(insert_pos, cell)
    else:
        row.append(cell)
    return cell

def _set_cell_value(sheet_data: etree._Element, cell_ref: str, value: Any, ns: str, is_number: bool = False):
    _, row_num = _parse_cell_ref(cell_ref)
    row = _find_or_create_row(sheet_data, row_num, ns)
    cell = _find_or_create_cell(row, cell_ref, ns)
    
    style = cell.get('s')
    for child in list(cell):
        cell.remove(child)
    
    if value is None or value == '':
        if 't' in cell.attrib: del cell.attrib['t']
        return
    
    if is_number:
        if 't' in cell.attrib: del cell.attrib['t']
        v = etree.SubElement(cell, f'{{{ns}}}v')
        v.text = str(value)
    else:
        cell.set('t', 'inlineStr')
        is_elem = etree.SubElement(cell, f'{{{ns}}}is')
        t_elem = etree.SubElement(is_elem, f'{{{ns}}}t')
        t_elem.text = str(value)
    
    if style:
        cell.set('s', style)

def _shift_rows(sheet_data: etree._Element, from_row: int, shift: int, ns: str):
    if shift <= 0: return
    rows = list(sheet_data.findall(f'{{{ns}}}row'))
    rows.sort(key=lambda r: int(r.get('r')), reverse=True)
    for row in rows:
        row_num = int(row.get('r'))
        if row_num >= from_row:
            new_num = row_num + shift
            row.set('r', str(new_num))
            for cell in row.findall(f'{{{ns}}}c'):
                old_ref = cell.get('r')
                col, _ = _parse_cell_ref(old_ref)
                cell.set('r', f'{col}{new_num}')

def _shift_merged_cells(root: etree._Element, from_row: int, shift: int, ns: str):
    if shift <= 0: return
    merge_cells = root.find(f'.//{{{ns}}}mergeCells')
    if merge_cells is None: return
    for merge in merge_cells.findall(f'{{{ns}}}mergeCell'):
        ref = merge.get('ref')
        if ':' not in ref: continue
        start, end = ref.split(':')
        start_col, start_row = _parse_cell_ref(start)
        end_col, end_row = _parse_cell_ref(end)
        if start_row >= from_row:
            merge.set('ref', f'{start_col}{start_row+shift}:{end_col}{end_row+shift}')

def _duplicate_row(sheet_data: etree._Element, source_row_num: int, target_row_num: int, ns: str) -> etree._Element:
    source_row = None
    for row in sheet_data.findall(f'{{{ns}}}row'):
        if row.get('r') == str(source_row_num):
            source_row = row
            break
    if source_row is None: return None
    import copy
    new_row = copy.deepcopy(source_row)
    new_row.set('r', str(target_row_num))
    for cell in new_row.findall(f'{{{ns}}}c'):
        old_ref = cell.get('r')
        col, _ = _parse_cell_ref(old_ref)
        cell.set('r', f'{col}{target_row_num}')
    # Insert
    inserted = False
    for i, row in enumerate(sheet_data.findall(f'{{{ns}}}row')):
        if int(row.get('r')) > target_row_num:
            sheet_data.insert(list(sheet_data).index(row), new_row)
            inserted = True
            break
# Helper to update text in an anchor's shape
def _update_shape_text_node(anchor: etree._Element, text_value: str, align: str = None):
    xdr_ns = NAMESPACES['xdr']
    a_ns = NAMESPACES['a']
    
    sp = anchor.find(f"{{{xdr_ns}}}sp")
    if sp is None: return
    
    txBody = sp.find(f"{{{xdr_ns}}}txBody")
    if txBody is None:
        txBody = etree.SubElement(sp, f"{{{xdr_ns}}}txBody")
        etree.SubElement(txBody, f"{{{a_ns}}}bodyPr")
        etree.SubElement(txBody, f"{{{a_ns}}}lstStyle")
    
    p = txBody.find(f"{{{a_ns}}}p")
    if p is None:
        p = etree.SubElement(txBody, f"{{{a_ns}}}p")
        
    # Update Alignment
    if align:
        pPr = p.find(f"{{{a_ns}}}pPr")
        if pPr is None:
            pPr = etree.Element(f"{{{a_ns}}}pPr")
            p.insert(0, pPr) # Ensure pPr is first
        pPr.set('algn', align)

    # Clear existing runs
    runs = p.findall(f"{{{a_ns}}}r")
    for r in runs:
        p.remove(r)
        
    # Create new run
    new_r = etree.Element(f"{{{a_ns}}}r")
    rPr = etree.SubElement(new_r, f"{{{a_ns}}}rPr")
    rPr.set('lang', 'es-PE')
    rPr.set('sz', '1100') # 11pt
    rPr.set('b', '0')
    
    # Ensure text is black
    solidFill = etree.SubElement(rPr, f"{{{a_ns}}}solidFill")
    srgbClr = etree.SubElement(solidFill, f"{{{a_ns}}}srgbClr")
    srgbClr.set('val', '000000')
    
    t = etree.SubElement(new_r, f"{{{a_ns}}}t")
    t.text = str(text_value) if text_value else ""
    
    # Insert new run BEFORE endParaRPr if it exists, otherwise append
    endParaRPr = p.find(f"{{{a_ns}}}endParaRPr")
    if endParaRPr is not None:
        p.insert(p.index(endParaRPr), new_r)
    else:
        p.append(new_r)


def generate_compression_excel(data: CompressionExportRequest) -> io.BytesIO:
    template_path = Path("app/templates/Template_Compresion.xlsx")
    if not template_path.exists():
        raise FileNotFoundError("Template_Compresion.xlsx not found")
    
    output = io.BytesIO()
    with zipfile.ZipFile(template_path, 'r') as z_in:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
            # 1. Handle worksheet
            sheet_xml = z_in.read('xl/worksheets/sheet1.xml')
            sheet_root = etree.fromstring(sheet_xml)
            ns = sheet_root.nsmap.get(None, NAMESPACES['main'])
            sheet_data = sheet_root.find(f'.//{{{ns}}}sheetData')
            
            # Shifting logic for > 18 items
            items = data.items
            extra_rows = max(0, len(items) - 18)
            if extra_rows > 0:
                _shift_rows(sheet_data, 34, extra_rows, ns)
                _shift_merged_cells(sheet_root, 34, extra_rows, ns)
                for i in range(18, len(items)):
                    # Duplicate row 33 (last item row)
                    _duplicate_row(sheet_data, 33, 16 + i, ns)
            
            # CLEAR ARTIFACTS IN CELLS (e.g. S in P34)
            # P34 might move if we shift rows, but let's clear it relative to shift
            # Original P34 is Row 34. If extra_rows > 0, it shifts.
            # But the artifact is in P34 of the TEMPLATE.
            # If we shift rows starting at 34, the artifact moves?
            # _shift_rows starts at 34.
            # If artifact is exactly at 34, it moves to 34+extra_rows.
            # We should check if P34 exists and clear it.
            # Safe approach: Clear P34 and P(34+extra_rows) if disparate.
            # And honestly, just clear the whole column P in relevant range.
            
            artifact_row = 34
            if extra_rows > 0:
                artifact_row += extra_rows
            
            # Clear P34 and determined artifact row
            _set_cell_value(sheet_data, 'P34', '', ns)
            _set_cell_value(sheet_data, f'P{artifact_row}', '', ns)
            
            # Fill items — Column mapping matches template:
            # B=Item, C=Código LEM, D=Fecha ensayo programado, E=Hora ensayo,
            # F=Carga máxima, G=Tipo fractura, H=Defectos, I=Realizado,
            # J=Fecha ensayo (actual), K=Revisado, L=Fecha revisado, M=Aprobado, N=Fecha aprobado
            for idx, item in enumerate(items):
                row_idx = 16 + idx
                _set_cell_value(sheet_data, f'B{row_idx}', item.item, ns, is_number=True)
                _set_cell_value(sheet_data, f'C{row_idx}', item.codigo_lem, ns)
                _set_cell_value(sheet_data, f'D{row_idx}', item.fecha_ensayo.strftime('%d/%m/%Y') if item.fecha_ensayo else '', ns)
                _set_cell_value(sheet_data, f'E{row_idx}', item.hora_ensayo or '', ns)
                _set_cell_value(sheet_data, f'F{row_idx}', item.carga_maxima, ns, is_number=True)
                _set_cell_value(sheet_data, f'G{row_idx}', item.tipo_fractura or '', ns)
                _set_cell_value(sheet_data, f'H{row_idx}', item.defectos or '', ns)
                _set_cell_value(sheet_data, f'I{row_idx}', item.realizado or '', ns)
                _set_cell_value(sheet_data, f'J{row_idx}', item.fecha_ensayo.strftime('%d/%m/%Y') if item.fecha_ensayo else '', ns)
                _set_cell_value(sheet_data, f'K{row_idx}', item.revisado or '', ns)
                _set_cell_value(sheet_data, f'L{row_idx}', item.fecha_revisado.strftime('%d/%m/%Y') if item.fecha_revisado else '', ns)
                _set_cell_value(sheet_data, f'M{row_idx}', item.aprobado or '', ns)
                _set_cell_value(sheet_data, f'N{row_idx}', item.fecha_aprobado.strftime('%d/%m/%Y') if item.fecha_aprobado else '', ns)
            
            # Footer data
            f_row = 35 + extra_rows
            _set_cell_value(sheet_data, f'E{f_row}', data.codigo_equipo or '', ns)
            _set_cell_value(sheet_data, f'I{f_row}', data.otros or '', ns)
            
            n_row = 37 + extra_rows
            _set_cell_value(sheet_data, f'D{n_row}', data.nota or '', ns)

            # 2. Handle Drawings
            if 'xl/drawings/drawing1.xml' in z_in.namelist():
                xml_data = z_in.read('xl/drawings/drawing1.xml')
                drawing_root = etree.fromstring(xml_data)
                xdr_ns = NAMESPACES['xdr']
                
                # Coordinate-based processing
                anchors_to_remove = []
                
                for anchor in drawing_root.xpath(".//xdr:twoCellAnchor", namespaces=NAMESPACES):
                    from_node = anchor.find(f"{{{xdr_ns}}}from")
                    if from_node is None: continue
                    col_node = from_node.find(f"{{{xdr_ns}}}col")
                    row_node = from_node.find(f"{{{xdr_ns}}}row")
                    
                    if col_node is None or row_node is None: continue
                    
                    c = int(col_node.text)
                    r = int(row_node.text)
                    
                    if c == 4 and r == 9: # Reception Value
                        _update_shape_text_node(anchor, data.recepcion_numero, align='ctr')
                        
                    elif c == 6 and r == 9: # OT Value
                        _update_shape_text_node(anchor, data.ot_numero, align='r')
                        
                    elif r >= 38: # Artifacts
                        anchors_to_remove.append(anchor)
                
                # Remove drawing artifacts
                for a in anchors_to_remove:
                    p = a.getparent()
                    if p is not None: p.remove(a)

                # Shift drawing anchors if rows were shifted
                if extra_rows > 0:
                    for anchor in drawing_root.xpath(".//xdr:twoCellAnchor", namespaces=NAMESPACES):
                        # Shift FROM/TO
                        for child_name in ['from', 'to']:
                            row_elem = anchor.find(f'{{{xdr_ns}}}{child_name}/{{{xdr_ns}}}row')
                            if row_elem is not None:
                                r = int(row_elem.text)
                                if r >= 16: # Shift everything below items start
                                    row_elem.text = str(r + extra_rows)
            else:
                drawing_root = None

            # 3. Write back
            for item in z_in.namelist():
                if item == 'xl/worksheets/sheet1.xml':
                    z_out.writestr(item, etree.tostring(sheet_root, encoding='utf-8', xml_declaration=True))
                elif item == 'xl/drawings/drawing1.xml':
                    z_out.writestr(item, etree.tostring(drawing_root, encoding='utf-8', xml_declaration=True))
                else:
                    z_out.writestr(item, z_in.read(item))
                    
    output.seek(0)
    return output
