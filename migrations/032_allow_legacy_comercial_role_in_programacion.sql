-- Backward compatibility for legacy users stored as `comercial`.
-- The CRM canonical role is `auxiliar_comercial`, but some profiles may still
-- carry the legacy literal `comercial`. Keep the RLS policy aligned so those
-- users can still read/write the commercial programacion table.

BEGIN;

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
    'auxiliar_comercial',
    'comercial'
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
    'auxiliar_comercial',
    'comercial'
  )
)
WITH CHECK (
  public.normalize_role_policy(get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial',
    'comercial'
  )
);

COMMIT;
