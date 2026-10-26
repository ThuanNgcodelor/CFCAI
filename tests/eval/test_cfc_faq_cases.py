from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.build_cfc_faq_test_cases import build_case_catalog
from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    KnowledgeRecord,
)
from src.chatbot.shared.enums import PageCode

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests/fixtures/cfc_faq_cases.json"
HELDOUT_PATH = ROOT / "tests/fixtures/cfc_faq_heldout_paraphrases.json"


def _catalog() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _records(catalog: dict) -> list[KnowledgeRecord]:
    return [
        KnowledgeRecord(
            record_id=f"faq:{case['faq_id']}",
            page_id=PageCode.CFC,
            title=" | ".join(case["questions"]),
            content=case["expected_answer"],
            status="APPROVED",
            intent=case["intent"],
            category=case["category"],
            risk_level=case["risk_level"],
            source_locator=case["source_locator"],
        )
        for case in catalog["cases"]
        if case["status"] == "ANSWERABLE"
    ]


def test_cfc_faq_fixture_is_synchronized_with_markdown_source() -> None:
    assert _catalog() == build_case_catalog()


def test_cfc_faq_catalog_covers_every_source_row_and_question_variant() -> None:
    catalog = _catalog()
    summary = catalog["summary"]
    assert summary == {
        "faq_rows": 47,
        "answerable_rows": 44,
        "missing_answer_rows": 3,
        "answerable_question_variants": 119,
        "all_question_variants": 129,
    }
    assert len({case["case_id"] for case in catalog["cases"]}) == 47
    assert [case["faq_number"] for case in catalog["cases"]] == list(range(1, 48))


def test_missing_answer_cases_are_explicit_and_never_treated_as_approved_answers() -> (
    None
):
    missing = [
        case for case in _catalog()["cases"] if case["status"] == "MISSING_ANSWER"
    ]
    assert [case["faq_number"] for case in missing] == [4, 17, 19]
    assert all(case["expected_answer"] is None for case in missing)
    assert all(case["faq_id"] is None for case in missing)


@pytest.mark.skipif(
    os.getenv("RUN_CFC_FAQ_EVAL") != "1",
    reason="Set RUN_CFC_FAQ_EVAL=1 to enforce the full FAQ retrieval gate.",
)
@pytest.mark.parametrize(
    ("case_id", "question", "expected_record_id"),
    [
        (case["case_id"], question, f"faq:{case['faq_id']}")
        for case in _catalog()["cases"]
        if case["status"] == "ANSWERABLE"
        for question in case["questions"]
    ],
)
def test_every_faq_question_variant_retrieves_its_expected_answer(
    case_id: str,
    question: str,
    expected_record_id: str,
) -> None:
    store = ApprovedKnowledgeStore(_records(_catalog()))
    matches = store.search(PageCode.CFC, question, limit=1, record_prefix="faq:")
    assert matches, f"{case_id} returned no FAQ record for {question!r}"
    assert matches[0].record_id == expected_record_id
    assert matches[0].page_id == PageCode.CFC
    assert store.search(PageCode.ZEO, question, limit=1, record_prefix="faq:") == []


def test_heldout_paraphrase_retrieval_meets_quality_gate() -> None:
    catalog = _catalog()
    heldout = json.loads(HELDOUT_PATH.read_text(encoding="utf-8"))["cases"]
    record_ids = {
        case["case_id"]: f"faq:{case['faq_id']}"
        for case in catalog["cases"]
        if case["status"] == "ANSWERABLE"
    }
    store = ApprovedKnowledgeStore(_records(catalog))
    top1 = 0
    top3 = 0
    failures = []
    for case in heldout:
        expected = record_ids[case["case_id"]]
        decision = store.search_with_confidence(
            PageCode.CFC,
            case["query"],
            limit=3,
            record_prefix="faq:",
        )
        ids = [record.record_id for record in decision.records]
        top1 += bool(ids and ids[0] == expected)
        top3 += expected in ids
        if not ids or ids[0] != expected:
            failures.append((case["case_id"], case["query"], ids))
    if top1 / len(heldout) < 0.90:
        pytest.fail(json.dumps(failures, ensure_ascii=False, indent=2))
    assert top3 / len(heldout) >= 0.98, failures
