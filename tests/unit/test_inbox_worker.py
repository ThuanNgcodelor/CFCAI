from datetime import UTC, datetime

from src.chatbot.infrastructure.messaging.inbox import DurableInboxStore
from src.chatbot.infrastructure.messaging.worker import InboxWorker
from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import InboxEvent, NormalizedMessage


def test_worker_claims_and_acknowledges_events() -> None:
    store = DurableInboxStore()
    event = InboxEvent(
        event_id="evt-worker-1",
        page_id=PageCode.CFC,
        sender_id="psid-1",
        message=NormalizedMessage(
            mid="mid-worker-1",
            sender_id="psid-1",
            recipient_id="page-cfc",
            timestamp=datetime.now(UTC),
            text="Xin chào",
        ),
    )
    store.record_event(event)
    seen: list[str] = []
    worker = InboxWorker(store, lambda item: seen.append(item.event_id))

    assert worker.run_once() == 1
    assert seen == ["evt-worker-1"]
