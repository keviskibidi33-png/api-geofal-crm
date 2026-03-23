from app.modules.common.router_factory import create_lab_router
from app.utils.export_filename import build_formato_filename

from .excel import generate_imp_organicas_excel
from .models import ImpOrganicasEnsayo
from .schemas import ImpOrganicasRequest

router = create_lab_router(
    api_slug="imp-organicas",
    display_name="Impurezas Organicas",
    bucket_name="imp-organicas",
    storage_prefix="IMPORG",
    id_header_name="X-IMPORG-Id",
    model=ImpOrganicasEnsayo,
    request_model=ImpOrganicasRequest,
    generate_excel=generate_imp_organicas_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-IMPORG",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "AG", "IMPUREZAS ORGANICAS"),
)
