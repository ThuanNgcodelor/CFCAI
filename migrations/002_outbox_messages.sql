CREATE TABLE IF NOT EXISTS outbox_messages (
    id BIGSERIAL PRIMARY KEY,
    outbox_id TEXT UNIQUE NOT NULL,
    conversation_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    batch_version INTEGER NOT NULL,
    expected_ownership TEXT NOT NULL DEFAULT 'AI',
    created_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_messages(status, id);
