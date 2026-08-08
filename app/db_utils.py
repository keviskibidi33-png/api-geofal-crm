"""
Shared database connection and environment utilities.
All modules should import _get_connection / _has_database_url / _get_cors_origins from here.
"""
from __future__ import annotations

import os
import psycopg2
from psycopg2.extras import RealDictCursor  # noqa: F401 — re-exported for convenience


def _db_disabled() -> bool:
    return (os.getenv("QUOTES_DISABLE_DB") or "").strip().lower() in {"1", "true", "yes", "on"}


def _get_database_url() -> str:
    url = os.getenv("QUOTES_DATABASE_URL")
    if not url:
        return (
            f"postgresql://{os.getenv('DB_USER', 'directus')}:"
            f"{os.getenv('DB_PASSWORD', 'directus')}@"
            f"{os.getenv('DB_HOST', 'postgres')}:"
            f"{os.getenv('DB_PORT', '5432')}/"
            f"{os.getenv('DB_DATABASE', 'directus')}"
        )
    return url


def _has_database_url() -> bool:
    if _db_disabled():
        return False
    url = (os.getenv("QUOTES_DATABASE_URL") or "").strip()
    if url:
        return True
    return bool(os.getenv("DB_HOST"))


def _get_connection():
    """Open a new psycopg2 connection. Caller is responsible for closing it."""
    dsn = _get_database_url()
    return psycopg2.connect(dsn, connect_timeout=3)


def _get_cors_origins() -> list[str]:
    origins = [
        "http://localhost:8474",
        "http://127.0.0.1:8474",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:3005",
        "http://localhost:3006",
        "http://localhost:3007",
        "http://localhost:3009",
        "http://localhost:3010",
        "http://localhost:3011",
        "http://localhost:3012",
        "http://localhost:3013",
        "http://localhost:3014",
        "http://localhost:3015",
        "http://localhost:3016",
        "http://localhost:3017",
        "http://localhost:3018",
        "http://localhost:3019",
        "http://localhost:3020",
        "http://localhost:3021",
        "http://localhost:3022",
        "http://localhost:3023",
        "http://localhost:3024",
        "http://localhost:3025",
        "http://localhost:3026",
        "http://localhost:3027",
        "http://localhost:3028",
        "http://localhost:3029",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "https://crm.geofal.com.pe",
        "https://recepcion.geofal.com.pe",
        "https://cotizador.geofal.com.pe",
        "https://programacion.geofal.com.pe",
        "https://compresion.geofal.com.pe",
        "https://laboratorio.geofal.com.pe",
        "https://humedad.geofal.com.pe",
        "https://cbr.geofal.com.pe",
        "https://proctor.geofal.com.pe",
        "https://llp.geofal.com.pe",
        "https://gran-suelo.geofal.com.pe",
        "https://gran-agregado.geofal.com.pe",
        "https://equiarena.geofal.com.pe",
        "https://equi-arena.geofal.com.pe",
        "https://ge-fino.geofal.com.pe",
        "https://ge-grueso.geofal.com.pe",
        "https://abra.geofal.com.pe",
        "https://abrass.geofal.com.pe",
        "https://peso-unitario.geofal.com.pe",
        "https://tamiz.geofal.com.pe",
        "https://contenido-humedad.geofal.com.pe",
        "https://planas.geofal.com.pe",
        "https://caras.geofal.com.pe",
        "https://cd.geofal.com.pe",
        "https://ph.geofal.com.pe",
        "https://cloro-soluble.geofal.com.pe",
        "https://sales-solubles.geofal.com.pe",
        "https://sulfatos-solubles.geofal.com.pe",
        "https://compresion-no-confinada.geofal.com.pe",
        "https://ensayos-especiales.geofal.com.pe",
        "https://comp.noconfinada.geofal.com.pe",
        "https://verificacion.geofal.com.pe",
        "https://verifiacion.geofal.com.pe",
    ]
    raw = os.getenv("QUOTES_CORS_ORIGINS")
    if raw:
        if raw == "*":
            return ["*"]
        extra = [o.strip() for o in raw.split(",") if o.strip()]
        origins.extend(extra)
    return list(set(origins))
