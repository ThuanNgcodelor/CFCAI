import uuid
from datetime import UTC, datetime, timedelta

import psycopg2

from src.chatbot.infrastructure.messaging.outbox import PostgresOutboxStore
from src.chatbot.modules.aggregation.service import MessageAggregator
from src.chatbot.modules.conversations.repository import PostgresConversationRepository
from src.chatbot.modules.conversations.state_machine import (
    ConversationStateStore,
    final_send_allowed,
)
from src.chatbot.shared.enums import IntentType, Ownership, PageCode, WorkflowType
from src.chatbot.shared.events import InboxEvent, NormalizedMessage, OutboxMessageSchema


def _message(mid: str, text: str) -> NormalizedMessage:
    return NormalizedMessage(
        mid=mid,
        sender_id="psid-1",
        recipient_id="page-cfc",
        timestamp=datetime.now(UTC),
        text=text,
    )


def test_four_messages_in_six_seconds_make_one_batch() -> None:
    now = datetime(2026, 10, 25, tzinfo=UTC)
    clock_now = [now]
    store = ConversationStateStore()
    aggregator = MessageAggregator(
        store,
        debounce_seconds=5,
        max_batch_seconds=20,
        clock=lambda: clock_now[0],
    )

    for index in range(4):
        clock_now[0] = now + timedelta(seconds=index * 2)
        aggregator.ingest(
            conversation_id="conv-1",
            page_id=PageCode.CFC,
            sender_id="psid-1",
            message=_message(f"mid-{index}", str(index)),
        )

    clock_now[0] = now + timedelta(seconds=11)
    batch = aggregator.claim_ready("conv-1")
    assert batch is not None
    assert [message.mid for message in batch.messages] == [
        "mid-0",
        "mid-1",
        "mid-2",
        "mid-3",
    ]


def test_takeover_invalidates_pending_ai_send() -> None:
    store = ConversationStateStore()
    state = store.get_or_create("conv-1", PageCode.CFC, "psid-1")
    expected_version = state.version
    expected_batch_version = state.batch_version

    store.takeover("conv-1", actor="agent-1", reason="Meta Business Suite reply")
    current = store.snapshot("conv-1")

    assert current.ownership == Ownership.HUMAN
    assert not final_send_allowed(
        current,
        expected_version=expected_version,
        expected_batch_version=expected_batch_version,
    )


def test_page_scope_mismatch_is_rejected() -> None:
    store = ConversationStateStore()
    store.get_or_create("conv-1", PageCode.CFC, "psid-1")

    try:
        store.get_or_create("conv-1", PageCode.ZEO, "psid-1")
    except ValueError as exc:
        assert "page scope" in str(exc)
    else:
        raise AssertionError("cross-page conversation reuse must be rejected")


def test_postgres_debounce_is_durable_and_idempotent(isolated_database_url: str) -> None:
    repository = PostgresConversationRepository(isolated_database_url)
    sender_id = f"psid-{uuid.uuid4().hex}"
    now = datetime.now(UTC)
    events = [
        InboxEvent(
            event_id=f"event-{index}-{uuid.uuid4().hex}",
            page_id=PageCode.CFC,
            sender_id=sender_id,
            received_at=now + timedelta(milliseconds=index),
            message=NormalizedMessage(
                mid=f"mid-{index}-{uuid.uuid4().hex}",
                sender_id=sender_id,
                recipient_id="configured-page",
                timestamp=now + timedelta(milliseconds=index),
                text=f"message {index}",
            ),
        )
        for index in range(2)
    ]
    for event in events:
        assert repository.ingest(event, debounce_seconds=1, max_batch_seconds=5)
    assert repository.ingest(events[0], debounce_seconds=1, max_batch_seconds=5) is None

    with psycopg2.connect(isolated_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE message_batches SET due_at=now() WHERE status='OPEN'")
    batches = repository.claim_ready()
    assert len(batches) == 1
    assert [message.text for message in batches[0].messages] == ["message 0", "message 1"]
    assert repository.complete_batch(
        batches[0].batch_id,
        expected_batch_version=batches[0].conversation.batch_version,
    )


def test_postgres_takeover_suppresses_pending_outbox(isolated_database_url: str) -> None:
    repository = PostgresConversationRepository(isolated_database_url)
    sender_id = f"psid-{uuid.uuid4().hex}"
    event = InboxEvent(
        event_id=f"event-{uuid.uuid4().hex}",
        page_id=PageCode.CFC,
        sender_id=sender_id,
        message=NormalizedMessage(
            mid=f"mid-{uuid.uuid4().hex}",
            sender_id=sender_id,
            recipient_id="configured-page",
            timestamp=datetime.now(UTC),
            text="hello",
        ),
    )
    scheduled = repository.ingest(event, debounce_seconds=1, max_batch_seconds=5)
    assert scheduled is not None
    conversation_id, batch_version, _ = scheduled
    outbox = PostgresOutboxStore(isolated_database_url)
    outbox_id = outbox.enqueue(
        OutboxMessageSchema(
            conversation_id=conversation_id,
            page_id=PageCode.CFC,
            recipient_id=sender_id,
            text="pending AI response",
            batch_version=batch_version,
            expected_conversation_version=0,
        )
    )

    state = repository.takeover(
        PageCode.CFC,
        conversation_id,
        actor="integration-test-agent",
        reason="manual takeover",
    )
    assert state.ownership == Ownership.HUMAN
    assert outbox.claim_pending() == []
    with psycopg2.connect(isolated_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT status FROM outbox_messages WHERE outbox_id=%s", (outbox_id,))
        assert cursor.fetchone()[0] == "SUPPRESSED"
        cursor.execute("SELECT count(*) FROM handoff_events WHERE conversation_id=%s", (conversation_id,))
        assert cursor.fetchone()[0] == 1


def test_postgres_context_slots_merge_and_are_page_scoped(
    isolated_database_url: str,
) -> None:
    repository = PostgresConversationRepository(isolated_database_url)
    sender_id = f"psid-{uuid.uuid4().hex}"
    event = InboxEvent(
        event_id=f"event-{uuid.uuid4().hex}",
        page_id=PageCode.CFC,
        sender_id=sender_id,
        message=NormalizedMessage(
            mid=f"mid-{uuid.uuid4().hex}",
            sender_id=sender_id,
            recipient_id="configured-page",
            timestamp=datetime.now(UTC),
            text="Tìm đại lý",
        ),
    )
    scheduled = repository.ingest(event, debounce_seconds=1, max_batch_seconds=5)
    assert scheduled is not None
    conversation_id = scheduled[0]
    state = repository.update_context(
        PageCode.CFC,
        conversation_id,
        workflow=WorkflowType.DEALER_LOOKUP,
        primary_intent=IntentType.DEALER_LOOKUP,
        slots={"province": "Kiên Giang"},
    )
    assert state.current_workflow == WorkflowType.DEALER_LOOKUP.value
    repository.update_context(
        PageCode.CFC,
        conversation_id,
        workflow=WorkflowType.DEALER_LOOKUP,
        primary_intent=IntentType.DEALER_LOOKUP,
        slots={"district": "Rạch Giá"},
    )
    assert repository.load_slots(
        PageCode.CFC, conversation_id, WorkflowType.DEALER_LOOKUP
    ) == {"province": "Kiên Giang", "district": "Rạch Giá"}
    assert repository.load_slots(
        PageCode.ZEO, conversation_id, WorkflowType.DEALER_LOOKUP
    ) == {}
    context = repository.load_understanding_context(PageCode.CFC, conversation_id)
    assert context["current_intent"] == IntentType.DEALER_LOOKUP.value
    assert context["current_slots"] == {
        "province": "Kiên Giang",
        "district": "Rạch Giá",
    }
    assert context["recent_customer_messages"][-1]["text"] == "Tìm đại lý"
