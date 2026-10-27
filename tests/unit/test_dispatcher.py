from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.delivery.dispatcher import OutboxDispatcher
from src.chatbot.shared.enums import PageCode, WorkflowType
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
    monkeypatch.setattr(settings, "DELIVERY_MODE", "live")
    monkeypatch.setattr(settings, "LIVE_SEND_APPROVED", True)
    monkeypatch.setattr(settings, "DELIVERY_NOT_BEFORE", "2000-01-01T00:00:00+00:00")
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


def test_dispatcher_pending_without_allowlist(monkeypatch) -> None:
    class Sender:
        def send_text(self, page_id, recipient_id, text):
            return "meta-message-id"

    monkeypatch.setattr(settings, "META_SEND_ENABLED", True)
    monkeypatch.setattr(settings, "META_TEST_RECIPIENT_ID", "")
    monkeypatch.setattr(settings, "DELIVERY_MODE", "live")
    monkeypatch.setattr(settings, "LIVE_SEND_APPROVED", True)
    monkeypatch.setattr(settings, "DELIVERY_NOT_BEFORE", "2000-01-01T00:00:00+00:00")
    store = InMemoryOutboxStore()
    store.enqueue(
        OutboxMessageSchema(
            conversation_id="CFC:user-1",
            page_id=PageCode.CFC,
            recipient_id="user-1",
            text="hello",
            batch_version=1,
        )
    )
    dispatcher = OutboxDispatcher(store, Sender())
    sent = dispatcher.dispatch_pending()
    assert sent == 1
    assert next(iter(store.messages.values())).status.value == "SENT"


def test_shadow_mode_records_and_suppresses_without_sending(monkeypatch) -> None:
    class Sender:
        def __init__(self) -> None:
            self.sent = 0

        def send_text(self, page_id, recipient_id, text):
            self.sent += 1
            return "must-not-be-used"

    class Recorder:
        def __init__(self) -> None:
            self.messages = []

        def record(self, message) -> None:
            self.messages.append(message)

    monkeypatch.setattr(settings, "META_SEND_ENABLED", False)
    monkeypatch.setattr(settings, "DELIVERY_MODE", "shadow")
    store = InMemoryOutboxStore()
    store.enqueue(
        OutboxMessageSchema(
            conversation_id="CFC:shadow-user",
            page_id=PageCode.CFC,
            recipient_id="shadow-user",
            text="shadow candidate",
            batch_version=1,
            workflow=WorkflowType.FAQ_ANSWER,
        )
    )
    sender = Sender()
    recorder = Recorder()

    assert OutboxDispatcher(store, sender, recorder).dispatch_pending() == 0
    assert sender.sent == 0
    assert len(recorder.messages) == 1
    assert next(iter(store.messages.values())).status.value == "SUPPRESSED"


def test_canary_is_scoped_by_configured_page_and_workflow(monkeypatch) -> None:
    class Sender:
        def __init__(self) -> None:
            self.sent = []

        def send_text(self, page_id, recipient_id, text):
            self.sent.append((page_id, recipient_id, text))
            return "meta-message-id"

    monkeypatch.setattr(settings, "META_SEND_ENABLED", True)
    monkeypatch.setattr(settings, "DELIVERY_MODE", "canary")
    monkeypatch.setattr(settings, "CANARY_SEND_APPROVED", True)
    monkeypatch.setattr(settings, "CANARY_PAGE_IDS", "CFC")
    monkeypatch.setattr(settings, "CANARY_WORKFLOWS", "FAQ_ANSWER")
    monkeypatch.setattr(settings, "CANARY_RECIPIENT_IDS", "")
    monkeypatch.setattr(settings, "CANARY_PERCENT", 100)
    monkeypatch.setattr(settings, "META_TEST_RECIPIENT_ID", "")
    monkeypatch.setattr(settings, "DELIVERY_NOT_BEFORE", "2000-01-01T00:00:00+00:00")
    store = InMemoryOutboxStore()
    store.enqueue(
        OutboxMessageSchema(
            conversation_id="CFC:faq-user",
            page_id=PageCode.CFC,
            recipient_id="faq-user",
            text="approved FAQ",
            batch_version=1,
            workflow=WorkflowType.FAQ_ANSWER,
        )
    )
    store.enqueue(
        OutboxMessageSchema(
            conversation_id="CFC:product-user",
            page_id=PageCode.CFC,
            recipient_id="product-user",
            text="must stay canary-blocked",
            batch_version=1,
            workflow=WorkflowType.PRODUCT_INQUIRY,
        )
    )
    sender = Sender()

    assert OutboxDispatcher(store, sender).dispatch_pending() == 1
    assert len(sender.sent) == 1
    statuses = {message.recipient_id: message.status.value for message in store.messages.values()}
    assert statuses == {"faq-user": "SENT", "product-user": "SUPPRESSED"}


def test_live_mode_without_release_fence_leaves_pending_message_unsent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "META_SEND_ENABLED", True)
    monkeypatch.setattr(settings, "DELIVERY_MODE", "live")
    monkeypatch.setattr(settings, "LIVE_SEND_APPROVED", True)
    monkeypatch.setattr(settings, "DELIVERY_NOT_BEFORE", "")
    store = InMemoryOutboxStore()
    store.enqueue(
        OutboxMessageSchema(
            conversation_id="CFC:old-pending",
            page_id=PageCode.CFC,
            recipient_id="old-pending",
            text="must not send after a mode switch",
            batch_version=1,
            workflow=WorkflowType.FAQ_ANSWER,
        )
    )

    assert OutboxDispatcher(store).dispatch_pending() == 0
    assert next(iter(store.messages.values())).status.value == "PENDING"
