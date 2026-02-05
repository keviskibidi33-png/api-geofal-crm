
import copy
from lxml import etree
from datetime import datetime, date

NAMESPACES = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
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
    for row in sheet_data.iterfind(f'{{{ns}}}row'):
        if row.get('r') == str(row_num):
            return row
    row = etree.SubElement(sheet_data, f'{{{ns}}}row')
    row.set('r', str(row_num))
    return row

def _find_or_create_cell(row_el: etree._Element, cell_ref: str, ns: str) -> etree._Element:
    """Finds or creates a cell element in a row."""
    c = row_el.find(f'{{{ns}}}c[@r="{cell_ref}"]')
    if c is None:
        c = etree.SubElement(row_el, f'{{{ns}}}c')
        c.set('r', cell_ref)
    return c

def _set_cell_value(row, ref, value, ns, is_number=False, get_string_idx=None):
    """
    Sets cell value. 
    Args:
        row: Row Element
        ref: Cell Reference (e.g. A1)
        value: Value to set
        ns: Namespace URL
        is_number: If True, set as number type
        get_string_idx: Function to get shared string index. 
                       If provided and not is_number, assumes shared string.
                       If NOT provided and not is_number, uses inlineStr.
    """
    c = _find_or_create_cell(row, ref, ns)
    
    style = c.get('s')
    # Clear children
    for child in list(c):
        c.remove(child)
    
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
    
    if style:
        c.set('s', style)

def _duplicate_row(sheet_data: etree._Element, source_row_num: int, target_row_num: int, ns: str):
    source_row = sheet_data.find(f'{{{ns}}}row[@r="{source_row_num}"]')
    if source_row is None:
        return
    
    new_row = copy.deepcopy(source_row)
    new_row.set('r', str(target_row_num))
    
    for cell in new_row.findall(f'{{{ns}}}c'):
        old_ref = cell.get('r')
        col, _ = _parse_cell_ref(old_ref)
        cell.set('r', f'{col}{target_row_num}')
        # Clear value but keep style
        for child in list(cell):
            # Keep style, remove value.
            # Usually verification/value is in <v>.
            if child.tag == f'{{{ns}}}v' or child.tag == f'{{{ns}}}is':
                cell.remove(child)
            # We keep 's' attribute (style) on the cell element itself
            
    # Insert in order
    rows = sheet_data.findall(f'{{{ns}}}row')
    inserted = False
    for r in rows:
        if int(r.get('r')) > target_row_num:
            r.addprevious(new_row)
            inserted = True
            break
    if not inserted:
        sheet_data.append(new_row)

def _shift_rows(sheet_data: etree._Element, from_row: int, shift: int, ns: str):
    if shift <= 0: return
    # Find all rows with r >= from_row
    # We must process in reverse order to avoid conflict if shifting down?
    # Actually if we shift down, we should process highest to lowest.
    
    rows = []
    for r in sheet_data.findall(f'{{{ns}}}row'):
        if int(r.get('r')) >= from_row:
            rows.append(r)
            
    rows.sort(key=lambda r: int(r.get('r')), reverse=True)
    
    for row in rows:
        row_num = int(row.get('r'))
        new_num = row_num + shift
        row.set('r', str(new_num))
        for cell in row.findall(f'{{{ns}}}c'):
            old_ref = cell.get('r')
            col, _ = _parse_cell_ref(old_ref)
            cell.set('r', f'{col}{new_num}')

def _shift_merged_cells(root: etree._Element, from_row: int, shift: int, ns: str):
    if shift <= 0: return
    merged_cells_node = root.find(f'{{{ns}}}mergeCells')
    if merged_cells_node is None: return
    for mc in merged_cells_node.findall(f'{{{ns}}}mergeCell'):
        ref = mc.get('ref')
        if not ref: continue
        parts = ref.split(':')
        new_parts = []
        changed = False
        for part in parts:
            c, r = _parse_cell_ref(part)
            if r >= from_row:
                new_parts.append(f"{c}{r + shift}")
                changed = True
            else:
                new_parts.append(part)
        if changed:
            mc.set('ref', ':'.join(new_parts))
