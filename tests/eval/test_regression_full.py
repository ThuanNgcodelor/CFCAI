"""Executable T01-T12 production regression matrix.

The JSON fixture is the readable contract; these tests execute the relevant
domain component for every case instead of merely checking that IDs exist.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from src.chatbot.infrastructure.messaging.inbox import DurableInboxStore
from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.aggregation.service import MessageAggregator
from src.chatbot.modules.conversations.state_machine import (
    ConversationStateStore,
    final_send_allowed,
)
from src.chatbot.modules.integrations.excel.importer import ExcelCatalogImporter
from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    KnowledgeRecord,
)
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    VietnameseNormalizer,
)
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.shared.enums import (
    CatalogStatus,
    IntentTransition,
    IntentType,
    PageCode,
)
from src.chatbot.shared.events import (
    InboxEvent,
    IntentAnalysisResult,
    NormalizedMessage,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    case["id"]: case
    for case in json.loads(
        (ROOT / "tests/fixtures/regression_cases.json").read_text(encoding="utf-8")
    )
}


class StaticIntentClient:
    def __init__(self, result: IntentAnalysisResult) -> None:
        self.result = result

    def analyze(self, page_id: str, text: str, context=None) -> IntentAnalysisResult:
        return self.result.model_copy(deep=True)


class FailingIntentClient:
    def analyze(self, page_id: str, text: str, context=None) -> IntentAnalysisResult:
        raise OSError("bounded model timeout")


class FakeHandoffRepository:
    def __init__(self, context: dict | None = None) -> None:
        self.context = context or {}
        self.tasks: list[dict] = []

    def load_understanding_context(self, page_id, conversation_id):
        return self.context

    def update_context(self, page_id, conversation_id, **kwargs):
        return SimpleNamespace(version=1)

    def create_handoff_task(self, page_id, conversation_id, **kwargs):
        self.tasks.append({"page_id": page_id, "conversation_id": conversation_id, **kwargs})
        return "handoff-test"


def _normalizer() -> VietnameseNormalizer:
    return VietnameseNormalizer(ROOT / "config/normalization/vi_intent.json")


def _event(text: str, *, page: PageCode = PageCode.CFC, suffix: str = "1") -> InboxEvent:
    return InboxEvent(
        event_id=f"regression-event-{suffix}",
        page_id=page,
        sender_id=f"regression-user-{suffix}",
        message=NormalizedMessage(
            mid=f"regression-mid-{suffix}",
            sender_id=f"regression-user-{suffix}",
            recipient_id=f"page-{page.value.casefold()}",
            timestamp=datetime.now(UTC),
            text=text,
        ),
    )


def _pipeline_reply(
    text: str,
    result: IntentAnalysisResult,
    *,
    knowledge_store=None,
    context: dict | None = None,
) -> tuple[str, FakeHandoffRepository]:
    outbox = InMemoryOutboxStore()
    repository = FakeHandoffRepository(context)
    pipeline = SafeMessagePipeline(
        outbox,
        intent_analyzer=HybridInputAnalyzer(StaticIntentClient(result), _normalizer()),
        knowledge_store=knowledge_store,
        conversation_repository=repository,
    )
    outbox_id = pipeline.process(_event(text), batch_version=1)
    assert outbox_id is not None
    return outbox.messages[outbox_id].text, repository


def test_t01_bulk_price_creates_handoff_without_quote_or_crop_question() -> None:
    case = CASES["T01"]
    reply, repository = _pipeline_reply(
        case["input_messages"][0],
        IntentAnalysisResult(primary_intent=IntentType.PRICE_INQUIRY, confidence=0.9),
    )
    assert repository.tasks and repository.tasks[0]["reason"] == "PRICE_INQUIRY"
    assert "đã tạo yêu cầu báo giá" in reply.casefold()
    assert "loại cây" not in reply.casefold()
    assert not any(currency in reply.casefold() for currency in ("đồng", " vnd", " nghìn"))


def test_t02_bare_crop_detail_retains_open_price_context() -> None:
    case = CASES["T02"]
    analyzer = HybridInputAnalyzer(
        StaticIntentClient(
            IntentAnalysisResult(primary_intent=IntentType.AGRI_ADVICE, confidence=0.8)
        ),
        _normalizer(),
    )
    result = analyzer.analyze(
        PageCode.CFC,
        case["input_messages"][0],
        {"current_intent": IntentType.PRICE_INQUIRY.value, "current_slots": {}},
    )
    assert result.primary_intent == IntentType.PRICE_INQUIRY_DETAIL
    assert result.intent_transition == IntentTransition.CONTINUE
    assert result.extracted_slots["crop"] == "mít"


def test_t03_explicit_tonnage_price_never_outputs_price() -> None:
    case = CASES["T03"]
    reply, repository = _pipeline_reply(
        case["input_messages"][0],
        IntentAnalysisResult(
            primary_intent=IntentType.PRICE_INQUIRY,
            confidence=0.95,
            extracted_slots={"product": "Cobanic 30", "quantity": "1", "unit": "tấn"},
        ),
    )
    assert repository.tasks
    assert "1 tấn" not in reply or "giá" not in reply.split("1 tấn")[0][-10:]
    assert "đồng" not in reply.casefold()


def test_t04_dealer_lookup_asks_region_without_forcing_phone() -> None:
    case = CASES["T04"]
    reply, _ = _pipeline_reply(
        case["input_messages"][0],
        IntentAnalysisResult(primary_intent=IntentType.DEALER_LOOKUP, confidence=0.95),
    )
    assert "tỉnh/huyện" in reply
    assert "có thể để lại số điện thoại" in reply
    assert "cho em xin số điện thoại" not in reply.casefold()


def test_t05_short_price_followup_retains_product_slot() -> None:
    case = CASES["T05"]
    analyzer = HybridInputAnalyzer(
        StaticIntentClient(
            IntentAnalysisResult(primary_intent=IntentType.PRICE_INQUIRY, confidence=0.9)
        ),
        _normalizer(),
    )
    result = analyzer.analyze(
        PageCode.CFC,
        case["input_messages"][0],
        {
            "current_intent": IntentType.PRODUCT_INQUIRY.value,
            "current_slots": {"product_mentions": ["Cobanic"]},
        },
    )
    assert result.primary_intent == IntentType.PRICE_INQUIRY
    assert result.extracted_slots["product_mentions"] == ["Cobanic"]


def test_t06_specific_product_returns_only_confident_match() -> None:
    case = CASES["T06"]
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord(
                "product:cobanic-21",
                PageCode.CFC,
                "Hữu cơ Cobanic 21",
                "Hữu cơ Cobanic 21, bao 25kg",
                "APPROVED",
            ),
            KnowledgeRecord(
                "product:unrelated",
                PageCode.CFC,
                "Sản phẩm khác",
                "Nội dung khác",
                "APPROVED",
            ),
        ]
    )
    reply, _ = _pipeline_reply(
        case["input_messages"][0],
        IntentAnalysisResult(
            primary_intent=IntentType.PRODUCT_INQUIRY,
            confidence=0.95,
            detected_skus=["Hữu cơ Cobanic 21"],
            extracted_slots={"detected_skus": ["Hữu cơ Cobanic 21"]},
        ),
        knowledge_store=store,
    )
    assert "Hữu cơ Cobanic 21" in reply
    assert "Sản phẩm khác" not in reply
    assert "tỉnh/huyện" in reply


def test_t07_four_rapid_messages_form_one_batch() -> None:
    case = CASES["T07"]
    start = datetime(2026, 10, 27, tzinfo=UTC)
    now = [start]
    aggregator = MessageAggregator(
        ConversationStateStore(),
        debounce_seconds=5,
        max_batch_seconds=20,
        clock=lambda: now[0],
    )
    for index, item in enumerate(case["input_burst"]):
        now[0] = start + timedelta(milliseconds=item["delay_ms"])
        aggregator.ingest(
            conversation_id="CFC:regression-burst",
            page_id=PageCode.CFC,
            sender_id="regression-burst",
            message=_event(item["text"], suffix=str(index)).message,
        )
    batch = aggregator.claim_ready(
        "CFC:regression-burst", now=start + timedelta(seconds=10)
    )
    assert batch is not None
    assert len(batch.messages) == len(case["input_burst"])


def test_t08_takeover_invalidates_stale_ai_result() -> None:
    _ = CASES["T08"]
    states = ConversationStateStore()
    initial = states.get_or_create("CFC:race", PageCode.CFC, "race")
    states.takeover("CFC:race", actor="agent", reason="manual reply")
    assert not final_send_allowed(
        states.snapshot("CFC:race"),
        expected_version=initial.version,
        expected_batch_version=initial.batch_version,
    )


def test_t09_duplicate_webhook_event_is_recorded_once() -> None:
    case = CASES["T09"]
    inbox = DurableInboxStore()
    event = _event("hello", suffix=case["event_id"])
    event.event_id = case["event_id"]
    inserted = [inbox.record_event(event) for _ in range(case["repeat_count"])]
    assert inserted == [True, False, False]
    assert inbox.count_events() == case["expected_processed_count"]


def test_t10_cfc_retrieval_never_reads_zeo_record() -> None:
    case = CASES["T10"]
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord(
                "faq:zeo-secret",
                PageCode.ZEO,
                "Zeolite xử lý nước hồ tôm",
                "Dữ liệu riêng ZEO không được lộ.",
                "APPROVED",
            )
        ]
    )
    outbox = InMemoryOutboxStore()
    pipeline = SafeMessagePipeline(outbox, knowledge_store=store)
    outbox_id = pipeline.process(_event(case["input_messages"][0]))
    assert outbox_id is not None
    reply = outbox.messages[outbox_id].text
    assert "Dữ liệu riêng ZEO" not in reply
    assert "Cò Bay" in reply


def test_t11_conflicting_excel_skus_are_quarantined_as_conflict(tmp_path: Path) -> None:
    _ = CASES["T11"]
    source = tmp_path / "catalog.xlsx"
    source.write_bytes(b"regression fixture")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mapping_version": 1,
                "sources": [
                    {
                        "page_id": "CFC",
                        "path": str(source),
                        "sheets": {
                            "Products": {
                                "record_type": "product",
                                "required_fields": ["sku", "name"],
                                "fields": {
                                    "sku": "SKU",
                                    "name": "Name",
                                    "specs": "Specs",
                                },
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    importer = ExcelCatalogImporter(mapping)
    importer.reader = SimpleNamespace(
        read_sheets=lambda _: {
            "Products": [
                {"SKU": "DUP-01", "Name": "Product", "Specs": "A"},
                {"SKU": "DUP-01", "Name": "Product", "Specs": "B"},
            ]
        }
    )
    report = importer.import_page(PageCode.CFC)
    assert report["conflict_count"] == 2
    assert {item["status"] for item in importer.staged_products} == {
        CatalogStatus.CONFLICT.value
    }


def test_t12_llm_timeout_uses_bounded_deterministic_fallback() -> None:
    case = CASES["T12"]
    analyzer = HybridInputAnalyzer(FailingIntentClient(), _normalizer())
    result = analyzer.analyze(PageCode.CFC, "xin giá Cobanic", {})
    assert result.primary_intent == IntentType.PRICE_INQUIRY
    assert result.requires_human_handoff
    assert case["expected_action"] == "GRACEFUL_FALLBACK_OR_HANDOFF"
