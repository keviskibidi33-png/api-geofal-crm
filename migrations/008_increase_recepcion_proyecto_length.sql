-- Increase project length for recepcion and plantillas
-- Fecha: 11/03/2026

ALTER TABLE IF EXISTS public.recepcion
    ALTER COLUMN proyecto TYPE VARCHAR(500);

ALTER TABLE IF EXISTS public.recepcion_plantillas
    ALTER COLUMN proyecto TYPE VARCHAR(500);

-- Legacy table name (if present in older deployments)
ALTER TABLE IF EXISTS public.recepcion_muestras
    ALTER COLUMN proyecto TYPE VARCHAR(500);
