
import os
import sys
from datetime import date

# Añadir el path de la app al sys.path para importar xlsx_direct_v2
sys.path.append(os.path.abspath('c:/Users/Lenovo/Documents/crmnew/api-geofal-crm'))

from app.xlsx_direct_v2 import export_xlsx_direct

template_path = 'c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/app/templates/Temp_Cotizacion.xlsx'
output_path = 'c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/test_cotizacion_result.xlsx'

data = {
    'cotizacion_numero': '586',
    'fecha_emision': date.today(),
    'cliente': 'GRUPO CONSTRUCTOR SAC',
    'ruc': '20608095137',
    'contacto': 'LIZBETH PAREDES',
    'telefono': '987654321',
    'email': 'lizbeth.paredes@example.com',
    'proyecto': 'MODIFICACIÓN DEL VIAL VSR-1 AEROPUERTO INTERNACIONAL JORGE CHÁVEZ',
    'ubicacion': 'CALLAO',
    'personal_comercial': 'ASESOR PRUEBA',
    'items': [
        {'codigo': 'ENS-001', 'descripcion': 'Proctor modificado', 'norma': 'ASTM D1557', 'acreditado': 'SI', 'costo_unitario': 150.0, 'cantidad': 1},
        {'codigo': 'ENS-002', 'descripcion': 'Análisis granulométrico por tamizado de agregado', 'norma': 'ASTM C136', 'acreditado': 'SI', 'costo_unitario': 100.0, 'cantidad': 1},
        {'codigo': 'ENS-003', 'descripcion': 'Contenido de humedad', 'norma': 'ASTM D2216', 'acreditado': 'NO', 'costo_unitario': 50.0, 'cantidad': 2},
    ],
    'include_igv': True,
    'igv_rate': 0.18,
    'condiciones_textos': ['Validez de la oferta: 30 días.', 'Muestras deben estar identificadas.'],
    'plazo_dias': 5,
    'condicion_pago': '50_adelanto',
    'correo': 'vendedor@geofal.com.pe'
}

try:
    print(f"Generando Excel de prueba usando {template_path}...")
    xlsx_output = export_xlsx_direct(template_path, data)
    
    with open(output_path, 'wb') as f:
        f.write(xlsx_output.getbuffer())
    
    print(f"Excel generado exitosamente en: {output_path}")
    print("Verificando integridad del ZIP...")
    import zipfile
    with zipfile.ZipFile(output_path, 'r') as z:
        corrupt = z.testzip()
        if corrupt:
            print(f"ERROR: El archivo ZIP generado está corrupto. Problema en: {corrupt}")
        else:
            print("El archivo ZIP es válido estructuralmente.")
            
except Exception as e:
    print(f"ERROR durante la generación: {e}")
    import traceback
    traceback.print_exc()
