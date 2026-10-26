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
