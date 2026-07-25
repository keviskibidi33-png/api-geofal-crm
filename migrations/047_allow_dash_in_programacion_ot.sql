-- 047_allow_dash_in_programacion_ot.sql
-- Allow '-' or non-numeric OT entries in programacion_lab without throwing exception in trigger

BEGIN;

CREATE OR REPLACE FUNCTION public.ensure_programacion_lab_item_numero()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    matches text[];
    max_item integer;
BEGIN
    -- Extract the first contiguous sequence of digits from the OT (e.g. "1108-26" -> "1108")
    matches := regexp_match(COALESCE(NEW.ot, ''), '(\d+)');
    
    IF matches IS NOT NULL AND matches[1] <> '' THEN
        NEW.item_numero := matches[1]::integer;
    ELSE
        IF NEW.item_numero IS NULL THEN
            SELECT COALESCE(MAX(item_numero), 0) + 1 INTO max_item FROM public.programacion_lab;
            NEW.item_numero := max_item;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

NOTIFY pgrst, 'reload schema';

COMMIT;
