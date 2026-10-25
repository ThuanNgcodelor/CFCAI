"""Deterministic message debounce and batch fencing."""

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from src.chatbot.modules.conversations.state_machine import ConversationStateStore
from src.chatbot.shared.enums import Ownership, PageCode
from src.chatbot.shared.events import NormalizedMessage


class BatchSchedule(BaseModel):
    conversation_id: str
    page_id: PageCode
    batch_version: int
    due_at: datetime
    first_at: datetime
    last_at: datetime
    message_ids: List[str] = Field(default_factory=list)


class ReadyBatch(BaseModel):
    conversation_id: str
    page_id: PageCode
    sender_id: str
    batch_version: int
    messages: List[NormalizedMessage]
    expected_state_version: int


class MessageAggregator:
    """Reference debounce implementation.

    Each inbound message is retained until a batch is claimed.  A newer
    message increments the batch version, making any stale AI result invalid
    at the final-send guard.  Production persistence must implement the same
    transitions transactionally in PostgreSQL.
    """

    def __init__(
        self,
        state_store: ConversationStateStore,
        *,
        debounce_seconds: float = 5.0,
        max_batch_seconds: float = 20.0,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if debounce_seconds <= 0 or max_batch_seconds <= 0:
            raise ValueError("debounce and max batch durations must be positive")
        if debounce_seconds > max_batch_seconds:
            raise ValueError("debounce cannot exceed max batch duration")
        self._state_store = state_store
        self._debounce = timedelta(seconds=debounce_seconds)
        self._max_batch = timedelta(seconds=max_batch_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._pending: Dict[str, List[NormalizedMessage]] = {}
        self._first_at: Dict[str, datetime] = {}
        self._due_at: Dict[str, datetime] = {}
        self._lock = RLock()

    def ingest(
        self,
        *,
        conversation_id: str,
        page_id: PageCode,
        sender_id: str,
        message: NormalizedMessage,
    ) -> BatchSchedule:
        now = self._clock()
        with self._lock:
            state = self._state_store.get_or_create(conversation_id, page_id, sender_id)
            if state.ownership != Ownership.AI:
                return BatchSchedule(
                    conversation_id=conversation_id,
                    page_id=page_id,
                    batch_version=state.batch_version,
                    due_at=now,
                    first_at=now,
                    last_at=now,
                    message_ids=[],
                )

            pending = self._pending.setdefault(conversation_id, [])
            pending.append(message)
            first_at = self._first_at.setdefault(conversation_id, now)
            batch_state = self._state_store.bump_batch(conversation_id)
            due_at = min(now + self._debounce, first_at + self._max_batch)
            self._due_at[conversation_id] = due_at
            return BatchSchedule(
                conversation_id=conversation_id,
                page_id=page_id,
                batch_version=batch_state.batch_version,
                due_at=due_at,
                first_at=first_at,
                last_at=now,
                message_ids=[item.mid for item in pending],
            )

    def claim_ready(
        self, conversation_id: str, *, now: Optional[datetime] = None
    ) -> Optional[ReadyBatch]:
        now = now or self._clock()
        with self._lock:
            due_at = self._due_at.get(conversation_id)
            pending = self._pending.get(conversation_id, [])
            if due_at is None or not pending or now < due_at:
                return None

            state = self._state_store.snapshot(conversation_id)
            if state.ownership != Ownership.AI:
                self._clear(conversation_id)
                return None

            batch = ReadyBatch(
                conversation_id=conversation_id,
                page_id=state.page_id,
                sender_id=state.sender_id,
                batch_version=state.batch_version,
                messages=list(pending),
                expected_state_version=state.version,
            )
            self._clear(conversation_id)
            return batch

    def _clear(self, conversation_id: str) -> None:
        self._pending.pop(conversation_id, None)
        self._first_at.pop(conversation_id, None)
        self._due_at.pop(conversation_id, None)
