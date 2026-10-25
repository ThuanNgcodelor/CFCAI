-- Phase 3: versioned staging, approval and atomic publication.
CREATE TABLE IF NOT EXISTS import_batches (
    batch_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    source_file TEXT NOT NULL,
    source_checksum TEXT NOT NULL,
    mapping_version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUARANTINED'
        CHECK (status IN ('QUARANTINED','APPROVED','PUBLISHED','REJECTED','CONFLICT')),
    record_count INTEGER NOT NULL DEFAULT 0,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    UNIQUE (page_id, source_checksum, mapping_version)
);

CREATE TABLE IF NOT EXISTS faq_items (
    faq_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    import_batch_id TEXT NOT NULL REFERENCES import_batches(batch_id),
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    intent TEXT NOT NULL,
    category TEXT,
    question_examples JSONB NOT NULL DEFAULT '[]'::jsonb,
    answer TEXT NOT NULL,
    audience TEXT NOT NULL DEFAULT 'customer',
    response_mode TEXT,
    risk_level TEXT,
    source_active BOOLEAN NOT NULL DEFAULT true,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUARANTINED'
        CHECK (status IN ('QUARANTINED','APPROVED','REJECTED','CONFLICT')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (import_batch_id, source_sheet, source_row)
);

CREATE TABLE IF NOT EXISTS catalog_items (
    catalog_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    import_batch_id TEXT NOT NULL REFERENCES import_batches(batch_id),
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    specs JSONB NOT NULL DEFAULT '{}'::jsonb,
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    internal_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_active BOOLEAN NOT NULL DEFAULT true,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUARANTINED'
        CHECK (status IN ('QUARANTINED','APPROVED','REJECTED','CONFLICT')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (import_batch_id, source_sheet, source_row)
);

CREATE INDEX IF NOT EXISTS idx_faq_items_scope
    ON faq_items(page_id,status,audience,source_active);
CREATE INDEX IF NOT EXISTS idx_catalog_items_scope
    ON catalog_items(page_id,status,source_active,sku);

CREATE TABLE IF NOT EXISTS catalog_publications (
    publication_id BIGSERIAL PRIMARY KEY,
    page_id TEXT NOT NULL CHECK (page_id IN ('CFC', 'ZEO')),
    version INTEGER NOT NULL,
    import_batch_id TEXT NOT NULL REFERENCES import_batches(batch_id),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','INACTIVE','ROLLED_BACK')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (page_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_publication_active
    ON catalog_publications(page_id) WHERE status='ACTIVE';

ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS source_batch_id TEXT;
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS audience TEXT NOT NULL DEFAULT 'customer';
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS source_locator TEXT;
CREATE INDEX IF NOT EXISTS idx_knowledge_runtime_scope
    ON knowledge_records(page_id,status,audience,is_active);
