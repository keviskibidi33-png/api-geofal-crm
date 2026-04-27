-- 022_enforce_non_empty_numero_fields.sql
-- Objetivo:
--   Evitar strings vacías ("") en columnas de texto que empiezan con numero_.
--   Permite NULL cuando la columna sea opcional, pero bloquea vacío/espacios.
--
-- Importante:
--   Primero sanea data existente para no romper al agregar constraints.

DO $$
DECLARE
    rec RECORD;
    constraint_name TEXT;
BEGIN
    -- 1) Normalizar vacíos a NULL cuando la columna sea nullable
    FOR rec IN
        SELECT c.table_schema, c.table_name, c.column_name, c.is_nullable
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.column_name LIKE 'numero\_%' ESCAPE '\'
          AND c.data_type IN ('character varying', 'text')
    LOOP
        EXECUTE format(
            'UPDATE %I.%I SET %I = NULL WHERE %I IS NOT NULL AND btrim(%I) = '''';',
            rec.table_schema, rec.table_name, rec.column_name, rec.column_name, rec.column_name
        );
    END LOOP;

    -- 2) Agregar CHECK dinámico por cada columna numero_* de texto
    FOR rec IN
        SELECT c.table_schema, c.table_name, c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.column_name LIKE 'numero\_%' ESCAPE '\'
          AND c.data_type IN ('character varying', 'text')
    LOOP
        constraint_name := format('chk_%s_%s_not_blank', rec.table_name, rec.column_name);
        constraint_name := left(constraint_name, 63);

        BEGIN
            EXECUTE format(
                'ALTER TABLE %I.%I ADD CONSTRAINT %I CHECK (%I IS NULL OR btrim(%I) <> '''');',
                rec.table_schema, rec.table_name, constraint_name, rec.column_name, rec.column_name
            );
        EXCEPTION
            WHEN duplicate_object THEN
                -- Ya existe, continuar idempotente
                NULL;
        END;
    END LOOP;
END $$;

