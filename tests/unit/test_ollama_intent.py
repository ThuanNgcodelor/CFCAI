import json

import pytest

from src.chatbot.modules.llm.ollama import OllamaIntentClient, OllamaUnderstandingError
from src.chatbot.shared.enums import IntentType


def _client() -> OllamaIntentClient:
    return OllamaIntentClient(
        "http://ollama",
        "qwen2.5:7b",
        prompt_path="config/prompts/intent.md",
        max_attempts=1,
    )


def test_prompt_contains_customer_request_but_no_commerce_context() -> None:
    prompt = _client().build_prompt(
        "CFC",
        "Cho tôi giá sản phẩm này",
        {"current_slots": {"product_mentions": ["sản phẩm này"]}},
    )
    payload = json.loads(prompt)
    assert payload["customer_message_batch"] == "Cho tôi giá sản phẩm này"
    assert payload["page_id"] == "CFC"
    assert "price_amount" not in prompt
    assert "internal_data" not in prompt
    assert "crm" not in prompt.casefold()


def test_price_intent_forces_handoff(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "primary_intent": "PRICE_INQUIRY",
                                "confidence": 0.4,
                            }
                        )
                    }
                }
            ).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    result = _client().analyze("CFC", "xin báo giá")
    assert result.primary_intent == IntentType.PRICE_INQUIRY
    assert result.requires_human_handoff is True


def test_structured_result_without_required_evidence_fails_closed(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "primary_intent": "GENERAL_FAQ",
                                "confidence": 0.8,
                                "evidence_message_ids": [],
                            }
                        )
                    }
                }
            ).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(OllamaUnderstandingError):
        _client().analyze(
            "CFC",
            "Công ty ở đâu?",
            {"message_ids": ["mid-1"]},
        )
