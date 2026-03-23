from app.modules.common.router_factory import create_lab_router
from app.utils.export_filename import build_formato_filename

from .excel import generate_terrones_fino_grueso_excel
from .models import TerronesFinoGruesoEnsayo
from .schemas import TerronesFinoGruesoRequest

router = create_lab_router(
    api_slug="terrones-fino-grueso",
    display_name="Terrones Fino Grueso",
    bucket_name="terrones-fino-grueso",
    storage_prefix="TERR",
    id_header_name="X-TERR-Id",
    model=TerronesFinoGruesoEnsayo,
    request_model=TerronesFinoGruesoRequest,
    generate_excel=generate_terrones_fino_grueso_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-TERR",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "AG", "TERRONES FINO GRUESO"),
)
