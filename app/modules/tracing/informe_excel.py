import io
import zipfile
import logging
import copy
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from lxml import etree

logger = logging.getLogger(__name__)

NAMESPACES = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
}

# Ruta del template
def _find_template():
    filename = "Resumen N-XXX-26 Compresion.xlsx"
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]  # app/

    possible_paths = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]

    for p in possible_paths:
        if p.exists():
            return str(p)

    return str(app_dir / "templates" / filename)

TEMPLATE_PATH = _find_template()

# --- XML Helpers ---

def _parse_cell_ref(ref: str) -> tuple[str, int]:
    col = ''.join(c for c in ref if c.isalpha())
    row = int(''.join(c for c in ref if c.isdigit()))
    return col, row

def _col_letter_to_num(col: str) -> int:
    num = 0
    for c in col.upper():
        num = num * 26 + (ord(c) - ord('A') + 1)
    return num

def _find_or_create_row(sheet_data: etree._Element, row_num: int, ns: str) -> etree._Element:
    for row in sheet_data.iterfind(f'{{{ns}}}row'):
        if row.get('r') == str(row_num):
            return row
    row = etree.SubElement(sheet_data, f'{{{ns}}}row')
    row.set('r', str(row_num))
    return row

def _set_cell_value_fast(row, ref, value, ns, is_number=False, get_string_idx=None):
    c = row.find(f'{{{ns}}}c[@r="{ref}"]')
    if c is None:
        c = etree.SubElement(row, f'{{{ns}}}c')
        c.set('r', ref)
    
    style = c.get('s')
    # Clear content
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

def _duplicate_row_xml(sheet_data: etree._Element, source_row_num: int, target_row_num: int, ns: str):
    source_row = sheet_data.find(f'{{{ns}}}row[@r="{source_row_num}"]')
    if source_row is None: return
    new_row = copy.deepcopy(source_row)
    new_row.set('r', str(target_row_num))
    for cell in new_row.findall(f'{{{ns}}}c'):
        old_ref = cell.get('r')
        col, _ = _parse_cell_ref(old_ref)
        cell.set('r', f'{col}{target_row_num}')
        for child in list(cell): cell.remove(child)
    # Append to sheetData
    sheet_data.append(new_row)

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
    mc_node = root.find(f'{{{ns}}}mergeCells')
    if mc_node is None: return
    for mc in mc_node.findall(f'{{{ns}}}mergeCell'):
        ref = mc.get('ref')
        if not ref or ':' not in ref: continue
        parts = ref.split(':')
        new_parts = []
        for p in parts:
            c, r = _parse_cell_ref(p)
            if r >= from_row: new_parts.append(f"{c}{r + shift}")
            else: new_parts.append(p)
        mc.set('ref', ':'.join(new_parts))

def _format_date(val) -> str:
    if val is None: return ""
    if isinstance(val, datetime): return val.strftime("%d/%m/%Y")
    if isinstance(val, str):
        if "/" in val: return val
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        except: return val
    return str(val)

def generate_informe_excel(data: dict) -> bytes:
    if not Path(TEMPLATE_PATH).exists():
        raise FileNotFoundError(f"Template no encontrado: {TEMPLATE_PATH}")

    # 1. Shared Strings Extraction
    shared_strings = []
    ss_xml_original = None
    with zipfile.ZipFile(TEMPLATE_PATH, 'r') as z:
        if 'xl/sharedStrings.xml' in z.namelist():
            ss_xml_original = z.read('xl/sharedStrings.xml')
            ss_root = etree.fromstring(ss_xml_original)
            ns_ss = ss_root.nsmap.get(None, NAMESPACES['main'])
            for si in ss_root.findall(f'{{{ns_ss}}}si'):
                t = si.find(f'{{{ns_ss}}}t')
                if t is not None: shared_strings.append((t.text or "").strip())
                else: shared_strings.append(''.join([x.text or '' for x in si.findall(f'.//{{{ns_ss}}}t')]).strip())

    ss_map = {text: i for i, text in enumerate(shared_strings)}
    def get_string_idx(text: str) -> int:
        text = str(text or "").strip()
        if text in ss_map: return ss_map[text]
        idx = len(shared_strings)
        shared_strings.append(text)
        ss_map[text] = idx
        return idx

    # 2. Sheet XML Modification
    sheet_file = 'xl/worksheets/sheet1.xml'
    with zipfile.ZipFile(TEMPLATE_PATH, 'r') as z:
        sheet_xml = z.read(sheet_file)
    
    root = etree.fromstring(sheet_xml)
    ns = NAMESPACES['main']
    sheet_data = root.find(f'.//{{{ns}}}sheetData')

    items = data.get("items", [])
    num_items = len(items)
    template_rows = 14
    data_start_row = 18

    # Dynamic row shifting for extra samples
    # User request: "agregale una fila de isntacia siempre" -> Add spacer row
    # We shift by extra_rows + 1 to ensure there is always at least one empty row between samples and footer
    extra_rows = 0
    if num_items > template_rows:
        extra_rows = num_items - template_rows
    
    # Always shift to guarantee footer is pushed down correctly, adding buffer
    # If we have enough space in template, we don't strictly *need* to shift, but 
    # the user wants to ensure separation.
    # Logic: 
    # Template has 14 rows (18-31). Footer starts at 32.
    # If we have 22 items. Ends at 18+22-1 = 39.
    # We need footer at 41 (gap at 40).
    # Original footer at 32. Shift needed: 41 - 32 = 9.
    # Formula: shift = (data_start_row + num_items + 1) - (original_footer_row)
    # original_footer_row = data_start_row + template_rows = 18 + 14 = 32
    # shift = (18 + 22 + 1) - 32 = 41 - 32 = 9.
    # 9 = (22 - 14) + 1 = extra_rows + 1.
    
    # If num_items <= template_rows (e.g. 5). Ends at 22.
    # We want footer at 32 (default). Gap is 23-31. No shift needed.
    
    shift_amount = 0
    if num_items > template_rows:
        shift_amount = extra_rows + 1 # +1 for spacer
        shift_at = data_start_row + template_rows # Row 32
        _shift_rows(sheet_data, shift_at, shift_amount, ns)
        _shift_merged_cells(root, shift_at, shift_amount, ns)
        
        # Replicate template rows for the new items
        source_row = data_start_row + template_rows - 1 # Row 31 (last formatted item row)
        for i in range(template_rows, num_items):
             _duplicate_row_xml(sheet_data, source_row, data_start_row + i, ns)
             
    # Cache for performance (refresh after shift)
    rows_cache = {r.get('r'): r for r in sheet_data.findall(f'{{{ns}}}row')}
    def write_cell(ref, value, is_num=False):
        _, r_num = _parse_cell_ref(ref)
        row_el = rows_cache.get(str(r_num))
        if row_el is None:
            row_el = _find_or_create_row(sheet_data, r_num, ns)
            rows_cache[str(r_num)] = row_el
        _set_cell_value_fast(row_el, ref, value, ns, is_num, get_string_idx)


    # Fill Header (Column L in Template)
    # Row 8 Validation: B8 is "Proyecto". If merged, writing to top-left B8 is correct.
    write_cell("B6", data.get("cliente", ""))
    write_cell("B7", data.get("direccion", ""))
    write_cell("B8", data.get("proyecto", ""))
    write_cell("B9", data.get("ubicacion", ""))
    write_cell("L6", data.get("recepcion_numero", ""))
    write_cell("L7", data.get("ot_numero", ""))
    write_cell("B11", data.get("estructura", ""))
    fc_header = data.get("fc_kg_cm2")
    write_cell("B12", fc_header, is_num=True if isinstance(fc_header, (int, float)) else False)
    write_cell("L10", _format_date(data.get("fecha_recepcion")))
    write_cell("L11", _format_date(data.get("fecha_moldeo")))
    
    fecha_rotura = data.get("fecha_rotura")
    if not fecha_rotura and items:
        fecha_rotura = items[0].get("fecha_ensayo")
    write_cell("L12", _format_date(fecha_rotura))
    write_cell("L13", data.get("hora_moldeo", ""))
    write_cell("L14", data.get("hora_rotura", ""))
    
    densidad = data.get("densidad")
    if isinstance(densidad, bool): den_val = "Sí" if densidad else "No"
    else: den_val = str(densidad) if densidad else ""
    write_cell("L15", den_val)

    # Fill Items
    for i, item in enumerate(items):
        r = data_start_row + i
        write_cell(f"A{r}", item.get("codigo_lem", ""))
        write_cell(f"B{r}", item.get("estructura", ""))
        
        # Override Column C (FC) to strip custom style (suffix "-CO-26")
        fc_ref = f"C{r}"
        fc_val = item.get("fc_kg_cm2")
        write_cell(fc_ref, fc_val, is_num=True)
        
        # Apply clean style 19
        _, r_num = _parse_cell_ref(fc_ref)
        row_el = rows_cache.get(str(r_num))
        if row_el is not None:
            c_node = row_el.find(f'{{{ns}}}c[@r="{fc_ref}"]')
            if c_node is not None:
                c_node.set('s', '19')

        write_cell(f"D{r}", item.get("codigo_cliente", ""))
        write_cell(f"E{r}", item.get("diametro_1"), is_num=True)
        write_cell(f"F{r}", item.get("diametro_2"), is_num=True)
        write_cell(f"G{r}", item.get("longitud_1"), is_num=True)
        write_cell(f"H{r}", item.get("longitud_2"), is_num=True)
        write_cell(f"I{r}", item.get("longitud_3"), is_num=True)
        write_cell(f"J{r}", item.get("carga_maxima"), is_num=True)
        write_cell(f"K{r}", item.get("tipo_fractura", ""))
        write_cell(f"L{r}", item.get("masa_muestra_aire"), is_num=True)
        
    # Fill Footer (Equipment Code)
    # Original footer start: 32
    # New footer start: 32 + shift_amount
    footer_start_row = 32 + shift_amount
    codigo_equipo = data.get("codigo_equipo", "")
    if codigo_equipo:
        # Write to B column in the footer row (Equipment row)
        # Assuming layout: A=Label, B=Code...
        write_cell(f"B{footer_start_row}", codigo_equipo)

    # ── 3. Final Serialization & Structural Cleanup ──

    # Update dimension ref tag (CRITICAL to avoid corruption when adding rows)
    max_row = data_start_row + num_items + shift_amount + 7 
    dim_node = root.find(f'{{{ns}}}dimension')
    if dim_node is not None:
        dim_node.set('ref', f"A1:L{max_row}")

    # CRITICAL: Excel require row elements within sheetData to be in strictly ascending order
    # Shifting and duplication can leave the XML tree out of order.
    rows_list = list(sheet_data.findall(f'{{{ns}}}row'))
    rows_list.sort(key=lambda r_node: int(r_node.get('r', 0)))
    
    # Re-append rows in correct order
    for r_el in list(sheet_data):
        if r_el.tag == f'{{{ns}}}row':
            sheet_data.remove(r_el)
    for r_el in rows_list:
        sheet_data.append(r_el)

    modified_sheet = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    
    # Rebuild Shared Strings with clean namespaces
    ss_root_new = etree.Element(f'{{{ns}}}sst', nsmap={None: ns})
    for text in shared_strings:
        si = etree.SubElement(ss_root_new, f'{{{ns}}}si')
        t = etree.SubElement(si, f'{{{ns}}}t')
        t.text = str(text)
    
    ss_root_new.set('count', str(len(shared_strings)))
    ss_root_new.set('uniqueCount', str(len(shared_strings)))
    modified_ss = etree.tostring(ss_root_new, encoding='utf-8', xml_declaration=True)

    # 4. Handle Drawings (Line shift if extra rows)
    drawing_file = 'xl/drawings/drawing1.xml'
    modified_drawing = None
    if shift_amount > 0:
        with zipfile.ZipFile(TEMPLATE_PATH, 'r') as z:
            if drawing_file in z.namelist():
                d_root = etree.fromstring(z.read(drawing_file))
                d_ns = {'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'}
                for anchor in d_root.xpath('//xdr:twoCellAnchor | //xdr:oneCellAnchor', namespaces=d_ns):
                    frow = anchor.find('.//xdr:from/xdr:row', namespaces=d_ns)
                    trow = anchor.find('.//xdr:to/xdr:row', namespaces=d_ns)
                    if frow is not None and int(frow.text) >= 31: # Footer area anchor
                        frow.text = str(int(frow.text) + shift_amount)
                        if trow is not None: trow.text = str(int(trow.text) + shift_amount)
                modified_drawing = etree.tostring(d_root, encoding='utf-8', xml_declaration=True)

    # 5. Pack into ZIP
    output = io.BytesIO()
    with zipfile.ZipFile(TEMPLATE_PATH, 'r') as z_in:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.namelist():
                if item == sheet_file: z_out.writestr(item, modified_sheet)
                elif item == 'xl/sharedStrings.xml': z_out.writestr(item, modified_ss)
                elif item == drawing_file and modified_drawing is not None: z_out.writestr(item, modified_drawing)
                else: z_out.writestr(item, z_in.read(item))
    
    output.seek(0)
    return output.getvalue()

