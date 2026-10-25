-- Phase 2: durable, page-scoped conversation runtime.
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    sender_id TEXT NOT NULL,
    ownership TEXT NOT NULL DEFAULT 'AI'
        CHECK (ownership IN ('AI', 'HUMAN', 'PAUSED')),
    version BIGINT NOT NULL DEFAULT 0,
    batch_version BIGINT NOT NULL DEFAULT 0,
    current_workflow TEXT,
    primary_intent TEXT,
    owner_actor TEXT,
    owner_reason TEXT,
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (page_id, sender_id),
    UNIQUE (conversation_id, page_id)
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    conversation_id TEXT NOT NULL,
    provider_message_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INBOUND', 'OUTBOUND')),
    sender_role TEXT NOT NULL CHECK (sender_role IN ('CUSTOMER', 'BOT', 'HUMAN_AGENT')),
    text TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL,
    batch_version BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (page_id, provider_message_id),
    FOREIGN KEY (conversation_id, page_id)
        REFERENCES conversations(conversation_id, page_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_unbatched
    ON conversation_messages(conversation_id, id) WHERE batch_version IS NULL;

CREATE TABLE IF NOT EXISTS message_batches (
    id BIGSERIAL PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    conversation_id TEXT NOT NULL,
    batch_version BIGINT NOT NULL,
    first_at TIMESTAMPTZ NOT NULL,
    last_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'PROCESSING', 'DONE', 'CANCELLED')),
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (conversation_id, batch_version),
    FOREIGN KEY (conversation_id, page_id)
        REFERENCES conversations(conversation_id, page_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_message_batches_open_conversation
    ON message_batches(conversation_id) WHERE status = 'OPEN';
CREATE INDEX IF NOT EXISTS idx_message_batches_due
    ON message_batches(status, due_at, id);

CREATE TABLE IF NOT EXISTS conversation_slots (
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    conversation_id TEXT NOT NULL,
    workflow TEXT NOT NULL,
    slots JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, workflow),
    FOREIGN KEY (conversation_id, page_id)
        REFERENCES conversations(conversation_id, page_id)
);

CREATE TABLE IF NOT EXISTS handoff_events (
    id BIGSERIAL PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    conversation_id TEXT NOT NULL,
    from_owner TEXT NOT NULL,
    to_owner TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (conversation_id, page_id)
        REFERENCES conversations(conversation_id, page_id)
);

ALTER TABLE outbox_messages
    ADD COLUMN IF NOT EXISTS expected_conversation_version BIGINT;
ALTER TABLE outbox_messages
    ALTER COLUMN batch_version TYPE BIGINT;
CREATE INDEX IF NOT EXISTS idx_outbox_conversation_guard
    ON outbox_messages(conversation_id, batch_version, status);
