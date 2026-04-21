CREATE TABLE IF NOT EXISTS public.ingenieria_archivos (
    id SERIAL PRIMARY KEY,
    codigo_referencia VARCHAR(80),
    modulo_crm VARCHAR(80),
    categoria VARCHAR(120) NOT NULL,
    nombre_archivo VARCHAR(255) NOT NULL,
    ruta_archivo TEXT NOT NULL,
    extension VARCHAR(20),
    version VARCHAR(40),
    responsable VARCHAR(120),
    estado VARCHAR(20) NOT NULL DEFAULT 'activo',
    observaciones TEXT,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_ingenieria_archivos_codigo_referencia ON public.ingenieria_archivos (codigo_referencia);
CREATE INDEX IF NOT EXISTS ix_ingenieria_archivos_modulo_crm ON public.ingenieria_archivos (modulo_crm);
CREATE INDEX IF NOT EXISTS ix_ingenieria_archivos_categoria ON public.ingenieria_archivos (categoria);
CREATE INDEX IF NOT EXISTS ix_ingenieria_archivos_estado ON public.ingenieria_archivos (estado);
