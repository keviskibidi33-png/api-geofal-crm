import shutil
from pathlib import Path

# Paths
ROOT = Path("c:/Users/Lenovo/Documents/crmnew/api-geofal-crm")
SRC_DIR = ROOT / "app/templates/Subir auditoria/Subir Agregados"
COPIAS_DIR = ROOT / "app/templates/copias"
COPIAS_DIR.mkdir(parents=True, exist_ok=True)

# Mappings: (new_filename, destination_folder, old_template_filename)
MAPPINGS = [
    (
        "1-INF.-N-000-26-AG18-P.E.-FINO-V10.xlsx",
        "app/templates/informes/Informes agregado/P.fino",
        "Template,GE_FINO.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG19-GRAN.-V10.xlsx",
        "app/templates/informes/Informes agregado/Gran agregado AG",
        "Template_GranAgregado.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG20-CH-V08.xlsx",
        "app/templates/informes/Informes agregado/ContHumedad ASTM C566-25",
        "Template_ContHumedad_C566.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG22-P.UNIT.-V07.xlsx",
        "app/templates/informes/Informes agregado/P.unit",
        "1-INF.-N-000-26-AG22-P.UNIT.-V07-1.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG23-MALLA-200-V08.xlsx",
        "app/templates/informes/Informes agregado/Tamiz",
        "Template_Tamiz.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG26 ABRAS.-ASTM-C535-V04.xlsx",
        "app/templates/informes/Informes agregado/Abrass", # Wait! ASTM C535 is coarse aggregate (which maps to module 'abra')
        "Template_ABRASCRM.xlsx" # Wait! Let's check which directory Template_ABRASCRM.xlsx is in.
    ),
    (
        "1-INF.-N-000-26-AG28-G.E.GRUESO-ASTM-C127-25-V04.xlsx",
        "app/templates/informes/Informes agregado/GE_GRUESO",
        "Template_GE_GRUESO.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG34-PLANAS-ASTM-D4791-V02.xlsx",
        "app/templates/informes/Informes agregado/Planas",
        "1-INF.-N-000-26-AG34-PLANAS-ASTM-D4791-V02-1-M.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG35-CARAS-ASTM-D5821-V04.xlsx",
        "app/templates/informes/Informes agregado/CARAS",
        "Template_Caras.xlsx"
    ),
    (
        "1-INF.-N-000-26-AG36-ABRAS.-ASTM-C131-V2.xlsx",
        "app/templates/informes/Informes agregado/Abra", # Wait! ASTM C131 is small-size coarse (which maps to module 'abrass')
        "Template_ABRA.xlsx" # Wait! Let's check which directory Template_ABRA.xlsx is in.
    ),
]

def migrate():
    # Let's adjust directories for Abra/Abrass based on where they actually are
    # In 'app/templates/informes/Informes agregado/':
    # Abra contains Template_ABRA.xlsx
    # Abrass contains Template_ABRASCRM.xlsx
    # Therefore:
    # AG26 (C535) goes to Abrass (which contains Template_ABRASCRM.xlsx)
    # AG36 (C131) goes to Abra (which contains Template_ABRA.xlsx)
    
    for new_file, dest_rel, old_file in MAPPINGS:
        src = SRC_DIR / new_file
        dest_dir = ROOT / dest_rel
        old_path = dest_dir / old_file
        
        if not src.exists():
            print(f"ERROR: Source file {src} does not exist!")
            continue
        
        # 1. Copy old to copias
        if old_path.exists():
            copia_name = old_file.replace(".xlsx", "-copia.xlsx")
            copia_dest = COPIAS_DIR / copia_name
            shutil.copy2(old_path, copia_dest)
            print(f"Copied old {old_file} to backup {copia_dest}")
            # 2. Delete old from target directory
            old_path.unlink()
            print(f"Deleted old template {old_path}")
        else:
            print(f"WARNING: Old file {old_path} not found to backup.")
            
        # 3. Copy new file to destination folder
        new_dest = dest_dir / new_file
        shutil.copy2(src, new_dest)
        print(f"Copied new file {new_file} to {new_dest}")

if __name__ == "__main__":
    migrate()
