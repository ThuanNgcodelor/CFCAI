import uuid
from datetime import UTC, datetime

# pyrefly: ignore[missing-import]
from fastapi.testclient import TestClient

from apps.api.main import app
from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.conversations.repository import PostgresConversationRepository
from src.chatbot.modules.ops.controls import OpsControlStore
from src.chatbot.modules.ops.repository import OpsAuditRepository
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.shared.enums import HandoffStatus, PageCode, WorkflowType
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


def test_admin_routes_require_configured_admin_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "test-admin-token")
    with TestClient(app) as client:
        assert client.get("/admin/ops/status").status_code == 403
        assert (
            client.get(
                "/admin/ops/status", headers={"X-Admin-Token": "test-admin-token"}
            ).status_code
            == 200
        )


def test_operator_role_cannot_access_unrelated_admin_area(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "")
    monkeypatch.setattr(settings, "ADMIN_ROLE_TOKENS_JSON", '{"operator":"ops-token"}')
    monkeypatch.setattr(settings, "INBOX_BACKEND", "memory")
    with TestClient(app) as client:
        headers = {"X-Admin-Token": "ops-token"}
        assert client.post("/admin/ops/CFC/pause", headers=headers).status_code == 200
        assert (
            client.get(
                "/admin/catalog/import-batches/CFC/not-a-batch/records", headers=headers
            ).status_code
            == 403
        )


def test_handoff_queue_claim_resolve_and_audit_are_page_scoped(
    isolated_database_url: str,
) -> None:
    repository = PostgresConversationRepository(isolated_database_url)
    sender_id = f"ops-{uuid.uuid4().hex}"
    event = InboxEvent(
        event_id=f"event-{uuid.uuid4().hex}",
        page_id=PageCode.CFC,
        sender_id=sender_id,
        message=NormalizedMessage(
            mid=f"mid-{uuid.uuid4().hex}",
            sender_id=sender_id,
            recipient_id="page-cfc",
            text="xin báo giá",
            timestamp=datetime.now(UTC),
        ),
    )
    scheduled = repository.ingest(event, debounce_seconds=1, max_batch_seconds=5)
    assert scheduled is not None
    conversation_id, batch_version, _ = scheduled
    task_id = repository.create_handoff_task(
        PageCode.CFC,
        conversation_id,
        batch_version=batch_version,
        workflow=WorkflowType.PRICE_HANDOFF,
        reason="PRICE_INQUIRY",
        slots={"phone": "0981205448"},
    )
    assert task_id is not None
    assert repository.list_handoff_tasks(page_id=PageCode.CFC)[0]["status"] == "PENDING"

    claimed = repository.claim_handoff_task(
        PageCode.CFC,
        task_id,
        actor="sales-operator",
        reason="assigned sales queue",
    )
    assert claimed["status"] == HandoffStatus.CLAIMED.value
    resolved = repository.resolve_handoff_task(
        PageCode.CFC,
        task_id,
        actor="sales-operator",
        resolution="customer contacted",
    )
    assert resolved["status"] == HandoffStatus.RESOLVED.value

    events = OpsAuditRepository(isolated_database_url).list_events(page_id=PageCode.CFC)
    assert [event["action"] for event in events] == ["HANDOFF_RESOLVE", "HANDOFF_CLAIM"]
    assert all("0981205448" not in str(event["details"]) for event in events)
