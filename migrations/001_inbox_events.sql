-- Phase 1 durable inbox baseline. Apply with the project's migration runner.
CREATE TABLE IF NOT EXISTS inbox_events (
    id BIGSERIAL PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    event_key TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    leased_until TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (page_id, event_key)
);

CREATE INDEX IF NOT EXISTS idx_inbox_events_page_received
    ON inbox_events (page_id, received_at);
CREATE INDEX IF NOT EXISTS idx_inbox_events_pending
    ON inbox_events (status, leased_until, id);
