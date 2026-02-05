import io
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

def _find_label_anchors(sheet_data: etree._Element, shared_strings: list[str], ns: str) -> dict[str, str]:
    """Finds cell references for labels in the template."""
    anchors = {}
    for row in sheet_data.findall(f'{{{ns}}}row'):
        for cell in row.findall(f'{{{ns}}}c'):
            if cell.get('t') == 's':
                v = cell.find(f'{{{ns}}}v')
                if v is not None:
                    try:
                        idx = int(v.text)
                        if 0 <= idx < len(shared_strings):
                            val = shared_strings[idx].strip().upper()
                            if val and val not in anchors:
                                anchors[val] = cell.get('r')
                    except: pass
    return anchors

def export_xlsx_direct(template_path: str, data: dict) -> io.BytesIO:
    """
    High-level export function with Label-Based Mapping.
    """
    import zipfile
    import io

    # 1. Read shared strings
    shared_strings = []
    with zipfile.ZipFile(template_path, 'r') as z:
        if 'xl/sharedStrings.xml' in z.namelist():
            ss_xml = z.read('xl/sharedStrings.xml')
            ss_root = etree.fromstring(ss_xml)
            ss_ns = ss_root.nsmap.get(None, NAMESPACES['main'])
            for si in ss_root.findall(f'{{{ss_ns}}}si'):
                t = si.find(f'{{{ss_ns}}}t')
                if t is not None:
                    shared_strings.append(t.text or "")
                else:
                    shared_strings.append("".join(node.text or "" for node in si.xpath(".//main:t", namespaces=NAMESPACES)))

    # 2. Read sheet1
    with zipfile.ZipFile(template_path, 'r') as z:
        sheet_xml = z.read('xl/worksheets/sheet1.xml')
    
    root = etree.fromstring(sheet_xml)
    ns = NAMESPACES['main']
    sheet_data = root.find(f'{{{ns}}}sheetData')

    # 3. Map labels to anchors
    anchors = _find_label_anchors(sheet_data, shared_strings, ns)
    
    # 4. Process Dynamic Rows (Items)
    # The logic for items usually involves finding a "marker" label and duplicating rows.
    # For Cotización, it's usually "ITEM", "DESCRIPCIÓN", etc.
    items = data.get('items', [])
    if items:
        # Find item table marker
        marker_ref = anchors.get("ITEM") or anchors.get("CÓDIGO") or "A20"
        _, marker_row = _parse_cell_ref(marker_ref)
        data_start_row = marker_row + 1
        
        # Cotización usually has one template row (data_start_row)
        if len(items) > 1:
            shift = len(items) - 1
            _shift_rows(sheet_data, data_start_row + 1, shift, ns)
            # Duplicate merged cells and rows
            for i in range(1, len(items)):
                target_row = data_start_row + i
                _duplicate_row(sheet_data, data_start_row, target_row, ns)
        
        # Fill items
        # We assume columns: A=Item, B=Code/Desc, etc. 
        # Better to have meta-mapping, but for now we follow the template pattern.
        for idx, item in enumerate(items):
            current_row_idx = data_start_row + idx
            row_el = _find_or_create_row(sheet_data, current_row_idx, ns)
            # Fill logic... (simplified for now, ideally uses meta-mapping)
            _set_cell_value(row_el, f"A{current_row_idx}", idx + 1, ns, is_number=True)
            _set_cell_value(row_el, f"B{current_row_idx}", item.get('descripcion', ''), ns)
            _set_cell_value(row_el, f"O{current_row_idx}", item.get('total', 0), ns, is_number=True)

    # 5. Fill Static Data (Headers/Footers)
    # Mapping data keys to labels
    label_to_key = {
        "CLIENTE:": "cliente",
        "RUC:": "ruc",
        "PROYECTO:": "proyecto",
        "FECHA:": "fecha_emision",
        "TOTAL:": "total",
    }
    
    for label, cell_ref in anchors.items():
        # Match label to data
        for lbl_match, key in label_to_key.items():
            if lbl_match in label:
                val = data.get(key, "")
                col, row_num = _parse_cell_ref(cell_ref)
                # Usually value is in neighbor cell
                target_col = _num_to_col_letter(_col_letter_to_num(col) + 1)
                row_el = _find_or_create_row(sheet_data, row_num, ns)
                _set_cell_value(row_el, f"{target_col}{row_num}", val, ns)

    # 6. Save back
    output = io.BytesIO()
    with zipfile.ZipFile(template_path, 'r') as z_in:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.namelist():
                if item == 'xl/worksheets/sheet1.xml':
                    z_out.writestr(item, etree.tostring(root))
                else:
                    z_out.writestr(item, z_in.read(item))
    
    output.seek(0)
    return output
