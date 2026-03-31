import zipfile
from lxml import etree

path = r"c:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates\Template,GE_FINO.xlsx"
ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

with zipfile.ZipFile(path, "r") as z:
    xml = z.read("xl/worksheets/sheet1.xml")
    # shared strings
    ss_xml = z.read("xl/sharedStrings.xml")

root = etree.fromstring(xml)
sd = root.find(f".//{{{ns}}}sheetData")

ss_root = etree.fromstring(ss_xml)
ss_ns = ns  # same namespace typically
strings = []
for si in ss_root.findall(f"{{{ns}}}si"):
    texts = si.itertext()
    strings.append("".join(texts))

print(f"Shared strings count: {len(strings)}")

for row_num in ["10", "11"]:
    print(f"\nRow {row_num}:")
    for row in sd.findall(f"{{{ns}}}row"):
        if row.get("r") == row_num:
            for c in row.findall(f"{{{ns}}}c"):
                ref = c.get("r")
                t = c.get("t")
                s = c.get("s")
                v = c.find(f"{{{ns}}}v")
                val_text = v.text if v is not None else None
                if t == "s" and val_text:
                    idx = int(val_text)
                    display = strings[idx] if idx < len(strings) else f"[idx={idx}]"
                else:
                    display = val_text
                print(f"  {ref}: type={t} style={s} value={display}")
