from app.modules.common.router_factory import apply_footer_defaults, create_lab_router
from app.utils.export_filename import build_formato_filename

from .excel import generate_densidad_huantar_excel
from .models import DensidadHuantarEnsayo
from .schemas import DensidadHuantarRequest

router = create_lab_router(
    api_slug="densidad-huantar",
    display_name="Densidad Huantar",
    bucket_name="densidad",
    storage_prefix="DH",
    id_header_name="X-DH-Id",
    model=DensidadHuantarEnsayo,
    request_model=DensidadHuantarRequest,
    payload_preprocessor=apply_footer_defaults,
    generate_excel=generate_densidad_huantar_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-DH",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "SU", "DENSIDAD HUANTAR"),
)
