-- 035_sanitize_programacion_item_numero.sql
-- One-time cleanup: only renumber duplicated programacion_lab.item_numero
-- values while preserving valid existing correlatives such as ITEM 22, then
-- enforce uniqueness at the database level.

BEGIN;

DROP TRIGGER IF EXISTS trg_programacion_lab_item_numero ON public.programacion_lab;

WITH duplicate_groups AS (
    SELECT item_numero
    FROM public.programacion_lab
    WHERE item_numero IS NOT NULL
    GROUP BY item_numero
    HAVING COUNT(*) > 1
),
duplicate_rows AS (
    SELECT
        l.id,
        l.item_numero,
        ROW_NUMBER() OVER (
            PARTITION BY l.item_numero
            ORDER BY COALESCE(l.created_at, 'epoch'::timestamptz) ASC, l.id ASC
        ) AS rn
    FROM public.programacion_lab l
    INNER JOIN duplicate_groups d
        ON d.item_numero = l.item_numero
),
max_current AS (
    SELECT COALESCE(MAX(item_numero), 0) AS current_max
    FROM public.programacion_lab
),
reassigned AS (
    SELECT
        dr.id,
        mc.current_max + ROW_NUMBER() OVER (
            ORDER BY dr.item_numero ASC, dr.rn ASC, dr.id ASC
        ) AS new_item_numero
    FROM duplicate_rows dr
    CROSS JOIN max_current mc
    WHERE dr.rn > 1
)
UPDATE public.programacion_lab l
SET item_numero = reassigned.new_item_numero
FROM reassigned
WHERE l.id = reassigned.id;

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
