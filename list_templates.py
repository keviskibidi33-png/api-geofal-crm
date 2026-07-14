import os

templates_dir = r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\app\templates"

for root, dirs, files in os.walk(templates_dir):
    rel_path = os.path.relpath(root, templates_dir)
    print(f"[{rel_path}]")
    for f in files:
        if f.endswith(".xlsx"):
            print(f"  - {f}")
