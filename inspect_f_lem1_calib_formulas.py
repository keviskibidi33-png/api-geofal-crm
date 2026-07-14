import openpyxl

template_path = r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates\informes\Densidad Huantar\1-INF.-N-001-26-SU06-DEN-V05.xlsx"
wb = openpyxl.load_workbook(template_path, data_only=False)
ws = wb["F LEM1"]

print("=== F LEM1 Calibration Cells ===")
cells = ["D18", "D19", "D20", "D21", "H18", "H19", "H20", "H21", "H22"]
for ref in cells:
    cell = ws[ref]
    print(f"  {ref}: value={repr(cell.value)}, data_type={cell.data_type}")
