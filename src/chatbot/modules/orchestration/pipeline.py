"""Safe inbound-to-outbox orchestration with Phase 5 Business Workflows and Response Composer."""

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
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.modules.workflows.sla import calculate_contact_deadline
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
        composer: ResponseComposer | None = None,
    ) -> None:
        self.outbox = outbox
        self.controls = controls or OpsControlStore()
        self.intent_analyzer = intent_analyzer
        self.knowledge_store = knowledge_store
        self.conversation_repository = conversation_repository
        self.composer = composer or ResponseComposer()

    @staticmethod
    def classify(text: str | None) -> IntentType:
        import re

        raw = (text or "").lower()
        cleaned = re.sub(r"(?<=[a-zA-Z0-9À-ỹ])[._]+(?=[a-zA-Z0-9À-ỹ])", " ", raw)
        cleaned = re.sub(r"(?<=[a-zA-ZÀ-ỹ])(?=\d)|(?<=\d)(?=[a-zA-ZÀ-ỹ])", " ", cleaned)
        if any(w in cleaned for w in ("giá", "gia", "bao nhiêu", "bao nhieu", "price", "báo giá", "bao gia", "mấy tiền", "may tien", "chi phí", "chi phi")):
            return IntentType.PRICE_INQUIRY
        if any(w in cleaned for w in ("đại lý", "dai ly", "ở đâu", "o dau", "mua ở đâu", "mua o dau", "cửa hàng", "cua hang")):
            return IntentType.DEALER_LOOKUP
        if any(w in cleaned for w in ("phân bón", "phan bon", "hữu cơ", "huu co", "cobanic", "cabonic", "npk", "mua")):
            return IntentType.PRODUCT_INQUIRY
        if any(w in cleaned for w in ("người thật", "nguoi that", "nhân viên", "nhan vien", "tư vấn viên", "admin")):
            return IntentType.HUMAN_REQUEST
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
            try:
                context = self.conversation_repository.load_understanding_context(
                    event.page_id, conversation_id
                )
            except ValueError:
                context = {}

        # Extract ad referral context if present
        ad_title: str | None = None
        if event.message.referral:
            ad_title = event.message.referral.get("ad_title")
            if ad_title:
                context["ad_title"] = ad_title

        analysis = None
        if self.intent_analyzer and text:
            analysis = self.intent_analyzer.analyze(event.page_id, text, context)
            intent = analysis.primary_intent
        else:
            intent = self.classify(text)

        effective_slots: dict[str, object] = dict(context.get("current_slots", {}))
        if analysis and analysis.extracted_slots:
            effective_slots.update(analysis.extracted_slots)

        # Pre-fill crop slot from ad context if not yet extracted
        if ad_title and not effective_slots.get("crop"):
            lower_ad = ad_title.lower()
            if "mít" in lower_ad:
                effective_slots["crop"] = "Mít"
            elif "sầu riêng" in lower_ad:
                effective_slots["crop"] = "Sầu riêng"
            elif "lúa" in lower_ad:
                effective_slots["crop"] = "Lúa"

        effective_conversation_version = conversation_version
        if self.conversation_repository and batch_version is not None:
            workflow = workflow_for_intent(intent)
            state = self.conversation_repository.update_context(
                event.page_id,
                conversation_id,
                workflow=workflow,
                primary_intent=intent,
                slots=effective_slots,
            )
            effective_conversation_version = state.version

        _, deadline_text = calculate_contact_deadline()
        answer = "Mình đã nhận được tin nhắn và sẽ phản hồi sớm."

        # Branch 1: Price Inquiries (INV-1: zero price hallucination)
        if intent in {IntentType.PRICE_INQUIRY, IntentType.PRICE_INQUIRY_DETAIL}:
            answer = self.composer.compose_price_response(
                event.page_id,
                slots=effective_slots,
                deadline_text=deadline_text,
                ad_title=ad_title,
                customer_text=text,
            )

        # Branch 2: Human request
        elif intent == IntentType.HUMAN_REQUEST:
            answer = self.composer.compose_human_handoff_response(event.page_id)

        # Branch 3: Product inquiries
        elif intent == IntentType.PRODUCT_INQUIRY:
            search_query = text
            if analysis:
                skus = analysis.extracted_slots.get("detected_skus") or []
                mentions = analysis.extracted_slots.get("product_mentions") or []
                if skus:
                    search_query = " ".join(skus)
                elif mentions:
                    search_query = " ".join(mentions)

            matches = []
            if self.knowledge_store:
                matches = self.knowledge_store.search(
                    PageCode(event.page_id),
                    search_query,
                    limit=1,
                    record_prefix=("product:", "crm-product:"),
                )
            product_record = matches[0] if matches else None
            answer = self.composer.compose_product_response(
                event.page_id,
                product_record=product_record,
                slots=effective_slots,
                ad_title=ad_title,
                deadline_text=deadline_text,
                customer_text=text,
            )

        # Branch 4: Dealer lookup
        elif intent == IntentType.DEALER_LOOKUP:
            loc = str(effective_slots.get("location") or effective_slots.get("province") or effective_slots.get("district") or "")
            matches = []
            if self.knowledge_store and (loc or text):
                matches = self.knowledge_store.search(
                    PageCode(event.page_id),
                    loc or text,
                    limit=1,
                    record_prefix=("dealer:",),
                )
            answer = self.composer.compose_dealer_response(
                event.page_id,
                dealers=matches,
                slots=effective_slots,
                deadline_text=deadline_text,
                customer_text=text,
            )

        # Branch 5: General FAQ / Greetings / Special topics
        else:
            lower_text = text.lower()
            if any(w in lower_text for w in ["tuyển dụng", "tuyen dung", "việc làm", "vị trí", "ứng tuyển", "xin việc"]):
                answer = self.composer.compose_career_response()
            elif event.page_id == PageCode.CFC and any(w in lower_text for w in ["nước giặt", "rửa chén", "zeo", "oplus", "pano", "bột giặt"]):
                answer = self.composer.compose_homecare_response()
            elif any(lower_text.startswith(g) for g in ["chào", "xin chào", "hello", "hi", "alo"]) and len(lower_text.split()) <= 4:
                answer = self.composer.compose_greeting_response(event.page_id, ad_title=ad_title)
            else:
                matches = []
                if self.knowledge_store and text:
                    matches = self.knowledge_store.search(
                        PageCode(event.page_id),
                        text,
                        limit=1,
                        record_prefix="faq:",
                    )
                if matches:
                    answer = matches[0].content
                else:
                    answer = self.composer.compose_greeting_response(event.page_id, ad_title=ad_title)

        # Final safety validation (Zero-price check)
        answer = self.composer.validate_no_price(answer)

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
