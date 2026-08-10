"""
Startup migrations — runs once per process restart.

Call run_startup_migrations() from the FastAPI lifespan event
so that migrations are isolated from the main app bootstrap.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _short_err(err: Exception) -> str:
    """Return a single-line summary of an exception without SQL dump."""
    msg = str(err).strip()
    first_line = msg.splitlines()[0] if msg else "Error desconocido"
    return re.sub(r"\[SQL:.*", "", first_line).strip()


_MIGRATIONS_RUN = False


def run_startup_migrations(engine) -> None:
    """Execute all pending in-code migrations against the database."""
    global _MIGRATIONS_RUN
    if _MIGRATIONS_RUN:
        logger.debug("Startup migrations already executed for this process.")
        return

    from sqlalchemy import text

    # ── Migration 044: control_probetas permissions ──────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE role_definitions
                SET permissions = jsonb_set(permissions, '{control_probetas}', '{"read": true, "write": true, "delete": true}'::jsonb, true)
                WHERE role_id IN ('admin', 'admin_general');
            """))
            conn.execute(text("""
                UPDATE role_definitions
                SET permissions = jsonb_set(permissions, '{control_probetas}', '{"read": true, "write": true, "delete": true}'::jsonb, true)
                WHERE role_id IN ('oficina_tecnica', 'oficina_tecnica_humedad', 'oficina_tecnica_humedad_tipificador', 'oficina_tecnica_sup');
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_muestras_concreto_fecha_rotura ON public.muestras_concreto (fecha_rotura);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_muestras_concreto_recepcion_id ON public.muestras_concreto (recepcion_id);"))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migrations 044-045 applied.")
    except Exception as err:
        logger.warning("Migration 044-045 skipped: %s", _short_err(err))

    # ── Migration 046: densidad_huantar permissions ──────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE role_definitions
                SET permissions = jsonb_set(permissions, '{densidad_huantar}', '{"read": true, "write": true, "delete": true}'::jsonb, true)
                WHERE role_id IN (
                    'admin', 'admin_general', 'oficina_tecnica', 'oficina_tecnica_humedad',
                    'oficina_tecnica_humedad_tipificador', 'oficina_tecnica_sup',
                    'jefe_laboratorio', 'tecnico', 'tecnico_suelos'
                );
            """))
            logger.info("Migration 046 applied.")
    except Exception as err:
        logger.warning("Migration 046 skipped: %s", _short_err(err))

    # ── Migration 047: seguimiento_cliente_comercial columns ─────────
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE public.seguimiento_cliente_comercial ADD COLUMN IF NOT EXISTS costo_cotiz_sin_igv VARCHAR(100);"))
            conn.execute(text("ALTER TABLE public.seguimiento_cliente_comercial ADD COLUMN IF NOT EXISTS categoria_servicio VARCHAR(20);"))
            conn.execute(text("ALTER TABLE public.seguimiento_cliente_comercial ADD COLUMN IF NOT EXISTS comentarios_asesor TEXT;"))
            conn.execute(text("ALTER TABLE public.seguimiento_cliente_comercial ADD COLUMN IF NOT EXISTS asesor_email VARCHAR(255);"))
            conn.execute(text("ALTER TABLE public.seguimiento_cliente_comercial_2 ADD COLUMN IF NOT EXISTS asesor_email VARCHAR(255);"))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 047 applied.")
    except Exception as err:
        logger.warning("Migration 047 skipped: %s", _short_err(err))

    # ── Migration 048: show_kpi + tabla_seguimiento on perfiles ──────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE public.perfiles ADD COLUMN IF NOT EXISTS show_kpi BOOLEAN NOT NULL DEFAULT true;
            """))
            conn.execute(text("""
                ALTER TABLE public.perfiles ADD COLUMN IF NOT EXISTS tabla_seguimiento VARCHAR(20) DEFAULT 'tabla2';
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 048 applied.")
    except Exception as err:
        logger.warning("Migration 048 skipped: %s", _short_err(err))

    # ── Migration 049: programacion_lab OT trigger ───────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION public.ensure_programacion_lab_item_numero()
                RETURNS trigger
                LANGUAGE plpgsql
                SECURITY DEFINER
                SET search_path = public
                AS $$
                DECLARE
                    matches text[];
                    max_item integer;
                BEGIN
                    matches := regexp_match(COALESCE(NEW.ot, ''), '(\\d+)');
                    IF matches IS NOT NULL AND matches[1] <> '' THEN
                        NEW.item_numero := matches[1]::integer;
                    ELSE
                        IF NEW.item_numero IS NULL THEN
                            SELECT COALESCE(MAX(item_numero), 0) + 1 INTO max_item FROM public.programacion_lab;
                            NEW.item_numero := max_item;
                        END IF;
                    END IF;
                    RETURN NEW;
                END;
                $$;
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 049 applied.")
    except Exception as err:
        logger.warning("Migration 049 skipped: %s", _short_err(err))

    # ── Migration 050: chat_channels & chat_messages tables ─────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.chat_channels (
                    id VARCHAR(100) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    is_private BOOLEAN DEFAULT false,
                    created_by VARCHAR(100),
                    allowed_roles TEXT[] DEFAULT '{}',
                    allowed_emails TEXT[] DEFAULT '{}',
                    category VARCHAR(50) DEFAULT 'general',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.chat_messages (
                    id VARCHAR(100) PRIMARY KEY,
                    channel_id VARCHAR(100) NOT NULL,
                    sender_id VARCHAR(100) NOT NULL,
                    sender_name VARCHAR(200),
                    sender_avatar TEXT,
                    content TEXT NOT NULL,
                    attachments JSONB DEFAULT '[]'::jsonb,
                    parent_id VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_messages_channel_id ON public.chat_messages (channel_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON public.chat_messages (created_at);"))
            conn.execute(text("""
                INSERT INTO public.chat_channels (id, name, description, is_private, category)
                VALUES 
                  ('general', 'general', 'Comunicados e información de empresa', false, 'general'),
                  ('ventas', 'comercial-ventas', 'Coordinación de cotizaciones y clientes', false, 'area'),
                  ('laboratorio', 'laboratorio-ensayos', 'Ensayos de campo, muestras y probetas', false, 'area'),
                  ('informes', 'informes-revision', 'Revisión y emisión de informes LEM', false, 'area'),
                  ('alertas', 'alertas-gerencia', 'Notificaciones y clientes prioritarios', true, 'area')
                ON CONFLICT (id) DO NOTHING;
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 050 applied.")
    except Exception as err:
        logger.warning("Migration 050 skipped: %s", _short_err(err))

    # ── Migration 051: control_ambiental tables for Supabase ──────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.control_verificacion_balanzas (
                    id BIGSERIAL PRIMARY KEY,
                    codigo_balanza VARCHAR(50) NOT NULL,
                    nombre_balanza VARCHAR(150),
                    mes_anio VARCHAR(50) NOT NULL,
                    ubicacion VARCHAR(100) NOT NULL,
                    codigos_pesas_patron VARCHAR(150) DEFAULT 'PP-01, PP-02, PP-05',
                    capacidad_g NUMERIC(10,2),
                    masa_patron_g NUMERIC(10,2),
                    error_max_permitido_g NUMERIC(10,3),
                    limpieza_nivelacion BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.control_verificacion_balanzas_filas (
                    id BIGSERIAL PRIMARY KEY,
                    header_id BIGINT REFERENCES public.control_verificacion_balanzas(id) ON DELETE CASCADE,
                    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
                    hora TIME NOT NULL DEFAULT '08:00',
                    temp_c NUMERIC(4,1),
                    humedad_pct NUMERIC(4,1),
                    pesadas JSONB DEFAULT '[]'::jsonb,
                    verificado_por VARCHAR(100) NOT NULL DEFAULT 'BEATRIZ',
                    revisado_por VARCHAR(100) NOT NULL DEFAULT 'ING. FABIAN',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.control_temperatura_humedad (
                    id BIGSERIAL PRIMARY KEY,
                    registro_codigo VARCHAR(50) DEFAULT 'F-LEM-P-05.01',
                    mes_anio VARCHAR(50) NOT NULL,
                    area_ambiente VARCHAR(100) NOT NULL,
                    aprobado_por VARCHAR(100) DEFAULT 'JEFE DE LABORATORIO',
                    fecha_aprobacion DATE DEFAULT CURRENT_DATE,
                    cumple_global BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.control_temperatura_humedad_filas (
                    id BIGSERIAL PRIMARY KEY,
                    header_id BIGINT REFERENCES public.control_temperatura_humedad(id) ON DELETE CASCADE,
                    fecha_registro DATE NOT NULL,
                    hora_toma TIME NOT NULL,
                    fecha_lectura DATE,
                    temp_min NUMERIC(4,1),
                    temp_max NUMERIC(4,1),
                    hum_min NUMERIC(4,1),
                    hum_max NUMERIC(4,1),
                    temperatura_c NUMERIC(4,1) NOT NULL,
                    humedad_relativa_pct NUMERIC(4,1) NOT NULL,
                    cumple BOOLEAN DEFAULT TRUE,
                    responsable_registro VARCHAR(100) NOT NULL,
                    responsable_revision VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 051 applied (control_ambiental tables).")
    except Exception as err:
        logger.warning("Migration 051 skipped: %s", _short_err(err))

    _MIGRATIONS_RUN = True


def run_startup_cleanup(engine) -> None:
    """
    Clean up orphaned and non-canonical trazabilidades.
    Runs after migrations. Separated so a failure here doesn't
    block the app from serving requests.
    """
    try:
        from sqlalchemy.orm import Session
        from app.modules.tracing.service import TracingService
        from app.modules.tracing.models import Trazabilidad

        with Session(engine) as db_session:
            resultado = TracingService.sanear_duplicados(db_session)
            if resultado.get("eliminados", 0) > 0 or resultado.get("sincronizados", 0) > 0:
                logger.info("[STARTUP-CLEANUP] Saneamiento completado: %s", resultado)

            trazas = db_session.query(Trazabilidad).all()
            import re as _re
            for t in trazas:
                num = t.numero_recepcion
                if num and (not _re.search(r'-\d{2}$', num) or num.endswith('-')):
                    recepcion, canonical = TracingService._buscar_recepcion_flexible(db_session, num)
                    if canonical and canonical != num:
                        canonical_exists = db_session.query(Trazabilidad).filter(
                            Trazabilidad.numero_recepcion == canonical
                        ).first()
                        if canonical_exists:
                            db_session.delete(t)
                        else:
                            t.numero_recepcion = canonical
            db_session.commit()
    except Exception as err:
        logger.warning("Startup trazabilidad cleanup skipped: %s", _short_err(err))
