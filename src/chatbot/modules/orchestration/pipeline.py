"""Minimal safe inbound-to-outbox orchestration.

This first production slice intentionally replies only with a neutral
acknowledgement. Product answers and prices remain behind approved workflows.
"""

from __future__ import annotations

import hashlib

from src.chatbot.infrastructure.messaging.outbox import OutboxStore
from src.chatbot.modules.conversations.repository import PostgresConversationRepository
from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    CompositeKnowledgeStore,
    PostgresKnowledgeStore,
)
from src.chatbot.modules.ops.controls import OpsControlStore
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    workflow_for_intent,
)
from src.chatbot.shared.enums import IntentType, Ownership, PageCode
from src.chatbot.shared.events import InboxEvent, OutboxMessageSchema


class SafeMessagePipeline:
    def __init__(
        self,
        outbox: OutboxStore,
        controls: OpsControlStore | None = None,
        intent_analyzer: HybridInputAnalyzer | None = None,
        knowledge_store: ApprovedKnowledgeStore | PostgresKnowledgeStore | CompositeKnowledgeStore | None = None,
        conversation_repository: PostgresConversationRepository | None = None,
    ) -> None:
        self.outbox = outbox
        self.controls = controls or OpsControlStore()
        self.intent_analyzer = intent_analyzer
        self.knowledge_store = knowledge_store
        self.conversation_repository = conversation_repository

    @staticmethod
    def classify(text: str | None) -> IntentType:
        normalized = (text or "").lower()
        if any(word in normalized for word in ("giá", "bao nhiêu", "price", "báo giá")):
            return IntentType.PRICE_INQUIRY
        return IntentType.GENERAL_FAQ

    def process(
        self,
        event: InboxEvent,
        *,
        batch_version: int | None = None,
        conversation_version: int | None = None,
    ) -> str | None:
        if not self.controls.can_auto_reply(event.page_id):
            return None
        text = event.message.text or ""
        conversation_id = f"{event.page_id.value}:{event.sender_id}"
        context: dict[str, object] = {}
        if self.conversation_repository and batch_version is not None:
            context = self.conversation_repository.load_understanding_context(
                event.page_id, conversation_id
            )
        analysis = None
        if self.intent_analyzer and text:
            analysis = self.intent_analyzer.analyze(event.page_id, text, context)
            intent = analysis.primary_intent
        else:
            intent = self.classify(text)

        effective_conversation_version = conversation_version
        if self.conversation_repository and batch_version is not None:
            workflow = workflow_for_intent(intent)
            state = self.conversation_repository.update_context(
                event.page_id,
                conversation_id,
                workflow=workflow,
                primary_intent=intent,
                slots=analysis.extracted_slots if analysis else {},
            )
            effective_conversation_version = state.version

        # Safety intents are final and can never be overwritten by retrieval.
        if intent in {
            IntentType.PRICE_INQUIRY,
            IntentType.PRICE_INQUIRY_DETAIL,
            IntentType.HUMAN_REQUEST,
        }:
            return None

        matches = []
        product_query = intent == IntentType.PRODUCT_INQUIRY
        dealer_query = intent == IntentType.DEALER_LOOKUP
        if self.knowledge_store and text:
            matches = self.knowledge_store.search(
                PageCode(event.page_id), text, limit=1,
                record_prefix=("dealer:",) if dealer_query else (("product:", "crm-product:") if product_query else "faq:"),
            )
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
        delivery_batch_version = batch_version
        if delivery_batch_version is None:
            delivery_batch_version = int.from_bytes(
                hashlib.sha256(event.event_id.encode("utf-8")).digest()[:4],
                "big",
            ) & 0x7FFFFFFF
        return self.outbox.enqueue(
            OutboxMessageSchema(
                conversation_id=conversation_id,
                page_id=event.page_id,
                recipient_id=event.sender_id,
                text=answer,
                batch_version=delivery_batch_version,
                expected_conversation_version=effective_conversation_version,
                expected_ownership=Ownership.AI,
            )
        )
