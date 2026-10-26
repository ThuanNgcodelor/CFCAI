ALTER TABLE faq_items
    ADD COLUMN IF NOT EXISTS learning_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE faq_items
    ADD COLUMN IF NOT EXISTS profile_slots JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS intent TEXT;
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS response_mode TEXT;
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS risk_level TEXT;
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS learning_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE knowledge_records
    ADD COLUMN IF NOT EXISTS profile_slots JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_knowledge_routing
    ON knowledge_records(page_id,status,audience,is_active,intent,category);

UPDATE knowledge_records k
SET intent=f.intent,
    category=f.category,
    response_mode=f.response_mode,
    risk_level=f.risk_level,
    learning_tags=f.learning_tags,
    profile_slots=f.profile_slots
FROM faq_items f
WHERE k.record_id='faq:'||f.faq_id
  AND k.page_id=f.page_id;
