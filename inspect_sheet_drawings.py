import zipfile
from lxml import etree

template_path = r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates\informes\Densidad Huantar\1-INF.-N-001-26-SU06-DEN-V05.xlsx"

NS_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"

with zipfile.ZipFile(template_path, "r") as z:
    for sheet_num in [1, 2]:
        rels_path = f"xl/worksheets/_rels/sheet{sheet_num}.xml.rels"
        try:
            raw_rels = z.read(rels_path)
            root = etree.fromstring(raw_rels)
            print(f"=== Relations in sheet{sheet_num} ===")
            for rel in root.findall(f"{{{NS_RELS}}}Relationship"):
                print(f"  Id: {rel.get('Id')} -> Type: {rel.get('Type').split('/')[-1]} -> Target: {rel.get('Target')}")
        except KeyError:
            print(f"No rels for sheet{sheet_num}")
