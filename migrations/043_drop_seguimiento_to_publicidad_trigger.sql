-- Migration: Drop tracking to publicidad sync trigger
-- Description: Removes trigger and function that synchronizes seguimiento_cliente_comercial into publicidad_geofal.

BEGIN;

DROP TRIGGER IF EXISTS trigger_sync_seguimiento_to_publicidad ON public.seguimiento_cliente_comercial;
DROP FUNCTION IF EXISTS public.sync_seguimiento_to_publicidad();

COMMIT;
