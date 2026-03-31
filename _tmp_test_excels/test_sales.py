from pathlib import Path
import zipfile
from lxml import etree
from app.modules.sales_solubles.schemas import SalesSolublesRequest
from app.modules.sales_solubles.excel import generate_sales_solubles_excel

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

out = Path(r"c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/_tmp_test_excels")
sales = SalesSolublesRequest(
    muestra="M-002", numero_ot="OT-456", fecha_ensayo="14/03/26",
    realizado_por="Tester", volumen_agua_ml=500, peso_suelo_g=100,
    volumen_solucion_tomada_ml=100,
    capsulas=[
        {"capsula_numero": "232131", "peso_capsula_g": 1231,
         "peso_capsula_sales_g": 1241, "peso_sales_g": 10, "contenido_sales_ppm": 200},
        {"capsula_numero": "232113", "peso_capsula_g": 213,
         "peso_capsula_sales_g": 223, "peso_sales_g": 10, "contenido_sales_ppm": 300},
    ],
)
sp = out / "sales_final2.xlsx"
sp.write_bytes(generate_sales_solubles_excel(sales))

z = zipfile.ZipFile(sp)
dups = [n for n in sorted(set(z.namelist())) if z.namelist().count(n) > 1]
print("dups:", dups)

# Check styles of target cells
styles_root = etree.fromstring(z.read("xl/styles.xml"))
cellxfs = styles_root.find(f".//{{{NS}}}cellXfs")

root = etree.fromstring(z.read("xl/worksheets/sheet2.xml"))
sd = root.find(f".//{{{NS}}}sheetData")

targets = ["G21", "H21", "G22", "H22", "G23", "H23", "G24", "H24",
           "G25", "H25", "G26", "H26", "G27", "H27", "G28", "H28"]

for row in sd.findall(f"{{{NS}}}row"):
    for c in row.findall(f"{{{NS}}}c"):
        ref = c.get("r")
        if ref in targets:
            s = c.get("s")
            v_el = c.find(f"{{{NS}}}v")
            is_el = c.find(f"{{{NS}}}is")
            val = None
            if v_el is not None:
                val = v_el.text
            elif is_el is not None:
                t_el = is_el.find(f"{{{NS}}}t")
                val = t_el.text if t_el is not None else None

            align_h = None
            if s is not None:
                xf = list(cellxfs)[int(s)]
                align = xf.find(f"{{{NS}}}alignment")
                align_h = align.get("horizontal") if align is not None else None

            print(f"  {ref} val={val} style={s} align={align_h}")

print("DONE")
