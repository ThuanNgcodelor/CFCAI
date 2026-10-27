"""Safe inbound-to-outbox orchestration with Phase 5 Business Workflows and Response Composer."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from src.chatbot.infrastructure.messaging.outbox import OutboxStore
from src.chatbot.modules.conversations.repository import PostgresConversationRepository
from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    CompositeKnowledgeStore,
    DealerLookupResult,
    KnowledgeSearchResult,
    PostgresKnowledgeStore,
)
from src.chatbot.modules.ops.controls import OpsControlStore
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    workflow_for_intent,
)
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.modules.workflows.policy_validator import OutputPolicyValidator
from src.chatbot.modules.workflows.sla import calculate_contact_deadline
from src.chatbot.shared.enums import IntentType, Ownership, PageCode, WorkflowType
from src.chatbot.shared.events import InboxEvent, OutboxMessageSchema


def filter_slots_for_workflow(
    workflow: WorkflowType, slots: dict[str, Any]
) -> dict[str, Any]:
    common_keys = {
        "phone",
        "location",
        "province",
        "district",
        "ward",
        "area",
        "parent_province",
        "admin_area_id",
        "admin_level",
        "crop",
        "product",
        "stage",
        "problem",
        "product_mentions",
        "detected_skus",
        "detected_formulas",
    }
    dealer_state_keys = {
        "dealer_search_status",
        "dealer_search_area",
        "dealer_parent_province",
        "dealer_match_scope",
    }
    if workflow == WorkflowType.PRICE_HANDOFF:
        allowed = common_keys | {"quantity", "unit"}
    elif workflow == WorkflowType.ORDER_TRACKING:
        allowed = {"order_code", "phone"}
    elif workflow == WorkflowType.DEALER_LOOKUP:
        allowed = common_keys | dealer_state_keys
    elif workflow in {WorkflowType.PRODUCT_INQUIRY, WorkflowType.AGRICULTURE_ADVICE}:
        allowed = common_keys
    else:
        allowed = common_keys
    return {k: v for k, v in slots.items() if k in allowed and v is not None}


class SafeMessagePipeline:
    def __init__(
        self,
        outbox: OutboxStore,
        controls: OpsControlStore | None = None,
        intent_analyzer: HybridInputAnalyzer | None = None,
        knowledge_store: ApprovedKnowledgeStore
        | PostgresKnowledgeStore
        | CompositeKnowledgeStore
        | None = None,
        conversation_repository: PostgresConversationRepository | None = None,
        composer: ResponseComposer | None = None,
        order_store: Any | None = None,
    ) -> None:
        self.outbox = outbox
        self.controls = controls or OpsControlStore()
        self.intent_analyzer = intent_analyzer
        self.knowledge_store = knowledge_store
        self.conversation_repository = conversation_repository
        self.composer = composer or ResponseComposer()
        self.order_store = order_store

    def _search_knowledge(
        self,
        page_id: PageCode,
        query: str,
        *,
        limit: int,
        record_prefix: str | tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> list[Any]:
        result = self._search_knowledge_result(
            page_id,
            query,
            limit=limit,
            record_prefix=record_prefix,
            categories=categories,
        )
        return list(result.records) if result.status == "CONFIDENT" else []

    def _search_knowledge_result(
        self,
        page_id: PageCode,
        query: str,
        *,
        limit: int,
        record_prefix: str | tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> KnowledgeSearchResult:
        if not self.knowledge_store:
            return KnowledgeSearchResult("NO_MATCH")
        confidence_search = getattr(
            self.knowledge_store, "search_with_confidence", None
        )
        if callable(confidence_search):
            return confidence_search(
                page_id,
                query,
                limit=limit,
                record_prefix=record_prefix,
                categories=categories,
            )
        try:
            records = self.knowledge_store.search(
                page_id,
                query,
                limit=limit,
                record_prefix=record_prefix,
                categories=categories,
            )
        except TypeError:
            # Keep third-party/test stores compatible while the metadata-aware
            # store contract rolls out.
            records = self.knowledge_store.search(page_id, query, limit, record_prefix)
        return KnowledgeSearchResult(
            "CONFIDENT" if records else "NO_MATCH",
            tuple(records[:limit]),
        )

    def _resolve_dealer_lookup(
        self,
        page_id: PageCode,
        slots: dict[str, object],
        customer_text: str,
    ) -> DealerLookupResult:
        """Resolve a dealer through exact admin data before considering GPS.

        The result is explicit even when no CRM record can be confirmed, so a
        later turn never has to pretend that the data are merely "updating".
        """
        location = str(
            slots.get("location")
            or slots.get("district")
            or slots.get("ward")
            or slots.get("province")
            or ""
        ).strip()
        area = None
        if self.intent_analyzer:
            normalizer = self.intent_analyzer.normalizer
            area = normalizer.area_resolver.by_id(str(slots.get("admin_area_id") or ""))
            if area is None:
                area = normalizer.resolve_location(
                    location,
                    parent_province=str(slots.get("province") or "") or None,
                )

        resolver = getattr(self.knowledge_store, "resolve_dealers", None)
        if callable(resolver):
            return resolver(page_id, location, area=area, limit=3)

        if not location and area is None:
            return DealerLookupResult(status="LOCATION_REQUIRED")
        if self.knowledge_store:
            search_term = location or customer_text
            matches = self._search_knowledge(
                page_id,
                search_term,
                limit=3,
                record_prefix=("dealer:",),
            )
            if matches:
                from src.chatbot.modules.knowledge.retriever import DealerCandidate

                return DealerLookupResult(
                    status="CONFIRMED_MATCH",
                    area_label=area.canonical if area else location or None,
                    parent_province=(
                        area.parent_province
                        if area and area.level != "province"
                        else (area.canonical if area else None)
                    ),
                    match_scope="EXACT_ADDRESS_TEXT",
                    candidates=tuple(
                        DealerCandidate(record=match) for match in matches[:3]
                    ),
                )
        return DealerLookupResult(
            status="NO_CONFIRMED_MATCH",
            area_label=area.canonical if area else location or None,
            parent_province=(
                area.parent_province
                if area and area.level != "province"
                else (area.canonical if area else None)
            ),
        )

    @staticmethod
    def classify(text: str | None) -> IntentType:
        raw = (text or "").lower()
        cleaned = re.sub(r"(?<=[a-zA-Z0-9À-ỹ])[._]+(?=[a-zA-Z0-9À-ỹ])", " ", raw)
        cleaned = re.sub(r"(?<=[a-zA-ZÀ-ỹ])(?=\d)|(?<=\d)(?=[a-zA-ZÀ-ỹ])", " ", cleaned)
        if any(
            w in cleaned
            for w in (
                "giá",
                "gia",
                "bao nhiêu",
                "bao nhieu",
                "price",
                "báo giá",
                "bao gia",
                "mấy tiền",
                "may tien",
                "chi phí",
                "chi phi",
            )
        ):
            return IntentType.PRICE_INQUIRY
        if any(
            w in cleaned
            for w in (
                "số điện thoại",
                "so dien thoai",
                "số liên hệ",
                "so lien he",
                "hotline",
                "liên hệ ai",
                "lien he ai",
                "gọi số nào",
                "goi so nao",
            )
        ):
            return IntentType.CONTACT_REQUEST
        if any(
            w in cleaned
            for w in (
                "đại lý",
                "dai ly",
                "ở đâu",
                "o dau",
                "mua ở đâu",
                "mua o dau",
                "cửa hàng",
                "cua hang",
            )
        ):
            return IntentType.DEALER_LOOKUP
        if any(
            w in cleaned
            for w in (
                "đơn hàng",
                "don hang",
                "mã đơn",
                "ma don",
                "tra cứu đơn",
                "tra cuu don",
                "kiểm tra đơn",
                "kiem tra don",
                "đơn tới đâu",
                "don toi dau",
                "hỏi đơn",
                "hoi don",
                "xem đơn",
                "xem don",
            )
        ) or re.search(r"\b(?:đơn|don)\s+[a-z0-9_-]+", cleaned):
            return IntentType.ORDER_TRACKING
        if any(
            w in cleaned
            for w in (
                "phân bón",
                "phan bon",
                "hữu cơ",
                "huu co",
                "cobanic",
                "cabonic",
                "npk",
                "mua",
            )
        ):
            return IntentType.PRODUCT_INQUIRY
        if any(
            w in cleaned
            for w in (
                "người thật",
                "nguoi that",
                "nhân viên",
                "nhan vien",
                "tư vấn viên",
                "admin",
            )
        ):
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

        # Check for image attachments
        attachments = event.message.attachments or []
        has_images = any(att.get("type") == "image" for att in attachments)
        attachment_types = sorted(
            {
                str(attachment.get("type") or "").casefold()
                for attachment in attachments
                if attachment.get("type")
            }
        )
        if attachment_types:
            # Only structural metadata reaches the understanding layer.  URLs
            # and raw provider payloads remain outside the LLM prompt.
            context["attachment_types"] = attachment_types

        analysis = None
        if self.intent_analyzer and (text or attachment_types):
            analysis = self.intent_analyzer.analyze(event.page_id, text, context)
            intent = analysis.primary_intent
        else:
            intent = self.classify(text)

        workflow = workflow_for_intent(intent)
        slot_source = (
            analysis.extracted_slots
            if analysis is not None
            else dict(context.get("current_slots", {}))
        )
        effective_slots: dict[str, object] = {
            key: value
            for key, value in slot_source.items()
            if value is not None and value != ""
        }
        effective_slots = filter_slots_for_workflow(workflow, effective_slots)

        image_inquiry = has_images and not text.strip()
        if has_images and self.intent_analyzer:
            has_product_reference = bool(
                analysis
                and (
                    analysis.detected_skus
                    or analysis.product_mentions
                    or analysis.extracted_slots.get("detected_skus")
                    or analysis.extracted_slots.get("product_mentions")
                )
            )
            configured_image_intent = self.intent_analyzer.normalizer.attachment_intent(
                "image",
                event.page_id,
                intent,
                normalized_text=self.intent_analyzer.normalizer.normalize(text),
                has_product_reference=has_product_reference,
            )
            image_inquiry = configured_image_intent == intent
        elif has_images:
            image_inquiry = intent not in {
                IntentType.PRICE_INQUIRY,
                IntentType.PRICE_INQUIRY_DETAIL,
                IntentType.DEALER_LOOKUP,
                IntentType.ORDER_TRACKING,
                IntentType.SALES_LEAD,
                IntentType.HUMAN_REQUEST,
                IntentType.CONTACT_REQUEST,
            }

        dealer_lookup: DealerLookupResult | None = None
        previously_no_confirmed_match = (
            str(
                dict(context.get("current_slots", {})).get("dealer_search_status") or ""
            )
            == "NO_CONFIRMED_MATCH"
        )
        if intent == IntentType.DEALER_LOOKUP:
            dealer_lookup = self._resolve_dealer_lookup(
                event.page_id,
                effective_slots,
                text,
            )
            effective_slots.update(dealer_lookup.state_slots())
            effective_slots = filter_slots_for_workflow(workflow, effective_slots)

        effective_conversation_version = conversation_version
        if self.conversation_repository and batch_version is not None:
            state = self.conversation_repository.update_context(
                event.page_id,
                conversation_id,
                workflow=workflow,
                primary_intent=intent,
                slots=effective_slots,
            )
            effective_conversation_version = state.version

        handoff_created = False
        handoff_intents = {
            IntentType.PRICE_INQUIRY,
            IntentType.PRICE_INQUIRY_DETAIL,
            IntentType.HUMAN_REQUEST,
        }
        sales_lead_complete = (
            intent == IntentType.SALES_LEAD
            and bool(effective_slots.get("phone"))
            and bool(
                effective_slots.get("location")
                or effective_slots.get("district")
                or effective_slots.get("province")
            )
        )
        if (
            (intent in handoff_intents or sales_lead_complete)
            and self.conversation_repository
            and batch_version is not None
        ):
            create_handoff = getattr(
                self.conversation_repository, "create_handoff_task", None
            )
            if callable(create_handoff):
                task_id = create_handoff(
                    event.page_id,
                    conversation_id,
                    batch_version=batch_version,
                    workflow=workflow,
                    reason=intent.value,
                    slots=effective_slots,
                )
                handoff_created = bool(task_id)

        _, deadline_text = calculate_contact_deadline()
        answer = "Mình đã nhận được tin nhắn và sẽ phản hồi sớm."
        grounding_texts: list[str] = []

        # Attachment-led requests use their configured workflow even when Meta
        # delivers a caption and images as separate events in the same batch.
        if image_inquiry:
            answer = self.composer.compose_image_inquiry_response(
                event.page_id,
                slots=effective_slots,
                deadline_text=deadline_text,
                customer_text=text,
            )

        # Branch 1: Price Inquiries (INV-1: zero price hallucination)
        elif intent in {IntentType.PRICE_INQUIRY, IntentType.PRICE_INQUIRY_DETAIL}:
            answer = self.composer.compose_price_response(
                event.page_id,
                slots=effective_slots,
                deadline_text=deadline_text,
                ad_title=ad_title,
                customer_text=text,
                customer_key=event.sender_id,
                handoff_created=handoff_created,
            )

        # Branch 2: Human request
        elif intent == IntentType.HUMAN_REQUEST:
            answer = self.composer.compose_human_handoff_response(
                event.page_id,
                handoff_created=handoff_created,
            )

        # Branch 2b: deterministic, config-backed contact directory
        elif intent == IntentType.CONTACT_REQUEST:
            answer = self.composer.compose_contact_response(
                event.page_id,
                customer_key=event.sender_id,
                customer_text=text,
            )

        # Branch 2c: dealer/distributor onboarding. A handoff is only confirmed
        # after both contact and area are present and the durable task exists.
        elif intent == IntentType.SALES_LEAD:
            answer = self.composer.compose_sales_lead_response(
                event.page_id,
                slots=effective_slots,
                handoff_created=handoff_created,
            )

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

            search_result = KnowledgeSearchResult("NO_MATCH", strategy="product")
            if self.knowledge_store:
                search_result = self._search_knowledge_result(
                    PageCode(event.page_id),
                    search_query,
                    limit=2,
                    record_prefix=("product:", "crm-product:"),
                )
            product_record = (
                search_result.records[0]
                if search_result.status == "CONFIDENT" and search_result.records
                else None
            )
            if product_record:
                grounding_texts.extend(
                    [str(product_record.title), str(product_record.content)]
                )
            answer = self.composer.compose_product_response(
                event.page_id,
                product_record=product_record,
                ambiguous=search_result.status == "AMBIGUOUS",
                slots=effective_slots,
                ad_title=ad_title,
                deadline_text=deadline_text,
                customer_text=text,
            )

        # Branch 4: Dealer lookup
        elif intent == IntentType.DEALER_LOOKUP:
            if dealer_lookup:
                for record in dealer_lookup.records:
                    grounding_texts.extend([record.title, record.content])
            answer = self.composer.compose_dealer_response(
                event.page_id,
                dealers=dealer_lookup.records if dealer_lookup else [],
                slots=effective_slots,
                deadline_text=deadline_text,
                customer_text=text,
                lookup_result=dealer_lookup,
                previously_no_confirmed_match=previously_no_confirmed_match,
            )

        # Branch 5: Agriculture advice. Retrieval is restricted to source
        # metadata for this workflow; an unrelated FAQ can never win by a
        # shared word such as "phân" or "trái".
        elif intent == IntentType.AGRI_ADVICE:
            query_parts = [text]
            for key in (
                "crop",
                "stage",
                "problem",
                "product",
                "product_mentions",
                "detected_skus",
            ):
                value = effective_slots.get(key)
                if isinstance(value, list):
                    query_parts.extend(str(item) for item in value)
                elif value:
                    query_parts.append(str(value))
            categories: tuple[str, ...] = ()
            if self.intent_analyzer:
                filters = self.intent_analyzer.normalizer.filters_for_workflow(
                    WorkflowType.AGRICULTURE_ADVICE
                )
                categories = filters.get("categories", ())
            matches = self._search_knowledge(
                PageCode(event.page_id),
                " ".join(query_parts),
                limit=1,
                record_prefix="faq:",
                categories=categories or None,
            )
            if matches:
                grounding_texts.extend([matches[0].title, matches[0].content])
            answer = self.composer.compose_agriculture_response(
                event.page_id,
                advice_record=matches[0] if matches else None,
                slots=effective_slots,
                deadline_text=deadline_text,
                customer_text=text,
                customer_key=event.sender_id,
            )

        # Branch 6: Order Tracking
        elif intent == IntentType.ORDER_TRACKING:
            phone = effective_slots.get("phone")
            if not phone and text:
                phone_match = re.search(r"(?:\+?84|0)(?:[\s.\-]?\d){9,10}(?!\d)", text)
                if phone_match:
                    digits = re.sub(r"\D", "", phone_match.group(0))
                    if digits.startswith("84"):
                        digits = "0" + digits[2:]
                    if re.match(r"^0[235789]\d{8}$|^02\d{9}$", digits):
                        phone = digits

            order_code = effective_slots.get("order_code")
            if not order_code and text:
                order_pat = re.compile(
                    r"\b(?:đơn\s*hàng|đơn|mã\s*đơn|mã|don\s*hang|don|ma\s*don|ma)\s*[:#\-]?\s*([A-Za-z0-9_-]{3,20})\b",
                    re.IGNORECASE,
                )
                m = order_pat.search(text)
                if m:
                    extracted = m.group(1).strip()
                    if extracted != str(phone):
                        order_code = extracted
                if not order_code:
                    standalone = re.search(
                        r"\b(?:[A-Za-z]{2,6}[0-9\-_]{2,12}|00\d{4,8})\b", text
                    )
                    if standalone and standalone.group(0) != str(phone):
                        order_code = standalone.group(0)

            orders = []
            order = None
            if self.order_store:
                if order_code:
                    order = self.order_store.find_by_code(str(order_code))
                elif phone:
                    orders = self.order_store.find_by_phone(str(phone))

            answer = self.composer.compose_order_response(
                event.page_id,
                orders=orders,
                order=order,
                phone=str(phone) if phone else None,
                order_code=str(order_code) if order_code else None,
                deadline_text=deadline_text,
                customer_text=text,
            )

        # Branch 6: General FAQ / Greetings / Special topics
        else:
            lower_text = text.lower()
            is_career = False
            is_homecare = False
            is_greeting = False
            if self.intent_analyzer:
                is_career = self.intent_analyzer.normalizer.contains(
                    "career_markers", lower_text
                )
                is_homecare = self.intent_analyzer.normalizer.contains(
                    "homecare_markers", lower_text
                )
                is_greeting = (
                    self.intent_analyzer.normalizer.contains(
                        "greeting_markers", lower_text
                    )
                    and len(lower_text.split()) <= 4
                )
            else:
                is_career = any(
                    w in lower_text
                    for w in [
                        "tuyển dụng",
                        "tuyen dung",
                        "việc làm",
                        "vị trí",
                        "ứng tuyển",
                        "xin việc",
                    ]
                )
                is_homecare = any(
                    re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", lower_text)
                    for marker in [
                        "nước giặt",
                        "rửa chén",
                        "zeo",
                        "oplus",
                        "pano",
                        "bột giặt",
                    ]
                )
                is_greeting = (
                    any(
                        lower_text.startswith(g)
                        for g in ["chào", "xin chào", "hello", "hi", "alo"]
                    )
                    and len(lower_text.split()) <= 4
                )

            if is_career:
                answer = self.composer.compose_career_response()
            elif event.page_id == PageCode.CFC and is_homecare:
                answer = self.composer.compose_homecare_response()
            elif is_greeting:
                answer = self.composer.compose_greeting_response(
                    event.page_id, ad_title=ad_title
                )
            elif has_images:
                answer = self.composer.compose_image_inquiry_response(
                    event.page_id,
                    slots=effective_slots,
                    deadline_text=deadline_text,
                    customer_text=text,
                )
            else:
                matches = []
                if self.knowledge_store and text:
                    matches = self._search_knowledge(
                        PageCode(event.page_id), text, limit=1, record_prefix="faq:"
                    )
                if matches:
                    grounding_texts.extend([matches[0].title, matches[0].content])
                    answer = matches[0].content
                else:
                    answer = self.composer.compose_greeting_response(
                        event.page_id, ad_title=ad_title
                    )

        # Final safety validation (Policy guard: zero-price, no jargon, persona, placeholders)
        allowed_phones: set[str] = set()
        if self.composer and self.composer.contact_directory:
            allowed_phones.update(
                self.composer.contact_directory.allowed_phones(event.page_id)
            )
        validation = OutputPolicyValidator.validate(
            answer,
            page_id=event.page_id,
            workflow=workflow,
            slots=effective_slots,
            allowed_phones=allowed_phones,
            deadline_text=deadline_text,
            handoff_created=handoff_created,
            grounding_texts=grounding_texts,
        )
        answer = validation.text

        delivery_batch_version = batch_version
        if delivery_batch_version is None:
            delivery_batch_version = (
                int.from_bytes(
                    hashlib.sha256(event.event_id.encode("utf-8")).digest()[:4],
                    "big",
                )
                & 0x7FFFFFFF
            )

        return self.outbox.enqueue(
            OutboxMessageSchema(
                conversation_id=conversation_id,
                page_id=event.page_id,
                recipient_id=event.sender_id,
                text=answer,
                batch_version=delivery_batch_version,
                expected_conversation_version=effective_conversation_version,
                expected_ownership=Ownership.AI,
                workflow=workflow,
            )
        )
