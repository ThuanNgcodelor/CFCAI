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
    assert "bạn kinh doanh sẽ báo giá" in msg_text or "giá 1 bao" in msg_text


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
