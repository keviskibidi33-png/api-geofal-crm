-- 035_sanitize_programacion_item_numero.sql
-- One-time cleanup: renumber programacion_lab.item_numero sequentially and
-- then enforce uniqueness at the database level.

BEGIN;

WITH ordered_rows AS (
    SELECT
        l.id,
        ROW_NUMBER() OVER (
            ORDER BY COALESCE(l.created_at, 'epoch'::timestamptz) ASC, l.id ASC
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
