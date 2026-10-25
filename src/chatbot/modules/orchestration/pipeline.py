"""Minimal safe inbound-to-outbox orchestration.

This first production slice intentionally replies only with a neutral
acknowledgement. Product answers and prices remain behind approved workflows.
"""

from __future__ import annotations

import hashlib

from src.chatbot.infrastructure.messaging.outbox import OutboxStore
from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    CompositeKnowledgeStore,
    PostgresKnowledgeStore,
)
from src.chatbot.modules.llm.ollama import OllamaIntentClient
from src.chatbot.modules.ops.controls import OpsControlStore
from src.chatbot.shared.enums import IntentType, Ownership, PageCode
from src.chatbot.shared.events import InboxEvent, OutboxMessageSchema


class SafeMessagePipeline:
    def __init__(
        self,
        outbox: OutboxStore,
        controls: OpsControlStore | None = None,
        intent_client: OllamaIntentClient | None = None,
        knowledge_store: ApprovedKnowledgeStore | PostgresKnowledgeStore | CompositeKnowledgeStore | None = None,
    ) -> None:
        self.outbox = outbox
        self.controls = controls or OpsControlStore()
        self.intent_client = intent_client
        self.knowledge_store = knowledge_store

    @staticmethod
    def classify(text: str | None) -> IntentType:
        normalized = (text or "").lower()
        if any(word in normalized for word in ("giá", "bao nhiêu", "price", "báo giá")):
            return IntentType.PRICE_INQUIRY
        return IntentType.GENERAL_FAQ

    def process(self, event: InboxEvent) -> str | None:
        if not self.controls.can_auto_reply(event.page_id):
            return None
        text = event.message.text or ""
        intent = self.classify(text)
        matches = []
        product_query = any(
            token in text.lower()
            for token in ("sản phẩm", "npk", "zeolite", "pano", "sku", "mã sản phẩm")
        ) or bool(__import__("re").search(r"\d+\s*[-.]\s*\d+", text))
        location_query = any(token in text.lower() for token in ("cần thơ", "kiên giang", "rạch giá", "hậu giang", "an giang"))
        dealer_query = any(token in text.lower() for token in ("đại lý", "nhà phân phối", "điểm mua")) or location_query
        if self.knowledge_store and text:
            matches = self.knowledge_store.search(
                PageCode(event.page_id), text, limit=1,
                record_prefix=("dealer:",) if dealer_query else (("product:", "crm-product:") if product_query else "faq:"),
            )
            if matches:
                intent = IntentType.PRODUCT_INQUIRY if product_query else IntentType.GENERAL_FAQ
        if not matches and not dealer_query and (
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
        answer = "Mình đã nhận được tin nhắn và sẽ phản hồi sớm."
        if dealer_query and matches:
            answer = "Dạ, mình tìm thấy nhà phân phối phù hợp: " + matches[0].content
        elif dealer_query:
            answer = "Dạ mình chưa tìm thấy nhà phân phối trong dữ liệu CRM ở khu vực này. Bạn cho mình xin tỉnh/thành hoặc quận/huyện cụ thể hơn nhé."
        elif matches:
            answer = matches[0].content
        # Every inbound message gets a unique delivery version. Reusing a
        # constant version would collide with the previous outbox row and
        # silently drop subsequent replies on PostgreSQL.
        batch_version = int.from_bytes(
            hashlib.sha256(event.event_id.encode("utf-8")).digest()[:4],
            "big",
        ) & 0x7FFFFFFF
        return self.outbox.enqueue(
            OutboxMessageSchema(
                conversation_id=conversation_id,
                page_id=event.page_id,
                recipient_id=event.sender_id,
                text=answer,
                batch_version=batch_version,
                expected_ownership=Ownership.AI,
            )
        )
