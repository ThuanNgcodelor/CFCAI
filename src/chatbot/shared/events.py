from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.chatbot.shared.enums import (
    IntentType,
    OutboxStatus,
    Ownership,
    PageCode,
)


class NormalizedMessage(BaseModel):
    mid: str
    sender_id: str
    recipient_id: str
    timestamp: datetime
    text: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class InboxEvent(BaseModel):
    event_id: str
    page_id: PageCode
    sender_id: str
    message: NormalizedMessage
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MessageBatch(BaseModel):
    batch_id: str
    conversation_id: str
    page_id: PageCode
    sender_id: str
    messages: list[NormalizedMessage]
    batch_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntentAnalysisResult(BaseModel):
    primary_intent: IntentType
    confidence: float
    detected_skus: list[str] = Field(default_factory=list)
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    clarification_needed: bool = False
    requires_human_handoff: bool = False


class OutboxMessageSchema(BaseModel):
    outbox_id: str | None = None
    conversation_id: str
    page_id: PageCode
    recipient_id: str
    text: str
    status: OutboxStatus = OutboxStatus.PENDING
    batch_version: int
    expected_ownership: Ownership = Ownership.AI
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
