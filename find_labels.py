
import zipfile
from lxml import etree

template_path = 'c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Temp_Cotizacion.xlsx'
with zipfile.ZipFile(template_path, 'r') as z:
    content = z.read('xl/worksheets/sheet1.xml')
    root = etree.fromstring(content)
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    
    for r in root.xpath('//m:row', namespaces=ns):
        r_num = r.get('r')
        for c in r.xpath('m:c', namespaces=ns):
            ref = c.get('r')
            # Look for inline text
            t = c.find('.//m:t', ns)
            val = t.text if t is not None else ''
            if val:
                print(f'{ref}: {val}')
