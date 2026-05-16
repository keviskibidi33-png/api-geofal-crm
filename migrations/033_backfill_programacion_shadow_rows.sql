-- Backfill and keep in sync the companion rows used by the programación grid.
-- programacion_lab is the base row; programacion_comercial and
-- programacion_administracion are the shadow rows edited by the commercial/admin views.

BEGIN;

-- Repair historical gaps: insert missing commercial rows for existing lab records.
INSERT INTO public.programacion_comercial (programacion_id, created_at, updated_at)
SELECT
    l.id,
    COALESCE(l.created_at, NOW()),
    COALESCE(l.updated_at, l.created_at, NOW())
FROM public.programacion_lab l
WHERE NOT EXISTS (
    SELECT 1
    FROM public.programacion_comercial c
    WHERE c.programacion_id = l.id
);

-- Repair historical gaps: insert missing admin rows for existing lab records.
INSERT INTO public.programacion_administracion (programacion_id, created_at, updated_at)
SELECT
    l.id,
    COALESCE(l.created_at, NOW()),
    COALESCE(l.updated_at, l.created_at, NOW())
FROM public.programacion_lab l
WHERE NOT EXISTS (
    SELECT 1
    FROM public.programacion_administracion a
    WHERE a.programacion_id = l.id
);

-- Keep future lab inserts synchronized with empty companion rows so edits work
-- immediately in the commercial/admin grids.
CREATE OR REPLACE FUNCTION public.ensure_programacion_shadow_rows()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.programacion_comercial
        WHERE programacion_id = NEW.id
    ) THEN
        INSERT INTO public.programacion_comercial (programacion_id, created_at, updated_at)
        VALUES (
            NEW.id,
            COALESCE(NEW.created_at, NOW()),
            COALESCE(NEW.updated_at, NEW.created_at, NOW())
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.programacion_administracion
        WHERE programacion_id = NEW.id
    ) THEN
        INSERT INTO public.programacion_administracion (programacion_id, created_at, updated_at)
        VALUES (
            NEW.id,
            COALESCE(NEW.created_at, NOW()),
            COALESCE(NEW.updated_at, NEW.created_at, NOW())
        );
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_programacion_lab_create_shadow_rows ON public.programacion_lab;

CREATE TRIGGER trg_programacion_lab_create_shadow_rows
AFTER INSERT ON public.programacion_lab
FOR EACH ROW
EXECUTE FUNCTION public.ensure_programacion_shadow_rows();

COMMIT;
