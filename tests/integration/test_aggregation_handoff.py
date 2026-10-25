from datetime import datetime, timedelta, timezone

from src.chatbot.modules.aggregation.service import MessageAggregator
from src.chatbot.modules.conversations.state_machine import (
    ConversationStateStore,
    final_send_allowed,
)
from src.chatbot.shared.enums import Ownership, PageCode
from src.chatbot.shared.events import NormalizedMessage


def _message(mid: str, text: str) -> NormalizedMessage:
    return NormalizedMessage(
        mid=mid,
        sender_id="psid-1",
        recipient_id="page-cfc",
        timestamp=datetime.now(timezone.utc),
        text=text,
    )


def test_four_messages_in_six_seconds_make_one_batch() -> None:
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
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

