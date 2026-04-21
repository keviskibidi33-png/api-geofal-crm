CREATE TABLE IF NOT EXISTS public.correlativos_reserva (
    id SERIAL PRIMARY KEY,
    numero INTEGER NOT NULL,
    user_id VARCHAR(80) NOT NULL,
    fecha TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    documento_referencia VARCHAR(255) NOT NULL,
    proposito TEXT,
    CONSTRAINT uq_correlativos_reserva_numero UNIQUE (numero)
);

CREATE INDEX IF NOT EXISTS ix_correlativos_reserva_numero ON public.correlativos_reserva (numero);
CREATE INDEX IF NOT EXISTS ix_correlativos_reserva_user_id ON public.correlativos_reserva (user_id);
CREATE INDEX IF NOT EXISTS ix_correlativos_reserva_fecha ON public.correlativos_reserva (fecha DESC);

CREATE TABLE IF NOT EXISTS public.correlativos_turnos (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(80) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'waiting',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_correlativos_turnos_user_id UNIQUE (user_id),
    CONSTRAINT chk_correlativos_turnos_estado CHECK (estado IN ('active', 'waiting'))
);

CREATE INDEX IF NOT EXISTS ix_correlativos_turnos_estado ON public.correlativos_turnos (estado);
CREATE INDEX IF NOT EXISTS ix_correlativos_turnos_joined_at ON public.correlativos_turnos (joined_at);
CREATE INDEX IF NOT EXISTS ix_correlativos_turnos_last_seen_at ON public.correlativos_turnos (last_seen_at);
