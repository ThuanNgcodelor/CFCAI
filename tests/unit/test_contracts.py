import json
from pathlib import Path


def load_yaml(f):
    try:
        import yaml

        return yaml.safe_load(f)
    except ImportError:
        # pyrefly: ignore[missing-import]
        from ruamel.yaml import YAML

        y = YAML(typ="safe")
        return y.load(f)


from src.chatbot.core.settings import settings
from src.chatbot.shared.enums import (
    CatalogStatus,
    IntentType,
    OutboxStatus,
    Ownership,
    PageCode,
    WorkflowType,
)
from src.chatbot.shared.events import InboxEvent, NormalizedMessage


def test_enums_integrity():
    assert PageCode.CFC.value == "CFC"
    assert PageCode.ZEO.value == "ZEO"
    assert Ownership.AI.value == "AI"
    assert Ownership.HUMAN.value == "HUMAN"
    assert IntentType.PRICE_INQUIRY.value == "PRICE_INQUIRY"
    assert WorkflowType.PRICE_HANDOFF.value == "PRICE_HANDOFF"
    assert OutboxStatus.SUPPRESSED.value == "SUPPRESSED"
    assert CatalogStatus.QUARANTINED.value == "QUARANTINED"


def test_regression_cases_fixture():
    fixture_path = Path("tests/fixtures/regression_cases.json")
    assert fixture_path.exists(), "regression_cases.json must exist"

    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    assert len(cases) == 12, "Must contain exactly 12 regression test cases (T01 - T12)"
    case_ids = [c["id"] for c in cases]
    for i in range(1, 13):
        expected_id = f"T{i:02d}"
        assert expected_id in case_ids, f"Missing test case {expected_id}"


def test_page_configs_integrity():
    for page_code in ["cfc", "zeo"]:
        config_path = Path(f"config/pages/{page_code}.yaml")
        assert config_path.exists(), f"Config file {config_path} must exist"
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = load_yaml(f)
            assert cfg["page"]["code"] == page_code.upper()
            assert cfg["pricing"]["mode"] == "HUMAN_HANDOFF"
            assert "PRICE_INQUIRY" in cfg["workflows"]


def test_event_models_instantiation():
    msg = NormalizedMessage(
        mid="mid_123",
        sender_id="sender_456",
        recipient_id="page_789",
        timestamp="2026-10-25T00:00:00Z",
        text="Xin giá phân bón",
    )
    inbox = InboxEvent(
        event_id="evt_123", page_id=PageCode.CFC, sender_id="sender_456", message=msg
    )
    assert inbox.page_id == PageCode.CFC
    assert inbox.message.text == "Xin giá phân bón"


def test_settings_load():
    assert settings.POSTGRES_PORT == 5432
    assert settings.REDIS_PORT in {6379, 6385}
    assert settings.DEBOUNCE_SECONDS == 5.0
