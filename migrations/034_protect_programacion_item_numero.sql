-- 034_protect_programacion_item_numero.sql
-- Keep programacion_lab.item_numero server-generated and immutable so the
-- programación grid cannot create duplicated correlativos from the client.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S'
          AND n.nspname = 'public'
          AND c.relname = 'programacion_lab_item_numero_seq'
    ) THEN
        CREATE SEQUENCE public.programacion_lab_item_numero_seq
            AS integer
            INCREMENT BY 1
            MINVALUE 1
            START WITH 1
            OWNED BY public.programacion_lab.item_numero;
    END IF;
END $$;

DO $$
DECLARE
    current_max integer;
BEGIN
    SELECT COALESCE(MAX(item_numero), 0)
    INTO current_max
    FROM public.programacion_lab;

    IF current_max > 0 THEN
        PERFORM setval('public.programacion_lab_item_numero_seq', current_max, true);
    ELSE
        PERFORM setval('public.programacion_lab_item_numero_seq', 1, false);
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.ensure_programacion_lab_item_numero()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.item_numero := nextval('public.programacion_lab_item_numero_seq');
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' AND NEW.item_numero IS DISTINCT FROM OLD.item_numero THEN
        NEW.item_numero := OLD.item_numero;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_programacion_lab_item_numero ON public.programacion_lab;
CREATE TRIGGER trg_programacion_lab_item_numero
BEFORE INSERT OR UPDATE OF item_numero ON public.programacion_lab
FOR EACH ROW
EXECUTE FUNCTION public.ensure_programacion_lab_item_numero();

NOTIFY pgrst, 'reload schema';

COMMIT;
