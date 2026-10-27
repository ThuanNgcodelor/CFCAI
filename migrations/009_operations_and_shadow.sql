-- Phase F7/F8: auditable operational controls and non-delivery shadow review.
-- This migration intentionally does not store customer text in the audit log.

ALTER TABLE handoff_tasks
    ADD COLUMN IF NOT EXISTS claimed_by TEXT;
ALTER TABLE handoff_tasks
    ADD COLUMN IF NOT EXISTS resolved_by TEXT;
ALTER TABLE handoff_tasks
    ADD COLUMN IF NOT EXISTS resolution TEXT;

CREATE TABLE IF NOT EXISTS ops_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    page_id TEXT CHECK (page_id IS NULL OR page_id IN ('CFC', 'ZEO')),
    conversation_id TEXT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ops_audit_scope
    ON ops_audit_log(page_id, conversation_id, created_at DESC);

-- The review row identifies a shadowed response without duplicating its body,
-- recipient identifier, or raw customer slots.  The authorized review endpoint
-- joins it back to the durable outbox only when explicitly requested.
CREATE TABLE IF NOT EXISTS delivery_shadow_reviews (
    review_id BIGSERIAL PRIMARY KEY,
    outbox_id TEXT NOT NULL UNIQUE,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    conversation_id TEXT NOT NULL,
    recipient_digest TEXT NOT NULL,
    response_digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_delivery_shadow_reviews_scope
    ON delivery_shadow_reviews(page_id, created_at DESC);

ALTER TABLE outbox_messages
    ADD COLUMN IF NOT EXISTS failure_code TEXT;
