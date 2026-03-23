-- Buckets and storage policies for the new aggregate/soil iframe forms.
-- Run in Supabase SQL editor with postgres/service role privileges.

insert into storage.buckets (id, name, public)
values
  ('cont-mat-organica', 'cont-mat-organica', true),
  ('terrones-fino-grueso', 'terrones-fino-grueso', true),
  ('azul-metileno', 'azul-metileno', true),
  ('part-livianas', 'part-livianas', true),
  ('imp-organicas', 'imp-organicas', true),
  ('sul-magnesio', 'sul-magnesio', true),
  ('angularidad', 'angularidad', true)
on conflict (id) do update
  set name = excluded.name,
      public = excluded.public;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Public Access Contenido Materia Organica'
  ) THEN
    CREATE POLICY "Public Access Contenido Materia Organica" ON storage.objects
      FOR ALL TO public
      USING (bucket_id = 'cont-mat-organica')
      WITH CHECK (bucket_id = 'cont-mat-organica');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Public Access Terrones Fino Grueso'
  ) THEN
    CREATE POLICY "Public Access Terrones Fino Grueso" ON storage.objects
      FOR ALL TO public
      USING (bucket_id = 'terrones-fino-grueso')
      WITH CHECK (bucket_id = 'terrones-fino-grueso');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Public Access Azul Metileno'
  ) THEN
    CREATE POLICY "Public Access Azul Metileno" ON storage.objects
      FOR ALL TO public
      USING (bucket_id = 'azul-metileno')
      WITH CHECK (bucket_id = 'azul-metileno');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Public Access Particulas Livianas'
  ) THEN
    CREATE POLICY "Public Access Particulas Livianas" ON storage.objects
      FOR ALL TO public
      USING (bucket_id = 'part-livianas')
      WITH CHECK (bucket_id = 'part-livianas');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Public Access Impurezas Organicas'
  ) THEN
    CREATE POLICY "Public Access Impurezas Organicas" ON storage.objects
      FOR ALL TO public
      USING (bucket_id = 'imp-organicas')
      WITH CHECK (bucket_id = 'imp-organicas');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Public Access Sulfato Magnesio'
  ) THEN
    CREATE POLICY "Public Access Sulfato Magnesio" ON storage.objects
      FOR ALL TO public
      USING (bucket_id = 'sul-magnesio')
      WITH CHECK (bucket_id = 'sul-magnesio');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Public Access Angularidad'
  ) THEN
    CREATE POLICY "Public Access Angularidad" ON storage.objects
      FOR ALL TO public
      USING (bucket_id = 'angularidad')
      WITH CHECK (bucket_id = 'angularidad');
  END IF;
END $$;

update role_definitions
set permissions = coalesce(permissions, '{}'::jsonb) || jsonb_build_object(
  'cont_mat_organica', jsonb_build_object('read', true, 'write', true, 'delete', true),
  'terrones_fino_grueso', jsonb_build_object('read', true, 'write', true, 'delete', true),
  'azul_metileno', jsonb_build_object('read', true, 'write', true, 'delete', true),
  'part_livianas', jsonb_build_object('read', true, 'write', true, 'delete', true),
  'imp_organicas', jsonb_build_object('read', true, 'write', true, 'delete', true),
  'sul_magnesio', jsonb_build_object('read', true, 'write', true, 'delete', true),
  'angularidad', jsonb_build_object('read', true, 'write', true, 'delete', true)
)
where role_id = 'admin';

update role_definitions
set permissions = coalesce(permissions, '{}'::jsonb) || jsonb_build_object(
  'cont_mat_organica', jsonb_build_object('read', true, 'write', true, 'delete', false),
  'terrones_fino_grueso', jsonb_build_object('read', true, 'write', true, 'delete', false),
  'azul_metileno', jsonb_build_object('read', true, 'write', true, 'delete', false),
  'part_livianas', jsonb_build_object('read', true, 'write', true, 'delete', false),
  'imp_organicas', jsonb_build_object('read', true, 'write', true, 'delete', false),
  'sul_magnesio', jsonb_build_object('read', true, 'write', true, 'delete', false),
  'angularidad', jsonb_build_object('read', true, 'write', true, 'delete', false)
)
where role_id in ('laboratorio', 'tecnico_suelos');
