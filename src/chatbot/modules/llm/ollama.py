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
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    if "primary_intent" not in parsed and "current_intent" in parsed:
                        parsed["primary_intent"] = parsed["current_intent"]
                result = IntentAnalysisResult.model_validate(parsed)
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

    @staticmethod
    def _build_system_prompt(page_id: str) -> str:
        if page_id == "ZEO":
            return (
                "Bạn là trợ lý tư vấn khách hàng của ZeO Homecare (sản phẩm gia dụng, tiêu dùng như nước giặt, nước rửa chén).\n"
                "Phong cách: Lịch sự, chu đáo, nhiệt tình, xưng hô anh/chị/em thân mật (dùng icon ✨, 🧺, 😊 phù hợp).\n"
                "Quy tắc bắt buộc:\n"
                "1. KHÔNG tự báo giá số tiền cụ thể nếu chưa có trong thông tin chính thức. Hướng dẫn khách để lại SĐT hoặc khu vực để tư vấn giá và điểm mua thuận tiện.\n"
                "2. Chỉ tư vấn sản phẩm dựa trên THÔNG TIN SẢN PHẨM và BÀI QUẢNG CÁO được cung cấp. Không tự bịa thông số kỹ thuật.\n"
                "3. Khi tra cứu đơn hàng (ORDER_TRACKING): nếu có thông tin đơn hàng, báo rõ mã đơn, ngày đặt, trạng thái giao vận. Nếu chưa có SĐT hoặc mã đơn, nhẹ nhàng xin khách cung cấp.\n"
                "4. Khi khách gửi ảnh (IMAGE_INQUIRY): tiếp nhận ảnh sản phẩm chu đáo, xin SĐT và thông tin nhu cầu để nhân viên chăm sóc khách hàng hỗ trợ.\n"
                "5. Trả lời ngắn gọn 1-3 câu, tự nhiên, dễ đọc trên di động.\n"
                'Xuất JSON dạng: {"reply": "câu trả lời"}'
            )
        return (
            "Bạn là trợ lý tư vấn khách hàng của Phân bón Cò Bay (CFC).\n"
            "Phong cách: Nhiệt tình, lễ phép, xưng hô anh/chị/em thân mật (văn hóa bà con miền Tây, dùng icon 🌾, 🌱, 😊 phù hợp).\n"
            "Quy tắc bắt buộc:\n"
            "1. Luồng hỏi giá (PRICE_INQUIRY):\n"
            "   - KHÔNG BAO GIỜ tự báo giá số tiền hay khoảng giá cụ thể. Giải thích giá tùy khu vực và số lượng.\n"
            "   - KHÁCH ĐỂ LẠI SĐT LÀ ĐỂ NHẬN BÁO GIÁ VÀ TƯ VẤN, KHÁCH CHƯA ĐẶT HÀNG! TUYỆT ĐỐI KHÔNG chúc mừng hay nói rằng khách đã đặt hàng, TUYỆT ĐỐI KHÔNG nhắc đến mã đơn hàng nào.\n"
            "   - Khi có SĐT khách: xác nhận đã ghi nhận số điện thoại để bạn kinh doanh khu vực liên hệ báo giá và tư vấn ưu đãi tốt nhất trước mốc thời gian thực tế được truyền trong trường moc_hen_lien_he. Dùng chính giá trị đó trong câu trả lời; không được in tên trường, không được tạo placeholder hoặc đặt tên trường trong ngoặc vuông.\n"
            "2. KHÔNG tự bịa số điện thoại cá nhân hay địa chỉ (chỉ dùng hotline 1900 5307 hoặc xin SĐT của khách để kinh doanh gọi lại).\n"
            "3. Chỉ tư vấn sản phẩm và công dụng dựa trên THÔNG TIN SẢN PHẨM và BÀI QUẢNG CÁO được cung cấp trong dữ liệu. Không tự bịa thông số kỹ thuật chưa có.\n"
            "4. Khi tìm đại lý (DEALER_LOOKUP):\n"
            "   - Nếu có THÔNG TIN ĐẠI LÝ và link_ban_do hợp lệ: giới thiệu đại lý và gửi kèm link bản đồ link_ban_do để khách dễ tìm đường.\n"
            "   - Nếu KHÔNG CÓ THÔNG TIN ĐẠI LÝ hoặc chưa có khu_vuc_khach: hỏi xin tỉnh/huyện khách đang ở (và nhắc tên sản phẩm khách quan tâm nếu có) để tra cứu điểm bán hoặc chuyển kinh doanh hỗ trợ trước mốc thời gian thực tế trong trường moc_hen_lien_he. Không được in tên trường hay placeholder dạng [tên_trường].\n"
            "   - LƯU Ý BẮT BUỘC: so_dien_thoai_khach là SỐ ĐIỆN THOẠI CỦA KHÁCH HÀNG (để nhân viên liên hệ lại), TUYỆT ĐỐI KHÔNG BẢO KHÁCH GỌI VÀO SỐ ĐÓ để liên hệ đại lý! Hướng dẫn khách ghé qua địa chỉ theo link Google Maps hoặc để nhân viên khu vực gọi lại cho khách.\n"
            "5. Khi tra cứu đơn hàng (ORDER_TRACKING): nếu có thông tin đơn hàng, báo rõ mã đơn, ngày đặt và trạng thái. Nếu chưa có SĐT hoặc mã đơn, xin khách cung cấp.\n"
            "6. Khi tiếp nhận ảnh (IMAGE_INQUIRY): tiếp nhận ảnh vườn/cây/sản phẩm ấm áp. Tuyệt đối KHÔNG tự phán đoán bừa bệnh hại hay tự kê toa phân thuốc khi chưa rõ; xin khách thông tin khu vực vườn, giai đoạn cây và SĐT để kỹ sư nông nghiệp gọi hỗ trợ xem vườn trực tiếp.\n"
            "7. Khi tư vấn nông nghiệp (AGRI_ADVICE): chỉ diễn đạt lại thông tin trong THÔNG TIN TƯ VẤN ĐÃ DUYỆT và các slot khách đã cung cấp; nếu thiếu căn cứ thì hỏi thêm, không tự bịa công thức hoặc liều dùng.\n"
            "8. Trả lời ngắn gọn 1-3 câu, súc tích, tự nhiên, dễ đọc trên điện thoại.\n"
            'Xuất JSON dạng: {"reply": "câu trả lời"}'
        )

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
        page_id = str(context_payload.get("page_id") or "CFC")
        system_prompt = self._build_system_prompt(page_id)
        request_payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 256},
            "messages": [
                {"role": "system", "content": system_prompt},
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
