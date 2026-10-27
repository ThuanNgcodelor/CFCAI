"""Deterministic contract tests for the Phase F6 evaluator itself."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_cfc_faq import evaluate
from src.chatbot.modules.orchestration.input_analyzer import VietnameseNormalizer
from src.chatbot.shared.enums import IntentType
from src.chatbot.shared.events import IntentAnalysisResult

ROOT = Path(__file__).resolve().parents[2]


class CatalogIntentClient:
    def __init__(self, catalog: dict) -> None:
        normalizer = VietnameseNormalizer(
            ROOT / "config/normalization/vi_intent.json",
            ROOT / "config/normalization/administrative_areas.json",
        )
        self.intents = {
            normalizer.normalize(question): case["intent"]
            for case in catalog["cases"]
            for question in case["questions"]
        }

    def analyze(self, page_id: str, text: str, context=None):
        return IntentAnalysisResult(
            primary_intent=IntentType(self.intents[text]), confidence=0.99
        )


def test_f6_evaluator_runs_all_variants_and_gates_only_approved_sources() -> None:
    catalog = json.loads(
        (ROOT / "tests/fixtures/cfc_faq_cases.json").read_text(encoding="utf-8")
    )
    heldout = json.loads(
        (ROOT / "tests/fixtures/cfc_faq_heldout_paraphrases.json").read_text(
            encoding="utf-8"
        )
    )
    baseline = json.loads(
        (ROOT / "tests/fixtures/cfc_faq_f6_baseline.json").read_text(encoding="utf-8")
    )
    report = evaluate(
        catalog,
        heldout=heldout,
        baseline=baseline,
        live=True,
        check_production=False,
        runtime_client=CatalogIntentClient(catalog),
    )

    assert report["retrieval_summary"]["top1_pass"] == 119
    assert report["heldout_summary"]["top1_pass"] == 28
    assert report["runtime_summary"]["total_variants"] == 119
    assert report["runtime_summary"]["active_total"] == 26
    assert report["runtime_summary"]["active_pass"] == 26
    assert report["runtime_summary"]["output_policy_violations"] == 0
    assert report["gate"] == {"status": "PASS", "failures": []}
    assert all(
        item["verdict"] == "NOT_GATED"
        for item in report["runtime_results"]
        if not item["source_active"]
    )
