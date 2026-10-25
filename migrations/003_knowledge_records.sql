CREATE TABLE IF NOT EXISTS knowledge_records (
    record_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUARANTINED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_page_status ON knowledge_records(page_id, status);
