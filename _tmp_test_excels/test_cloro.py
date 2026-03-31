from pathlib import Path
import zipfile
from lxml import etree
from app.modules.sales_solubles.schemas import SalesSolublesRequest
from app.modules.sales_solubles.excel import generate_sales_solubles_excel

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

out = Path(r"c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/_tmp_test_excels")
cloro = CloroSolubleRequest(
    muestra="M-001", numero_ot="OT-123", fecha_ensayo="14/03/26",
    realizado_por="Juan Perez", cliente="Cliente Test SA",
    observaciones="Observacion de prueba completa",
    revisado_por="Maria Lopez", revisado_fecha="15/03/26",
    aprobado_por="Carlos Ruiz", aprobado_fecha="16/03/26",
    volumen_agua_ml=300, peso_suelo_seco_g=100, alicuota_tomada_ml=30,
    titulacion_suelo_g=10, titulacion_nitrato_plata=2313, ph_ensayo=7.5,
    factor_dilucion=10, condicion_secado_aire="X", condicion_secado_horno="X",
    equipo_horno_codigo="HOR-001", equipo_balanza_001_codigo="BAL-001",
    resultados=[
        {"mililitros_solucion_usada": 5.2, "contenido_cloruros_ppm": 150.5},
        {"mililitros_solucion_usada": 5.1, "contenido_cloruros_ppm": 148.3},
    ],
)
cp = out / "cloro_completo.xlsx"
cp.write_bytes(generate_cloro_soluble_excel(cloro))

z = zipfile.ZipFile(cp)
dups = [n for n in sorted(set(z.namelist())) if z.namelist().count(n) > 1]
print("dups:", dups)

root = etree.fromstring(z.read("xl/worksheets/sheet2.xml"))
merges_el = root.find(f".//{{{NS}}}mergeCells")
merges = []
if merges_el is not None:
    for mc in merges_el.findall(f"{{{NS}}}mergeCell"):
        ref = mc.get("ref")
        if any(str(r) in ref for r in range(22, 29)):
            merges.append(ref)
print("merges:", sorted(merges))

sd = root.find(f".//{{{NS}}}sheetData")
targets = ["B10", "D10", "E10", "G10",
           "G22", "G23", "G24", "G25", "G26", "G27", "G28",
           "G29", "H29", "G30", "H30", "A35", "F40", "F41"]
for row in sd.findall(f"{{{NS}}}row"):
    for c in row.findall(f"{{{NS}}}c"):
        ref = c.get("r")
        if ref in targets:
            v_el = c.find(f"{{{NS}}}v")
            is_el = c.find(f"{{{NS}}}is")
            val = None
            if v_el is not None:
                val = v_el.text
            elif is_el is not None:
                t_el = is_el.find(f"{{{NS}}}t")
                val = t_el.text if t_el is not None else None
            print(f"  {ref} = {val}")

print("DONE")
