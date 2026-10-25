---
name: phase-gatekeeper
description: >-
  Inspects and verifies Phase completion against ROADMAP.md and Definition of Done (DoD).
  Use this skill whenever checking whether a development phase is completed, evaluating
  automated test gates, or preparing to transition to the next development phase.
---

# Phase Gatekeeper & Definition of Done (DoD) Skill

Use this skill to systematically enforce quality gates and verify phase transitions. **No phase is complete without passing all its acceptance criteria.**

## 1. Phase Verification Protocol

When asked: *"Làm sao để biết phase này đã xong?"* or before marking any phase `[x]` in [ROADMAP.md](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/ROADMAP.md):

1. **Step 1: Check Acceptance Criteria (DoD)**  
   Open [ROADMAP.md](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/ROADMAP.md) and cross-reference every checklist item for the target phase.
2. **Step 2: Run Automated Test Gate**  
   Execute the designated automated test command for the phase:
   - **Phase 0:** `pytest tests/unit/test_contracts.py`
   - **Phase 1:** `pytest tests/integration/test_webhook_inbox.py`
   - **Phase 2:** `pytest tests/integration/test_aggregation_handoff.py`
   - **Phase 3:** `pytest tests/integration/test_excel_importer.py`
   - **Phase 4:** `pytest tests/eval/test_qwen_understanding.py`
   - **Phase 5:** `pytest tests/integration/test_workflows.py`
   - **Phase 6:** `pytest tests/integration/test_knowledge_retrieval.py`
   - **Phase 7:** `pytest tests/integration/test_ops_controls.py`
   - **Phase 8:** `pytest tests/eval/test_regression_full.py`
3. **Step 3: Verify Zero-Regressions**  
   Verify that existing tests from previous phases have not been broken.
4. **Step 4: Sign-Off and Update Roadmap**  
   Only after Step 1, 2, and 3 pass with 0 errors:
   - Update the checkboxes in [ROADMAP.md](file:///c:/Users/David%20Nguyen/Desktop/Word/CFCAI/ROADMAP.md) to `[x]`.
   - Provide the user with a concise summary of what was delivered and what the next phase requires.

## 2. Go-Live Gate Summary (For Phase 8)

Before production auto-reply can ever be enabled:
- [ ] Signature verification & deduplication active.
- [ ] Takeover suppress logic verified under race-condition tests.
- [ ] Zero price quoted in all evaluation test runs.
- [ ] No cross-page data leakage between CFC and ZEO.
- [ ] Kill switch and Ops pause/resume functional per page.
