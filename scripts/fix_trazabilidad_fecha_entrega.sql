-- Fix required by tracing flow in production.
-- Adds the missing column expected by the backend model.

alter table public.trazabilidad
add column if not exists fecha_entrega timestamptz null;

