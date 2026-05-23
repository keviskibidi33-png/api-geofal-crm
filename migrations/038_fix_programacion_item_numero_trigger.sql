-- 038_fix_programacion_item_numero_trigger.sql
-- Fix the trigger on programacion_lab so item_numero only extracts the first contiguous sequence
-- of digits (the OT number) from the ot column, instead of stripping all non-digits (which appends the year suffix like -26).

BEGIN;

-- 1. Update the trigger function to extract only the first group of digits from NEW.ot
CREATE OR REPLACE FUNCTION public.ensure_programacion_lab_item_numero()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    ot_digits text;
    matches text[];
BEGIN
    -- Extract the first contiguous sequence of digits from the OT (e.g. "1108-26" -> "1108")
    matches := regexp_match(COALESCE(NEW.ot, ''), '(\d+)');
    
    IF matches IS NULL OR matches[1] = '' THEN
        RAISE EXCEPTION 'programacion_lab.ot is required to derive item_numero';
    END IF;

    ot_digits := matches[1];
    NEW.item_numero := ot_digits::integer;
    RETURN NEW;
END;
$$;

-- 2. Temporarily drop the trigger to update existing records without trigger interference
DROP TRIGGER IF EXISTS trg_programacion_lab_item_numero ON public.programacion_lab;

-- 3. Fix the existing records where item_numero got the year suffix (e.g. 109726 -> 1097)
UPDATE public.programacion_lab
SET item_numero = (regexp_match(COALESCE(ot, ''), '(\d+)'))[1]::integer
WHERE ot IS NOT NULL
  AND (regexp_match(COALESCE(ot, ''), '(\d+)'))[1] IS NOT NULL
  AND item_numero IS DISTINCT FROM (regexp_match(COALESCE(ot, ''), '(\d+)'))[1]::integer;

-- 4. Re-create the trigger to protect future inserts and updates
CREATE TRIGGER trg_programacion_lab_item_numero
BEFORE INSERT OR UPDATE OF ot, item_numero ON public.programacion_lab
FOR EACH ROW
EXECUTE FUNCTION public.ensure_programacion_lab_item_numero();

NOTIFY pgrst, 'reload schema';

COMMIT;
