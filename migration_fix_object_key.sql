-- Migration: Add object_key column to verificacion_muestras table
-- Cause: Internal Server Error (psycopg2.errors.UndefinedColumn) column verificacion_muestras.object_key does not exist

ALTER TABLE verificacion_muestras ADD COLUMN IF NOT EXISTS object_key VARCHAR(500);

-- Update existing records if necessary (optional)
COMMENT ON COLUMN verificacion_muestras.object_key IS 'Ruta del archivo en el Storage de Supabase';
