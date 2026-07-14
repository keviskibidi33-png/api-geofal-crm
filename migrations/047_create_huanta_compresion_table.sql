-- Migration 047: Create Huanta compression table

CREATE TABLE IF NOT EXISTS public.huanta_compresion (
    id SERIAL PRIMARY KEY,
    probeta_id INTEGER NOT NULL UNIQUE REFERENCES public.huanta_probetas(id) ON DELETE CASCADE,
    codigo_probeta VARCHAR(50) NOT NULL,
    codigo_lote_interno VARCHAR(80) NOT NULL,
    codigo_muestra_lem VARCHAR(200) NOT NULL DEFAULT '',
    fecha_rotura VARCHAR(20) NOT NULL,
    diam_1 VARCHAR(20),
    diam_2 VARCHAR(20),
    long_1 VARCHAR(20),
    long_2 VARCHAR(20),
    long_3 VARCHAR(20),
    carga_maxima DOUBLE PRECISION,
    tipo_fractura VARCHAR(50),
    estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    observaciones TEXT,
    fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_huanta_compresion_lote ON public.huanta_compresion (codigo_lote_interno);

NOTIFY pgrst, 'reload schema';
