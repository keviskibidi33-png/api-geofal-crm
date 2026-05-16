-- 035_sanitize_programacion_item_numero.sql
-- One-time cleanup: remove legacy duplicated/invalid item_numero values and
-- then enforce uniqueness at the database level.

BEGIN;

WITH duplicate_keys AS (
    SELECT item_numero
    FROM public.programacion_lab
    WHERE item_numero IS NOT NULL
    GROUP BY item_numero
    HAVING COUNT(*) > 1
),
rows_to_renumber AS (
    SELECT
        l.id,
        ROW_NUMBER() OVER (
            ORDER BY COALESCE(l.created_at, 'epoch'::timestamptz) ASC, l.id ASC
        ) AS new_seq
    FROM public.programacion_lab l
    WHERE l.item_numero IS NULL
       OR l.item_numero IN (SELECT dk.item_numero FROM duplicate_keys dk)
),
current_max AS (
    SELECT COALESCE(MAX(item_numero), 0) AS max_item
    FROM public.programacion_lab
)
UPDATE public.programacion_lab l
SET item_numero = current_max.max_item + rows_to_renumber.new_seq
FROM rows_to_renumber, current_max
WHERE l.id = rows_to_renumber.id;

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
