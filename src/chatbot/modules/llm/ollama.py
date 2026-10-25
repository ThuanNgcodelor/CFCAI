"""Strict Ollama adapter for intent extraction only.

Prices are intentionally removed before prompt construction. This adapter does
not generate customer-facing answers and therefore cannot authorize pricing or
override human handoff rules.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from src.chatbot.shared.enums import IntentType
from src.chatbot.shared.events import IntentAnalysisResult


class OllamaIntentClient:
    def __init__(
        self, base_url: str, model: str, timeout_seconds: float = 20.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def build_prompt(page_id: str, text: str) -> str:
        # Never pass price-related context to the model.
        safe_text = text.replace("giá", "").replace("price", "")
        return (
            "Bạn chỉ phân loại ý định, không trả lời khách hàng và không suy đoán giá.\n"
            f"page_id={page_id}\n"
            "Các intent hợp lệ: PRODUCT_INQUIRY, PRICE_INQUIRY, DEALER_LOOKUP, "
            "AGRI_ADVICE, SALES_LEAD, HUMAN_REQUEST, GENERAL_FAQ, UNKNOWN.\n"
            f"Tin nhắn: {safe_text}\n"
            "Trả về JSON duy nhất: {primary_intent, confidence, detected_skus, "
            "extracted_slots, clarification_needed, requires_human_handoff}."
        )

    def analyze(self, page_id: str, text: str) -> IntentAnalysisResult:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "prompt": self.build_prompt(page_id, text),
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        result: dict[str, Any] = json.loads(body["response"])
        intent = IntentType(result["primary_intent"])
        # PRICE_INQUIRY always hands off, regardless of model confidence.
        is_price = intent == IntentType.PRICE_INQUIRY
        return IntentAnalysisResult(
            primary_intent=intent,
            confidence=float(result.get("confidence", 0.0)),
            detected_skus=list(result.get("detected_skus", [])),
            extracted_slots=dict(result.get("extracted_slots", {})),
            clarification_needed=bool(result.get("clarification_needed", False)),
            requires_human_handoff=is_price
            or bool(result.get("requires_human_handoff", False)),
        )
