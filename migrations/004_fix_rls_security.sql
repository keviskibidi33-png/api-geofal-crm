-- ============================================================
-- MIGRACIÓN: Corrección de Seguridad RLS
-- Fecha: 2026-01-24
-- Descripción: Corrige warnings de seguridad en Supabase
--   - Habilita RLS en quote_sequences
--   - Reemplaza políticas "Always True" por políticas apropiadas
--   - Corrige search_path en funciones
-- ============================================================

-- ============================================================
-- 1. HABILITAR RLS EN quote_sequences
-- ============================================================

ALTER TABLE public.quote_sequences ENABLE ROW LEVEL SECURITY;

-- Política: Solo usuarios autenticados pueden leer secuencias
CREATE POLICY "Usuarios autenticados pueden ver secuencias"
ON public.quote_sequences FOR SELECT
TO authenticated
USING (true);

-- Política: Solo el service role puede insertar/actualizar secuencias
-- (La API usa service role key para esto)
CREATE POLICY "Service role puede gestionar secuencias"
ON public.quote_sequences FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- ============================================================
-- 2. CORREGIR POLÍTICAS RLS "ALWAYS TRUE" EN auditoria
-- ============================================================

-- Eliminar políticas existentes demasiado permisivas
DROP POLICY IF EXISTS "Usuarios autenticados pueden ver auditoria" ON public.auditoria;
DROP POLICY IF EXISTS "Enable read access for all users" ON public.auditoria;
DROP POLICY IF EXISTS "Enable insert for authenticated users only" ON public.auditoria;

-- Nueva política: Solo admins pueden ver auditoría
CREATE POLICY "Admins pueden ver auditoria"
ON public.auditoria FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.vendedores 
    WHERE vendedores.id = auth.uid() 
    AND vendedores.role = 'admin'
  )
);

-- Inserts solo via service role (server actions)
CREATE POLICY "Service role puede insertar auditoria"
ON public.auditoria FOR INSERT
TO service_role
WITH CHECK (true);

-- ============================================================
-- 3. CORREGIR POLÍTICAS RLS EN clientes
-- ============================================================

-- Eliminar políticas permisivas existentes
DROP POLICY IF EXISTS "Usuarios autenticados pueden ver clientes" ON public.clientes;
DROP POLICY IF EXISTS "Usuarios autenticados pueden insertar clientes" ON public.clientes;
DROP POLICY IF EXISTS "Usuarios autenticados pueden actualizar clientes" ON public.clientes;
DROP POLICY IF EXISTS "Usuarios autenticados pueden eliminar clientes" ON public.clientes;
DROP POLICY IF EXISTS "Enable read access for all users" ON public.clientes;

-- Política de lectura: usuarios autenticados ven clientes no eliminados
CREATE POLICY "Autenticados ven clientes activos"
ON public.clientes FOR SELECT
TO authenticated
USING (deleted_at IS NULL);

-- Política de inserción: usuarios autenticados pueden crear
CREATE POLICY "Autenticados pueden crear clientes"
ON public.clientes FOR INSERT
TO authenticated
WITH CHECK (true);

-- Política de actualización: usuarios autenticados pueden actualizar
CREATE POLICY "Autenticados pueden actualizar clientes"
ON public.clientes FOR UPDATE
TO authenticated
USING (deleted_at IS NULL)
WITH CHECK (true);

-- Política de eliminación: solo admins pueden eliminar permanentemente
CREATE POLICY "Admins pueden eliminar clientes"
ON public.clientes FOR DELETE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.vendedores 
    WHERE vendedores.id = auth.uid() 
    AND vendedores.role = 'admin'
  )
);

-- ============================================================
-- 4. CORREGIR POLÍTICAS RLS EN contactos
-- ============================================================

DROP POLICY IF EXISTS "Usuarios autenticados pueden ver contactos" ON public.contactos;
DROP POLICY IF EXISTS "Usuarios autenticados pueden insertar contactos" ON public.contactos;
DROP POLICY IF EXISTS "Usuarios autenticados pueden actualizar contactos" ON public.contactos;
DROP POLICY IF EXISTS "Usuarios autenticados pueden eliminar contactos" ON public.contactos;

-- Contactos: visibles si el cliente asociado es visible
CREATE POLICY "Autenticados ven contactos de clientes activos"
ON public.contactos FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.clientes 
    WHERE clientes.id = contactos.cliente_id 
    AND clientes.deleted_at IS NULL
  )
);

CREATE POLICY "Autenticados pueden crear contactos"
ON public.contactos FOR INSERT
TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.clientes 
    WHERE clientes.id = cliente_id 
    AND clientes.deleted_at IS NULL
  )
);

CREATE POLICY "Autenticados pueden actualizar contactos"
ON public.contactos FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.clientes 
    WHERE clientes.id = contactos.cliente_id 
    AND clientes.deleted_at IS NULL
  )
);

CREATE POLICY "Autenticados pueden eliminar contactos"
ON public.contactos FOR DELETE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.clientes 
    WHERE clientes.id = contactos.cliente_id 
    AND clientes.deleted_at IS NULL
  )
);

-- ============================================================
-- 5. CORREGIR POLÍTICAS RLS EN cotizaciones
-- ============================================================

DROP POLICY IF EXISTS "Usuarios autenticados pueden ver cotizaciones" ON public.cotizaciones;
DROP POLICY IF EXISTS "Enable read access for all users" ON public.cotizaciones;

-- Solo cotizaciones visibles
CREATE POLICY "Autenticados ven cotizaciones visibles"
ON public.cotizaciones FOR SELECT
TO authenticated
USING (visibilidad = 'visible' OR visibilidad IS NULL);

CREATE POLICY "Autenticados pueden crear cotizaciones"
ON public.cotizaciones FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "Autenticados pueden actualizar cotizaciones"
ON public.cotizaciones FOR UPDATE
TO authenticated
USING (visibilidad = 'visible' OR visibilidad IS NULL);

-- Service role para operaciones de API
CREATE POLICY "Service role gestiona cotizaciones"
ON public.cotizaciones FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- ============================================================
-- 6. CORREGIR POLÍTICAS RLS EN proyectos
-- ============================================================

DROP POLICY IF EXISTS "Usuarios autenticados pueden ver proyectos" ON public.proyectos;
DROP POLICY IF EXISTS "Enable read access for all users" ON public.proyectos;

CREATE POLICY "Autenticados ven proyectos activos"
ON public.proyectos FOR SELECT
TO authenticated
USING (deleted_at IS NULL);

CREATE POLICY "Autenticados pueden crear proyectos"
ON public.proyectos FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "Autenticados pueden actualizar proyectos"
ON public.proyectos FOR UPDATE
TO authenticated
USING (deleted_at IS NULL);

CREATE POLICY "Admins pueden eliminar proyectos"
ON public.proyectos FOR DELETE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.vendedores 
    WHERE vendedores.id = auth.uid() 
    AND vendedores.role = 'admin'
  )
);

-- ============================================================
-- 7. CORREGIR FUNCIONES CON SEARCH_PATH MUTABLE
-- ============================================================

-- Función: update_client_project_count
CREATE OR REPLACE FUNCTION public.update_client_project_count()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE clientes 
    SET proyectos = COALESCE(proyectos, 0) + 1,
        updated_at = NOW()
    WHERE id = NEW.cliente_id;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE clientes 
    SET proyectos = GREATEST(COALESCE(proyectos, 0) - 1, 0),
        updated_at = NOW()
    WHERE id = OLD.cliente_id;
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;

-- Función: is_admin_user
CREATE OR REPLACE FUNCTION public.is_admin_user()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM vendedores 
    WHERE id = auth.uid() 
    AND role = 'admin'
  );
END;
$$;

-- Función: update_updated_at_column
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

-- Función: handle_new_user (sincroniza auth.users con vendedores)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.vendedores (id, email, full_name, role, created_at, updated_at)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data->>'role', 'vendor'),
    NOW(),
    NOW()
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(EXCLUDED.full_name, vendedores.full_name),
    updated_at = NOW();
  RETURN NEW;
END;
$$;

-- ============================================================
-- 8. VERIFICACIÓN
-- ============================================================

-- Mostrar tablas con RLS habilitado
DO $$
DECLARE
  r RECORD;
BEGIN
  RAISE NOTICE '=== VERIFICACIÓN RLS ===';
  FOR r IN 
    SELECT schemaname, tablename, rowsecurity 
    FROM pg_tables 
    WHERE schemaname = 'public' 
    AND tablename IN ('clientes', 'proyectos', 'cotizaciones', 'contactos', 'auditoria', 'vendedores', 'quote_sequences')
  LOOP
    RAISE NOTICE 'Tabla: % - RLS: %', r.tablename, r.rowsecurity;
  END LOOP;
END $$;

-- ============================================================
-- COMENTARIOS
-- ============================================================
-- 
-- Después de ejecutar esta migración:
-- 1. Verificar en Supabase Dashboard que los warnings desaparecieron
-- 2. Probar que el CRM sigue funcionando correctamente
-- 3. El service_role key se usa desde el backend (Server Actions y API)
-- 4. El anon key se usa desde el frontend para operaciones normales
--
-- IMPORTANTE: Si hay problemas de permisos, verificar que:
-- - El frontend usa NEXT_PUBLIC_SUPABASE_ANON_KEY
-- - Los Server Actions usan SUPABASE_SERVICE_ROLE_KEY
-- - La API usa SUPABASE_SERVICE_ROLE_KEY
-- ============================================================
