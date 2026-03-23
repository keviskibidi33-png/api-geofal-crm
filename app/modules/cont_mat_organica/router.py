from app.utils.export_filename import build_formato_filename
from app.modules.common.router_factory import apply_footer_defaults, create_lab_router

from .excel import generate_cont_mat_organica_excel
from .models import ContMatOrganicaEnsayo
from .schemas import ContMatOrganicaRequest

router = create_lab_router(
    api_slug="cont-mat-organica",
    display_name="Contenido Materia Organica",
    bucket_name="cont-mat-organica",
    storage_prefix="CMO",
    id_header_name="X-CMO-Id",
    model=ContMatOrganicaEnsayo,
    request_model=ContMatOrganicaRequest,
    payload_preprocessor=apply_footer_defaults,
    generate_excel=generate_cont_mat_organica_excel,
    build_numero_ensayo=lambda payload: f"{payload.numero_ot}-CMO",
    build_download_filename=lambda payload: build_formato_filename(payload.muestra, "AG", "CONTENIDO MATERIA ORGANICA"),
)
