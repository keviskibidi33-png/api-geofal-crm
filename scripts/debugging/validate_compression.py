import sys
import os
from datetime import date, time

# Ensure we can import from app
sys.path.append(os.getcwd())

from app.modules.compresion.schemas import CompressionExportRequest, CompressionItem
from app.modules.compresion.excel import generate_compression_excel

def generate_test_files():
    print("Generating validation files...")

    # Case 1: Standard (few items)
    items_standard = []
    for i in range(1, 6):
        items_standard.append(CompressionItem(
            item=i,
            codigo_lem=f"LEM-{i:03d}",
            fecha_ensayo=date(2023, 10, 26),
            hora_ensayo="09:00",
            carga_maxima=150.5 + i,
            tipo_fractura="3",
            defectos="Ninguno",
            realizado="J.P.",
            revisado="M.G.",
            fecha_revisado=date(2023, 10, 27),
            aprobado="L.R.",
            fecha_aprobado=date(2023, 10, 28)
        ))

    payload_standard = CompressionExportRequest(
        recepcion_numero="REC-TEST-001",
        ot_numero="OT-TEST-001",
        items=items_standard,
        codigo_equipo="PRENSA-01",
        otros="OTROS DATOS",
        nota="Nota de prueba para formato estándar."
    )

    try:
        pdf_bytes = generate_compression_excel(payload_standard)
        with open("Validacion_Compresion_Estandar.xlsx", "wb") as f:
            f.write(pdf_bytes.read())
        print(" -> Generated Validacion_Compresion_Estandar.xlsx")
    except Exception as e:
        print(f"ERROR Standard: {e}")
        import traceback
        traceback.print_exc()

    # Case 2: Overflow (20 items) to test shifting
    items_overflow = []
    for i in range(1, 21):
        items_overflow.append(CompressionItem(
            item=i,
            codigo_lem=f"LEM-{i:03d}",
            fecha_ensayo=date(2023, 10, 26),
            hora_ensayo="10:00",
            carga_maxima=200.0 + i,
            tipo_fractura="1",
            defectos="Poroso" if i % 2 == 0 else "Normal",
            realizado="J.P.",
            revisado="M.G.",
            fecha_revisado=date(2023, 10, 27),
            aprobado="L.R.",
            fecha_aprobado=date(2023, 10, 28)
        ))

    payload_overflow = CompressionExportRequest(
        recepcion_numero="REC-OVERFLOW-020",
        ot_numero="OT-OVERFLOW-999",
        items=items_overflow,
        codigo_equipo="PRENSA-02",
        otros="PRUEBA DE DESPLAZAMIENTO",
        nota="Esta prueba verifica que el formato no se rompa con 20 items."
    )

    try:
        pdf_bytes = generate_compression_excel(payload_overflow)
        with open("Validacion_Compresion_20Item.xlsx", "wb") as f:
            f.write(pdf_bytes.read())
        print(" -> Generated Validacion_Compresion_20Item.xlsx")
    except Exception as e:
        print(f"ERROR Overflow: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_test_files()
