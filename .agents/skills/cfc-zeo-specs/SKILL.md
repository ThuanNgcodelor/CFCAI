---
name: cfc-zeo-specs
description: >-
  Comprehensive architectural cheat-sheet and specification guide for the CFC-ZEO AI Chatbot.
  Use this skill whenever you need to look up system boundaries, database schemas, multi-page
  isolation rules, zero-price-hallucination policies, or the message pipeline contracts.
---

# CFC–ZEO System Architecture & Specification Skill

This skill provides immediate, structured access to the core rules, boundaries, and data models of the CFC–ZEO AI Chatbot project, saving tokens and avoiding repetitive full-file parsing.

## 1. Core Architectural Invariants

- **INV-1: Zero Price Hallucination**  
  Never include price data in LLM generation prompts. All `PRICE_INQUIRY` intents trigger an immediate `HUMAN_HANDOFF` workflow. Bot confirms receipt and may ask at most one clarifying question (e.g. quantity or general area). It must never quote, estimate, or read prices from catalogs.
- **INV-2: Strict Multi-Page Isolation**  
  Two distinct pages: `CFC` (brand Cò Bay, organic fertilizer, agriculture) and `ZEO` (Zeolite, aquaculture, detergents). Every DB query, cache key, prompt, and catalog lookup MUST include `page_id`. No cross-page data leakage.
- **INV-3: Double-Check Ownership (Anti-Race Condition)**  
  Messenger Send API is only called if `ownership == 'AI'` and `batch_version` matches inside the delivery transaction. If a human agent in Meta Business Suite has taken over (`HUMAN`), pending AI messages are immediately suppressed.
- **INV-4: Durable Inbox/Outbox**  
  FastAPI Webhook writes directly to PostgreSQL `inbox_events` and dedups before returning 200 OK. Workers claim tasks using `SELECT ... FOR UPDATE SKIP LOCKED` with lease timeout. Redis is for caching and debounce schedule only.
- **INV-5: Data Staging**  
  Excel files (`docs/CfcCoBayN8n.xlsx` & `docs/ZeoN8n.xlsx`) are staging inputs. Newly imported records are `QUARANTINED`. Only `APPROVED` records are readable by the chatbot.

---

## 2. Module Boundaries (`src/chatbot/modules/`)

| Module | Core Responsibility | Forbidden Action |
|---|---|---|
| `channels` | Webhook verification (HMAC-SHA256), Meta API | Business decisions, price logic |
| `aggregation` | Debounce 5s, batch grouping, lock | Direct LLM calls |
| `conversations` | State machine, session slots, ownership | Storing raw catalog data |
| `handoff` | Human takeover detection, pause/resume | Fabricating prices |
| `orchestration` | Pipeline coordination: Intent -> Workflow -> Guard | Direct calls to Meta Send API |
| `llm` | Ollama Qwen 8B structured JSON caller | Making business authorization decisions |
| `catalog` | SKU, aliases, attributes from approved DB | Making up unlisted product specs |
| `knowledge` | FAQ, approved docs retrieval | Real-time pricing or unverified docs |
| `delivery` | Outbox worker, retry, final send guard | Changing conversation ownership |
| `integrations` | Excel reader, validator, mapper | Chat runtime logic |

---

## 3. Database Entities Summary

1. `inbox_events`: `event_id` (PK), `page_id`, `sender_id`, `raw_payload`, `status`, `received_at`.
2. `conversations`: `id` (PK), `page_id`, `customer_psid`, `ownership` (`AI` vs `HUMAN`), `batch_version`, `last_active_at`.
3. `messages`: `id` (PK), `conversation_id`, `direction` (`IN` vs `OUT`), `sender_role` (`CUSTOMER`, `BOT`, `HUMAN_AGENT`), `text`, `metadata`.
4. `catalog_items`: `id` (PK), `page_id`, `sku`, `name`, `aliases` (array), `specs` (jsonb), `status` (`QUARANTINED`, `APPROVED`).
5. `faq_items`: `id` (PK), `page_id`, `intent`, `question_examples` (jsonb), `answer`, `status`.
6. `handoff_tasks`: `id` (PK), `page_id`, `conversation_id`, `reason`, `status` (`PENDING`, `CLAIMED`, `RESOLVED`), `created_at`.
7. `outbox_messages`: `id` (PK), `conversation_id`, `page_id`, `recipient_id`, `payload`, `status` (`PENDING`, `SUPPRESSED`, `SENT`), `created_at`.

---

## 4. Key Reference Documents
- Master Architecture: [CFC_ZEO_AI_Chatbot_Architecture_v1.0.md](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/docs/CFC_ZEO_AI_Chatbot_Architecture_v1.0.md)
- Implementation Roadmap: [ROADMAP.md](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/ROADMAP.md)
- Agent Operating System: [Agent.md](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/Agent.md)
