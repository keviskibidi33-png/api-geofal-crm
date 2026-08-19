import io
import json
import openpyxl
from datetime import datetime
from app.modules.recepcion.excel import ExcelLogic
from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto

def test_generar_excel_suelo_agregado_fidelity():
    excel_logic = ExcelLogic()

    recepcion = RecepcionMuestra(
        numero_recepcion="100-26",
        numero_ot="OT-100-26",
        numero_cotizacion="COT-500-26",
        tipo_recepcion="SUELO_AGREGADO",
        cliente="CONSTRUCTORA DEL SUR S.A.C.",
        domicilio_legal="AV. AREQUIPA 123",
        ruc="20123456789",
        persona_contacto="ING. MARIO LOPEZ",
        email="mlopez@delsur.pe",
        telefono="999888777",
        solicitante="SOLICITANTE TEST",
        domicilio_solicitante="DOMICILIO SOLICITANTE TEST",
        proyecto="MEJORAMIENTO CARRETERA",
        ubicacion="HUARI, ANCASH",
        fecha_recepcion=datetime(2026, 8, 20),
        fecha_estimada_culminacion=datetime(2026, 8, 28),
        emision_digital=True,
        emision_fisica=False,
        entregado_por="ING. MARIO LOPEZ",
        recibido_por="BETZABETH SARAVIA",
        observaciones="Muestras selladas en sacos.",
    )

    m1 = MuestraConcreto(
        item_numero=1,
        codigo_muestra_lem="1500-SU-26",
        identificacion_muestra="M-01 C-01 (0.00 - 1.50 M)",
        procedencia="CALICATA 01",
        cantera="CANTERA CENTRAL",
        cantidad="50 KG",
        ensayos_json=json.dumps([
            {"codigo": "SU24", "descripcion": "ANÁLISIS GRANULOMÉTRICO POR TAMIZADO EN SUELOS", "norma": "ASTM D6913/D6913M-17"},
            {"codigo": "SU23", "descripcion": "LÍMITES DE ATTERBERG (LL, LP)", "norma": "ASTM D4318-17ε1"},
            {"codigo": "SU20", "descripcion": "CONTENIDO DE HUMEDAD", "norma": "ASTM D2216-19"}
        ])
    )

    m2 = MuestraConcreto(
        item_numero=2,
        codigo_muestra_lem="1501-SU-26",
        identificacion_muestra="M-02 C-02 (0.00 - 2.00 M)",
        procedencia="CALICATA 02",
        cantera="CANTERA NORTE",
        cantidad="60 KG",
        ensayos_json=json.dumps([
            {"codigo": "SU24", "descripcion": "ANÁLISIS GRANULOMÉTRICO POR TAMIZADO EN SUELOS", "norma": "ASTM D6913/D6913M-17"},
            {"codigo": "SU22", "descripcion": "PESO ESPECÍFICO Y ABSORCIÓN", "norma": "ASTM C127"}
        ])
    )

    recepcion.muestras = [m1, m2]

    excel_bytes = excel_logic.generar_excel_recepcion(recepcion)
    assert excel_bytes is not None
    assert len(excel_bytes) > 5000

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb['RECEP. SU-AG']

    # Assert Headers
    assert ws['D6'].value == "100-26"
    assert ws['D7'].value == "COT-500-26"
    assert ws['M6'].value == "X"
    assert ws['M7'].value is None or ws['M7'].value == ""

    # Assert Customer
    assert ws['D10'].value == "CONSTRUCTORA DEL SUR S.A.C."
    assert ws['D12'].value == "20123456789"
    assert ws['D13'].value == "ING. MARIO LOPEZ"
    assert ws['D18'].value == "MEJORAMIENTO CARRETERA"

    # Assert Sample 1 (rows 22-25, h=max(4,3)=4)
    assert ws['A22'].value == 1
    assert ws['B22'].value == "1500-SU-26"
    assert ws['F22'].value == "M-01 C-01 (0.00 - 1.50 M)"
    assert ws['F23'].value == "CALICATA 01"
    assert ws['F24'].value == "CANTERA CENTRAL"
    assert ws['F25'].value == "50 KG"
    assert ws['H22'].value == "SU24"
    assert ws['H23'].value == "SU23"
    assert ws['H24'].value == "SU20"

    # Row 26 = separator (1 empty row)
    assert ws['A26'].value is None
    assert ws['H26'].value is None

    # Assert Sample 2 (correlative: rows 27-30, h=max(4,2)=4)
    assert ws['A27'].value == 2
    assert ws['B27'].value == "1501-SU-26"
    assert ws['F27'].value == "M-02 C-02 (0.00 - 2.00 M)"
    assert ws['F28'].value == "CALICATA 02"
    assert ws['F29'].value == "CANTERA NORTE"
    assert ws['F30'].value == "60 KG"
    assert ws['H27'].value == "SU24"
    assert ws['H28'].value == "SU22"

    # Row 31 = separator
    assert ws['A31'].value is None

    # Assert Footer (obs_row = 22 + 10 = 32, resp_row = 34)
    assert ws['C32'].value == "Muestras selladas en sacos."
    assert ws['C34'].value == "ING. MARIO LOPEZ"
    assert ws['K34'].value == "BETZABETH SARAVIA"

    print("Test generar_excel_suelo_agregado (2 samples correlative) passed successfully!")

    # Test 1 sample (h=4, sep=1 → total=5, obs_row=27, resp_row=29)
    recepcion.muestras = [m1]
    excel_bytes_1 = excel_logic.generar_excel_recepcion(recepcion)
    wb_1 = openpyxl.load_workbook(io.BytesIO(excel_bytes_1), data_only=True)
    ws_1 = wb_1['RECEP. SU-AG']
    assert ws_1['A22'].value == 1
    assert ws_1['B22'].value == "1500-SU-26"
    # Row 27 must be Observaciones (obs_row = 22 + 5 = 27)
    assert ws_1['C27'].value == "Muestras selladas en sacos."
    print("Test generar_excel_suelo_agregado (1 sample) passed successfully!")

    # Test 3 samples (m1=h4, m2=h4, m3=h4 → total=15, obs_row=37, resp_row=39)
    m3 = MuestraConcreto(
        item_numero=3,
        codigo_muestra_lem="1502-SU-26",
        identificacion_muestra="M-03 C-03 (2.00 - 3.00 M)",
        procedencia="CALICATA 03",
        cantera="CANTERA SUR",
        cantidad="70 KG",
        ensayos_json=json.dumps([
            {"codigo": "SU20", "descripcion": "CONTENIDO DE HUMEDAD", "norma": "ASTM D2216-19"}
        ])
    )
    recepcion.muestras = [m1, m2, m3]
    excel_bytes_3 = excel_logic.generar_excel_recepcion(recepcion)
    wb_3 = openpyxl.load_workbook(io.BytesIO(excel_bytes_3), data_only=True)
    ws_3 = wb_3['RECEP. SU-AG']
    # m1: rows 22-25, sep 26 | m2: rows 27-30, sep 31 | m3: rows 32-35, sep 36
    assert ws_3['A22'].value == 1
    assert ws_3['A27'].value == 2
    assert ws_3['A32'].value == 3
    assert ws_3['B32'].value == "1502-SU-26"
    assert ws_3['F32'].value == "M-03 C-03 (2.00 - 3.00 M)"
    # obs_row = 22 + 15 = 37
    assert ws_3['C37'].value == "Muestras selladas en sacos."
    print("Test generar_excel_suelo_agregado (3 samples correlative expansion) passed successfully!")

if __name__ == "__main__":
    test_generar_excel_suelo_agregado_fidelity()
