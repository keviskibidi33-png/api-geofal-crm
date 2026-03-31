import zipfile
from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

# Check template
print("=== TEMPLATE ===")
p = r"c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Template_Compresion_No_Confinada.xlsx"
z = zipfile.ZipFile(p)
names = z.namelist()
dups = [n for n in sorted(set(names)) if names.count(n) > 1]
print("template dups:", dups)

# Check existing merges in sheet2
root = etree.fromstring(z.read("xl/worksheets/sheet2.xml"))
merges_el = root.find(f".//{{{NS}}}mergeCells")
if merges_el is not None:
    print("existing merges involving F/G/H rows 17-23:")
    for mc in merges_el.findall(f"{{{NS}}}mergeCell"):
        ref = mc.get("ref")
        if ref and any(c in ref for c in ["F", "G", "H"]):
            for r in range(17, 24):
                if str(r) in ref:
                    print(f"  {ref}")
                    break

# Check generated file
print("\n=== GENERATED ===")
p2 = r"c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/_tmp_test_excels/cnc_test.xlsx"
z2 = zipfile.ZipFile(p2)
names2 = z2.namelist()
dups2 = [n for n in sorted(set(names2)) if names2.count(n) > 1]
print("generated dups:", dups2)

root2 = etree.fromstring(z2.read("xl/worksheets/sheet2.xml"))
merges_el2 = root2.find(f".//{{{NS}}}mergeCells")
if merges_el2 is not None:
    print("all merges in generated rows 17-23:")
    for mc in merges_el2.findall(f"{{{NS}}}mergeCell"):
        ref = mc.get("ref")
        if ref:
            for r in range(17, 24):
                if str(r) in ref:
                    print(f"  {ref}")
                    break

    count_attr = merges_el2.get("count")
    actual = len(merges_el2.findall(f"{{{NS}}}mergeCell"))
    print(f"mergeCells count attr: {count_attr}, actual: {actual}")
