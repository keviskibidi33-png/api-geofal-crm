import io
import zipfile
import unicodedata
from typing import Any
from lxml import etree
from datetime import date
from app.xlsx_direct_v2 import (
    NAMESPACES, _parse_cell_ref, _col_letter_to_num, _find_or_create_row, 
    _find_or_create_cell, _set_cell_value, _duplicate_row, _shift_rows, _shift_merged_cells
)


def _normalize_header_text(value: Any) -> str:
    """Normalize header labels for resilient matching."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("\n", " ").replace("\r", " ")
    text = "".join(ch if ch.isalnum() else " " for ch in text.upper())
    return " ".join(text.split())


def _extract_cell_text(cell: etree._Element, ns: str, shared_strings: list[str]) -> str:
    """Extract plain text from XML cell values (shared strings or inline strings)."""
    cell_type = cell.get("t")
    if cell_type == "s":
        v = cell.find(f'{{{ns}}}v')
        if v is None or not v.text:
            return ""
        try:
            idx = int(v.text)
        except (TypeError, ValueError):
            return ""
        return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
    if cell_type == "inlineStr":
        text_nodes = cell.findall(f'.//{{{ns}}}t')
        return "".join(node.text or "" for node in text_nodes)

    v = cell.find(f'{{{ns}}}v')
    return v.text if v is not None and v.text else ""


def _resolve_admin_header_field(normalized_header: str) -> tuple[str, bool] | None:
    """Map normalized ADMIN template headers to API item fields."""
    direct_map: dict[str, tuple[str, bool]] = {
        "ITEM": ("item_numero", False),
        "RECEP N": ("recep_numero", False),
        "FECHA RECEPCION": ("fecha_recepcion", False),
        "CLIENTE": ("cliente_nombre", False),
        "PROYECTO": ("proyecto", False),
        "COTIZACION": ("cotizacion_lab", False),
        "FACTURACION": ("numero_factura", False),
        "N FACTURA": ("numero_factura", False),
        "NO FACTURA": ("numero_factura", False),
        "NRO FACTURA": ("numero_factura", False),
        "NUMERO FACTURA": ("numero_factura", False),
        "ESTADO PAGO": ("estado_pago", False),
        "ESTADO PARA AUTORIZAR": ("estado_autorizar", False),
        "NOTA": ("nota_admin", False),
        "FECHA SOLICITUD": ("fecha_solicitud_com", False),
        "FECHA ENTREGA": ("fecha_entrega_com", False),
        "MOTIVO DIAS ATRASO": ("motivo_dias_atraso_com", False),
    }
    if normalized_header in direct_map:
        return direct_map[normalized_header]
    if normalized_header.startswith("EVIDENCIA SOLICITUD"):
        return ("evidencia_solicitud_envio", False)
    if normalized_header.startswith("DIAS ATRASO"):
        return ("dias_atraso_envio_coti", True)
    return None


def _discover_admin_template_mapping(
    sheet_data: etree._Element, ns: str, shared_strings: list[str]
) -> tuple[int, dict[str, tuple[str, bool]]]:
    """
    Discover header row and column mapping from ADMIN template.
    Falls back to legacy fixed layout A-H when headers cannot be detected.
    """
    fallback_start_row = 6
    fallback_map: dict[str, tuple[str, bool]] = {
        "A": ("item_numero", False),
        "B": ("recep_numero", False),
        "C": ("fecha_recepcion", False),
        "D": ("cliente_nombre", False),
        "E": ("numero_factura", False),
        "F": ("estado_pago", False),
        "G": ("estado_autorizar", False),
        "H": ("nota_admin", False),
    }

    best_score = 0
    best_header_row = 0
    best_mapping: dict[str, tuple[str, bool]] = {}

    for row in sheet_data.findall(f'{{{ns}}}row'):
        row_ref = row.get("r")
        if not row_ref:
            continue
        try:
            row_num = int(row_ref)
        except ValueError:
            continue
        if row_num > 20:
            continue

        row_mapping: dict[str, tuple[str, bool]] = {}
        for cell in row.findall(f'{{{ns}}}c'):
            cell_ref = cell.get("r")
            if not cell_ref:
                continue
            col_letter, _ = _parse_cell_ref(cell_ref)
            header_text = _extract_cell_text(cell, ns, shared_strings)
            normalized = _normalize_header_text(header_text)
            if not normalized:
                continue
            field_info = _resolve_admin_header_field(normalized)
            if field_info:
                row_mapping[col_letter] = field_info

        score = len(row_mapping)
        if score > best_score:
            best_score = score
            best_header_row = row_num
            best_mapping = row_mapping

    if best_score >= 4 and best_header_row > 0:
        return best_header_row + 1, best_mapping
    return fallback_start_row, fallback_map


def export_programacion_xlsx(template_path: str, items: list[dict]) -> io.BytesIO:
    """
    Exporta Programacion XLSX modificando el XML del template directamente.
    Mapeo:
    ITEM: A
    RECEP. N: B
    OT: C
    CODIGOS MUESTRAS: D
    FECHA RECEPCION: E
    FECHA INICIO: F
    FECHA ENTREGA: G
    CLIENTE: H
    DESCRIPCION SERVICIO: I
    PROYECTO: J
    FECHA ENTREG REAL: K
    ESTADO: L
    COTIZACION: M
    AUTORIZ: N
    NOTA: P
    DIAS ATE: Q
    MOTIVO ATRASO: R
    EVIDENCIA RECEPC: S
    EVIDENCIA INFORME: T
    
    Data starts at Row 9.
    """
    
    # 1. Load shared strings
    shared_strings = []
    shared_strings_map = {}
    ss_xml_original = None
    
    with zipfile.ZipFile(template_path, 'r') as z:
        if 'xl/sharedStrings.xml' in z.namelist():
            ss_xml_original = z.read('xl/sharedStrings.xml')
            ss_root = etree.fromstring(ss_xml_original)
            ns = ss_root.nsmap.get(None, NAMESPACES['main'])
            
            for si in ss_root.findall(f'{{{ns}}}si'):
                t = si.find(f'{{{ns}}}t')
                if t is not None and t.text:
                    shared_strings.append(t.text)
                    shared_strings_map[t.text] = len(shared_strings) - 1
                else:
                    r_texts = si.findall(f'.//{{{ns}}}t')
                    text = ''.join([t.text or '' for t in r_texts])
                    shared_strings.append(text)
                    if text:
                        shared_strings_map[text] = len(shared_strings) - 1

    def get_string_idx(text: str) -> int:
        if text is None: text = ""
        s_text = str(text)
        if s_text in shared_strings_map:
            return shared_strings_map[s_text]
        idx = len(shared_strings)
        shared_strings.append(s_text)
        shared_strings_map[s_text] = idx
        return idx

    # 2. Modify Sheet 1
    # We assume 'sheet1.xml' is the data sheet.
    sheet_file = 'xl/worksheets/sheet1.xml'
    
    # Check if sheet1 exists
    with zipfile.ZipFile(template_path, 'r') as z:
        if sheet_file not in z.namelist():
            # If not sheet1, try finding the first sheet
            # But usually it is sheet1.
            pass
        sheet_data_xml = z.read(sheet_file)
        
    root = etree.fromstring(sheet_data_xml)
    ns = root.nsmap.get(None, NAMESPACES['main'])
    sheet_data = root.find(f'.//{{{ns}}}sheetData')
    
    START_ROW = 9
    
    if sheet_data is not None:
        # Loop items
        for idx, item in enumerate(items):
            current_row = START_ROW + idx
            
            # If not first item, duplicate the row style/structure from START_ROW
            if idx > 0:
                _duplicate_row(sheet_data, START_ROW, current_row, ns)
                # Note: duplicate_row inserts the row. If we had rows below, they are pushed down?
                # The _duplicate_row logic in v2 inserts and apparently does NOT shift others automatically unless specified?
                # Checking v2 code:
                # "insert(list(sheet_data).index(row), new_row)" -> inserts before next row.
                # It does NOT shift 'r' attributes of subsequent rows.
                # However, usually we generate these sequentially. If there were footer rows, we'd need _shift_rows first.
                # Assuming the template has empty rows or we are appending. 
                # If the template is a fixed form with footer, we MUST shift rows first.
                # User says "rellenar las casillas y asi sucesivamente".
                # Safest approach: Shift rows below by 1 FIRST, then duplicate.
                # But _duplicate_row duplicates SOURCE row to TARGET row.
                
                # Let's assume infinite list. But if there are totals at the bottom, we need to shift.
                # Since I don't know if there are totals, but usually these "Control" sheets might be just a list.
                # I'll rely on appending logic if no existing row at target, othewise shift.
                pass

        # Wait, the correct logic for dynamic list insertion in a potentially bounded table is:
        # 1. Determine Count.
        # 2. Shift everything below START_ROW by (Count - 1).
        # 3. Duplicate Row START_ROW (Count - 1) times.
        # 4. Fill data.
        
        count = len(items)
        if count > 1:
            # We have 1 row (9). We need count-1 more.
            # Shift everything from row 10 downwards by count-1
            _shift_rows(sheet_data, START_ROW + 1, count - 1, ns)
            # Also merged cells
            _shift_merged_cells(root, START_ROW + 1, count - 1, ns)
            
            # Now duplicate row 9 into 10, 11, ...
            for i in range(1, count):
                _duplicate_row(sheet_data, START_ROW, START_ROW + i, ns)
                
        # Fill Data
        for idx, item in enumerate(items):
            row = START_ROW + idx
            # Mapping
            # A: ITEM
            _set_cell_value(sheet_data, f'A{row}', item.get('item_numero', ''), ns, get_string_idx=get_string_idx)
            # B: RECEP
            _set_cell_value(sheet_data, f'B{row}', item.get('recep_numero', ''), ns, get_string_idx=get_string_idx)
            # C: OT
            _set_cell_value(sheet_data, f'C{row}', item.get('ot', ''), ns, get_string_idx=get_string_idx)
            # D: CODIGOS
            _set_cell_value(sheet_data, f'D{row}', item.get('codigo_muestra', ''), ns, get_string_idx=get_string_idx)
            # E: FECHA RECEPCION
            _set_cell_value(sheet_data, f'E{row}', item.get('fecha_recepcion', ''), ns, get_string_idx=get_string_idx)
            # F: FECHA INICIO
            _set_cell_value(sheet_data, f'F{row}', item.get('fecha_inicio', ''), ns, get_string_idx=get_string_idx)
            # G: FECHA ENTREGA
            _set_cell_value(sheet_data, f'G{row}', item.get('fecha_entrega_estimada', ''), ns, get_string_idx=get_string_idx)
            # H: CLIENTE
            _set_cell_value(sheet_data, f'H{row}', item.get('cliente_nombre', ''), ns, get_string_idx=get_string_idx)
            # I: DESCRIPCION
            _set_cell_value(sheet_data, f'I{row}', item.get('descripcion_servicio', ''), ns, get_string_idx=get_string_idx)
            # J: PROYECTO
            _set_cell_value(sheet_data, f'J{row}', item.get('proyecto', ''), ns, get_string_idx=get_string_idx)
            # K: REAL
            _set_cell_value(sheet_data, f'K{row}', item.get('entrega_real', ''), ns, get_string_idx=get_string_idx)
            # L: ESTADO
            _set_cell_value(sheet_data, f'L{row}', item.get('estado_trabajo', ''), ns, get_string_idx=get_string_idx)
            # M: COTIZACION
            _set_cell_value(sheet_data, f'M{row}', item.get('cotizacion_lab', ''), ns, get_string_idx=get_string_idx)
            # N: AUTORIZ
            _set_cell_value(sheet_data, f'N{row}', item.get('autorizacion_lab', ''), ns, get_string_idx=get_string_idx)
            # P: NOTA (O skipped?) User said "NOTA: P8". O is missing? Maybe hidden or empty.
            _set_cell_value(sheet_data, f'P{row}', item.get('nota_lab', ''), ns, get_string_idx=get_string_idx)
            # Q: DIAS ATE
            _set_cell_value(sheet_data, f'Q{row}', item.get('dias_atraso_lab', ''), ns, is_number=True)
            # R: MOTIVO
            _set_cell_value(sheet_data, f'R{row}', item.get('motivo_dias_atraso_lab', ''), ns, get_string_idx=get_string_idx)
            # S: EVIDENCIA REC
            _set_cell_value(sheet_data, f'S{row}', item.get('evidencia_envio_recepcion', ''), ns, get_string_idx=get_string_idx)
            # T: EVIDENCIA INF
            _set_cell_value(sheet_data, f'T{row}', item.get('envio_informes', ''), ns, get_string_idx=get_string_idx)

    # 3. Serialize
    modified_sheet1 = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    
    # 4. Update Shared Strings
    modified_ss = None
    if ss_xml_original:
        ss_root = etree.fromstring(ss_xml_original)
        ss_ns = ss_root.nsmap.get(None, NAMESPACES['main'])
        
        # Clear existing keys to avoid dupe/mess? No, reconstruct.
        for child in list(ss_root):
            ss_root.remove(child)
        
        for text in shared_strings:
            si = etree.SubElement(ss_root, f'{{{ss_ns}}}si')
            t = etree.SubElement(si, f'{{{ss_ns}}}t')
            t.text = text if text else ''
        
        ss_root.set('count', str(len(shared_strings)))
        ss_root.set('uniqueCount', str(len(shared_strings)))
        
        modified_ss = etree.tostring(ss_root, encoding='utf-8', xml_declaration=True)

    # 5. Write Output
    output = io.BytesIO()
    with zipfile.ZipFile(template_path, 'r') as z_in:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.namelist():
                if item == sheet_file:
                    z_out.writestr(item, modified_sheet1)
                elif item == 'xl/sharedStrings.xml' and modified_ss:
                    z_out.writestr(item, modified_ss)
                else:
                    z_out.writestr(item, z_in.read(item))
                    
    output.seek(0)
    return output


def export_programacion_comercial_xlsx(template_path: str, items: list[dict]) -> io.BytesIO:
    """
    Exporta Programacion COMERCIAL XLSX modificando el XML del template directamente.
    Mapeo (segun Template_Programacion_Comercial.xlsx):
    ITEM: A
    RECEP.N: B
    FECHA RECEPCIÓN: C
    CLIENTE: D
    COTIZACION: E
    FECHA SOLICITUD: F
    FECHA ENTREGA: G
    EVIDENCIA SOLICITUD - ENVIO - ACEPTACION COTIZ: H
    DIAS ATRASO ENVIO COTIZ.: I
    MOTIVO DIAS ATRASO: J
    
    Data starts at Row 9.
    """
    
    # 1. Load shared strings
    shared_strings = []
    shared_strings_map = {}
    ss_xml_original = None
    
    with zipfile.ZipFile(template_path, 'r') as z:
        if 'xl/sharedStrings.xml' in z.namelist():
            ss_xml_original = z.read('xl/sharedStrings.xml')
            ss_root = etree.fromstring(ss_xml_original)
            ns = ss_root.nsmap.get(None, NAMESPACES['main'])
            
            for si in ss_root.findall(f'{{{ns}}}si'):
                t = si.find(f'{{{ns}}}t')
                if t is not None and t.text:
                    shared_strings.append(t.text)
                    shared_strings_map[t.text] = len(shared_strings) - 1
                else:
                    r_texts = si.findall(f'.//{{{ns}}}t')
                    text = ''.join([t.text or '' for t in r_texts])
                    shared_strings.append(text)
                    if text:
                        shared_strings_map[text] = len(shared_strings) - 1

    def get_string_idx(text: str) -> int:
        if text is None: text = ""
        s_text = str(text)
        if s_text in shared_strings_map:
            return shared_strings_map[s_text]
        idx = len(shared_strings)
        shared_strings.append(s_text)
        shared_strings_map[s_text] = idx
        return idx

    # 2. Modify Sheet 1
    sheet_file = 'xl/worksheets/sheet1.xml'
    
    with zipfile.ZipFile(template_path, 'r') as z:
        sheet_data_xml = z.read(sheet_file)
        
    root = etree.fromstring(sheet_data_xml)
    ns = root.nsmap.get(None, NAMESPACES['main'])
    sheet_data = root.find(f'.//{{{ns}}}sheetData')
    
    START_ROW = 9
    
    if sheet_data is not None:
        count = len(items)
        if count > 1:
            _shift_rows(sheet_data, START_ROW + 1, count - 1, ns)
            _shift_merged_cells(root, START_ROW + 1, count - 1, ns)
            
            for i in range(1, count):
                _duplicate_row(sheet_data, START_ROW, START_ROW + i, ns)
                
        # Fill Data
        for idx, item in enumerate(items):
            row = START_ROW + idx
            # A: ITEM
            _set_cell_value(sheet_data, f'A{row}', item.get('item_numero', ''), ns, get_string_idx=get_string_idx)
            # B: RECEP.N
            _set_cell_value(sheet_data, f'B{row}', item.get('recep_numero', ''), ns, get_string_idx=get_string_idx)
            # C: FECHA RECEPCIÓN
            _set_cell_value(sheet_data, f'C{row}', item.get('fecha_recepcion', ''), ns, get_string_idx=get_string_idx)
            # D: CLIENTE
            _set_cell_value(sheet_data, f'D{row}', item.get('cliente_nombre', ''), ns, get_string_idx=get_string_idx)
            # E: COTIZACION
            _set_cell_value(sheet_data, f'E{row}', item.get('cotizacion_lab', ''), ns, get_string_idx=get_string_idx)
            # F: FECHA SOLICITUD
            _set_cell_value(sheet_data, f'F{row}', item.get('fecha_solicitud_com', ''), ns, get_string_idx=get_string_idx)
            # G: FECHA ENTREGA
            _set_cell_value(sheet_data, f'G{row}', item.get('fecha_entrega_com', ''), ns, get_string_idx=get_string_idx)
            # H: EVIDENCIA
            _set_cell_value(sheet_data, f'H{row}', item.get('evidencia_solicitud_envio', ''), ns, get_string_idx=get_string_idx)
            # I: DIAS ATRASO
            _set_cell_value(sheet_data, f'I{row}', item.get('dias_atraso_envio_coti', ''), ns, is_number=True)
            # J: MOTIVO
            _set_cell_value(sheet_data, f'J{row}', item.get('motivo_dias_atraso_com', ''), ns, get_string_idx=get_string_idx)

    # 3. Serialize
    modified_sheet1 = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    
    # 4. Update Shared Strings
    modified_ss = None
    if ss_xml_original:
        ss_root = etree.fromstring(ss_xml_original)
        ss_ns = ss_root.nsmap.get(None, NAMESPACES['main'])
        
        for child in list(ss_root):
            ss_root.remove(child)
        
        for text in shared_strings:
            si = etree.SubElement(ss_root, f'{{{ss_ns}}}si')
            t = etree.SubElement(si, f'{{{ss_ns}}}t')
            t.text = text if text else ''
        
        ss_root.set('count', str(len(shared_strings)))
        ss_root.set('uniqueCount', str(len(shared_strings)))
        
        modified_ss = etree.tostring(ss_root, encoding='utf-8', xml_declaration=True)

    # 5. Write Output
    output = io.BytesIO()
    with zipfile.ZipFile(template_path, 'r') as z_in:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.namelist():
                if item == sheet_file:
                    z_out.writestr(item, modified_sheet1)
                elif item == 'xl/sharedStrings.xml' and modified_ss:
                    z_out.writestr(item, modified_ss)
                else:
                    z_out.writestr(item, z_in.read(item))
                    
    output.seek(0)
    return output


def export_programacion_administracion_xlsx(template_path: str, items: list[dict]) -> io.BytesIO:
    """
    Exporta Programacion ADMINISTRACION XLSX modificando el XML del template directamente.
    Detecta headers del template y llena columnas por nombre para evitar
    errores cuando se inserten o reordenen columnas (p.ej. PROYECTO/FACTURACION).
    Si no detecta headers, usa el layout legacy A-H (data desde fila 6).
    """
    
    # 1. Load shared strings
    shared_strings = []
    shared_strings_map = {}
    ss_xml_original = None
    
    with zipfile.ZipFile(template_path, 'r') as z:
        if 'xl/sharedStrings.xml' in z.namelist():
            ss_xml_original = z.read('xl/sharedStrings.xml')
            ss_root = etree.fromstring(ss_xml_original)
            ns = ss_root.nsmap.get(None, NAMESPACES['main'])
            
            for si in ss_root.findall(f'{{{ns}}}si'):
                t = si.find(f'{{{ns}}}t')
                if t is not None and t.text:
                    shared_strings.append(t.text)
                    shared_strings_map[t.text] = len(shared_strings) - 1
                else:
                    r_texts = si.findall(f'.//{{{ns}}}t')
                    text = ''.join([t.text or '' for t in r_texts])
                    shared_strings.append(text)
                    if text:
                        shared_strings_map[text] = len(shared_strings) - 1

    def get_string_idx(text: str) -> int:
        if text is None: text = ""
        s_text = str(text)
        if s_text in shared_strings_map:
            return shared_strings_map[s_text]
        idx = len(shared_strings)
        shared_strings.append(s_text)
        shared_strings_map[s_text] = idx
        return idx

    # 2. Modify Sheet 1
    sheet_file = 'xl/worksheets/sheet1.xml'
    
    with zipfile.ZipFile(template_path, 'r') as z:
        sheet_data_xml = z.read(sheet_file)
        
    root = etree.fromstring(sheet_data_xml)
    ns = root.nsmap.get(None, NAMESPACES['main'])
    sheet_data = root.find(f'.//{{{ns}}}sheetData')
    
    START_ROW = 6
    column_mapping: dict[str, tuple[str, bool]] = {
        "A": ("item_numero", False),
        "B": ("recep_numero", False),
        "C": ("fecha_recepcion", False),
        "D": ("cliente_nombre", False),
        "E": ("numero_factura", False),
        "F": ("estado_pago", False),
        "G": ("estado_autorizar", False),
        "H": ("nota_admin", False),
    }
    
    if sheet_data is not None:
        START_ROW, column_mapping = _discover_admin_template_mapping(
            sheet_data=sheet_data,
            ns=ns,
            shared_strings=shared_strings,
        )

        count = len(items)
        if count > 1:
            _shift_rows(sheet_data, START_ROW + 1, count - 1, ns)
            _shift_merged_cells(root, START_ROW + 1, count - 1, ns)
            
            for i in range(1, count):
                _duplicate_row(sheet_data, START_ROW, START_ROW + i, ns)
                
        # Fill Data
        for idx, item in enumerate(items):
            row = START_ROW + idx
            for col_letter, (field_name, is_number) in sorted(
                column_mapping.items(),
                key=lambda entry: _col_letter_to_num(entry[0]),
            ):
                if field_name == "estado_autorizar":
                    value = item.get("autorizacion_lab") or item.get("estado_autorizar", "")
                elif field_name == "numero_factura":
                    value = item.get("numero_factura") or item.get("facturacion", "")
                else:
                    value = item.get(field_name, "")

                _set_cell_value(
                    sheet_data,
                    f"{col_letter}{row}",
                    value,
                    ns,
                    is_number=is_number,
                    get_string_idx=get_string_idx,
                )

    # 3. Serialize
    modified_sheet1 = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    
    # 4. Update Shared Strings
    modified_ss = None
    if ss_xml_original:
        ss_root = etree.fromstring(ss_xml_original)
        ss_ns = ss_root.nsmap.get(None, NAMESPACES['main'])
        
        for child in list(ss_root):
            ss_root.remove(child)
        
        for text in shared_strings:
            si = etree.SubElement(ss_root, f'{{{ss_ns}}}si')
            t = etree.SubElement(si, f'{{{ss_ns}}}t')
            t.text = text if text else ''
        
        ss_root.set('count', str(len(shared_strings)))
        ss_root.set('uniqueCount', str(len(shared_strings)))
        
        modified_ss = etree.tostring(ss_root, encoding='utf-8', xml_declaration=True)

    # 5. Write Output
    output = io.BytesIO()
    with zipfile.ZipFile(template_path, 'r') as z_in:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.namelist():
                if item == sheet_file:
                    z_out.writestr(item, modified_sheet1)
                elif item == 'xl/sharedStrings.xml' and modified_ss:
                    z_out.writestr(item, modified_ss)
                else:
                    z_out.writestr(item, z_in.read(item))
                    
    output.seek(0)
    return output

