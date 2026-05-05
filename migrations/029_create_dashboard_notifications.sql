CREATE TABLE IF NOT EXISTS dashboard_notifications (
    notification_key TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ NULL,
    acknowledged_by UUID NULL,
    resolved_at TIMESTAMPTZ NULL,
    resolved_by UUID NULL,
    last_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT dashboard_notifications_status_check
        CHECK (status IN ('open', 'acknowledged', 'resolved'))
);

CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_status
    ON dashboard_notifications (status);

CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_type_status
    ON dashboard_notifications (type, status);

CREATE INDEX IF NOT EXISTS idx_dashboard_notifications_last_detected_at
    ON dashboard_notifications (last_detected_at DESC);
