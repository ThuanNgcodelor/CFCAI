"""Conversation ownership state and final-send fencing.

This module intentionally has no Redis/PostgreSQL dependency.  It is the
deterministic domain layer used by both the durable repositories and tests.
"""

from datetime import UTC, datetime
from threading import RLock

from pydantic import BaseModel, Field

from src.chatbot.shared.enums import Ownership, PageCode


class ConversationState(BaseModel):
    conversation_id: str
    page_id: PageCode
    sender_id: str
    ownership: Ownership = Ownership.AI
    version: int = 0
    batch_version: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    owner_reason: str | None = None
    owner_actor: str | None = None


class ConversationStateStore:
    """Thread-safe reference implementation of the ownership state machine.

    Production repositories must persist the same transitions transactionally
    with an optimistic version predicate.  The in-memory implementation keeps
    Phase 2 deterministic while the PostgreSQL repository is introduced.
    """

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._lock = RLock()

    def get_or_create(
        self, conversation_id: str, page_id: PageCode, sender_id: str
    ) -> ConversationState:
        with self._lock:
            current = self._states.get(conversation_id)
            if current is None:
                current = ConversationState(
                    conversation_id=conversation_id,
                    page_id=page_id,
                    sender_id=sender_id,
                )
                self._states[conversation_id] = current
            elif current.page_id != page_id or current.sender_id != sender_id:
                raise ValueError("conversation identity/page scope mismatch")
            return current.model_copy(deep=True)

    def _transition(
        self,
        conversation_id: str,
        *,
        ownership: Ownership,
        actor: str,
        reason: str,
    ) -> ConversationState:
        with self._lock:
            current = self._states[conversation_id]
            current.ownership = ownership
            current.version += 1
            current.batch_version += 1
            current.owner_actor = actor
            current.owner_reason = reason
            current.updated_at = datetime.now(UTC)
            return current.model_copy(deep=True)

    def takeover(
        self, conversation_id: str, actor: str, reason: str
    ) -> ConversationState:
        return self._transition(
            conversation_id,
            ownership=Ownership.HUMAN,
            actor=actor,
            reason=reason,
        )

    def pause(self, conversation_id: str, actor: str, reason: str) -> ConversationState:
        return self._transition(
            conversation_id,
            ownership=Ownership.PAUSED,
            actor=actor,
            reason=reason,
        )

    def resume(
        self, conversation_id: str, actor: str, reason: str
    ) -> ConversationState:
        return self._transition(
            conversation_id,
            ownership=Ownership.AI,
            actor=actor,
            reason=reason,
        )

    def bump_batch(self, conversation_id: str) -> ConversationState:
        with self._lock:
            current = self._states[conversation_id]
            current.batch_version += 1
            current.updated_at = datetime.now(UTC)
            return current.model_copy(deep=True)

    def snapshot(self, conversation_id: str) -> ConversationState:
        with self._lock:
            return self._states[conversation_id].model_copy(deep=True)


def final_send_allowed(
    state: ConversationState,
    *,
    expected_version: int,
    expected_batch_version: int,
) -> bool:
    """Fence an AI send immediately before the provider API call."""

    return (
        state.ownership == Ownership.AI
        and state.version == expected_version
        and state.batch_version == expected_batch_version
    )
