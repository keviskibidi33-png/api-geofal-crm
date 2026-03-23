from app.modules.common.router_factory import create_lab_router
from app.utils.export_filename import build_formato_filename

from .excel import generate_azul_metileno_excel
from .models import AzulMetilenoEnsayo
from .schemas import AzulMetilenoRequest

router = create_lab_router(
    api_slug="azul-metileno",
    display_name="Azul Metileno",
    bucket_name="azul-metileno",
    storage_prefix="AM",
    id_header_name="X-AM-Id",
    model=AzulMetilenoEnsayo,
    request_model=AzulMetilenoRequest,
    generate_excel=generate_azul_metileno_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-AM",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "AG", "AZUL METILENO"),
)

