from lxml import etree
import zipfile
import io
from pathlib import Path

NAMESPACES = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
}

def dump_labels(template_path):
    print(f"Dumping labels from: {template_path}")
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
        sheet_xml = z.read('xl/worksheets/sheet1.xml')
    
    root = etree.fromstring(sheet_xml)
    ns = NAMESPACES['main']
    sheet_data = root.find(f'{{{ns}}}sheetData')

    for row in sheet_data.findall(f'{{{ns}}}row'):
        for cell in row.findall(f'{{{ns}}}c'):
            if cell.get('t') == 's':
                v = cell.find(f'{{{ns}}}v')
                if v is not None:
                    try:
                        idx = int(v.text)
                        if 0 <= idx < len(shared_strings):
                            val = shared_strings[idx].strip()
                            if val:
                                print(f"[{cell.get('r')}]: '{val}'")
                    except: pass

if __name__ == "__main__":
    template = Path("c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Temp_Cotizacion.xlsx")
    if template.exists():
        dump_labels(template)
    else:
        print("Template not found")
