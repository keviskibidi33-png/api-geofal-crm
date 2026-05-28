-- Migration: Drop observaciones from public.seguimiento_cliente_comercial
-- Description: Removes the unused observaciones column.

BEGIN;

ALTER TABLE public.seguimiento_cliente_comercial DROP COLUMN IF EXISTS observaciones;

COMMIT;
