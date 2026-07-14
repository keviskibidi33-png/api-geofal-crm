import openpyxl

template_path = r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates\informes\Densidad Huantar\1-INF.-N-001-26-SU06-DEN-V05.xlsx"
wb = openpyxl.load_workbook(template_path)
ws = wb["F LEM1"]

print("=== ALL MERGED CELLS IN F LEM1 ===")
for r in sorted(list(ws.merged_cells.ranges), key=lambda x: x.bounds[1]):
    print(f"  Range: {r.coord}")
