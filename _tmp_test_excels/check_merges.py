import zipfile
from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

p = r"c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Template_SALES_SOLUBLES.xlsx"
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read("xl/worksheets/sheet2.xml"))
merges = root.find(f".//{{{NS}}}mergeCells")

print("All merges in rows 21-28:")
if merges is not None:
    for mc in merges.findall(f"{{{NS}}}mergeCell"):
        ref = mc.get("ref")
        for r in range(21, 29):
            if str(r) in ref:
                print(f"  {ref}")
                break

print()
print("Cells in cols A-F, rows 21-28:")
sd = root.find(f".//{{{NS}}}sheetData")
for row in sd.findall(f"{{{NS}}}row"):
    rn = row.get("r")
    if rn and 21 <= int(rn) <= 28:
        for c in row.findall(f"{{{NS}}}c"):
            ref = c.get("r")
            col = "".join(ch for ch in ref if ch.isalpha())
            if col in ("A", "B", "C", "D", "E", "F"):
                s = c.get("s")
                v = c.find(f"{{{NS}}}v")
                val = v.text if v is not None else None
                istr = c.find(f"{{{NS}}}is")
                inline = None
                if istr is not None:
                    t = istr.find(f"{{{NS}}}t")
                    inline = t.text if t is not None else None
                print(f"  {ref} style={s} v={val} inline={inline}")
