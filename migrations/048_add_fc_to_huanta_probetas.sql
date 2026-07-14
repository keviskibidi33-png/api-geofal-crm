-- Migration 048: Add f_c column to huanta_probetas

ALTER TABLE public.huanta_probetas ADD COLUMN IF NOT EXISTS f_c VARCHAR(50) NOT NULL DEFAULT '-';

NOTIFY pgrst, 'reload schema';
