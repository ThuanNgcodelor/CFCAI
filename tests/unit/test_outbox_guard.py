from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import OutboxMessageSchema


def test_outbox_claim_requires_matching_batch_and_ai_ownership() -> None:
    store = InMemoryOutboxStore()
    message = OutboxMessageSchema(
        conversation_id="conv-1",
        page_id=PageCode.CFC,
        recipient_id="psid-1",
        text="Đã tiếp nhận yêu cầu.",
        batch_version=2,
    )
    store.enqueue(message)
    assert store.claim_sendable("conv-1", 1) is None
    claimed = store.claim_sendable("conv-1", 2)
    assert claimed is not None
    assert claimed.batch_version == 2
