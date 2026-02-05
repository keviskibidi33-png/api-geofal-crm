import os
from pathlib import Path

def test_template_resolution():
    print("Verifying Template Resolution Logic...")
    
    # 1. Simulate Cotizacion logic
    TEMPLATE_VARIANTS = {
        'V1': 'Temp_Cotizacion.xlsx',
        'V2': 'V2 - PROBETAS.xlsx',
        'V3': 'V3 - DENSIDAD DE CAMPO Y MUESTREO.xlsx',
        'V4': 'V4 - EXTRACCIÓN DE DIAMANTINA.xlsx',
        'V5': 'V5 - DIAMANTINA PARA PASES.xlsx',
        'V6': 'V6 - ALBAÑILERÍA.xlsx',
        'V7': 'V7 - VIGA BECKELMAN.xlsx',
        'V8': 'V8 - CONTROL DE CALIDAD DE CONCRETO FRESCO EN OBRA.xlsx',
    }
    
    # We are simulating running from app/modules/cotizacion/excel.py
    # So __file__ would be that.
    # We simulate current_dir as that path.
    current_dir = Path("c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/modules/cotizacion")
    app_dir = current_dir.parents[1]
    
    def simulate_get_template_path(filename):
        possible_paths = [
            app_dir / "templates" / filename,
            Path("/app/templates") / filename,
            current_dir.parents[2] / "app" / "templates" / filename,
        ]
        for p in possible_paths:
            if p.exists():
                return p
        return None

    filename = "Temp_Cotizacion.xlsx"
    resolved = simulate_get_template_path(filename)
    print(f"Cotizacion ({filename}): {'[OK]' if resolved and resolved.exists() else '[FAIL]'}")
    if resolved: print(f"  -> Found at: {resolved}")

    # 2. Simulate Programacion logic
    filename_prog = "Template_Programacion.xlsx"
    resolved_prog = simulate_get_template_path(filename_prog)
    print(f"Programacion ({filename_prog}): {'[OK]' if resolved_prog and resolved_prog.exists() else '[FAIL]'}")
    if resolved_prog: print(f"  -> Found at: {resolved_prog}")

    # 3. Simulate Recepcion logic
    filename_recep = "Temp_Recepcion.xlsx"
    resolved_recep = simulate_get_template_path(filename_recep)
    print(f"Recepcion ({filename_recep}): {'[OK]' if resolved_recep and resolved_recep.exists() else '[FAIL]'}")
    if resolved_recep: print(f"  -> Found at: {resolved_recep}")

if __name__ == "__main__":
    test_template_resolution()
