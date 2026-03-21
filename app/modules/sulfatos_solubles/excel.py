
"""Excel generator for Sulfatos Solubles."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.utils.http_client import http_get

from .schemas import SulfatosSolublesRequest

logger = logging.getLogger(__name__)


def _find_template_path(filename: str) -> Path:
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]

    candidates = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _fetch_template_from_storage(filename: str) -> bytes | None:
    bucket = os.getenv("SUPABASE_TEMPLATES_BUCKET")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not bucket or not supabase_url or not supabase_key:
        return None

    template_key = f"{filename}"
    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{template_key}"
    try:
        resp = http_get(
            url,
            headers={"Authorization": f"Bearer {supabase_key}"},
            timeout=20,
            request_name="supabase.sulfatos_solubles.template_fetch",
        )
        if resp.status_code == 200:
            return resp.content
        logger.warning("Template download failed: %s (%s)", filename, resp.status_code)
    except Exception:
        logger.exception("Template download error: %s", filename)
    return None


def _get_template_bytes(filename: str) -> bytes:
    local_path = _find_template_path(filename)
    if local_path.exists():
        return local_path.read_bytes()

    storage_bytes = _fetch_template_from_storage(filename)
    if storage_bytes:
        return storage_bytes

    raise FileNotFoundError(f"Template {filename} not found")


def generate_sulfatos_solubles_excel(payload: SulfatosSolublesRequest) -> bytes:
    """
    Generate Excel from template. Injection mapping pending coordinates.
    """
    template_bytes = _get_template_bytes("Template_SULFATOS_SOLUBLES.xlsx")
    # TODO: inject payload values once cell coordinates are provided.
    return template_bytes
