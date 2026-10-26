"""Integration tests for Phase 5 Business Workflows and Response Composer."""

import datetime
from zoneinfo import ZoneInfo

from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    CompositeKnowledgeStore,
    KnowledgeRecord,
    PostgresKnowledgeStore,
    RedisCrmDealerStore,
    RedisCrmProductStore,
)
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    VietnameseNormalizer,
)
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.modules.workflows.support_contacts import SupportContactDirectory
from src.chatbot.shared.enums import IntentTransition, IntentType, PageCode
from src.chatbot.shared.events import (
    InboxEvent,
    IntentAnalysisResult,
    NormalizedMessage,
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class MockIntentClient:
    def __init__(self, intent: IntentType, slots: dict | None = None):
        self.intent = intent
        self.slots = slots or {}

    def analyze(self, page_id: str, text: str, context: dict | None = None) -> IntentAnalysisResult:
        return IntentAnalysisResult(
            primary_intent=self.intent,
            confidence=0.95,
            extracted_slots=self.slots,
            detected_skus=self.slots.get("detected_skus", []),
            product_mentions=self.slots.get("product_mentions", []),
        )


def _make_event(text: str, referral: dict | None = None) -> InboxEvent:
    return InboxEvent(
        event_id="evt-wf-1",
        page_id=PageCode.CFC,
        sender_id="customer-test",
        message=NormalizedMessage(
            mid="mid-wf-1",
            sender_id="customer-test",
            recipient_id="page-cfc",
            timestamp=datetime.datetime.now(datetime.UTC),
            text=text,
            referral=referral,
        ),
    )


def test_workflow_price_inquiry_without_phone():
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox)
    event = _make_event("gia.bao.nhieu1bao")
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    # Zero-price compliance
    assert "Dạ giá 1 bao phân" in reply or "bạn kinh doanh sẽ báo giá" in reply
    assert "số điện thoại" in reply
    assert "nha 🌾" in reply


def test_workflow_price_inquiry_with_phone():
    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(MockIntentClient(IntentType.PRICE_INQUIRY), normalizer)
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer)
    event = _make_event("Giá bao nhiêu 1 bao vậy em? Số anh 0918123456 ở Cần Thơ")
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "0918123456" in reply
    assert "liên hệ trực tiếp" in reply or "báo giá chi tiết" in reply


def test_workflow_product_cobanic_fallback_template():
    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(IntentType.PRODUCT_INQUIRY, {"detected_skus": ["Cobanic 21"]}),
        normalizer,
    )
    store = CompositeKnowledgeStore(
        PostgresKnowledgeStore(),
        RedisCrmProductStore(),
        RedisCrmDealerStore(),
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer, knowledge_store=store)
    event = _make_event(
        "có phân bón Cabonic 21 ko",
        referral={"ad_title": "Mít sắp vô bông mà lá còn nhỏ, rễ còn thưa - sao yên tâm?"},
    )
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "Cobanic" in reply
    assert "điểm bán" in reply or "tỉnh/huyện" in reply
    assert "số điện thoại" in reply


def test_workflow_product_with_llm_generator():
    class MockGenerator:
        def __init__(self):
            self.last_payload = None

        def generate(self, payload):
            self.last_payload = payload
            # Dynamically synthesizes using the passed product info and ad title
            return (
                f"Dạ em chào anh/chị ạ 😊 {payload['thong_tin_san_pham'].split('|')[0].strip()} "
                "bên em có nấm Trichoderma rất tốt cho vườn mít. Để em báo điểm bán gần nhất cho mình, "
                "anh/chị cho em xin tỉnh/huyện và SĐT ạ!"
            )

    gen = MockGenerator()
    composer = ResponseComposer(generator=gen)
    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(IntentType.PRODUCT_INQUIRY, {"detected_skus": ["Cobanic 21"]}),
        normalizer,
    )
    store = CompositeKnowledgeStore(
        PostgresKnowledgeStore(),
        RedisCrmProductStore(),
        RedisCrmDealerStore(),
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer, knowledge_store=store, composer=composer)
    event = _make_event(
        "có phân bón Cabonic 21 ko",
        referral={"ad_title": "Mít sắp vô bông mà lá còn nhỏ, rễ còn thưa - sao yên tâm?"},
    )
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "Cobanic" in reply
    assert "Trichoderma" in reply
    assert "mít" in reply.lower()
    assert gen.last_payload["bai_quang_cao"] == "Mít sắp vô bông mà lá còn nhỏ, rễ còn thưa - sao yên tâm?"


def test_workflow_dealer_lookup_asking_location():
    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(MockIntentClient(IntentType.DEALER_LOOKUP), normalizer)
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer)
    event = _make_event("Tôi muốn tìm đại lý gần nhất")
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "tỉnh/huyện" in reply
    assert "số điện thoại" in reply


def test_workflow_agriculture_uses_approved_metadata_and_slots():
    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(
            IntentType.AGRI_ADVICE,
            {"crop": "cây khách cung cấp", "stage": "giai đoạn khách cung cấp"},
        ),
        normalizer,
    )
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord(
                "faq:approved-agri",
                PageCode.CFC,
                "Câu hỏi nông nghiệp|hướng dẫn cách dùng",
                "Hướng dẫn đã được duyệt theo đúng giai đoạn khách cung cấp.",
                "APPROVED",
                intent="source_agronomy_intent",
                category="agronomy",
            ),
            KnowledgeRecord(
                "faq:unrelated",
                PageCode.CFC,
                "Câu hỏi chung",
                "Không được chọn nội dung này.",
                "APPROVED",
                intent="opening_hours",
                category="faq",
            ),
        ]
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer, knowledge_store=store)
    outbox_id = pipeline.process(_make_event("hướng dẫn cách dùng"))
    assert outbox_id is not None
    assert "Hướng dẫn đã được duyệt" in outbox.messages[outbox_id].text
    assert "Không được chọn" not in outbox.messages[outbox_id].text


def test_workflow_agriculture_asks_context_before_using_generic_match():
    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(IntentType.AGRI_ADVICE),
        normalizer,
    )
    store = ApprovedKnowledgeStore(
        [KnowledgeRecord("faq:agri", PageCode.CFC, "Câu hỏi", "Nội dung không được đoán.", "APPROVED", category="agronomy")]
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer, knowledge_store=store)
    outbox_id = pipeline.process(_make_event("Tôi muốn được tư vấn cách dùng"))
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "loại cây" in reply
    assert "Nội dung không được đoán" not in reply


def test_workflow_dealer_lookup_shows_address_without_google_maps_link():
    class MockDealerStore:
        def search(self, page_id, query, limit=1, record_prefix=None):
            from src.chatbot.modules.knowledge.retriever import KnowledgeRecord
            return [
                KnowledgeRecord(
                    record_id="dealer:DL001",
                    page_id=page_id,
                    title="Đại lý Nông Dược Huỳnh Hưng",
                    content="Đại lý Nông Dược Huỳnh Hưng — Ấp 3, Xã An Hữu, Đồng Tháp",
                    status="APPROVED",
                )
            ]

    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(IntentType.DEALER_LOOKUP, {"location": "Đồng Tháp"}),
        normalizer,
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer, knowledge_store=MockDealerStore())
    event = _make_event("cho mình tìm đại lý ở Đồng Tháp")
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "Huỳnh Hưng" in reply
    assert "Ấp 3, Xã An Hữu, Đồng Tháp" in reply
    assert "maps/search" not in reply
    assert "google.com/maps" not in reply


def test_workflow_image_inquiry_attachment_only():
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox)
    event = InboxEvent(
        event_id="evt-img-1",
        page_id=PageCode.CFC,
        sender_id="customer-img",
        message=NormalizedMessage(
            mid="mid-img-1",
            sender_id="customer-img",
            recipient_id="page-cfc",
            timestamp=datetime.datetime.now(datetime.UTC),
            text="",
            attachments=[{"type": "image", "payload": {"url": "https://example.com/leaf.jpg"}}],
        ),
    )
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "hình ảnh" in reply
    assert "kỹ sư nông nghiệp" in reply or "chuyên viên kỹ thuật" in reply


def test_workflow_order_tracking_with_phone():
    class MockOrderStore:
        def find_by_phone(self, phone: str):
            return [
                {
                    "order_id": "ord-1",
                    "order_code": "SO-2026-999",
                    "status": "Đang vận chuyển",
                    "order_date": "2026-10-25",
                }
            ]

        def find_by_code(self, code: str):
            return None

    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(IntentType.ORDER_TRACKING, {"phone": "0918123456"}),
        normalizer,
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer, order_store=MockOrderStore())
    event = _make_event("Kiểm tra đơn hàng giúp anh, số 0918123456")
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "SO-2026-999" in reply
    assert "Đang vận chuyển" in reply


def test_workflow_order_tracking_with_code():
    class MockOrderStore:
        def find_by_phone(self, phone: str):
            return []

        def find_by_code(self, code: str):
            if code == "00003328":
                return {
                    "order_id": 13067,
                    "order_code": "00003328",
                    "status": "Đã thực hiện",
                    "order_date": "2026-05-28",
                }
            return None

    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(IntentType.ORDER_TRACKING, {"order_code": "00003328"}),
        normalizer,
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer, order_store=MockOrderStore())
    event = _make_event("tra cứu đơn hàng 00003328")
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "00003328" in reply
    assert "Đã thực hiện" in reply


def test_workflow_image_inquiry_on_zeo_page():
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox)
    event = InboxEvent(
        event_id="evt-img-zeo-1",
        page_id=PageCode.ZEO,
        sender_id="customer-zeo",
        message=NormalizedMessage(
            mid="mid-img-zeo-1",
            sender_id="customer-zeo",
            recipient_id="page-zeo",
            timestamp=datetime.datetime.now(datetime.UTC),
            text="",
            attachments=[{"type": "image", "payload": {"url": "https://example.com/soap.jpg"}}],
        ),
    )
    outbox_id = pipeline.process(event)
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "ZeO" in reply
    assert "Cò Bay" not in reply


def test_deterministic_slot_extraction_order_code_and_phone():
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    slots1 = normalizer.deterministic_slots("tra cứu đơn hàng 00003328")
    assert slots1.get("order_code") == "00003328"

    slots2 = normalizer.deterministic_slots("đơn hàng DHPB06-320 của số 0972669456")
    assert slots2.get("order_code") == "DHPB06-320"
    assert slots2.get("phone") == "0972669456"


def test_deterministic_slot_extraction_location_gazetteer():
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")

    kien_giang = normalizer.deterministic_slots("Kiên giang")
    assert kien_giang["location"] == "Kiên Giang"
    assert kien_giang["province"] == "Kiên Giang"
    assert kien_giang["admin_level"] == "province"

    tphcm = normalizer.deterministic_slots("tphcm")
    assert tphcm["location"] == "Hồ Chí Minh"
    assert tphcm["province"] == "Hồ Chí Minh"
    assert tphcm["admin_level"] == "province"


def test_deterministic_slot_extraction_copies_crop_and_stage_without_dictionary():
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    slots = normalizer.deterministic_slots("bón cho cây mít ở giai đoạn nuôi trái")
    assert slots["crop"] == "mít"
    assert slots["stage"] == "nuôi trái"


def test_dealer_context_keeps_location_when_customer_sends_phone():
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(MockIntentClient(IntentType.UNKNOWN), normalizer)

    result = analyzer.analyze(
        PageCode.CFC,
        "0388509046",
        {
            "current_intent": IntentType.DEALER_LOOKUP.value,
            "current_slots": {"location": "Kiên Giang", "province": "Kiên Giang"},
        },
    )

    assert result.primary_intent == IntentType.DEALER_LOOKUP
    assert result.extracted_slots["location"] == "Kiên Giang"
    assert result.extracted_slots["province"] == "Kiên Giang"
    assert result.extracted_slots["phone"] == "0388509046"


def test_missing_dealer_with_phone_confirms_location_and_phone():
    outbox = InMemoryOutboxStore()
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(
            IntentType.DEALER_LOOKUP,
            {"location": "Kiên Giang", "province": "Kiên Giang", "phone": "0388509046"},
        ),
        normalizer,
    )
    pipeline = SafeMessagePipeline(outbox, intent_analyzer=analyzer)

    outbox_id = pipeline.process(_make_event("0388509046"))
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "Kiên Giang" in reply
    assert "chưa có điểm bán được xác nhận" in reply
    assert "đang cập nhật" not in reply
    assert "[moc_hen_lien_he]" not in reply
    assert "khu vực nào" not in reply


def test_placeholder_sanitizer_replaces_deadline_markers():
    reply = ResponseComposer.sanitize_placeholders(
        "Em sẽ liên hệ trước [moc_hen_lien_he] ([deadline]) [unknown_marker].",
        "15h hôm nay",
    )

    assert reply == "Em sẽ liên hệ trước 15h hôm nay (15h hôm nay)."


def test_placeholder_sanitizer_handles_all_supported_template_syntaxes():
    reply = ResponseComposer.sanitize_placeholders(
        "A {unknown} {{second}} ${third} [fourth] "
        "trước {moc\\_hen\\_lien\\_he}.",
        "16h hôm nay",
    )

    assert "unknown" not in reply
    assert "second" not in reply
    assert "third" not in reply
    assert "fourth" not in reply
    assert "{" not in reply and "[" not in reply and "$" not in reply
    assert "16h hôm nay" in reply


def test_cobanic_product_reply_rejects_phone_placeholder_without_customer_phone():
    class LeakingGenerator:
        def generate(self, payload):
            return (
                "Anh/chị muốn tìm mua Hữu cơ Cobanic 21, đúng rồi nhé! "
                "Em sẽ để lại số điện thoại {so\\_dien\\_thoai\\_khach} "
                "để kinh doanh liên hệ báo giá."
            )

    composer = ResponseComposer(generator=LeakingGenerator())
    record = KnowledgeRecord(
        "product:cobanic-21",
        PageCode.CFC,
        "Hữu cơ Cobanic 21",
        "Phân hữu cơ 21%, bao 25kg",
        "APPROVED",
    )

    reply = composer.compose_product_response(
        PageCode.CFC,
        product_record=record,
        slots={},
        customer_text="Tôi muốn tìm mua Hữu cơ Cobanic 21",
        deadline_text="18h30 hôm nay",
    )

    assert "so_dien_thoai_khach" not in reply
    assert "{" not in reply and "}" not in reply
    assert "Em sẽ để lại số điện thoại" not in reply
    assert "tỉnh/huyện" in reply


def test_generated_reply_cannot_claim_customer_phone_when_slot_is_missing():
    class FalseClaimGenerator:
        def generate(self, payload):
            return "Dạ em đã ghi nhận số điện thoại của anh/chị để nhân viên gọi lại."

    composer = ResponseComposer(generator=FalseClaimGenerator())
    record = KnowledgeRecord(
        "product:safe",
        PageCode.CFC,
        "Sản phẩm đã duyệt",
        "Nội dung đã duyệt",
        "APPROVED",
    )

    reply = composer.compose_product_response(
        PageCode.CFC,
        product_record=record,
        slots={},
    )

    assert "đã ghi nhận số điện thoại" not in reply
    assert "tỉnh/huyện" in reply


def test_contact_request_and_price_use_configured_contacts():
    directory = SupportContactDirectory.from_file(
        "config/business/support_contacts.json"
    )
    composer = ResponseComposer(contact_directory=directory)
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    analyzer = HybridInputAnalyzer(
        MockIntentClient(IntentType.GENERAL_FAQ),
        normalizer,
    )

    contact_outbox = InMemoryOutboxStore()
    contact_pipeline = SafeMessagePipeline(
        contact_outbox,
        intent_analyzer=analyzer,
        composer=composer,
    )
    contact_id = contact_pipeline.process(_make_event("Cho tôi xin số hotline"))
    assert contact_id is not None
    contact_reply = contact_outbox.messages[contact_id].text
    assert "Trưởng phòng Kinh doanh Lê Trọng Nhơn" in contact_reply
    assert "0981 205 448" in contact_reply
    assert "1900 5307" in contact_reply

    price_outbox = InMemoryOutboxStore()
    price_pipeline = SafeMessagePipeline(
        price_outbox,
        intent_analyzer=analyzer,
        composer=composer,
    )
    price_id = price_pipeline.process(_make_event("Xin giá Cobanic 21"))
    assert price_id is not None
    price_reply = price_outbox.messages[price_id].text
    assert "0981 205 448" in price_reply
    assert "1900 5307" in price_reply
    assert "đồng" not in price_reply.lower()


def test_filter_slots_prunes_order_code_from_price_and_dealer_workflows():
    from src.chatbot.modules.orchestration.pipeline import filter_slots_for_workflow
    from src.chatbot.shared.enums import WorkflowType

    polluted_slots = {
        "phone": "0388509046",
        "area": "Kiên Giang",
        "product": "Cobanic 30",
        "quantity": "1",
        "unit": "bao",
        "order_code": "0000332",
    }
    price_slots = filter_slots_for_workflow(WorkflowType.PRICE_HANDOFF, polluted_slots)
    assert "order_code" not in price_slots
    assert price_slots["phone"] == "0388509046"
    assert price_slots["quantity"] == "1"

    dealer_slots = filter_slots_for_workflow(WorkflowType.DEALER_LOOKUP, polluted_slots)
    assert "order_code" not in dealer_slots
    assert "quantity" not in dealer_slots
    assert dealer_slots["area"] == "Kiên Giang"


def test_product_inquiry_marker_recognition():
    normalizer = VietnameseNormalizer("config/normalization/vi_intent.json")
    assert normalizer.contains("product_markers", "có phân bón npk ko")
    analyzer = HybridInputAnalyzer(MockIntentClient(IntentType.UNKNOWN), normalizer)
    result = analyzer.analyze(PageCode.CFC, "Có phân bón npk ko", {"current_intent": "DEALER_LOOKUP"})
    assert result.primary_intent == IntentType.PRODUCT_INQUIRY
    assert result.intent_transition == IntentTransition.SWITCH


def test_dealer_lookup_requires_location_and_does_not_match_product_tokens():
    import json

    from src.chatbot.modules.knowledge.retriever import RedisCrmDealerStore

    class FakeRedis:
        def get(self, key):
            if key == "cfc:dealers:locations":
                return json.dumps([
                    {
                        "name": "CÔNG TY TNHH MỘT THÀNH VIÊN PHÂN BÓN HỮU CƠ ĐẬM ĐẶC",
                        "address": None,
                        "code": None,
                    },
                    {
                        "name": "Đại lý Phân Bón Tuấn Kiệt",
                        "address": "Số 475 Tổ 1, Ấp An Điền, Xã Châu Thành, Tỉnh Tây Ninh",
                        "code": "DL002",
                    },
                ])
            return None

    store = RedisCrmDealerStore()
    store._redis = FakeRedis()

    # Query with product tokens and no location
    query = "Tôi muốn tìm mua Hữu cơ Cobanic 21\nTôi muốn tìm đại lý gần nhất"
    matches = store.search(PageCode.CFC, query, limit=1, record_prefix=("dealer:",))
    # Must NOT match the organic fertilizer dealer with no address
    assert len(matches) == 0

    # Query with specific dealer location
    loc_matches = store.search(PageCode.CFC, "Tây Ninh", limit=1, record_prefix=("dealer:",))
    assert len(loc_matches) == 1
    assert loc_matches[0].title == "Đại lý Phân Bón Tuấn Kiệt"
    assert "Tây Ninh" in loc_matches[0].content

    unaccented_matches = store.search(PageCode.CFC, "Tay Ninh", limit=1, record_prefix=("dealer:",))
    assert len(unaccented_matches) == 1
