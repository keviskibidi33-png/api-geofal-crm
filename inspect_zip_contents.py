import zipfile

template_path = r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates\informes\Densidad Huantar\1-INF.-N-001-26-SU06-DEN-V05.xlsx"

with zipfile.ZipFile(template_path, "r") as z:
    print("Files in template:")
    for f in sorted(z.namelist()):
        if "sheet" in f or "drawing" in f or "rels" in f:
            print(f"  {f}")
