from app.modules.common.router_factory import apply_footer_defaults, create_lab_router
from app.utils.export_filename import build_formato_filename

from .excel import generate_part_livianas_excel
from .models import PartLivianasEnsayo
from .schemas import PartLivianasRequest

router = create_lab_router(
    api_slug="part-livianas",
    display_name="Particulas Livianas",
    bucket_name="part-livianas",
    storage_prefix="PL",
    id_header_name="X-PL-Id",
    model=PartLivianasEnsayo,
    request_model=PartLivianasRequest,
    generate_excel=generate_part_livianas_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-PL",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "AG", "PARTICULAS LIVIANAS"),
    payload_preprocessor=apply_footer_defaults,
)
