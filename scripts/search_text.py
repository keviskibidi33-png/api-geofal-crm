import zipfile
from lxml import etree
import sys
sys.path.append('.')
from app.modules.common.excel_xml import find_template_path

path = find_template_path('Template_GranAgregado.xlsx')
with zipfile.ZipFile(path, 'r') as z:
    sst_root = etree.fromstring(z.read('xl/sharedStrings.xml'))
    ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    strings = []
    for si in sst_root.findall('ns:si', ns):
        # concatenate all <t> in <si>
        t_text = "".join(t.text for t in si.findall('.//ns:t', ns) if t.text)
        strings.append(t_text)
        
    print(f"Loaded {len(strings)} shared strings.")
    
    for name in z.namelist():
        if name.startswith('xl/worksheets/'):
            root = etree.fromstring(z.read(name))
            for cell in root.findall('.//ns:c', ns):
                ref = cell.get('r')
                t = cell.get('t')
                v_el = cell.find('ns:v', ns)
                val = ""
                if v_el is not None:
                    if t == 's':
                        idx = int(v_el.text)
                        val = strings[idx] if idx < len(strings) else f"s:{idx}"
                    else:
                        val = v_el.text
                else:
                    t_el = cell.find('.//ns:t', ns)
                    if t_el is not None:
                        val = t_el.text
                if val and ('FABIAN' in val.upper() or 'IRMA' in val.upper() or 'REVISADO POR' in val.upper()):
                    print(f"{name} -> cell {ref}: {val}")
