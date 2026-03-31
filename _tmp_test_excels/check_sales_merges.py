import zipfile
from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

p = r"c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/_tmp_test_excels/sales_final.xlsx"
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read("xl/worksheets/sheet2.xml"))
merges = root.find(f".//{{{NS}}}mergeCells")

print("Merges in rows 21-28:")
if merges is not None:
    for mc in sorted(merges.findall(f"{{{NS}}}mergeCell"), key=lambda x: x.get("ref")):
        ref = mc.get("ref")
        for r in range(21, 29):
            if str(r) in ref:
                print(f"  {ref}")
                break
