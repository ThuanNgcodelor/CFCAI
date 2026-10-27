import re
from datetime import UTC, datetime

from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.shared.enums import IntentType, PageCode
from src.chatbot.shared.events import (
    InboxEvent,
    IntentAnalysisResult,
    NormalizedMessage,
)


def _event(text: str) -> InboxEvent:
    return InboxEvent(
        event_id="pipeline-1",
        page_id=PageCode.CFC,
        sender_id="psid-1",
        message=NormalizedMessage(
            mid="mid-1",
            sender_id="psid-1",
            recipient_id="page-1",
            timestamp=datetime.now(UTC),
            text=text,
        ),
    )


def test_pipeline_creates_scoped_outbox_for_safe_message() -> None:
    outbox = InMemoryOutboxStore()
    assert SafeMessagePipeline(outbox).process(_event("Xin chào")) == "outbox-1"
    assert outbox.messages["outbox-1"].page_id == PageCode.CFC
    assert "Cò Bay kính chào" in outbox.messages["outbox-1"].text


def test_pipeline_handles_price_inquiry_without_hallucinating_price() -> None:
    outbox = InMemoryOutboxStore()
    assert SafeMessagePipeline(outbox).process(_event("Cho tôi báo giá")) == "outbox-1"
    msg_text = outbox.messages["outbox-1"].text
    # Must never hallucinate exact price
    assert not re.search(r"\b\d+[\s.]*(?:đ|k|đồng|vnd)\b", msg_text, re.IGNORECASE)
    # Must politely explain and request customer contact info
    assert "bộ phận kinh doanh" in msg_text
    assert "số điện thoại" in msg_text
    assert "bạn" not in msg_text.casefold()


def test_pipeline_handles_human_request() -> None:
    class FakeIntent:
        def analyze(self, page_id: PageCode, text: str, context) -> IntentAnalysisResult:
            assert page_id == PageCode.CFC
            return IntentAnalysisResult(
                primary_intent=IntentType.HUMAN_REQUEST,
                confidence=1.0,
                requires_human_handoff=True,
            )

    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=FakeIntent())
    assert pipeline.process(_event("Tôi muốn gặp nhân viên")) == "outbox-1"
    assert "nhân viên" in outbox.messages["outbox-1"].text


def test_pipeline_suppresses_internal_jargon() -> None:
    class RogueGenerator:
        def generate(self, payload):
            return "Dạ snapshot CRM ghi nhận trong database là đại lý đang có hàng ạ."

    from src.chatbot.modules.workflows.composer import ResponseComposer

    composer = ResponseComposer(generator=RogueGenerator())
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox, composer=composer)
    outbox_id = pipeline.process(_event("Cho tôi hỏi giá phân bón"))
    assert outbox_id is not None
    msg = outbox.messages[outbox_id].text
    assert "snapshot crm" not in msg.lower()
    assert "database" not in msg.lower()
    assert "báo giá" in msg


def test_pipeline_suppresses_unresolved_placeholders() -> None:
    class PlaceholderGenerator:
        def generate(self, payload):
            return "Dạ sản phẩm {{product_title}} sẽ được giao trước [moc_hen_lien_he] nha anh/chị!"

    from src.chatbot.modules.workflows.composer import ResponseComposer

    composer = ResponseComposer(generator=PlaceholderGenerator())
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox, composer=composer)
    outbox_id = pipeline.process(_event("Báo giá sản phẩm"))
    assert outbox_id is not None
    msg = outbox.messages[outbox_id].text
    assert "{{" not in msg
    assert "}}" not in msg
    assert "[moc_hen_lien_he]" not in msg


def test_pipeline_blocks_unauthorized_phone_and_fake_confirmation() -> None:
    class RoguePhoneGenerator:
        def generate(self, payload):
            return "Dạ em đã ghi nhận số điện thoại của anh/chị, vui lòng gọi số 0949111222 nha!"

    from src.chatbot.modules.workflows.composer import ResponseComposer

    composer = ResponseComposer(generator=RoguePhoneGenerator())
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox, composer=composer)
    outbox_id = pipeline.process(_event("Cho tôi báo giá"))
    assert outbox_id is not None
    msg = outbox.messages[outbox_id].text
    assert "0949111222" not in msg
    assert "đã ghi nhận số điện thoại" not in msg


def test_pipeline_enforces_persona_integrity() -> None:
    class BadPersonaGenerator:
        def generate(self, payload):
            return "Chào bạn, bà con nên dùng loại này rất tốt nha!"

    from src.chatbot.modules.workflows.composer import ResponseComposer

    composer = ResponseComposer(generator=BadPersonaGenerator())
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox, composer=composer)
    outbox_id = pipeline.process(_event("Báo giá phân bón"))
    assert outbox_id is not None
    msg = outbox.messages[outbox_id].text
    assert "chào bạn" not in msg.lower()
    assert "bà con" not in msg.lower()


def test_pipeline_outbox_envelope_side_effects() -> None:
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox)
    outbox_id = pipeline.process(
        _event("Xin chào"),
        batch_version=102,
        conversation_version=5,
    )
    assert outbox_id is not None
    envelope = outbox.messages[outbox_id]
    assert envelope.page_id == PageCode.CFC
    assert envelope.recipient_id == "psid-1"
    assert envelope.batch_version == 102
    assert envelope.expected_conversation_version == 5
    assert envelope.expected_ownership.value == "AI"
