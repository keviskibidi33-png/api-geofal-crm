-- Migration: Add comments columns to public.seguimiento_cliente_comercial
-- Description: Adds comentarios_asistente and comentarios_asesor columns.

BEGIN;

ALTER TABLE public.seguimiento_cliente_comercial 
ADD COLUMN IF NOT EXISTS comentarios_asistente TEXT,
ADD COLUMN IF NOT EXISTS comentarios_asesor TEXT;

COMMIT;
