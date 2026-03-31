from pathlib import Path
import zipfile
from lxml import etree
from app.modules.compresion_no_confinada.schemas import CompresionNoConfinadaRequest
from app.modules.compresion_no_confinada.excel import generate_compresion_no_confinada_excel

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

out = Path(r"c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/_tmp_test_excels")
payload = CompresionNoConfinadaRequest(
    muestra="M-001", numero_ot="OT-123", fecha_ensayo="14/03/26",
    realizado_por="Tester",
    tara_numero="12312",
    tara_suelo_humedo_g=31,
    tara_suelo_seco_g=312321,
    peso_tara_g=321321,
    diametro_cm=[12312312, 23123, 321211],
    altura_cm=[12312],
    area_cm2=[None],
    volumen_cm3=[None],
    peso_gr=[2123],
    p_unitario_humedo=[None],
    p_unitario_seco=[None],
    lectura_carga_kg=[12312, 123123, 123321, 12331223, 1123, 1232],
    deformacion_tiempo=["0:00", "0:15", "0:46", "1:16", "1:47", "2:17"],
    deformacion_mm=[0, 0.412, 1.237, 2.062, 2.886, 3.711],
    deformacion_pulg_001=[0, 0.162, 0.487, 0.812, 1.136, 1.461],
)

cp = out / "cnc_test.xlsx"
cp.write_bytes(generate_compresion_no_confinada_excel(payload))

z = zipfile.ZipFile(cp)
dups = [n for n in sorted(set(z.namelist())) if z.namelist().count(n) > 1]
print("dups:", dups)

# Find sheet path
sheet_names = [n for n in z.namelist() if "sheet" in n.lower() and n.endswith(".xml")]
print("sheets:", sheet_names)

for sn in sheet_names:
    root = etree.fromstring(z.read(sn))
    merges_el = root.find(f".//{{{NS}}}mergeCells")
    if merges_el is None:
        continue
    fh_merges = []
    for mc in merges_el.findall(f"{{{NS}}}mergeCell"):
        ref = mc.get("ref")
        if ref and "F" in ref and any(str(r) in ref for r in range(17, 24)):
            fh_merges.append(ref)
    if fh_merges:
        print(f"{sn} F:H merges:", sorted(fh_merges))

    sd = root.find(f".//{{{NS}}}sheetData")
    targets = ["F17", "G17", "H17", "F18", "G18", "H18", "F19", "F20", "F21", "F22", "F23"]
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
