import sys, traceback
sys.path.insert(0, '.')
from app.modules.recepcion.excel import ExcelLogic
proc = ExcelLogic()

files = [
    r'app/templates/recepcion-resubir/recepciones/REC Nº 1876-26 De Vicente Constructora.xlsx',
    r'app/templates/recepcion-resubir/recepciones/REC Nº 1877-26 VV Bravo.xlsx',
    r'app/templates/recepcion-resubir/recepciones/REC Nº 1878-26 De Vicente Constructora.xlsx',
    r'app/templates/recepcion-resubir/recepciones/REC Nº 1880-26 CHINA ROAD AND BRIDGE CORPORATION SUCURSAL PERU.xlsx',
    r'app/templates/recepcion-resubir/recepciones/REC Nº 1881-26 JG3 CONSTRUCCIONES SA.xlsx',
    r'app/templates/recepcion-resubir/recepciones/REC Nº 1882-26 SINOHYDRO CORPORATION.xlsx',
    r'app/templates/recepcion-resubir/recepciones/REC Nº 1883-26 De Vicente Constructora.xlsx',
]

for path in files:
    fname = path.split('/')[-1]
    try:
        with open(path, 'rb') as f:
            content = f.read()
        result = proc.parsear_recepcion(content)
        print(f'=== {fname} ===')
        print(f'  tipo: {result.get("tipo_recepcion")}')
        print(f'  recepcion: {result.get("numero_recepcion")}')
        print(f'  muestras: {len(result.get("muestras", []))}')
    except Exception as e:
        print(f'=== {fname} ===')
        print(f'  ERROR: {e}')
        traceback.print_exc()
    print()
