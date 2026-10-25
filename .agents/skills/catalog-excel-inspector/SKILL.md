---
name: catalog-excel-inspector
description: >-
  Inspects, validates, and extracts schemas and records from source Excel files
  (CfcCoBayN8n.xlsx and ZeoN8n.xlsx) in docs/. Use this skill when working on
  Phase 3 data imports, catalog mapping, FAQ extraction, or verifying SKU formats.
---

# Catalog & Excel Inspector Skill

This skill documents the structure, column mappings, and validation procedures for the Excel staging files located in [docs/](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/docs).

## 1. Source Files Overview

### `docs/CfcCoBayN8n.xlsx` (Page: CFC / Brand: Cò Bay)
- **Sheet `FAQ`:**
  - Columns: `active`, `brand`, `category`, `intent`, `question_examples`, `answer`, `priority`, `source_id`, `updated_at`, `audience`, `answer_mode`, `risk_level`, `learning_tags`, `profile_slots`, `escalation_policy`
  - Mapping: Imports directly to `faq_items` table with `page_id='CFC'`.
- **Sheet `KnowledgeSnapshot`:**
  - Columns: `snapshot_key`, `brand_scope`, `knowledge_count`, `updated_at`, `snapshot_json`
- **Sheet `LearningQueue`:**
  - Columns: `event_id`, `status`, `channel`, `sender_id`, `message_id`, `user_message`, `fallback_reason`, `rag_score`, `created_at`, `admin_answer`, `question_examples`, `intent`, `category`, `brand`, `priority`

### `docs/ZeoN8n.xlsx` (Page: ZEO / Brand: Zeolite)
- **Sheet `FAQ`:** Same schema as CFC FAQ, mapped to `page_id='ZEO'`.
- **Sheet `Shopee`, `Web`, `Lazada` (Product Catalog):**
  - Key Columns: `active`, `item_id`, `name`, `brand`, `category`, `price`, `specs`, `keywords`, `variants`, `in_stock`, `updated_at`
  - Mapping: Imports into `catalog_items` table with `page_id='ZEO'`.

## 2. Ingestion & Validation Rules

1. **Staging Rule:**
   - Any record imported from Excel has `status = 'QUARANTINED'` by default.
   - Only records reviewed and approved have `status = 'APPROVED'`.
2. **Never Quote Price from Catalog:**
   - Even though sheets `Shopee`, `Web`, `Lazada` contain a `price` column, this column is for internal reference/admin only. **It MUST be omitted from LLM prompt contexts.**
3. **Conflict Detection (Case T11):**
   - If two rows have the same SKU with conflicting specs or names, the import worker must flag a `CONFLICT_ERROR` and keep both quarantined instead of picking one automatically.
