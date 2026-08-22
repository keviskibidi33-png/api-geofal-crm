import io
import sys
import zipfile
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.gran_agregado.excel import TEMPLATE_PATH, generate_gran_agregado_excel
from app.modules.gran_agregado.schemas import GranAgregadoRequest

def test_gran_agregado_excel_generation():
    # Verify template exists
    assert Path(TEMPLATE_PATH).exists(), f"Template not found at {TEMPLATE_PATH}"

    # Build valid request payload
    payload = GranAgregadoRequest(
        muestra="123-AG-26",
        numero_ot="OT-9999-26",
        fecha_ensayo="2026/07/13",
        realizado_por="OPERADOR TEST",
        tipo_muestra="AGREGADO GRUESO",
        tamano_maximo_particula_visual_in="3/4\"",
        forma_particula="ANGULAR",
        masa_muestra_humeda_inicial_total_global_g=1500.5,
        masa_muestra_seca_global_g=1480.2,
        masa_muestra_seca_constante_global_g=1479.9,
        masa_muestra_seca_lavada_global_g=1450.1,
        masa_retenida_tamiz_g=[0.0, 10.5, 20.3, 40.1, 5.0, 100.2] + [0.0] * 12,
        masa_antes_tamizado_g=1450.1,
        masa_despues_tamizado_g=1449.8,
        error_tamizado_pct=0.02,
        balanza_01g_codigo="BAL-01",
        horno_codigo="HOR-02",
        observaciones="Sin observaciones",
        revisado_por="REVISOR",
        revisado_fecha="2026/07/14",
        aprobado_por="APROBADOR",
        aprobado_fecha="2026/07/15"
    )

    # Generate Excel bytes
    xlsx_bytes = generate_gran_agregado_excel(payload)
    assert xlsx_bytes is not None
    assert len(xlsx_bytes) > 0

    # Check zip XML structure directly
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zin:
        s1 = etree.fromstring(zin.read("xl/worksheets/sheet1.xml"))
        s4 = etree.fromstring(zin.read("xl/worksheets/sheet4.xml"))
        ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        
        # Check FORMATO
        assert s1.find(".//ns:c[@r='B11']/ns:is/ns:t", ns).text == "123-AG-26"
        assert s1.find(".//ns:c[@r='D11']/ns:is/ns:t", ns).text == "9999-26"
        
        # Check datos sheet has method, aggregate type, and operator
        assert s4.find(".//ns:c[@r='C10']/ns:is/ns:t", ns).text == "Global"
        assert s4.find(".//ns:c[@r='C9']/ns:is/ns:t", ns).text == "Grueso"
        assert s4.find(".//ns:c[@r='F10']/ns:is/ns:t", ns).text == "OPERADOR TEST"

    print("Gran Agregado Excel generation test passed successfully!")
