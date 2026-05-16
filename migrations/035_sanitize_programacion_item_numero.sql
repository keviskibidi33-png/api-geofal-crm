-- 035_sanitize_programacion_item_numero.sql
-- One-time cleanup: remove legacy duplicated/invalid item_numero values and
-- then enforce uniqueness at the database level.

BEGIN;

WITH duplicate_rows AS (
    SELECT
        id,
        item_numero,
        ROW_NUMBER() OVER (
            PARTITION BY item_numero
            ORDER BY created_at ASC NULLS LAST, id ASC
        ) AS rn
    FROM public.programacion_lab
),
to_fix AS (
    SELECT
        l.id,
        ROW_NUMBER() OVER (
            ORDER BY l.created_at ASC NULLS LAST, l.id ASC
        ) AS new_seq
    FROM public.programacion_lab l
    JOIN duplicate_rows d ON d.id = l.id
    WHERE d.rn > 1 OR l.item_numero IS NULL
),
current_max AS (
    SELECT COALESCE(MAX(item_numero), 0) AS max_item
    FROM public.programacion_lab
)
UPDATE public.programacion_lab l
SET item_numero = current_max.max_item + to_fix.new_seq
FROM to_fix, current_max
WHERE l.id = to_fix.id;

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
