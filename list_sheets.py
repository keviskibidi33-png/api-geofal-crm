import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

def list_sheets(template_path):
    z = zipfile.ZipFile(template_path)
    wb_ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 
             'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    wb_root = ET.fromstring(z.read('xl/workbook.xml'))
    rel_root = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rel_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    
    rels = {r.get('Id'): r.get('Target') for r in rel_root.findall('.//rel:Relationship', rel_ns)}
    sheets = wb_root.findall('.//m:sheet', wb_ns)
    
    print(f"{'Sheet Name':<30} | {'State':<10} | {'Path'}")
    print("-" * 60)
    for s in sheets:
        name = s.get('name')
        state = s.get('state') or 'visible'
        rid = s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        path = rels.get(rid)
        print(f"{name:<30} | {state:<10} | {path}")

if __name__ == "__main__":
    template = Path("c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Temp_Cotizacion.xlsx")
    if template.exists():
        list_sheets(template)
    else:
        print("Template not found")
