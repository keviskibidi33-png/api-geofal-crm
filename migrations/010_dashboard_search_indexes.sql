-- Dashboard search indexes
-- Fecha: 21/03/2026
-- Objetivo: soportar /dashboard/search sin seq scans completos a medida que crecen clientes/proyectos/cotizaciones.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Clientes: búsqueda por empresa, nombre, email y RUC; sugerencias recientes.
CREATE INDEX IF NOT EXISTS idx_clientes_empresa_trgm
    ON public.clientes USING gin (empresa gin_trgm_ops)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_clientes_nombre_trgm
    ON public.clientes USING gin (nombre gin_trgm_ops)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_clientes_email_trgm
    ON public.clientes USING gin (email gin_trgm_ops)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_clientes_ruc_trgm
    ON public.clientes USING gin (ruc gin_trgm_ops)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_clientes_recent_active
    ON public.clientes (created_at DESC)
    WHERE deleted_at IS NULL;

-- Contactos: join de apoyo para búsqueda de clientes.
CREATE INDEX IF NOT EXISTS idx_contactos_nombre_trgm
    ON public.contactos USING gin (nombre gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_contactos_cliente_principal
    ON public.contactos (cliente_id, es_principal DESC);

-- Proyectos: búsqueda y sugerencias recientes.
CREATE INDEX IF NOT EXISTS idx_proyectos_nombre_trgm
    ON public.proyectos USING gin (nombre gin_trgm_ops)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_proyectos_recent_active
    ON public.proyectos (created_at DESC)
    WHERE deleted_at IS NULL;

-- Cotizaciones: búsqueda por número y cliente; sugerencias recientes.
CREATE INDEX IF NOT EXISTS idx_cotizaciones_numero_trgm
    ON public.cotizaciones USING gin (numero gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_cotizaciones_cliente_nombre_trgm
    ON public.cotizaciones USING gin (cliente_nombre gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_cotizaciones_recent
    ON public.cotizaciones (created_at DESC);
