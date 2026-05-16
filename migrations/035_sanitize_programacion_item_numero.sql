-- 035_sanitize_programacion_item_numero.sql
-- One-time cleanup: renumber the full programacion_lab.item_numero sequence
-- starting at 209, preserving the current relative order, then enforce
-- uniqueness at the database level.

BEGIN;

DROP TRIGGER IF EXISTS trg_programacion_lab_item_numero ON public.programacion_lab;

WITH ordered_rows AS (
    SELECT
        l.id,
        208 + ROW_NUMBER() OVER (
            ORDER BY COALESCE(l.item_numero, 999999999) ASC,
                     COALESCE(l.created_at, 'epoch'::timestamptz) ASC,
                     l.id ASC
        ) AS new_item_numero
    FROM public.programacion_lab l
)
UPDATE public.programacion_lab l
SET item_numero = ordered_rows.new_item_numero
FROM ordered_rows
WHERE l.id = ordered_rows.id;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND t.relname = 'programacion_lab'
          AND c.conname = 'uq_programacion_lab_item_numero'
    ) THEN
        ALTER TABLE public.programacion_lab
            ADD CONSTRAINT uq_programacion_lab_item_numero UNIQUE (item_numero);
    END IF;
END $$;

CREATE TRIGGER trg_programacion_lab_item_numero
BEFORE INSERT OR UPDATE OF item_numero ON public.programacion_lab
FOR EACH ROW
EXECUTE FUNCTION public.ensure_programacion_lab_item_numero();

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

NOTIFY pgrst, 'reload schema';

COMMIT;
