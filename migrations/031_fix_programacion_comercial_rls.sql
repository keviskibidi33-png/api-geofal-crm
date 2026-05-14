-- Allow current commercial roles to write the commercial programacion table.
-- The CRM now stores/uses the canonical commercial role auxiliar_comercial.

BEGIN;

CREATE OR REPLACE FUNCTION public.normalize_role_policy(role_name text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT replace(lower(coalesce(role_name, '')), ' ', '_');
$$;

ALTER TABLE public.programacion_comercial ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Permitir lectura a usuarios autorizados" ON public.programacion_comercial;
DROP POLICY IF EXISTS "Permitir escritura a roles comerciales" ON public.programacion_comercial;

CREATE POLICY "Permitir lectura a usuarios autorizados"
ON public.programacion_comercial
FOR SELECT
TO authenticated
USING (
  public.normalize_role_policy(get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial'
  )
);

CREATE POLICY "Permitir escritura a roles comerciales"
ON public.programacion_comercial
FOR ALL
TO authenticated
USING (
  public.normalize_role_policy(get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial'
  )
)
WITH CHECK (
  public.normalize_role_policy(get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial'
  )
);

COMMIT;
