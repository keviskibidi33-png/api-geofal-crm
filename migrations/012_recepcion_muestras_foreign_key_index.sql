-- Accelerates lookups and joins by recepcion_id in recepcion workflows.
CREATE INDEX IF NOT EXISTS ix_muestras_concreto_recepcion_id
    ON public.muestras_concreto (recepcion_id);

