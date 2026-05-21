import os
import sys

# Ensure the root of the project is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from app.database import SessionLocal, engine, Base
# Make sure the model is imported so create_all knows about it
from app.modules.seguimiento_cliente_comercial.models import SeguimientoClienteComercial
from app.modules.seguimiento_cliente_comercial.service import SeguimientoClienteComercialService

def main():
    print("Iniciando la creación de la tabla y migración de datos...")
    
    # 1. Ensure table exists
    try:
        Base.metadata.create_all(bind=engine)
        print("Tabla 'seguimiento_cliente_comercial' verificada/creada con éxito.")
    except Exception as e:
        print(f"Error al crear la tabla en la base de datos: {e}")
        sys.exit(1)
        
    # 2. Path to template
    template_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "templates",
            "Seguimiento cliente ACTUALIZADO.xlsx"
        )
    )
    
    if not os.path.exists(template_path):
        print(f"Error: El archivo plantilla no existe en: {template_path}")
        sys.exit(1)
        
    print(f"Leyendo plantilla desde: {template_path}")
    
    # Read the file bytes
    with open(template_path, "rb") as f:
        file_content = f.read()
        
    # 3. Perform import
    db = SessionLocal()
    try:
        print("Importando registros a la base de datos...")
        count = SeguimientoClienteComercialService.importar_excel(db, file_content, creado_por="SEED_SCRIPT")
        print(f"¡Éxito! Se importaron {count} registros a la tabla 'seguimiento_cliente_comercial'.")
    except Exception as e:
        db.rollback()
        print(f"Error durante la importación: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
