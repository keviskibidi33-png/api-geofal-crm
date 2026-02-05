import zipfile
import re
from pathlib import Path

def extract_rows(template_path, sheet_rel_path, rows):
    z = zipfile.ZipFile(template_path)
    xml = z.read(f"xl/{sheet_rel_path}").decode('utf-8')
    
    for r in rows:
        pattern = rf'<row r="{r}".*?</row>'
        match = re.search(pattern, xml)
        if match:
            print(f"Row {r}: {match.group(0)}")
        else:
            print(f"Row {r}: NOT FOUND")

if __name__ == "__main__":
    template = Path("c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Temp_Cotizacion.xlsx")
    extract_rows(template, "worksheets/sheet8.xml", [14, 15])
