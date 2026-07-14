import openpyxl

template_path = r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates\informes\Densidad Huantar\1-INF.-N-001-26-SU06-DEN-V05.xlsx"
wb = openpyxl.load_workbook(template_path)
ws = wb["F LEM2"]

print("=== F LEM2 Row 27 ===")
for col in ["E", "F", "G", "H"]:
    cell = ws[f"{col}27"]
    print(f"  {col}27: value={repr(cell.value)}, data_type={cell.data_type}")
