import io
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.gran_suelo.excel import TEMPLATE_PATH, generate_gran_suelo_excel
from app.modules.gran_suelo.schemas import GranSueloRequest

def test_gran_suelo_excel_generation():
    # Verify template exists
    assert Path(TEMPLATE_PATH).exists(), f"Template not found at {TEMPLATE_PATH}"

    # Build valid request payload
    payload = GranSueloRequest(
        muestra="123-SU-26",
        numero_ot="OT-9999-26",
        fecha_ensayo="2026/07/13",
        realizado_por="OPERADOR TEST",
        metodo_prueba="A",
        tamizado_tipo="GLOBAL",
        metodo_muestreo="SECADO AL HORNO",
        tipo_muestra="Disturbed",
        condicion_muestra="ALTERADO",
        tamano_maximo_particula_in="1\"",
        forma_particula="Subredondeada",
        tamiz_separador="No. 4",
        masa_seca_global_g=1500.0,
        subespecie_masa_humeda_g=500.0,
        subespecie_masa_seca_g=480.0,
        contenido_agua_wfp_pct=4.17,
        masa_porcion_gruesa_lavada_cpwmd_g=0.0,
        masa_retenida_plato_cpmrpan_g=0.0,
        perdida_cpl_pct=0.1,
        masa_subespecimen_lavado_fina_g=470.0,
        clasificacion_visual_simbolo="GP",
        clasificacion_visual_nombre="Grava pobremente graduada",
        masa_retenida_primer_tamiz_g=0.0,
        masa_retenida_tamiz_g=[0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 150.0, 100.0, 50.0, 40.0, 30.0, 20.0, 10.0, 50.0],
        balanza_01g_codigo="EQP-0046",
        horno_110_codigo="EQP-0012",
        observaciones="Sin observaciones",
        revisado_por="REVISOR",
        revisado_fecha="2026/07/14",
        aprobado_por="APROBADOR",
        aprobado_fecha="2026/07/15"
    )

    # Generate Excel bytes
    xlsx_bytes = generate_gran_suelo_excel(payload)
    assert xlsx_bytes is not None
    assert len(xlsx_bytes) > 0

    # Check zip XML structure directly
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zin:
        s1 = etree.fromstring(zin.read("xl/worksheets/sheet1.xml"))
        s2 = etree.fromstring(zin.read("xl/worksheets/sheet2.xml"))
        ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        
        # Check FORMATO
        assert s1.find(".//ns:c[@r='D11']/ns:is/ns:t", ns).text == "123-SU-26"
        assert s1.find(".//ns:c[@r='F11']/ns:is/ns:t", ns).text == "9999-26"
        
        # Check A.Granul sheet has method, sample type, and operator
        assert s2.find(".//ns:c[@r='R3']/ns:is/ns:t", ns).text == "Global"
        assert s2.find(".//ns:c[@r='R2']/ns:is/ns:t", ns).text == "Método A"
        assert s2.find(".//ns:c[@r='V3']/ns:is/ns:t", ns).text == "OPERADOR TEST"

    print("Gran Suelo Excel generation test passed successfully!")
