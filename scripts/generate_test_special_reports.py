import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.cloro_soluble.excel import TEMPLATE_FILENAME as CLORO_TEMPLATE, generate_cloro_soluble_excel
from app.modules.cloro_soluble.schemas import CloroSolubleRequest, CloroSolubleResultado
from app.modules.densidad_huantar.excel import TEMPLATE_FILE as DENSIDAD_HUANTAR_TEMPLATE, generate_densidad_huantar_excel
from app.modules.densidad_huantar.schemas import DensidadHuantarPunto, DensidadHuantarRequest
from app.modules.ph.excel import TEMPLATE_FILENAME as PH_TEMPLATE, generate_ph_excel
from app.modules.ph.schemas import PHRequest
from app.modules.sales_solubles.excel import TEMPLATE_FILENAME as SALES_TEMPLATE, generate_sales_solubles_excel
from app.modules.sales_solubles.schemas import SalesSolublesCapsula, SalesSolublesRequest
from report_test_helpers import write_report_export


def output_dir() -> Path:
    directory = Path(os.environ.get("GEOFAL_TEST_OUTPUT_DIR", ROOT / "test_exports" / "informes_todos"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def main() -> None:
    directory = output_dir()

    ph_payload = PHRequest(
        muestra="PH-106-26",
        numero_ot="OT-PH-26",
        fecha_ensayo="2026/07/23",
        realizado_por="OPERADOR TEST",
        ph_resultado=7.2,
    )
    write_report_export(directory, PH_TEMPLATE, ph_payload.muestra, generate_ph_excel(ph_payload))

    cloro_payload = CloroSolubleRequest(
        muestra="CL-107-26",
        numero_ot="OT-CLORUROS-26",
        fecha_ensayo="2026/07/23",
        realizado_por="OPERADOR TEST",
        resultados=[
            CloroSolubleResultado(mililitros_solucion_usada=12.5, contenido_cloruros_ppm=250.0),
        ],
    )
    write_report_export(directory, CLORO_TEMPLATE, cloro_payload.muestra, generate_cloro_soluble_excel(cloro_payload))

    sales_payload = SalesSolublesRequest(
        muestra="SA-108-26",
        numero_ot="OT-SALES-26",
        fecha_ensayo="2026/07/23",
        realizado_por="OPERADOR TEST",
        capsulas=[
            SalesSolublesCapsula(
                capsula_numero="C-01",
                peso_capsula_g=41.1,
                peso_capsula_sales_g=41.2,
                peso_sales_g=0.1,
                contenido_sales_ppm=1000.0,
            ),
        ],
    )
    write_report_export(directory, SALES_TEMPLATE, sales_payload.muestra, generate_sales_solubles_excel(sales_payload))

    densidad_huantar_payload = DensidadHuantarRequest(
        muestra="DH-109-26",
        numero_ot="OT-DENSIDAD-HUANTAR-26",
        fecha_ensayo="2026/07/14",
        realizado_por="OPERADOR TEST",
        puntos=[DensidadHuantarPunto(punto_numero=1, ubicacion="Punto 1", tipo_muestra="SUELO")],
    )
    write_report_export(
        directory,
        DENSIDAD_HUANTAR_TEMPLATE,
        densidad_huantar_payload.muestra,
        generate_densidad_huantar_excel(densidad_huantar_payload),
    )

    print(f"Generados 4 informes especiales en {directory}")
    print(f"Templates: {PH_TEMPLATE}, {CLORO_TEMPLATE}, {SALES_TEMPLATE}, {DENSIDAD_HUANTAR_TEMPLATE}")


if __name__ == "__main__":
    main()
