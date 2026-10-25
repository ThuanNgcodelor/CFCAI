from datetime import UTC, datetime

from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import InboxEvent, NormalizedMessage


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


def test_pipeline_does_not_create_outbox_for_price() -> None:
    outbox = InMemoryOutboxStore()
    assert SafeMessagePipeline(outbox).process(_event("Cho tôi báo giá")) is None
    assert outbox.messages == {}
