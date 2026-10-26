from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

import pytest

from src.chatbot.core.settings import settings
from src.chatbot.modules.llm.ollama import OllamaIntentClient, OllamaUnderstandingError
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    VietnameseNormalizer,
)
from src.chatbot.shared.enums import IntentTransition, IntentType, PageCode
from src.chatbot.shared.events import IntentAnalysisResult

ROOT = Path(__file__).resolve().parents[2]


class ScriptedClient:
    def __init__(self, result: IntentAnalysisResult) -> None:
        self.result = result

    def analyze(
        self, page_id: str, text: str, context: dict[str, Any] | None = None
    ) -> IntentAnalysisResult:
        assert page_id in {"CFC", "ZEO"}
        return self.result.model_copy(deep=True)


class TimeoutClient:
    def analyze(
        self, page_id: str, text: str, context: dict[str, Any] | None = None
    ) -> IntentAnalysisResult:
        raise OllamaUnderstandingError("timeout")


def _analyzer(result: IntentAnalysisResult) -> HybridInputAnalyzer:
    return HybridInputAnalyzer(
        ScriptedClient(result),
        VietnameseNormalizer("config/normalization/vi_intent.json"),
    )


@pytest.mark.parametrize(
    ("message", "model_intent", "expected_intent"),
    [
        ("HC vs 25kg 30% nhiều tấn", IntentType.PRICE_INQUIRY, IntentType.PRICE_INQUIRY),
        ("Mình chỉ hỏi giá Cobanic 30 giá 1 tấn bao nhiêu", IntentType.GENERAL_FAQ, IntentType.PRICE_INQUIRY),
        ("Tôi muốn tìm đại lý gần nhất", IntentType.DEALER_LOOKUP, IntentType.DEALER_LOOKUP),
        ("Tôi muốn tìm mua Hữu cơ Cobanic 21", IntentType.PRODUCT_INQUIRY, IntentType.PRODUCT_INQUIRY),
    ],
)
def test_real_transcript_intents(
    message: str, model_intent: IntentType, expected_intent: IntentType
) -> None:
    result = _analyzer(
        IntentAnalysisResult(primary_intent=model_intent, confidence=0.9)
    ).analyze(PageCode.CFC, message)
    assert result.primary_intent == expected_intent
    if expected_intent == IntentType.PRICE_INQUIRY:
        assert result.requires_human_handoff


def test_source_question_intents_follow_governance_metadata() -> None:
    catalog = json.loads(
        (ROOT / "tests/fixtures/cfc_faq_cases.json").read_text(encoding="utf-8")
    )
    total = 0
    correct = 0
    failures = []
    for case in catalog["cases"]:
        expected = IntentType(case["intent"])
        analyzer = _analyzer(
            IntentAnalysisResult(primary_intent=expected, confidence=0.9)
        )
        for question in case["questions"]:
            total += 1
            result = analyzer.analyze(PageCode.CFC, question)
            correct += result.primary_intent == expected
            if result.primary_intent != expected:
                failures.append((case["case_id"], question, expected, result.primary_intent))
    assert total == 129
    assert correct / total >= 0.95, failures


def test_configured_slot_fixture_meets_f1_gate() -> None:
    fixture = json.loads(
        (ROOT / "tests/fixtures/cfc_slot_cases.json").read_text(encoding="utf-8")
    )
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    true_positive = 0
    false_positive = 0
    false_negative = 0
    failures = []
    scored_slots = {
        "product_mentions", "crop", "stage", "location", "quantity", "unit", "phone"
    }
    for case in fixture["cases"]:
        actual = normalizer.deterministic_slots(normalizer.normalize(case["text"]))
        expected = case["expected"]
        if any(actual.get(key) != value for key, value in expected.items()):
            failures.append((case["text"], expected, actual))
        for key, value in actual.items():
            if key not in scored_slots:
                continue
            if key in expected and expected[key] == value:
                true_positive += 1
            else:
                false_positive += 1
        false_negative += sum(
            key not in actual or actual[key] != value
            for key, value in expected.items()
            if key in scored_slots
        )
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    f1 = 2 * precision * recall / (precision + recall)
    assert f1 >= 0.95, failures


def test_explicit_agronomy_action_switches_from_open_price_workflow() -> None:
    analyzer = _analyzer(
        IntentAnalysisResult(primary_intent=IntentType.AGRI_ADVICE, confidence=0.8)
    )
    result = analyzer.analyze(
        PageCode.CFC,
        "Rải mít",
        {
            "current_workflow": "PRICE_HANDOFF",
            "current_intent": "PRICE_INQUIRY",
            "current_slots": {"product_mentions": ["Cobanic 30"]},
            "message_ids": ["mid-1"],
        },
    )
    assert result.primary_intent == IntentType.AGRI_ADVICE
    assert result.intent_transition == IntentTransition.SWITCH
    assert result.extracted_slots["crop"] == "mít"
    assert "product_mentions" not in result.extracted_slots
    assert not result.requires_human_handoff


def test_location_name_containing_price_word_is_not_a_price_intent() -> None:
    analyzer = _analyzer(
        IntentAnalysisResult(primary_intent=IntentType.GENERAL_FAQ, confidence=0.8)
    )
    result = analyzer.analyze(
        PageCode.CFC,
        "Rạch Giá",
        {
            "current_workflow": "DEALER_LOOKUP",
            "current_intent": "DEALER_LOOKUP",
            "current_slots": {},
        },
    )
    assert result.primary_intent == IntentType.DEALER_LOOKUP
    assert result.intent_transition == IntentTransition.CONTINUE
    assert result.extracted_slots["location"] == "Rạch Giá"
    assert result.extracted_slots["province"] == "An Giang"


def test_quantity_only_followup_continues_open_price_workflow() -> None:
    analyzer = _analyzer(
        IntentAnalysisResult(primary_intent=IntentType.UNKNOWN, confidence=0.4)
    )
    result = analyzer.analyze(
        PageCode.CFC,
        "30 tấn",
        {
            "current_workflow": "PRICE_HANDOFF",
            "current_intent": "PRICE_INQUIRY",
            "current_slots": {"product_mentions": ["Cobanic 30"]},
        },
    )
    assert result.primary_intent == IntentType.PRICE_INQUIRY_DETAIL
    assert result.intent_transition == IntentTransition.CONTINUE
    assert result.extracted_slots["quantity"] == "30"
    assert result.extracted_slots["unit"] == "tấn"
    assert result.extracted_slots["product_mentions"] == ["Cobanic 30"]


def test_contact_request_is_forced_before_model_guess() -> None:
    analyzer = _analyzer(
        IntentAnalysisResult(primary_intent=IntentType.GENERAL_FAQ, confidence=0.8)
    )

    result = analyzer.analyze(PageCode.CFC, "Cho tôi xin số hotline công ty")

    assert result.primary_intent == IntentType.CONTACT_REQUEST
    assert not result.requires_human_handoff


def test_switch_from_open_price_workflow_to_dealer() -> None:
    analyzer = _analyzer(
        IntentAnalysisResult(primary_intent=IntentType.DEALER_LOOKUP, confidence=0.9)
    )
    result = analyzer.analyze(
        PageCode.CFC,
        "Tôi muốn tìm đại lý gần nhất",
        {
            "current_workflow": "PRICE_HANDOFF",
            "current_intent": "PRICE_INQUIRY_DETAIL",
            "current_slots": {"location": "Khánh Hòa"},
            "message_ids": ["mid-1"],
        },
    )
    assert result.primary_intent == IntentType.DEALER_LOOKUP
    assert result.intent_transition == IntentTransition.SWITCH
    assert result.extracted_slots["location"] == "Khánh Hòa"



def test_timeout_is_bounded_and_fails_closed() -> None:
    analyzer = HybridInputAnalyzer(
        TimeoutClient(),
        VietnameseNormalizer("config/normalization/vi_intent.json"),
    )
    price = analyzer.analyze(PageCode.CFC, "xin giá 1 tấn")
    assert price.primary_intent == IntentType.PRICE_INQUIRY
    assert price.extracted_slots["quantity"] == "1"
    assert price.requires_human_handoff

    unknown = analyzer.analyze(PageCode.CFC, "nội dung không rõ")
    assert unknown.primary_intent == IntentType.UNKNOWN
    assert unknown.requires_human_handoff


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_OLLAMA_EVAL") != "1",
    reason="Set RUN_LIVE_OLLAMA_EVAL=1 for the local model gate",
)
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Mình chỉ hỏi giá Cobanic 30 giá 1 tấn bao nhiêu", IntentType.PRICE_INQUIRY),
        ("Tôi muốn tìm đại lý gần nhất", IntentType.DEALER_LOOKUP),
        ("Tôi muốn tìm mua Hữu cơ Cobanic 21", IntentType.PRODUCT_INQUIRY),
        ("Hướng dẫn tôi bón phân cho mít", IntentType.AGRI_ADVICE),
    ],
)
def test_live_qwen_structured_understanding(message: str, expected: IntentType) -> None:
    client = OllamaIntentClient(
        settings.OLLAMA_BASE_URL,
        settings.OLLAMA_MODEL_TAG,
        settings.OLLAMA_TIMEOUT_SECONDS,
        prompt_path=settings.INTENT_PROMPT_PATH,
        max_attempts=1,
    )
    if not client.is_ready():
        pytest.fail("Ollama/model is not ready for the requested live gate")
    analyzer = HybridInputAnalyzer(
        client,
        VietnameseNormalizer(settings.INTENT_NORMALIZATION_PATH),
    )
    result = analyzer.analyze(PageCode.CFC, message)
    assert result.primary_intent == expected
