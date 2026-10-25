"""Durable inbox adapters.

The in-memory adapter is intentionally limited to unit tests. Production must
set ``INBOX_BACKEND=postgres`` and use :class:`PostgresInboxStore`.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from src.chatbot.core.settings import settings
from src.chatbot.shared.events import InboxEvent

logger = logging.getLogger(__name__)


class InboxStore(Protocol):
    def record_event(self, event: InboxEvent) -> bool: ...

    def get_events_for_page(self, page_id: str) -> list[InboxEvent]: ...

    def count_events(self) -> int: ...

    def claim_pending_events(
        self, limit: int = 20, lease_seconds: int = 60
    ) -> list[InboxEvent]: ...

    def mark_processed(self, event_ids: list[str]) -> None: ...


class DurableInboxStore:
    """Deterministic test adapter; never use as production source of truth."""

    def __init__(self) -> None:
        self._seen_event_ids: set[tuple[str, str]] = set()
        self._events_by_page: dict[str, list[InboxEvent]] = {"CFC": [], "ZEO": []}

    def record_event(self, event: InboxEvent) -> bool:
        key = (event.page_id.value, event.event_id)
        if key in self._seen_event_ids:
            logger.info("[Inbox:test] duplicate ignored: %s", key)
            return False
        self._seen_event_ids.add(key)
        self._events_by_page.setdefault(event.page_id.value, []).append(event)
        return True

    def get_events_for_page(self, page_id: str) -> list[InboxEvent]:
        return list(self._events_by_page.get(page_id, []))

    def count_events(self) -> int:
        return len(self._seen_event_ids)

    def claim_pending_events(
        self, limit: int = 20, lease_seconds: int = 60
    ) -> list[InboxEvent]:
        return [event for events in self._events_by_page.values() for event in events][
            :limit
        ]

    def mark_processed(self, event_ids: list[str]) -> None:
        return None


class PostgresInboxStore:
    """PostgreSQL durable inbox with page-scoped idempotency.

    The adapter is synchronous because the current webhook handler is small
    and the project has not introduced an async repository boundary yet. The
    production follow-up is to move this call behind an async repository/worker
    without changing the table contract.
    """

    _schema_sql = """
    CREATE TABLE IF NOT EXISTS inbox_events (
        id BIGSERIAL PRIMARY KEY,
        page_id TEXT NOT NULL,
        event_key TEXT NOT NULL,
        sender_id TEXT NOT NULL,
        payload JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        received_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (page_id, event_key)
    );
    CREATE INDEX IF NOT EXISTS idx_inbox_events_page_received
        ON inbox_events (page_id, received_at);
    ALTER TABLE inbox_events ADD COLUMN IF NOT EXISTS leased_until TIMESTAMPTZ;
    CREATE INDEX IF NOT EXISTS idx_inbox_events_pending
        ON inbox_events (status, leased_until, id);
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = self._normalize_dsn(database_url)
        self._schema_ready = False

    @staticmethod
    def _normalize_dsn(database_url: str) -> str:
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self._database_url)

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self._schema_sql)
        self._schema_ready = True

    def record_event(self, event: InboxEvent) -> bool:
        self._ensure_schema()
        payload = event.model_dump(mode="json")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    INSERT INTO inbox_events
                        (page_id, event_key, sender_id, payload, received_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (page_id, event_key) DO NOTHING
                    RETURNING id
                    """,
                (
                    event.page_id.value,
                    event.event_id,
                    event.sender_id,
                    json.dumps(payload, ensure_ascii=False),
                    event.received_at,
                ),
            )
            inserted = cursor.fetchone() is not None
        if not inserted:
            logger.info(
                "[Inbox:postgres] duplicate ignored: %s/%s",
                event.page_id,
                event.event_id,
            )
        return inserted

    def get_events_for_page(self, page_id: str) -> list[InboxEvent]:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM inbox_events WHERE page_id = %s ORDER BY id",
                (page_id,),
            )
            return [InboxEvent.model_validate(row[0]) for row in cursor.fetchall()]

    def count_events(self) -> int:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM inbox_events")
            return int(cursor.fetchone()[0])

    def claim_pending_events(
        self, limit: int = 20, lease_seconds: int = 60
    ) -> list[InboxEvent]:
        """Atomically lease pending events for one worker instance."""
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH candidates AS (
                    SELECT id FROM inbox_events
                    WHERE status = 'PENDING'
                      AND (leased_until IS NULL OR leased_until < now())
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE inbox_events AS e
                SET status = 'PROCESSING', leased_until = now() + (%s * interval '1 second')
                FROM candidates
                WHERE e.id = candidates.id
                RETURNING e.payload
                """,
                (limit, lease_seconds),
            )
            return [InboxEvent.model_validate(row[0]) for row in cursor.fetchall()]

    def mark_processed(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE inbox_events SET status = 'PROCESSED', leased_until = NULL WHERE event_key = ANY(%s)",
                (event_ids,),
            )


def build_inbox_store() -> InboxStore:
    if settings.INBOX_BACKEND.lower() == "postgres":
        return PostgresInboxStore(settings.get_database_url())
    return DurableInboxStore()


durable_inbox: InboxStore = build_inbox_store()
