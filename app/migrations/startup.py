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

    # ── Migration 052: ordenes_trabajo tipo column ──────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE ordenes_trabajo ADD COLUMN IF NOT EXISTS tipo VARCHAR(50) DEFAULT 'CONCRETO';"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ordenes_trabajo_tipo ON ordenes_trabajo (tipo);"))
            logger.info("Migration 052 applied (ordenes_trabajo tipo column).")
    except Exception as err:
        logger.warning("Migration 052 skipped: %s", _short_err(err))

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
                INSERT INTO public.chat_channels (id, name, description, is_private, category, allowed_roles)
                VALUES 
                  ('general', 'general', 'Comunicados e información de empresa', false, 'general', '{}'),
                  ('ventas', 'comercial-ventas', 'Coordinación de cotizaciones y clientes', true, 'area', '{"admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial"}'),
                  ('laboratorio', 'laboratorio-ensayos', 'Ensayos de campo, muestras y probetas', true, 'area', '{"admin", "admin_general", "gerencia", "super_admin", "laboratorio", "jefe_laboratorio", "jefe_de_laboratorio", "tecnico", "tecnico_suelos", "laboratorio_tipificador"}'),
                  ('informes', 'informes-revision', 'Revisión y emisión de informes LEM', true, 'area', '{"admin", "admin_general", "gerencia", "super_admin", "comercial", "auxiliar_comercial", "laboratorio", "jefe_laboratorio", "jefe_de_laboratorio"}'),
                  ('alertas', 'alertas-gerencia', 'Notificaciones y clientes prioritarios', true, 'area', '{"admin", "admin_general", "gerencia", "super_admin"}')
                ON CONFLICT (id) DO UPDATE SET
                  is_private = EXCLUDED.is_private,
                  allowed_roles = EXCLUDED.allowed_roles;
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 050 applied (chat_channels area roles updated).")
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

    # ── Migration 052: Chat Realtime Publication ──────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_publication_tables 
                        WHERE pubname = 'supabase_realtime' AND tablename = 'chat_messages'
                    ) THEN
                        ALTER PUBLICATION supabase_realtime ADD TABLE public.chat_messages;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_publication_tables 
                        WHERE pubname = 'supabase_realtime' AND tablename = 'chat_channels'
                    ) THEN
                        ALTER PUBLICATION supabase_realtime ADD TABLE public.chat_channels;
                    END IF;
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END $$;
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_messages_channel_created ON public.chat_messages (channel_id, created_at DESC);"))
            logger.info("Migration 052 applied (chat_messages & chat_channels supabase_realtime publication).")
    except Exception as err:
        logger.warning("Migration 052 skipped: %s", _short_err(err))

    # ── Migration 053: Chat Message Read Receipts ──────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ NULL;"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_messages_is_read ON public.chat_messages (channel_id, is_read);"))
            logger.info("Migration 053 applied (chat_messages is_read column).")
    except Exception as err:
        logger.warning("Migration 053 skipped: %s", _short_err(err))

    # ── Migration 054: Chat Message Reactions JSONB ────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS reactions JSONB DEFAULT '{}'::jsonb;"))
            logger.info("Migration 054 applied (chat_messages reactions column).")
    except Exception as err:
        logger.warning("Migration 054 skipped: %s", _short_err(err))

    # ── Migration 055: Chat Message Pinning ───────────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS pinned_by VARCHAR(100) NULL;"))
            conn.execute(text("ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMPTZ NULL;"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chat_messages_is_pinned ON public.chat_messages (channel_id, is_pinned);"))
            logger.info("Migration 055 applied (chat_messages is_pinned columns).")
    except Exception as err:
        logger.warning("Migration 055 skipped: %s", _short_err(err))

    # ── Migration 056: ordenes_trabajo table & ot permissions ────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.ordenes_trabajo (
                    id SERIAL PRIMARY KEY,
                    numero_ot VARCHAR(100) UNIQUE NOT NULL,
                    numero_recepcion VARCHAR(100),
                    referencia VARCHAR(255) DEFAULT '-',
                    cliente VARCHAR(255),
                    proyecto VARCHAR(255),
                    fecha_recepcion VARCHAR(50),
                    plazo_entrega_dias VARCHAR(50),
                    inicio_programado VARCHAR(50),
                    fin_programado VARCHAR(50),
                    inicio_real VARCHAR(50),
                    fin_real VARCHAR(50),
                    variacion_inicio VARCHAR(50),
                    variacion_fin VARCHAR(50),
                    duracion_real_ejecucion_dias VARCHAR(50),
                    observaciones TEXT,
                    ot_aperturada_por VARCHAR(255),
                    ot_designada_a VARCHAR(255),
                    items JSONB NOT NULL DEFAULT '[]'::jsonb,
                    estado VARCHAR(50) NOT NULL DEFAULT 'PENDIENTE',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    creado_por VARCHAR(255),
                    actualizado_por VARCHAR(255)
                );
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ordenes_trabajo_numero_ot ON public.ordenes_trabajo (numero_ot);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ordenes_trabajo_numero_recepcion ON public.ordenes_trabajo (numero_recepcion);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ordenes_trabajo_estado ON public.ordenes_trabajo (estado);"))
            conn.execute(text("""
                UPDATE role_definitions
                SET permissions = jsonb_set(permissions, '{ot}', '{"read": true, "write": true, "delete": true}'::jsonb, true)
                WHERE role_id IN ('admin', 'admin_general', 'jefe_laboratorio', 'oficina_tecnica', 'oficina_tecnica_sup', 'tecnico', 'tecnico_suelos');
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 056 applied (ordenes_trabajo table).")
    except Exception as err:
        logger.warning("Migration 056 skipped: %s", _short_err(err))

    # ── Migration 057: tipo_recepcion & flexible sample fields ────────
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE public.recepcion ADD COLUMN IF NOT EXISTS tipo_recepcion VARCHAR(50) DEFAULT 'CONCRETO';"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ADD COLUMN IF NOT EXISTS tamano_peso VARCHAR(100);"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ADD COLUMN IF NOT EXISTS procedencia VARCHAR(255);"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ADD COLUMN IF NOT EXISTS descripcion_muestra TEXT;"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ADD COLUMN IF NOT EXISTS cantidad VARCHAR(100);"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ADD COLUMN IF NOT EXISTS ensayos_requeridos TEXT;"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ADD COLUMN IF NOT EXISTS norma_requerida VARCHAR(255);"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ALTER COLUMN estructura DROP NOT NULL;"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ALTER COLUMN fc_kg_cm2 DROP NOT NULL;"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ALTER COLUMN fecha_moldeo DROP NOT NULL;"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ALTER COLUMN edad DROP NOT NULL;"))
            conn.execute(text("ALTER TABLE public.muestras_concreto ALTER COLUMN fecha_rotura DROP NOT NULL;"))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 057 applied (tipo_recepcion & sample columns).")
    except Exception as err:
        logger.warning("Migration 057 skipped: %s", _short_err(err))

    # ── Migration 058: kanban_cards table ────────────────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.kanban_cards (
                    id VARCHAR(64) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    proyecto_nombre VARCHAR(255) NOT NULL,
                    codigo_ot VARCHAR(100),
                    column_id VARCHAR(30) NOT NULL DEFAULT 'todo',
                    priority VARCHAR(20) NOT NULL DEFAULT 'media',
                    assigned_to VARCHAR(150) NOT NULL DEFAULT 'Laboratorio',
                    assigned_avatar TEXT,
                    due_date VARCHAR(50),
                    image_url TEXT,
                    notes JSONB NOT NULL DEFAULT '[]'::jsonb,
                    tracing_summary JSONB,
                    created_by VARCHAR(100),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_kanban_cards_column_id ON public.kanban_cards (column_id);
                CREATE INDEX IF NOT EXISTS idx_kanban_cards_codigo_ot ON public.kanban_cards (codigo_ot);
                CREATE INDEX IF NOT EXISTS idx_kanban_cards_created_at ON public.kanban_cards (created_at DESC);
                NOTIFY pgrst, 'reload schema';
            """))
            logger.info("Migration 058 applied (kanban_cards table).")
    except Exception as err:
        logger.warning("Migration 058 skipped: %s", _short_err(err))

    # ── Migration 059: Backfill tipo_recepcion a CONCRETO en registros históricos ─
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE public.recepcion
                SET tipo_recepcion = 'CONCRETO'
                WHERE tipo_recepcion IS NULL OR tipo_recepcion = '';
            """))
            logger.info("Migration 059 applied (tipo_recepcion CONCRETO backfilled).")
    except Exception as err:
        logger.warning("Migration 059 skipped: %s", _short_err(err))

    # ── Migration 060: Normalizar revisado_por 'ING. FABIAN' → 'FABIAN LA ROSA' ──
    # Backfill de registros históricos en tablas de control ambiental.
    # Se ejecuta siempre (idempotente por el WHERE), costo cero si ya fue migrado.
    try:
        with engine.begin() as conn:
            # Tabla de filas de verificación de balanzas
            conn.execute(text("""
                UPDATE public.control_verificacion_balanzas_filas
                SET revisado_por = 'FABIAN LA ROSA'
                WHERE revisado_por = 'ING. FABIAN';
            """))
            # Tabla de filas de control de temperatura y humedad
            conn.execute(text("""
                UPDATE public.control_temperatura_humedad_filas
                SET responsable_revision = 'FABIAN LA ROSA'
                WHERE responsable_revision = 'ING. FABIAN';
            """))
            # Corregir también el DEFAULT de la columna en balanzas (para futuros registros)
            conn.execute(text("""
                ALTER TABLE public.control_verificacion_balanzas_filas
                ALTER COLUMN revisado_por SET DEFAULT '';
            """))
            logger.info("Migration 060 applied (ING. FABIAN → FABIAN LA ROSA backfill en control ambiental).")
    except Exception as err:
        logger.warning("Migration 060 skipped: %s", _short_err(err))

    # ── Migration 061: ot & ot_concreto permissions ──────────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE role_definitions
                SET permissions = jsonb_set(
                    jsonb_set(permissions, '{ot_concreto}', '{"read": true, "write": true, "delete": true}'::jsonb, true),
                    '{ot}', '{"read": true, "write": true, "delete": true}'::jsonb, true
                )
                WHERE role_id IN (
                    'admin', 'admin_general', 'jefe_laboratorio', 'oficina_tecnica',
                    'oficina_tecnica_humedad', 'oficina_tecnica_humedad_tipificador',
                    'oficina_tecnica_sup', 'laboratorio', 'laboratorio_tipificador'
                );
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 061 applied (ot & ot_concreto permissions for jefe_laboratorio and lab roles).")
    except Exception as err:
        logger.warning("Migration 061 skipped: %s", _short_err(err))

    # ── Migration 062: muestras_concreto cantera & ensayos_json ─────────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE public.muestras_concreto
                ADD COLUMN IF NOT EXISTS cantera VARCHAR(255),
                ADD COLUMN IF NOT EXISTS codigo_ensayo VARCHAR(50),
                ADD COLUMN IF NOT EXISTS ensayos_json TEXT;
            """))
            conn.execute(text("NOTIFY pgrst, 'reload schema';"))
            logger.info("Migration 062 applied (cantera, codigo_ensayo, ensayos_json on muestras_concreto).")
    except Exception as err:
        logger.warning("Migration 062 skipped: %s", _short_err(err))

    # ── Migration 063: create datos_clientes table & permissions ─────────
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.datos_clientes (
                    id SERIAL PRIMARY KEY,
                    cliente VARCHAR(255) NOT NULL,
                    ruc VARCHAR(20) NOT NULL,
                    domicilio_legal TEXT NOT NULL,
                    persona_contacto VARCHAR(255),
                    email VARCHAR(255),
                    telefono VARCHAR(50),
                    solicitante VARCHAR(255) NOT NULL,
                    domicilio_solicitante TEXT NOT NULL,
                    proyecto VARCHAR(500) NOT NULL,
                    ubicacion TEXT NOT NULL,
                    estado VARCHAR(20) DEFAULT 'INCOMPLETO',
                    activo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_datos_clientes_cliente ON public.datos_clientes(cliente);
                CREATE INDEX IF NOT EXISTS idx_datos_clientes_ruc ON public.datos_clientes(ruc);
                CREATE INDEX IF NOT EXISTS idx_datos_clientes_proyecto ON public.datos_clientes(proyecto);
                CREATE INDEX IF NOT EXISTS idx_datos_clientes_estado ON public.datos_clientes(estado);

                UPDATE role_definitions
                SET permissions = jsonb_set(
                    permissions,
                    '{datos_clientes}',
                    '{"read": true, "write": true, "delete": true}'::jsonb,
                    true
                )
                WHERE role_id IN (
                    'admin', 'admin_general', 'jefe_laboratorio', 'oficina_tecnica',
                    'oficina_tecnica_humedad', 'oficina_tecnica_humedad_tipificador',
                    'oficina_tecnica_sup', 'laboratorio', 'laboratorio_tipificador',
                    'auxiliar_comercial', 'recepcion'
                );
                NOTIFY pgrst, 'reload schema';
            """))
            logger.info("Migration 063 applied (datos_clientes table & role permissions).")
    except Exception as err:
        logger.warning("Migration 063 skipped: %s", _short_err(err))

    # ── Migration 064: Expand string columns to TEXT to avoid truncation ──
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                ALTER TABLE ordenes_trabajo ALTER COLUMN proyecto TYPE TEXT;
                ALTER TABLE ordenes_trabajo ALTER COLUMN cliente TYPE TEXT;
                ALTER TABLE ordenes_trabajo ALTER COLUMN referencia TYPE TEXT;
                ALTER TABLE ordenes_trabajo ALTER COLUMN ot_aperturada_por TYPE TEXT;
                ALTER TABLE ordenes_trabajo ALTER COLUMN ot_designada_a TYPE TEXT;
                
                ALTER TABLE recepcion ALTER COLUMN proyecto TYPE TEXT;
                ALTER TABLE recepcion ALTER COLUMN cliente TYPE TEXT;
                ALTER TABLE recepcion ALTER COLUMN solicitante TYPE TEXT;
                ALTER TABLE recepcion ALTER COLUMN domicilio_legal TYPE TEXT;
                ALTER TABLE recepcion ALTER COLUMN domicilio_solicitante TYPE TEXT;
                ALTER TABLE recepcion ALTER COLUMN ubicacion TYPE TEXT;

                ALTER TABLE datos_clientes ALTER COLUMN proyecto TYPE TEXT;
                ALTER TABLE datos_clientes ALTER COLUMN cliente TYPE TEXT;
                ALTER TABLE datos_clientes ALTER COLUMN solicitante TYPE TEXT;
                ALTER TABLE datos_clientes ALTER COLUMN domicilio_legal TYPE TEXT;
                ALTER TABLE datos_clientes ALTER COLUMN domicilio_solicitante TYPE TEXT;
                ALTER TABLE datos_clientes ALTER COLUMN ubicacion TYPE TEXT;
            """))
            logger.info("Migration 064 applied (expanded project & text columns to TEXT).")
    except Exception as err:
        logger.warning("Migration 064 skipped: %s", _short_err(err))

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

            # Eliminación total de recepciones auto-inyectadas
            from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
            from app.modules.ot.models import OrdenTrabajo

            auto_recs = db_session.query(RecepcionMuestra).filter(
                RecepcionMuestra.tipo_recepcion == "CONCRETO",
                RecepcionMuestra.domicilio_legal == "Sin especificar",
            ).all()

            for s_rec in auto_recs:
                # Si tiene una OT creada manualmente con responsables asignados, preservar
                has_valid_ot = db_session.query(OrdenTrabajo).filter(
                    OrdenTrabajo.numero_recepcion == s_rec.numero_recepcion,
                    OrdenTrabajo.ot_aperturada_por.isnot(None),
                    OrdenTrabajo.ot_aperturada_por != "",
                    OrdenTrabajo.ot_aperturada_por != "-",
                ).first()
                if has_valid_ot:
                    continue

                r_num = str(s_rec.numero_recepcion).strip()
                logger.info("[STARTUP-CLEANUP] Eliminando recepcion auto-inyectada: %s", r_num)
                db_session.query(MuestraConcreto).filter(MuestraConcreto.recepcion_id == s_rec.id).delete()
                db_session.delete(s_rec)

            db_session.commit()
            logger.info("[STARTUP-CLEANUP] Purga total de recepciones auto-inyectadas completada.")
    except Exception as err:
        logger.warning("Startup trazabilidad cleanup skipped: %s", _short_err(err))
