import zipfile
from lxml import etree

template_path = r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates\informes\Densidad Huantar\1-INF.-N-001-26-SU06-DEN-V05.xlsx"

with zipfile.ZipFile(template_path, "r") as z:
    wb_xml = z.read("xl/workbook.xml")
    rels_xml = z.read("xl/_rels/workbook.xml.rels")

wb_root = etree.fromstring(wb_xml)
rels_root = etree.fromstring(rels_xml)

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"

# Map rId -> Target
rel_map = {}
for rel in rels_root.findall(f"{{{NS_RELS}}}Relationship"):
    rel_map[rel.get("Id")] = rel.get("Target")

print("SHEETS RELATION MAPPING:")
for sheet in wb_root.find(f".//{{{NS_MAIN}}}sheets").findall(f"{{{NS_MAIN}}}sheet"):
    name = sheet.get("name")
    r_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    target = rel_map.get(r_id)
    print(f"  Sheet: {name!r} -> rId: {r_id!r} -> Target: {target!r}")
