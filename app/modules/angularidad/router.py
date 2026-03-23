from app.modules.common.router_factory import apply_footer_defaults, create_lab_router
from app.utils.export_filename import build_formato_filename

from .excel import generate_angularidad_excel
from .models import AngularidadEnsayo
from .schemas import AngularidadRequest

router = create_lab_router(
    api_slug="angularidad",
    display_name="Angularidad",
    bucket_name="angularidad",
    storage_prefix="ANG",
    id_header_name="X-ANG-Id",
    model=AngularidadEnsayo,
    request_model=AngularidadRequest,
    generate_excel=generate_angularidad_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-ANG",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "AG", "ANGULARIDAD"),
    payload_preprocessor=apply_footer_defaults,
)
