-- Auditable operator actions for source staging and publication lifecycle.
CREATE TABLE IF NOT EXISTS data_ingestion_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    page_id TEXT CHECK (page_id IS NULL OR page_id IN ('CFC', 'ZEO')),
    batch_id TEXT,
    source_id TEXT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_ingestion_audit_scope
    ON data_ingestion_audit(page_id, created_at DESC);
