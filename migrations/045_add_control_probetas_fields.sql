-- Migration 045: Add control probetas columns to muestras_concreto table

ALTER TABLE public.muestras_concreto
ADD COLUMN IF NOT EXISTS elemento VARCHAR(50) DEFAULT '-',
ADD COLUMN IF NOT EXISTS densidad VARCHAR(50) DEFAULT '-',
ADD COLUMN IF NOT EXISTS status_ensayo VARCHAR(50) DEFAULT '-',
ADD COLUMN IF NOT EXISTS status_entrega VARCHAR(50) DEFAULT '-',
ADD COLUMN IF NOT EXISTS fecha_entrega VARCHAR(50) DEFAULT '-';

-- Notify PostgREST to reload schema
NOTIFY pgrst, 'reload schema';
