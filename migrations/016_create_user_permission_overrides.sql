CREATE TABLE IF NOT EXISTS public.user_permission_overrides (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    permissions JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_user_permission_overrides_user
        FOREIGN KEY (user_id) REFERENCES public.perfiles(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_user_permission_overrides_user_id
    ON public.user_permission_overrides(user_id);

CREATE INDEX IF NOT EXISTS ix_user_permission_overrides_enabled
    ON public.user_permission_overrides(enabled);
