"""
Main FastAPI application entry point.
Clean, lightweight orchestrator.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import JWTAuthMiddleware, get_current_user, current_actor
from app.database import engine
from app.db_utils import _get_connection, _has_database_url, _get_cors_origins
from app.migrations.startup import run_startup_migrations, run_startup_cleanup

# Audit log listeners
import app.audit

# Routers
from app.modules.recepcion.router import router as recepciones_router
from app.modules.cotizacion.router import router as cotizacion_router
from app.modules.programacion.router import router as programacion_router
from app.modules.verificacion.router import router as verificacion_router
from app.modules.compresion.router import router as compresion_router
from app.modules.tracing.router import router as tracing_router
from app.modules.humedad.router import router as humedad_router
from app.modules.cont_humedad.router import router as cont_humedad_router
from app.modules.planas.router import router as planas_router
from app.modules.caras.router import router as caras_router
from app.modules.cbr.router import router as cbr_router
from app.modules.proctor.router import router as proctor_router
from app.modules.llp.router import router as llp_router
from app.modules.gran_suelo.router import router as gran_suelo_router
from app.modules.gran_agregado.router import router as gran_agregado_router
from app.modules.abra.router import router as abra_router
from app.modules.abrass.router import router as abrass_router
from app.modules.peso_unitario.router import router as peso_unitario_router
from app.modules.tamiz.router import router as tamiz_router
from app.modules.equi_arena.router import router as equi_arena_router
from app.modules.ge_fino.router import router as ge_fino_router
from app.modules.ge_grueso.router import router as ge_grueso_router
from app.modules.cd.router import router as cd_router
from app.modules.ph.router import router as ph_router
from app.modules.cloro_soluble.router import router as cloro_soluble_router
from app.modules.sales_solubles.router import router as sales_solubles_router
from app.modules.sulfatos_solubles.router import router as sulfatos_solubles_router
from app.modules.compresion_no_confinada.router import router as compresion_no_confinada_router
from app.modules.cont_mat_organica.router import router as cont_mat_organica_router
from app.modules.terrones_fino_grueso.router import router as terrones_fino_grueso_router
from app.modules.azul_metileno.router import router as azul_metileno_router
from app.modules.part_livianas.router import router as part_livianas_router
from app.modules.imp_organicas.router import router as imp_organicas_router
from app.modules.sul_magnesio.router import router as sul_magnesio_router
from app.modules.angularidad.router import router as angularidad_router
from app.modules.ingenieria_archivos.router import router as ingenieria_archivos_router
from app.modules.correlativos.router import router as correlativos_router
from app.modules.control_informes.router import router as control_informes_router
from app.modules.seguimiento_cliente_comercial.router import router as seguimiento_comercial_router
from app.modules.seguimiento_cliente_comercial_2.router import router as seguimiento_comercial_2_router
from app.modules.publicidad_geofal.router import router as publicidad_geofal_router
from app.modules.control_probetas.router import router as control_probetas_router
from app.modules.densidad_huantar.router import router as densidad_huantar_router
from app.modules.huanta_probetas.router import router as huanta_probetas_router
from app.modules.huanta_compresion.router import router as huanta_compresion_router
from app.modules.roles.router import router as roles_router
from app.modules.notifications.router import router as notifications_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.users.router import router as users_router
from app.modules.control_ambiental.router import router as control_ambiental_router
from app.modules.control_ambiental.models import Base as ControlAmbientalBase
from app.modules.chat.router import router as chat_router
from app.modules.chat.models import Base as ChatBase
from app.modules.ot.router import router as ot_router
from app.modules.ot.models import Base as OTBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

# Startup migrations execution
try:
    from app.modules.recepcion.models import Base as RecepcionBase
    from app.modules.verificacion.models import Base as VerificacionBase
    from app.database import Base as MainBase

    RecepcionBase.metadata.create_all(bind=engine)
    VerificacionBase.metadata.create_all(bind=engine)
    ControlAmbientalBase.metadata.create_all(bind=engine)
    ChatBase.metadata.create_all(bind=engine)
    OTBase.metadata.create_all(bind=engine)
    MainBase.metadata.create_all(bind=engine)
    
    run_startup_migrations(engine)
    run_startup_cleanup(engine)
except Exception as e:
    logger.warning("Could not run startup migrations (DB might be offline): %s", e)

# App initialization
app = FastAPI(title="CRM Geofal Backend API", version="2.0.0")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to guarantee JSON error response with CORS headers."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "message": str(exc) if os.getenv("ALLOW_INSECURE_DEV_AUTH") == "true" else "Error interno del servidor",
            "path": request.url.path
        }
    )


# CORS setup
_origins = _get_cors_origins()
_allow_creds = "*" not in _origins and len(_origins) > 0
_origin_regex = r"https?://([a-zA-Z0-9-]+\.)*geofal\.com\.pe(:\d+)?|https?://localhost(:\d+)?|https?://127\.0\.0\.1(:\d+)?"


@app.middleware("http")
async def force_https_behind_proxy(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    return await call_next(request)


app.add_middleware(JWTAuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=_allow_creds,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Storage-Object-Key"],
    max_age=3600,
)

# Global Exception Handler to preserve CORS headers on unhandled 500 errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Global unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Error interno del servidor: {str(exc)}"},
    )

# Health & Debug Endpoints
@app.get("/")
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "crm-geofal-backend", "db": _has_database_url()}


@app.get("/debug-db", dependencies=[Depends(get_current_user)])
async def debug_db():
    """Verify database connection and schema for troubleshooting (Secured)."""
    actor = current_actor.get() or {}
    user_role = (actor.get("role") or "").strip().lower()
    if user_role not in {"admin", "admin_general"}:
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requieren permisos de administrador.")

    if not _has_database_url():
        return {"error": "DATABASE_URL not set"}
    try:
        conn = _get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            tables = [r[0] for r in cur.fetchall()]
            return {
                "status": "connected",
                "version": version,
                "tables_count": len(tables),
            }
    except Exception as e:
        logger.exception("Error en debug-db: %s", e)
        return {"status": "error", "message": str(e)}
    finally:
        if "conn" in locals() and conn:
            conn.close()


# Mount feature routers
app.include_router(recepciones_router)
app.include_router(cotizacion_router)
app.include_router(programacion_router)
app.include_router(verificacion_router)
app.include_router(compresion_router)
app.include_router(tracing_router)
app.include_router(humedad_router)
app.include_router(cont_humedad_router)
app.include_router(planas_router)
app.include_router(caras_router)
app.include_router(cbr_router)
app.include_router(proctor_router)
app.include_router(llp_router)
app.include_router(gran_suelo_router)
app.include_router(gran_agregado_router)
app.include_router(abra_router)
app.include_router(abrass_router)
app.include_router(peso_unitario_router)
app.include_router(tamiz_router)
app.include_router(equi_arena_router)
app.include_router(ge_fino_router)
app.include_router(ge_grueso_router)
app.include_router(cd_router)
app.include_router(ph_router)
app.include_router(cloro_soluble_router)
app.include_router(sales_solubles_router)
app.include_router(sulfatos_solubles_router)
app.include_router(compresion_no_confinada_router)
app.include_router(cont_mat_organica_router)
app.include_router(terrones_fino_grueso_router)
app.include_router(azul_metileno_router)
app.include_router(part_livianas_router)
app.include_router(imp_organicas_router)
app.include_router(sul_magnesio_router)
app.include_router(angularidad_router)
app.include_router(ingenieria_archivos_router)
app.include_router(correlativos_router)
app.include_router(control_informes_router)
app.include_router(seguimiento_comercial_router)
app.include_router(seguimiento_comercial_2_router)
app.include_router(publicidad_geofal_router)
app.include_router(control_probetas_router)
app.include_router(densidad_huantar_router)
app.include_router(huanta_probetas_router)
app.include_router(huanta_compresion_router)
app.include_router(roles_router)
app.include_router(notifications_router)
app.include_router(dashboard_router)
app.include_router(users_router)
app.include_router(control_ambiental_router)
# app.include_router(chat_router)  # Desactivado temporalmente hasta nuevo aviso
app.include_router(ot_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
