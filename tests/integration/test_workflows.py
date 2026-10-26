"""Integration tests for Phase 5 Business Workflows and Response Composer."""

import datetime
from zoneinfo import ZoneInfo

from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.knowledge.retriever import (
    CompositeKnowledgeStore,
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
from src.chatbot.shared.enums import IntentType, PageCode
from src.chatbot.shared.events import InboxEvent, IntentAnalysisResult, NormalizedMessage

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


def test_workflow_dealer_lookup_with_google_maps_link():
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
    assert "maps/search" in reply
    assert "google.com/maps" in reply


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


