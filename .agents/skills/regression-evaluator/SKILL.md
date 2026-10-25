---
name: regression-evaluator
description: >-
  Runs and evaluates the 12 core regression test cases (T01 through T12) based on
  real-world chat screenshots. Use this skill to verify zero-price hallucination,
  message aggregation debounce, ownership takeover race conditions, and cross-page isolation.
---

# 12 Core Regression Test Evaluator Skill

This skill provides guidelines and validation criteria for the 12 essential regression scenarios defined in Section 18 of [CFC_ZEO_AI_Chatbot_Architecture_v1.0.md](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/docs/CFC_ZEO_AI_Chatbot_Architecture_v1.0.md).

## Test Cases Matrix

| Case ID | Input Scenario | Expected System Behavior | Invariant Tested |
|---|---|---|---|
| **T01** | “HC vs 25kg 30% nhiều tấn” | Detect buying/quote intent, clarify SKU/quantity if needed, trigger human sales handoff; do NOT ask crop type first. | INV-1 (No price) |
| **T02** | “Rải mít” following price chat | If customer was inquiring price, do not automatically switch to usage advice unless explicitly asking how to apply. | State Machine |
| **T03** | “Mình chỉ hỏi giá Cobanic 30 giá 1 tấn bao nhiêu” | Intent: `PRICE_INQUIRY`, quantity: 1 ton, human handoff; NEVER invent or quote price. | INV-1 (No price) |
| **T04** | “Tôi muốn tìm đại lý gần nhất” | Ask for brief region/district; do NOT force providing phone number upfront. | Policy Router |
| **T05** | “xin giá” | If SKU in context, retain it; otherwise ask which product; do NOT dump long catalog. | Context Builder |
| **T06** | “Tôi muốn tìm mua Hữu cơ Cobanic 21” | Resolve product SKU or clarify version; ask buying area; do NOT list unrelated lines. | Catalog Resolver |
| **T07** | 4 messages sent within 6 seconds | Grouped into 1 message batch; exactly 1 intent evaluation. | Aggregator (5s debounce) |
| **T08** | Admin takeover while Qwen is thinking | Pending AI message is marked `SUPPRESSED` and NEVER sent out. | INV-3 (Ownership Guard) |
| **T09** | Meta retries identical event | Deduplicated via `event_id`/`mid`; processed exactly once. | Idempotency |
| **T10** | CFC customer asks for ZEO SKU | Zero leakage of ZEO data; clarify or redirect per policy. | INV-2 (Page Isolation) |
| **T11** | Excel import has duplicate/conflicting SKUs | Import flags validation conflict; does not guess or pick arbitrarily. | INV-5 (Data Staging) |
| **T12** | Ollama LLM timeout | Fallback to brief polite response or transfer to agent; no infinite retry loops. | Fail-closed |

## Automated Test Command

To run the regression suite:
```bash
pytest tests/eval/test_regression_full.py -v
```
All 12 cases MUST pass 100% before Phase 8 sign-off.
