import os

import psycopg2
import pytest

from src.chatbot.infrastructure.messaging.inbox import PostgresInboxStore
from src.chatbot.modules.channels.meta.normalizer import normalize_messenger_payload


def _store_or_skip() -> PostgresInboxStore:
    dsn = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://cfc_admin:cfc_secret_password@localhost:5432/cfc_zeo_db",
    )
    store = PostgresInboxStore(dsn)
    try:
        store.count_events()
    except psycopg2.Error as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    return store


def test_postgres_inbox_deduplicates_by_page_and_event() -> None:
    store = _store_or_skip()
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "dev-page-cfc",
                "time": 1700000000000,
                "messaging": [
                    {
                        "sender": {"id": "dev-user"},
                        "recipient": {"id": "dev-page-cfc"},
                        "message": {"mid": "integration-mid-1", "text": "hello"},
                    }
                ],
            }
        ],
    }
    event = normalize_messenger_payload(payload)[0]
    # Keep the integration test repeatable without deleting user data: use a
    # unique event key per run and assert only the first insert wins.
    event.event_id = f"{event.event_id}-{os.getpid()}"
    assert store.record_event(event) is True
    assert store.record_event(event) is False
    assert any(
        item.event_id == event.event_id for item in store.get_events_for_page("CFC")
    )
