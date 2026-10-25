from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.delivery.dispatcher import OutboxDispatcher
from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import OutboxMessageSchema


def test_dispatcher_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "META_SEND_ENABLED", False)
    store = InMemoryOutboxStore()
    store.enqueue(
        OutboxMessageSchema(
            conversation_id="CFC:psid",
            page_id=PageCode.CFC,
            recipient_id="psid",
            text="hello",
            batch_version=1,
        )
    )
    assert OutboxDispatcher(store).dispatch_one("CFC:psid", 1) is False
    assert next(iter(store.messages.values())).status.value == "PENDING"


def test_dispatcher_marks_sent_with_allowlist(monkeypatch) -> None:
    class Sender:
        def send_text(self, page_id, recipient_id, text):
            return "meta-message-id"

    monkeypatch.setattr(settings, "META_SEND_ENABLED", True)
    monkeypatch.setattr(settings, "META_TEST_RECIPIENT_ID", "psid")
    store = InMemoryOutboxStore()
    store.enqueue(
        OutboxMessageSchema(
            conversation_id="CFC:psid",
            page_id=PageCode.CFC,
            recipient_id="psid",
            text="hello",
            batch_version=1,
        )
    )
    assert OutboxDispatcher(store, Sender()).dispatch_one("CFC:psid", 1) is True
    assert next(iter(store.messages.values())).status.value == "SENT"
