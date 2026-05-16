-- 036_sync_programacion_item_numero_with_ot.sql
-- Enforce that programacion_lab.item_numero always matches the numeric part
-- of OT so user edits to OT keep ITEM and OT aligned.

BEGIN;

CREATE OR REPLACE FUNCTION public.ensure_programacion_lab_item_numero()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    ot_digits text;
BEGIN
    ot_digits := regexp_replace(COALESCE(NEW.ot, ''), '\D', '', 'g');

    IF ot_digits = '' THEN
        RAISE EXCEPTION 'programacion_lab.ot is required to derive item_numero';
    END IF;

    NEW.item_numero := ot_digits::integer;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_programacion_lab_item_numero ON public.programacion_lab;
CREATE TRIGGER trg_programacion_lab_item_numero
BEFORE INSERT OR UPDATE OF ot, item_numero ON public.programacion_lab
FOR EACH ROW
EXECUTE FUNCTION public.ensure_programacion_lab_item_numero();

UPDATE public.programacion_lab
SET item_numero = NULLIF(regexp_replace(COALESCE(ot, ''), '\D', '', 'g'), '')::integer
WHERE ot IS NOT NULL
  AND regexp_replace(COALESCE(ot, ''), '\D', '', 'g') <> '';

NOTIFY pgrst, 'reload schema';

COMMIT;
