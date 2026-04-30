CREATE TABLE IF NOT EXISTS public.control_informes_turnos (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(80) NOT NULL,
    user_name VARCHAR(140),
    estado VARCHAR(20) NOT NULL DEFAULT 'waiting',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NULL,
    CONSTRAINT uq_control_informes_turnos_user_id UNIQUE (user_id),
    CONSTRAINT chk_control_informes_turnos_estado CHECK (estado IN ('active', 'waiting'))
);

CREATE INDEX IF NOT EXISTS ix_control_informes_turnos_estado ON public.control_informes_turnos (estado);
CREATE INDEX IF NOT EXISTS ix_control_informes_turnos_joined_at ON public.control_informes_turnos (joined_at);
CREATE INDEX IF NOT EXISTS ix_control_informes_turnos_activated_at ON public.control_informes_turnos (activated_at);
CREATE INDEX IF NOT EXISTS ix_control_informes_turnos_expires_at ON public.control_informes_turnos (expires_at);
