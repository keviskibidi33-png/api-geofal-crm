from lxml import etree
import zipfile
import io
from pathlib import Path

NAMESPACES = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
}

def dump_all_labels(template_path, sheet_rel_path):
    print(f"Dumping ALL labels from: {sheet_rel_path}")
    shared_strings = []
    with zipfile.ZipFile(template_path, 'r') as z:
        if 'xl/sharedStrings.xml' in z.namelist():
            ss_xml = z.read('xl/sharedStrings.xml')
            ss_root = etree.fromstring(ss_xml)
            ns_ss = ss_root.nsmap.get(None, NAMESPACES['main'])
            for si in ss_root.findall(f'{{{ns_ss}}}si'):
                t = si.find(f'{{{ns_ss}}}t')
                if t is not None:
                    shared_strings.append(t.text or "")
                else:
                    shared_strings.append("".join(node.text or "" for node in si.xpath(".//main:t", namespaces=NAMESPACES)))

    with zipfile.ZipFile(template_path, 'r') as z:
        sheet_xml = z.read(f"xl/{sheet_rel_path}")
    
    root = etree.fromstring(sheet_xml)
    ns = NAMESPACES['main']
    sheet_data = root.find(f'{{{ns}}}sheetData')

    for row in sheet_data.findall(f'{{{ns}}}row'):
        for cell in row.findall(f'{{{ns}}}c'):
            val = ""
            if cell.get('t') == 's':
                v = cell.find(f'{{{ns}}}v')
                if v is not None:
                    try:
                        idx = int(v.text)
                        if 0 <= idx < len(shared_strings):
                            val = shared_strings[idx].strip()
                    except: pass
            
            if val:
                print(f"[{cell.get('r')}]: '{val}'")

if __name__ == "__main__":
    template = Path("c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Temp_Cotizacion.xlsx")
    dump_all_labels(template, "worksheets/sheet8.xml")
