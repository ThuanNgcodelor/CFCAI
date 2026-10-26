import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from src.chatbot.core.settings import settings


@pytest.fixture(autouse=True)
def restore_settings():
    original = {
        "ENVIRONMENT": settings.ENVIRONMENT,
        "CFC_PAGE_ID": settings.CFC_PAGE_ID,
        "ZEO_PAGE_ID": settings.ZEO_PAGE_ID,
        "CFC_APP_SECRET": settings.CFC_APP_SECRET,
        "ZEO_APP_SECRET": settings.ZEO_APP_SECRET,
    }
    yield
    for key, value in original.items():
        setattr(settings, key, value)


def _client() -> TestClient:
    settings.ENVIRONMENT = "test"
    settings.CFC_PAGE_ID = "page-cfc"
    settings.ZEO_PAGE_ID = "page-zeo"
    settings.CFC_APP_SECRET = "cfc-secret"
    settings.ZEO_APP_SECRET = "zeo-secret"
    return TestClient(app)


def _payload(page_id: str, mid: str = "mid-integration") -> bytes:
    return json.dumps(
        {
            "object": "page",
            "entry": [
                {
                    "id": page_id,
                    "time": 1700000000000,
                    "messaging": [
                        {
                            "sender": {"id": "psid-integration"},
                            "recipient": {"id": page_id},
                            "message": {"mid": mid, "text": "Xin chào"},
                        }
                    ],
                }
            ],
        }
    ).encode()


def _signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_webhook_verifies_page_secret_and_deduplicates() -> None:
    client = _client()
    body = _payload("page-cfc", mid=f"mid-integration-{uuid.uuid4().hex}")
    headers = {"X-Hub-Signature-256": _signature(body, "cfc-secret")}

    first = client.post("/webhook", content=body, headers=headers)
    second = client.post("/webhook", content=body, headers=headers)

    assert first.status_code == 200
    assert first.json()["new_recorded"] == 1
    assert second.status_code == 200
    assert second.json()["new_recorded"] == 0


def test_webhook_rejects_wrong_page_secret_and_unknown_page() -> None:
    client = _client()
    body = _payload("page-cfc", mid="mid-wrong-secret")
    wrong_secret = _signature(body, "zeo-secret")
    assert (
        client.post(
            "/webhook",
            content=body,
            headers={"X-Hub-Signature-256": wrong_secret},
        ).status_code
        == 403
    )

    unknown = _payload("page-unknown", mid="mid-unknown")
    assert (
        client.post(
            "/webhook",
            content=unknown,
            headers={"X-Hub-Signature-256": _signature(unknown, "cfc-secret")},
        ).status_code
        == 403
    )
