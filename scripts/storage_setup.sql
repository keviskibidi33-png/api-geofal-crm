-- =========================================================
-- CONFIGURACIÓN DE STORAGE: VERIFICACION, COMPRESIONES, HUMEDAD, CBR, PROCTOR, LLP, GRAN SUELO, GRAN AGREGADO
-- =========================================================

-- 1. Asegurar que los buckets existen y son públicos
-- Postgres user (postgres) tiene permisos sobre el esquema storage
INSERT INTO storage.buckets (id, name, public)
VALUES 
  ('verificacion', 'verificacion', true),
  ('compresiones', 'compresiones', true),
  ('humedad', 'humedad', true),
  ('cbr', 'cbr', true),
  ('proctor', 'proctor', true),
  ('llp', 'llp', true),
  ('gran-suelo', 'gran-suelo', true),
  ('gran-agregado', 'gran-agregado', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- 1.1 Normalizar bucket legacy duplicado por mayúsculas/minúsculas
-- Canonico: 'proctor' (minúscula)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM storage.buckets WHERE id = 'Proctor') THEN
    IF EXISTS (SELECT 1 FROM storage.objects WHERE bucket_id = 'Proctor') THEN
      RAISE WARNING 'Bucket legacy "Proctor" contiene archivos. No se elimina automáticamente.';
    ELSE
      DELETE FROM storage.buckets WHERE id = 'Proctor';
      RAISE NOTICE 'Bucket legacy vacío "Proctor" eliminado. Se usa solo "proctor".';
    END IF;
  END IF;
END $$;

-- 2. Limpiar políticas previas para evitar duplicados
DROP POLICY IF EXISTS "Public Access Verificacion" ON storage.objects;
DROP POLICY IF EXISTS "Public Access Compresiones" ON storage.objects;
DROP POLICY IF EXISTS "Public Access Humedad" ON storage.objects;
DROP POLICY IF EXISTS "Public Access CBR" ON storage.objects;
DROP POLICY IF EXISTS "Public Access Proctor" ON storage.objects;
DROP POLICY IF EXISTS "Public Access LLP" ON storage.objects;
DROP POLICY IF EXISTS "Public Access Gran Suelo" ON storage.objects;
DROP POLICY IF EXISTS "Public Access Gran Agregado" ON storage.objects;
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

CREATE POLICY "Public Access Humedad"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'humedad')
WITH CHECK (bucket_id = 'humedad');

CREATE POLICY "Public Access CBR"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'cbr')
WITH CHECK (bucket_id = 'cbr');

CREATE POLICY "Public Access Proctor"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'proctor')
WITH CHECK (bucket_id = 'proctor');

CREATE POLICY "Public Access LLP"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'llp')
WITH CHECK (bucket_id = 'llp');

CREATE POLICY "Public Access Gran Suelo"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'gran-suelo')
WITH CHECK (bucket_id = 'gran-suelo');

CREATE POLICY "Public Access Gran Agregado"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'gran-agregado')
WITH CHECK (bucket_id = 'gran-agregado');

-- Reforzar Recepciones si es necesario
DROP POLICY IF EXISTS "Public Access Recepciones" ON storage.objects;
CREATE POLICY "Public Access Recepciones"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'recepciones')
WITH CHECK (bucket_id = 'recepciones');
