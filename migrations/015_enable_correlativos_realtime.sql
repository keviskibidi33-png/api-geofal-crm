-- 015_enable_correlativos_realtime.sql
-- Habilita Supabase Realtime para tablas de correlativos.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'public' AND tablename = 'correlativos_reserva'
    ) THEN
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE public.correlativos_reserva;
        EXCEPTION
            WHEN duplicate_object THEN
                -- ya estaba agregado
                NULL;
        END;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'public' AND tablename = 'correlativos_turnos'
    ) THEN
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE public.correlativos_turnos;
        EXCEPTION
            WHEN duplicate_object THEN
                -- ya estaba agregado
                NULL;
        END;
    END IF;
END
$$;
