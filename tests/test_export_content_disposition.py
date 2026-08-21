from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.cbr import router as cbr_router
from app.modules.caras import router as caras_router
from app.modules.common.router_factory import resolve_download_filename
from app.modules.compresion.service import build_concrete_template_filename
from app.utils.export_filename import build_filename_from_template
from app.modules.cbr.schemas import CBRRequest
from app.modules.caras.schemas import CarasRequest


def test_router_factory_filename_uses_template_before_legacy_builder():
    payload = SimpleNamespace(muestra="157-AG-26")

    filename = resolve_download_filename(
        payload,
        "1-INF.-N-000-26-AG35-CARAS-ASTM-D5821-V04.xlsx",
        lambda _: "legacy.xlsx",
    )

    assert filename == "1-INF.-N-157-26-AG35-CARAS-ASTM-D5821-V04.xlsx"


def test_concrete_filename_preserves_dynamic_template_suffix(monkeypatch):
    monkeypatch.setenv("CONCRETE_TEMPLATE_PREFIX", "1-INF.-N-000-26-CO12-COM-V04")
    template = build_concrete_template_filename(3)

    assert build_filename_from_template(template, "REC-157-26") == (
        "1-INF.-N-157-26-CO12-COM-V04 -3.xlsx"
    )


def test_cbr_content_disposition_preserves_template_version(monkeypatch):
    payload = CBRRequest(
        muestra="157-SU-26",
        numero_ot="1021-26",
        fecha_ensayo="2026/08/04",
        realizado_por="TEST",
    )
    monkeypatch.setattr(cbr_router, "_ensure_payload_column", lambda db: None)
    monkeypatch.setattr(cbr_router, "generate_cbr_excel", lambda payload: b"xlsx")
    monkeypatch.setattr(cbr_router, "_upload_to_supabase_storage", lambda **kwargs: None)
    monkeypatch.setattr(
        cbr_router,
        "_guardar_ensayo",
        lambda **kwargs: SimpleNamespace(id=1),
    )

    response = cbr_router.generar_excel_cbr(payload, download=True, db=SimpleNamespace(rollback=lambda: None))

    assert response.headers["Content-Disposition"] == (
        'attachment; filename="1-INF.-N-157-26-SU37-CBR-ASTM-D1883-V03.xlsx"'
    )


def test_caras_content_disposition_preserves_template_version(monkeypatch):
    payload = CarasRequest(
        muestra="157-AG-26",
        numero_ot="1021-26",
        fecha_ensayo="2026/08/04",
        realizado_por="TEST",
    )
    monkeypatch.setattr(caras_router, "_ensure_payload_column", lambda db: None)
    monkeypatch.setattr(caras_router, "generate_caras_excel", lambda payload, db=None: b"xlsx")
    monkeypatch.setattr(caras_router, "_upload_to_supabase_storage", lambda **kwargs: None)
    monkeypatch.setattr(
        caras_router,
        "_guardar_ensayo",
        lambda **kwargs: SimpleNamespace(id=1),
    )

    response = caras_router.generar_excel_caras(payload, download=True, db=SimpleNamespace(rollback=lambda: None))

    assert response.headers["Content-Disposition"] == (
        'attachment; filename="1-INF.-N-157-26-AG35-CARAS-ASTM-D5821-V04.xlsx"'
    )
