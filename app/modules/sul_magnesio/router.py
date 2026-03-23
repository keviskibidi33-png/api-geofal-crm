from app.modules.common.router_factory import create_lab_router
from app.utils.export_filename import build_formato_filename

from .excel import generate_sul_magnesio_excel
from .models import SulMagnesioEnsayo
from .schemas import SulMagnesioRequest

router = create_lab_router(
    api_slug="sul-magnesio",
    display_name="Sulfato Magnesio",
    bucket_name="sul-magnesio",
    storage_prefix="SM",
    id_header_name="X-SM-Id",
    model=SulMagnesioEnsayo,
    request_model=SulMagnesioRequest,
    generate_excel=generate_sul_magnesio_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-SM",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "AG", "SULFATO MAGNESIO"),
)
