"""Minimal safe inbound-to-outbox orchestration.

This first production slice intentionally replies only with a neutral
acknowledgement. Product answers and prices remain behind approved workflows.
"""

from __future__ import annotations

from src.chatbot.infrastructure.messaging.outbox import OutboxStore
from src.chatbot.modules.llm.ollama import OllamaIntentClient
from src.chatbot.modules.ops.controls import OpsControlStore
from src.chatbot.shared.enums import IntentType, Ownership
from src.chatbot.shared.events import InboxEvent, OutboxMessageSchema


class SafeMessagePipeline:
    def __init__(
        self,
        outbox: OutboxStore,
        controls: OpsControlStore | None = None,
        intent_client: OllamaIntentClient | None = None,
    ) -> None:
        self.outbox = outbox
        self.controls = controls or OpsControlStore()
        self.intent_client = intent_client

    @staticmethod
    def classify(text: str | None) -> IntentType:
        normalized = (text or "").lower()
        if any(word in normalized for word in ("giá", "bao nhiêu", "price", "báo giá")):
            return IntentType.PRICE_INQUIRY
        return IntentType.GENERAL_FAQ

    def process(self, event: InboxEvent) -> str | None:
        if not self.controls.can_auto_reply(event.page_id):
            return None
        intent = self.classify(event.message.text)
        if (
            intent != IntentType.PRICE_INQUIRY
            and self.intent_client
            and event.message.text
        ):
            try:
                intent = self.intent_client.analyze(
                    event.page_id.value, event.message.text
                ).primary_intent
            except (OSError, ValueError, KeyError, TypeError):
                intent = IntentType.GENERAL_FAQ
        # Never auto-answer prices; a future handoff service will create the task.
        if intent == IntentType.PRICE_INQUIRY:
            return None
        conversation_id = f"{event.page_id.value}:{event.sender_id}"
        return self.outbox.enqueue(
            OutboxMessageSchema(
                conversation_id=conversation_id,
                page_id=event.page_id,
                recipient_id=event.sender_id,
                text="Mình đã nhận được tin nhắn và sẽ phản hồi sớm.",
                batch_version=1,
                expected_ownership=Ownership.AI,
            )
        )
