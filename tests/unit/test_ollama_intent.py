import json

from src.chatbot.modules.llm.ollama import OllamaIntentClient
from src.chatbot.shared.enums import IntentType


def test_prompt_does_not_include_price_word() -> None:
    prompt = OllamaIntentClient.build_prompt("CFC", "Cho tôi giá sản phẩm này")
    assert "cho tôi  sản phẩm này" in prompt.lower()
    assert "100.000" not in prompt


def test_price_intent_forces_handoff(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "response": json.dumps(
                        {"primary_intent": "PRICE_INQUIRY", "confidence": 0.4}
                    )
                }
            ).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    result = OllamaIntentClient("http://ollama", "qwen2.5:7b").analyze(
        "CFC", "xin báo giá"
    )
    assert result.primary_intent == IntentType.PRICE_INQUIRY
    assert result.requires_human_handoff is True
