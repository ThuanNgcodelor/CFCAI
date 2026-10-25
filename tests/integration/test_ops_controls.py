from datetime import UTC, datetime

from fastapi.testclient import TestClient

from apps.api.main import app
from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.ops.controls import OpsControlStore
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import InboxEvent, NormalizedMessage


def test_kill_switch_and_pause_are_page_scoped() -> None:
    controls = OpsControlStore()
    controls.pause(PageCode.CFC)
    assert not controls.can_auto_reply(PageCode.CFC)
    assert controls.can_auto_reply(PageCode.ZEO)
    controls.resume(PageCode.CFC)
    controls.set_enabled(PageCode.ZEO, False)
    assert controls.can_auto_reply(PageCode.CFC)
    assert not controls.can_auto_reply(PageCode.ZEO)


def test_pipeline_respects_page_kill_switch() -> None:
    controls = OpsControlStore()
    controls.set_enabled(PageCode.CFC, False)
    event = InboxEvent(
        event_id="ops-1",
        page_id=PageCode.CFC,
        sender_id="psid",
        message=NormalizedMessage(
            mid="mid",
            sender_id="psid",
            recipient_id="page",
            text="hello",
            timestamp=datetime.now(UTC),
        ),
    )
    assert SafeMessagePipeline(InMemoryOutboxStore(), controls).process(event) is None


def test_ops_api_pause_resume() -> None:
    client = TestClient(app)
    assert client.post("/admin/ops/CFC/pause").json()["paused"] is True
    assert client.get("/admin/ops/status").json()["CFC"]["paused"] is True
    assert client.post("/admin/ops/CFC/resume").json()["paused"] is False
