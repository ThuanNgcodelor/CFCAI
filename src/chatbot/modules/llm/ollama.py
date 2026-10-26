"""Ollama adapter for structured understanding only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from src.chatbot.shared.enums import IntentType
from src.chatbot.shared.events import IntentAnalysisResult


class OllamaUnderstandingError(RuntimeError):
    """Raised after the bounded Ollama attempts are exhausted."""


class OllamaIntentClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 20.0,
        *,
        prompt_path: str | Path = "config/prompts/intent.md",
        max_attempts: int = 2,
    ) -> None:
        if timeout_seconds <= 0 or max_attempts not in {1, 2}:
            raise ValueError("timeout must be positive and max_attempts must be 1 or 2")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.prompt_path = Path(prompt_path)
        self.system_prompt = self.prompt_path.read_text(encoding="utf-8").strip()

    def build_prompt(
        self,
        page_id: str,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Build a data-only user payload; never include catalog/CRM/price records."""
        safe_context = context or {}
        payload = {
            "page_id": page_id,
            "conversation_state": {
                "current_workflow": safe_context.get("current_workflow"),
                "current_intent": safe_context.get("current_intent"),
                "current_slots": safe_context.get("current_slots", {}),
            },
            "recent_customer_messages": safe_context.get(
                "recent_customer_messages", []
            ),
            "message_ids": safe_context.get("message_ids", []),
            "customer_message_batch": text,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def is_ready(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/api/tags", timeout=min(self.timeout_seconds, 5.0)
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
            return any(item.get("name") == self.model for item in body.get("models", []))
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            return False

    def analyze(
        self,
        page_id: str,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> IntentAnalysisResult:
        request_payload = {
            "model": self.model,
            "stream": False,
            "format": IntentAnalysisResult.model_json_schema(),
            "options": {"temperature": 0.0, "num_predict": 384},
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.build_prompt(page_id, text, context)},
            ],
        }
        last_error: Exception | None = None
        for _ in range(self.max_attempts):
            request = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    body = json.loads(response.read().decode("utf-8"))
                content = body["message"]["content"]
                result = IntentAnalysisResult.model_validate_json(content)
                if result.primary_intent == IntentType.PRICE_INQUIRY:
                    result.requires_human_handoff = True
                result.clarification_needed = result.needs_clarification
                return result
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                urllib.error.URLError,
            ) as exc:
                last_error = exc
        raise OllamaUnderstandingError("Ollama structured understanding failed") from last_error


class OllamaResponseGenerator:
    """Uses Ollama to generate natural, polite conversational replies guided by retrieved facts."""

    _SYSTEM_PROMPT = """Bạn là trợ lý tư vấn khách hàng của Phân bón Cò Bay (CFC).
Phong cách: Nhiệt tình, lễ phép, xưng hô anh/chị/em thân mật (văn hóa bà con miền Tây, dùng icon 🌾, 🌱, 😊 phù hợp).
Quy tắc bắt buộc:
1. KHÔNG BAO GIỜ tự báo giá số tiền hay khoảng giá cụ thể. Giải thích giá tùy khu vực và số lượng, xin SĐT, tỉnh/huyện, loại cây, số lượng bao để bạn kinh doanh gọi báo giá đúng mốc hẹn.
2. KHÔNG tự bịa số điện thoại cá nhân hay địa chỉ (chỉ dùng hotline 1900 5307 hoặc xin SĐT của khách để kinh doanh gọi lại).
3. Chỉ tư vấn sản phẩm và công dụng dựa trên THÔNG TIN SẢN PHẨM và BÀI QUẢNG CÁO được cung cấp trong dữ liệu. Không tự bịa thông số kỹ thuật chưa có.
4. Trả lời ngắn gọn 1-3 câu, súc tích, tự nhiên, dễ đọc trên điện thoại.
Xuất JSON dạng: {"reply": "câu trả lời"}"""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, context_payload: dict[str, Any]) -> str | None:
        request_payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 256},
            "messages": [
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context_payload, ensure_ascii=False)},
            ],
        }
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            parsed = json.loads(content)
            reply = parsed.get("reply", "").strip()
            return reply if reply else None
        except Exception:
            return None
