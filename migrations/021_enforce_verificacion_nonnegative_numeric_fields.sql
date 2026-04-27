-- Sanea datos legacy inválidos y endurece la integridad de verificación.
-- Objetivo: impedir valores negativos en campos numéricos de muestras_verificadas
-- para que un registro corrupto no vuelva a romper el módulo completo.

BEGIN;

UPDATE public.muestras_verificadas
SET
    diametro_1_mm = CASE WHEN diametro_1_mm < 0 THEN NULL ELSE diametro_1_mm END,
    diametro_2_mm = CASE WHEN diametro_2_mm < 0 THEN NULL ELSE diametro_2_mm END,
    tolerancia_porcentaje = CASE WHEN tolerancia_porcentaje < 0 THEN NULL ELSE tolerancia_porcentaje END,
    longitud_1_mm = CASE WHEN longitud_1_mm < 0 THEN NULL ELSE longitud_1_mm END,
    longitud_2_mm = CASE WHEN longitud_2_mm < 0 THEN NULL ELSE longitud_2_mm END,
    longitud_3_mm = CASE WHEN longitud_3_mm < 0 THEN NULL ELSE longitud_3_mm END,
    masa_muestra_aire_g = CASE WHEN masa_muestra_aire_g < 0 THEN NULL ELSE masa_muestra_aire_g END
WHERE
    diametro_1_mm < 0
    OR diametro_2_mm < 0
    OR tolerancia_porcentaje < 0
    OR longitud_1_mm < 0
    OR longitud_2_mm < 0
    OR longitud_3_mm < 0
    OR masa_muestra_aire_g < 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_muestras_verificadas_diametro_1_mm_nonnegative'
    ) THEN
        ALTER TABLE public.muestras_verificadas
            ADD CONSTRAINT chk_muestras_verificadas_diametro_1_mm_nonnegative
            CHECK (diametro_1_mm IS NULL OR diametro_1_mm >= 0) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_muestras_verificadas_diametro_2_mm_nonnegative'
    ) THEN
        ALTER TABLE public.muestras_verificadas
            ADD CONSTRAINT chk_muestras_verificadas_diametro_2_mm_nonnegative
            CHECK (diametro_2_mm IS NULL OR diametro_2_mm >= 0) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_muestras_verificadas_tolerancia_porcentaje_nonnegative'
    ) THEN
        ALTER TABLE public.muestras_verificadas
            ADD CONSTRAINT chk_muestras_verificadas_tolerancia_porcentaje_nonnegative
            CHECK (tolerancia_porcentaje IS NULL OR tolerancia_porcentaje >= 0) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_muestras_verificadas_longitud_1_mm_nonnegative'
    ) THEN
        ALTER TABLE public.muestras_verificadas
            ADD CONSTRAINT chk_muestras_verificadas_longitud_1_mm_nonnegative
            CHECK (longitud_1_mm IS NULL OR longitud_1_mm >= 0) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_muestras_verificadas_longitud_2_mm_nonnegative'
    ) THEN
        ALTER TABLE public.muestras_verificadas
            ADD CONSTRAINT chk_muestras_verificadas_longitud_2_mm_nonnegative
            CHECK (longitud_2_mm IS NULL OR longitud_2_mm >= 0) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_muestras_verificadas_longitud_3_mm_nonnegative'
    ) THEN
        ALTER TABLE public.muestras_verificadas
            ADD CONSTRAINT chk_muestras_verificadas_longitud_3_mm_nonnegative
            CHECK (longitud_3_mm IS NULL OR longitud_3_mm >= 0) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_muestras_verificadas_masa_muestra_aire_g_nonnegative'
    ) THEN
        ALTER TABLE public.muestras_verificadas
            ADD CONSTRAINT chk_muestras_verificadas_masa_muestra_aire_g_nonnegative
            CHECK (masa_muestra_aire_g IS NULL OR masa_muestra_aire_g >= 0) NOT VALID;
    END IF;
END
$$;

ALTER TABLE public.muestras_verificadas VALIDATE CONSTRAINT chk_muestras_verificadas_diametro_1_mm_nonnegative;
ALTER TABLE public.muestras_verificadas VALIDATE CONSTRAINT chk_muestras_verificadas_diametro_2_mm_nonnegative;
ALTER TABLE public.muestras_verificadas VALIDATE CONSTRAINT chk_muestras_verificadas_tolerancia_porcentaje_nonnegative;
ALTER TABLE public.muestras_verificadas VALIDATE CONSTRAINT chk_muestras_verificadas_longitud_1_mm_nonnegative;
ALTER TABLE public.muestras_verificadas VALIDATE CONSTRAINT chk_muestras_verificadas_longitud_2_mm_nonnegative;
ALTER TABLE public.muestras_verificadas VALIDATE CONSTRAINT chk_muestras_verificadas_longitud_3_mm_nonnegative;
ALTER TABLE public.muestras_verificadas VALIDATE CONSTRAINT chk_muestras_verificadas_masa_muestra_aire_g_nonnegative;

COMMIT;
