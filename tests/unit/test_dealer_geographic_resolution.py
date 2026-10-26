"""Evidence-based dealer lookup regression tests."""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace

from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.knowledge.retriever import RedisCrmDealerStore
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    VietnameseNormalizer,
)
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.shared.administrative_areas import (
    AdministrativeArea,
    AdministrativeAreaResolver,
)
from src.chatbot.shared.enums import IntentType, PageCode
from src.chatbot.shared.events import (
    InboxEvent,
    IntentAnalysisResult,
    NormalizedMessage,
)


class FakeRedis:
    def __init__(self, dealers: list[dict[str, object]]) -> None:
        self._payload = json.dumps(dealers, ensure_ascii=False)

    def get(self, key: str) -> str | None:
        return self._payload if key == "cfc:dealers:locations" else None


def dealer_store(dealers: list[dict[str, object]]) -> RedisCrmDealerStore:
    store = object.__new__(RedisCrmDealerStore)
    store._redis = FakeRedis(dealers)
    return store


def normalizer() -> VietnameseNormalizer:
    return VietnameseNormalizer("config/normalization/vi_intent.json")


def test_administrative_gazetteer_resolves_unaccented_district_and_parent_province():
    slots = normalizer().deterministic_slots("Tôi ở thoi lai")

    assert slots["location"] == "Thới Lai"
    assert slots["district"] == "Thới Lai"
    assert slots["province"] == "Cần Thơ"
    assert slots["parent_province"] == "Cần Thơ"
    assert slots["admin_area_id"] == "vn-can-tho-thoi-lai"


def test_configured_province_replaces_builtin_province_aliases(tmp_path):
    source = tmp_path / "areas.json"
    source.write_text(
        json.dumps(
            {
                "areas": [
                    {
                        "id": "configured-can-tho",
                        "canonical": "Cần Thơ",
                        "level": "province",
                        "aliases": ["Can Tho", "CT"],
                        "latitude": 10.03,
                        "longitude": 105.78,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    resolver = AdministrativeAreaResolver.from_file(
        source,
        fallback_areas=[
            AdministrativeArea(
                area_id="builtin-can-tho",
                canonical="Cần Thơ",
                level="province",
                aliases=("Cần Thơ",),
            )
        ],
    )

    area = resolver.resolve("CT")

    assert area is not None
    assert area.area_id == "configured-can-tho"
    assert area.has_coordinates


def test_exact_district_returns_at_most_three_address_backed_dealers_without_map_link():
    area = normalizer().resolve_location("thoi lai")
    assert area is not None
    store = dealer_store(
        [
            {
                "name": f"Đại lý Thới Lai {index}",
                "code": f"TL{index}",
                "address": f"Ấp {index}, Huyện Thới Lai, Cần Thơ",
            }
            for index in range(1, 5)
        ]
        + [
            {
                "name": "Đại lý khác tỉnh",
                "code": "OTHER",
                "address": "Châu Thành, Hậu Giang",
            }
        ]
    )

    result = store.resolve_dealers(PageCode.CFC, "Thới Lai", area=area, limit=10)

    assert result.status == "CONFIRMED_MATCH"
    assert result.match_scope == "EXACT_ADMIN_AREA"
    assert len(result.candidates) == 3
    reply = ResponseComposer().compose_dealer_response(
        PageCode.CFC,
        dealers=result.records,
        slots=result.state_slots(),
        lookup_result=result,
    )
    assert "Đại lý Thới Lai 1" in reply
    assert "Đại lý Thới Lai 3" in reply
    assert "Đại lý Thới Lai 4" not in reply
    assert "Google Maps" not in reply
    assert "google.com" not in reply


def test_parent_province_records_without_area_coordinates_are_not_called_nearest():
    area = normalizer().resolve_location("Thới Lai")
    assert area is not None and not area.has_coordinates
    store = dealer_store(
        [
            {
                "name": "Đại lý Cần Thơ",
                "code": "CT1",
                "address": "Quận Ninh Kiều, Cần Thơ",
                "latitude": 10.034,
                "longitude": 105.78,
            }
        ]
    )

    result = store.resolve_dealers(PageCode.CFC, "Thới Lai", area=area)
    first_reply = ResponseComposer().compose_dealer_response(
        PageCode.CFC,
        dealers=result.records,
        slots=result.state_slots(),
        lookup_result=result,
    )
    repeated_reply = ResponseComposer().compose_dealer_response(
        PageCode.CFC,
        dealers=result.records,
        slots=result.state_slots(),
        lookup_result=result,
        previously_no_confirmed_match=True,
    )

    assert result.status == "NO_CONFIRMED_MATCH"
    assert "chưa có điểm bán được xác nhận" in first_reply
    assert "đang cập nhật" not in first_reply
    assert "đã kiểm tra lại" in repeated_reply
    assert "Đại lý Cần Thơ" not in first_reply


def test_gps_distance_fallback_ranks_only_parent_province_dealers_with_coordinates():
    area = AdministrativeArea(
        area_id="test-district",
        canonical="Khu vực kiểm thử",
        level="district",
        parent_province="Cần Thơ",
        aliases=("Khu vực kiểm thử",),
        latitude=10.0,
        longitude=105.7,
    )
    store = dealer_store(
        [
            {
                "name": "Đại lý xa",
                "code": "FAR",
                "address": "Ninh Kiều, Cần Thơ",
                "latitude": 10.3,
                "longitude": 105.9,
            },
            {
                "name": "Đại lý gần",
                "code": "NEAR",
                "address": "Cái Răng, Cần Thơ",
                "latitude": 10.01,
                "longitude": 105.71,
            },
            {
                "name": "Đại lý không GPS",
                "code": "NO-GPS",
                "address": "Bình Thủy, Cần Thơ",
            },
        ]
    )

    result = store.resolve_dealers(PageCode.CFC, area.canonical, area=area)

    assert result.status == "CONFIRMED_MATCH"
    assert result.match_scope == "GPS_DISTANCE"
    assert [candidate.record.title for candidate in result.candidates] == [
        "Đại lý gần",
        "Đại lý xa",
    ]
    assert all(candidate.distance_km is not None for candidate in result.candidates)


class DealerIntentClient:
    def analyze(
        self, page_id: str, text: str, context: dict | None = None
    ) -> IntentAnalysisResult:
        return IntentAnalysisResult(primary_intent=IntentType.DEALER_LOOKUP)


class GeneralFaqIntentClient:
    def analyze(
        self, page_id: str, text: str, context: dict | None = None
    ) -> IntentAnalysisResult:
        return IntentAnalysisResult(primary_intent=IntentType.GENERAL_FAQ)


def test_dealer_challenge_keeps_dealer_workflow_and_prior_search_state():
    result = HybridInputAnalyzer(
        GeneralFaqIntentClient(), normalizer()
    ).analyze(
        PageCode.CFC,
        "Tôi nhớ có mà sao lại cập nhật dữ liệu",
        {
            "current_intent": IntentType.DEALER_LOOKUP.value,
            "current_workflow": "DEALER_LOOKUP",
            "current_slots": {
                "location": "Thới Lai",
                "district": "Thới Lai",
                "province": "Cần Thơ",
                "dealer_search_status": "NO_CONFIRMED_MATCH",
            },
        },
    )

    assert result.primary_intent == IntentType.DEALER_LOOKUP
    assert result.intent_transition.value == "CONTINUE"
    assert result.extracted_slots["location"] == "Thới Lai"
    assert result.extracted_slots["dealer_search_status"] == "NO_CONFIRMED_MATCH"


class CapturingConversationRepository:
    def __init__(self) -> None:
        self.saved_slots: dict[str, object] | None = None

    def load_understanding_context(self, page_id, conversation_id):
        return {"current_slots": {}}

    def update_context(self, page_id, conversation_id, *, workflow, primary_intent, slots):
        self.saved_slots = dict(slots)
        return SimpleNamespace(version=7)


def test_pipeline_persists_no_confirmed_match_in_dealer_dialogue_state():
    repository = CapturingConversationRepository()
    pipeline = SafeMessagePipeline(
        InMemoryOutboxStore(),
        intent_analyzer=HybridInputAnalyzer(DealerIntentClient(), normalizer()),
        knowledge_store=dealer_store(
            [
                {
                    "name": "Đại lý Cần Thơ",
                    "code": "CT1",
                    "address": "Ninh Kiều, Cần Thơ",
                }
            ]
        ),
        conversation_repository=repository,
    )
    event = InboxEvent(
        event_id="dealer-state",
        page_id=PageCode.CFC,
        sender_id="customer",
        message=NormalizedMessage(
            mid="dealer-state-mid",
            sender_id="customer",
            recipient_id="page",
            timestamp=datetime.datetime.now(datetime.UTC),
            text="thoi lai",
        ),
    )

    pipeline.process(event, batch_version=1)

    assert repository.saved_slots is not None
    assert repository.saved_slots["dealer_search_status"] == "NO_CONFIRMED_MATCH"
    assert repository.saved_slots["dealer_search_area"] == "Thới Lai"
