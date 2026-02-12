-- =========================================================
-- CONFIGURACIÓN DE STORAGE: VERIFICACION Y COMPRESIONES
-- =========================================================

-- 1. Asegurar que los buckets existen y son públicos
-- Postgres user (postgres) tiene permisos sobre el esquema storage
INSERT INTO storage.buckets (id, name, public)
VALUES 
  ('verificacion', 'verificacion', true),
  ('compresiones', 'compresiones', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- 2. Limpiar políticas previas para evitar duplicados
DROP POLICY IF EXISTS "Public Access Verificacion" ON storage.objects;
DROP POLICY IF EXISTS "Public Access Compresiones" ON storage.objects;
DROP POLICY IF EXISTS "All Access Recepciones" ON storage.objects;

-- 3. Aplicar política "ALL" para acceso público (lectura y escritura)
-- Basado en la configuración de 'recepciones' solicitada por el usuario
CREATE POLICY "Public Access Verificacion"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'verificacion')
WITH CHECK (bucket_id = 'verificacion');

CREATE POLICY "Public Access Compresiones"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'compresiones')
WITH CHECK (bucket_id = 'compresiones');

-- Reforzar Recepciones si es necesario
DROP POLICY IF EXISTS "Public Access Recepciones" ON storage.objects;
CREATE POLICY "Public Access Recepciones"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'recepciones')
WITH CHECK (bucket_id = 'recepciones');
