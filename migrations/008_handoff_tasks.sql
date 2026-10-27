-- Phase F5: durable, auditable handoff requests created by business workflows.
CREATE TABLE IF NOT EXISTS handoff_tasks (
    task_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    conversation_id TEXT NOT NULL,
    batch_version BIGINT NOT NULL,
    workflow TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'CLAIMED', 'RESOLVED', 'EXPIRED')),
    slots JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    UNIQUE (conversation_id, batch_version, workflow),
    FOREIGN KEY (conversation_id, page_id)
        REFERENCES conversations(conversation_id, page_id)
);

CREATE INDEX IF NOT EXISTS idx_handoff_tasks_pending
    ON handoff_tasks(page_id, status, created_at);
