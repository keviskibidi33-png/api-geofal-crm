-- Migration 046: Create Huanta probetas table

CREATE TABLE IF NOT EXISTS public.huanta_probetas (
    id SERIAL PRIMARY KEY,
    item INTEGER NOT NULL,
    codigo_probeta VARCHAR(50) NOT NULL UNIQUE,
    sigla VARCHAR(20) NOT NULL DEFAULT 'HHTA',
    elemento VARCHAR(200) NOT NULL DEFAULT '-',
    detalle_elemento VARCHAR(300) NOT NULL DEFAULT '-',
    fecha_moldeo VARCHAR(20) NOT NULL,
    edad INTEGER NOT NULL DEFAULT 7,
    fecha_rotura VARCHAR(20) NOT NULL,
    codigo_muestra_lem VARCHAR(200) NOT NULL DEFAULT '',
    codigo_lote_interno VARCHAR(80) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    observaciones TEXT,
    fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_huanta_probetas_lote ON public.huanta_probetas (codigo_lote_interno);
CREATE INDEX IF NOT EXISTS idx_huanta_probetas_estado ON public.huanta_probetas (estado);

NOTIFY pgrst, 'reload schema';
