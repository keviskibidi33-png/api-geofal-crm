-- Increase telefono length for recepcion
-- Fecha: 11/03/2026

ALTER TABLE IF EXISTS public.recepcion
    ALTER COLUMN telefono TYPE VARCHAR(50);

-- Legacy table name (if present in older deployments)
ALTER TABLE IF EXISTS public.recepcion_muestras
    ALTER COLUMN telefono TYPE VARCHAR(50);
