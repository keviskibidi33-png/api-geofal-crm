import xml.etree.ElementTree as ET
from zipfile import ZipFile
from pathlib import Path
from app.modules.common.excel_xml import find_template_path

TEMPLATES = [
    "1-INF.-N-000-26-AG18-P.E.-FINO-V10.xlsx",
    "1-INF.-N-000-26-AG19-GRAN.-V10.xlsx",
    "1-INF.-N-000-26-AG20-CH-V08.xlsx",
    "1-INF.-N-000-26-AG22-P.UNIT.-V07.xlsx",
    "1-INF.-N-000-26-AG23-MALLA-200-V08.xlsx",
    "1-INF.-N-000-26-AG26 ABRAS.-ASTM-C535-V04.xlsx",
    "1-INF.-N-000-26-AG28-G.E.GRUESO-ASTM-C127-25-V04.xlsx",
    "1-INF.-N-000-26-AG34-PLANAS-ASTM-D4791-V02.xlsx",
    "1-INF.-N-000-26-AG35-CARAS-ASTM-D5821-V04.xlsx",
    "1-INF.-N-000-26-AG36-ABRAS.-ASTM-C131-V2.xlsx"
]

def check():
    for tname in TEMPLATES:
        try:
            p = find_template_path(tname)
            z = ZipFile(p)
            
            # Read sheets
            wb_xml = ET.fromstring(z.read('xl/workbook.xml'))
            sheets = wb_xml.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet')
            sheet_map = {}
            for s in sheets:
                name = s.attrib.get('name')
                rid = s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                sheet_map[rid] = {'name': name}
                
            # Read rels
            rels_xml = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            rels = rels_xml.findall('.//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
            for r in rels:
                rid = r.attrib.get('Id')
                target = r.attrib.get('Target')
                if rid in sheet_map:
                    sheet_map[rid]['target'] = target
            
            print(f"\n=== {tname} ===")
            for rid, info in sheet_map.items():
                print(f"  {info.get('name')} -> {info.get('target')} (rId: {rid})")
        except Exception as e:
            print(f"Error reading {tname}: {e}")

if __name__ == "__main__":
    check()
