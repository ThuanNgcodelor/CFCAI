from datetime import UTC, datetime
from typing import Any

# pyrefly: ignore[missing-import]
from pydantic import BaseModel, ConfigDict, Field

from src.chatbot.shared.enums import (
    IntentTransition,
    IntentType,
    OutboxStatus,
    Ownership,
    PageCode,
    WorkflowType,
)


class NormalizedMessage(BaseModel):
    mid: str
    sender_id: str
    recipient_id: str
    timestamp: datetime
    text: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    referral: dict[str, Any] | None = None
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
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    primary_intent: IntentType
    intent_transition: IntentTransition = IntentTransition.START
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    product_mentions: list[str] = Field(default_factory=list)
    detected_skus: list[str] = Field(default_factory=list)
    quantity: str | None = None
    unit: str | None = None
    location: str | None = None
    crop: str | None = None
    stage: str | None = None
    problem: str | None = None
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    needs_clarification: bool = False
    clarification_needed: bool = False
    requires_human_handoff: bool = False
    evidence_message_ids: list[str] = Field(default_factory=list)


class OutboxMessageSchema(BaseModel):
    outbox_id: str | None = None
    conversation_id: str
    page_id: PageCode
    recipient_id: str
    text: str
    status: OutboxStatus = OutboxStatus.PENDING
    batch_version: int
    expected_conversation_version: int | None = None
    expected_ownership: Ownership = Ownership.AI
    # Runtime metadata used by the release policy. It is not customer-facing
    # knowledge and remains optional for compatibility with existing outbox rows.
    workflow: WorkflowType | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
