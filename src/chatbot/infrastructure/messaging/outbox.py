"""Durable outbound queue with the final ownership/version fence."""

from __future__ import annotations

import json
from typing import Protocol

from src.chatbot.core.settings import settings
from src.chatbot.shared.enums import OutboxStatus, Ownership
from src.chatbot.shared.events import OutboxMessageSchema


class OutboxStore(Protocol):
    def enqueue(self, message: OutboxMessageSchema) -> str: ...

    def claim_sendable(
        self, conversation_id: str, batch_version: int
    ) -> OutboxMessageSchema | None: ...

    def claim_pending(self, limit: int = 10, recipient_id: str | None = None) -> list[OutboxMessageSchema]: ...

    def suppress(self, outbox_id: str) -> None: ...

    def mark_sent(self, outbox_id: str) -> None: ...

    def mark_failed(self, outbox_id: str) -> None: ...


class InMemoryOutboxStore:
    def __init__(self) -> None:
        self.messages: dict[str, OutboxMessageSchema] = {}

    def enqueue(self, message: OutboxMessageSchema) -> str:
        outbox_id = message.outbox_id or f"outbox-{len(self.messages) + 1}"
        self.messages[outbox_id] = message.model_copy(update={"outbox_id": outbox_id})
        return outbox_id

    def claim_sendable(
        self, conversation_id: str, batch_version: int
    ) -> OutboxMessageSchema | None:
        for message in self.messages.values():
            if (
                message.conversation_id == conversation_id
                and message.batch_version == batch_version
                and message.status == OutboxStatus.PENDING
                and message.expected_ownership == Ownership.AI
            ):
                return message.model_copy(update={"status": OutboxStatus.SENDING})
        return None

    def claim_pending(self, limit: int = 10, recipient_id: str | None = None) -> list[OutboxMessageSchema]:
        claimed: list[OutboxMessageSchema] = []
        for key, message in self.messages.items():
            if len(claimed) >= limit:
                break
            if message.status != OutboxStatus.PENDING or message.expected_ownership != Ownership.AI:
                continue
            if recipient_id and message.recipient_id != recipient_id:
                continue
            updated = message.model_copy(update={"status": OutboxStatus.SENDING})
            self.messages[key] = updated
            claimed.append(updated)
        return claimed

    def suppress(self, outbox_id: str) -> None:
        if outbox_id in self.messages:
            self.messages[outbox_id] = self.messages[outbox_id].model_copy(
                update={"status": OutboxStatus.SUPPRESSED}
            )

    def mark_sent(self, outbox_id: str) -> None:
        if outbox_id in self.messages:
            self.messages[outbox_id] = self.messages[outbox_id].model_copy(
                update={"status": OutboxStatus.SENT}
            )

    def mark_failed(self, outbox_id: str) -> None:
        if outbox_id in self.messages:
            self.messages[outbox_id] = self.messages[outbox_id].model_copy(
                update={"status": OutboxStatus.FAILED}
            )


class PostgresOutboxStore:
    _schema_sql = """
    CREATE TABLE IF NOT EXISTS outbox_messages (
        id BIGSERIAL PRIMARY KEY,
        outbox_id TEXT UNIQUE NOT NULL,
        conversation_id TEXT NOT NULL,
        page_id TEXT NOT NULL,
        recipient_id TEXT NOT NULL,
        payload JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        batch_version INTEGER NOT NULL,
        expected_ownership TEXT NOT NULL DEFAULT 'AI',
        expected_conversation_version BIGINT,
        created_at TIMESTAMPTZ NOT NULL,
        sent_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_messages(status, id);
    ALTER TABLE outbox_messages
        ADD COLUMN IF NOT EXISTS expected_conversation_version BIGINT;
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url.replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
        self._ready = False

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self.database_url)

    def _ensure_schema(self) -> None:
        if not self._ready:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(self._schema_sql)
            self._ready = True

    def enqueue(self, message: OutboxMessageSchema) -> str:
        self._ensure_schema()
        outbox_id = (
            message.outbox_id
            or f"outbox-{message.conversation_id}-{message.batch_version}"
        )
        payload = message.model_dump(mode="json")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO outbox_messages
                (outbox_id, conversation_id, page_id, recipient_id, payload,
                 status, batch_version, expected_ownership,
                 expected_conversation_version, created_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                ON CONFLICT (outbox_id) DO NOTHING""",
                (
                    outbox_id,
                    message.conversation_id,
                    message.page_id.value,
                    message.recipient_id,
                    json.dumps(payload),
                    message.status.value,
                    message.batch_version,
                    message.expected_ownership.value,
                    message.expected_conversation_version,
                    message.created_at,
                ),
            )
        return outbox_id

    def claim_sendable(
        self, conversation_id: str, batch_version: int
    ) -> OutboxMessageSchema | None:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """WITH item AS (
                    SELECT o.id FROM outbox_messages o
                    JOIN conversations c ON c.conversation_id=o.conversation_id
                                           AND c.page_id=o.page_id
                    WHERE o.conversation_id=%s AND o.batch_version=%s
                      AND o.status='PENDING' AND o.expected_ownership='AI'
                      AND c.ownership='AI' AND c.batch_version=o.batch_version
                      AND (o.expected_conversation_version IS NULL
                           OR c.version=o.expected_conversation_version)
                    ORDER BY o.id FOR UPDATE OF o SKIP LOCKED LIMIT 1
                ) UPDATE outbox_messages o SET status='SENDING'
                FROM item WHERE o.id=item.id RETURNING o.outbox_id, o.payload""",
                (conversation_id, batch_version),
            )
            row = cursor.fetchone()
        return (
            OutboxMessageSchema.model_validate(row[1]).model_copy(
                update={"outbox_id": row[0], "status": OutboxStatus.SENDING}
            )
            if row
            else None
        )

    def claim_pending(self, limit: int = 10, recipient_id: str | None = None) -> list[OutboxMessageSchema]:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE outbox_messages o SET status='SUPPRESSED'
                WHERE o.status='PENDING' AND o.expected_ownership='AI'
                  AND EXISTS (
                    SELECT 1 FROM conversations c
                    WHERE c.conversation_id=o.conversation_id AND c.page_id=o.page_id
                      AND (c.ownership<>'AI' OR c.batch_version<>o.batch_version
                           OR (o.expected_conversation_version IS NOT NULL
                               AND c.version<>o.expected_conversation_version))
                  )"""
            )
            cursor.execute(
                """WITH items AS (
                    SELECT o.id FROM outbox_messages o
                    JOIN conversations c ON c.conversation_id=o.conversation_id
                                           AND c.page_id=o.page_id
                    WHERE o.status='PENDING' AND o.expected_ownership='AI'
                      AND c.ownership='AI' AND c.batch_version=o.batch_version
                      AND (o.expected_conversation_version IS NULL
                           OR c.version=o.expected_conversation_version)
                      AND (%s IS NULL OR o.recipient_id=%s)
                    ORDER BY o.id FOR UPDATE OF o SKIP LOCKED LIMIT %s
                ) UPDATE outbox_messages o SET status='SENDING'
                FROM items WHERE o.id=items.id RETURNING o.outbox_id, o.payload""",
                (recipient_id, recipient_id, limit),
            )
            rows = cursor.fetchall()
        return [
            OutboxMessageSchema.model_validate(row[1]).model_copy(
                update={"outbox_id": row[0], "status": OutboxStatus.SENDING}
            )
            for row in rows
        ]

    def suppress(self, outbox_id: str) -> None:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE outbox_messages SET status='SUPPRESSED' WHERE outbox_id=%s",
                (outbox_id,),
            )

    def mark_sent(self, outbox_id: str) -> None:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE outbox_messages SET status='SENT', sent_at=now() WHERE outbox_id=%s",
                (outbox_id,),
            )

    def mark_failed(self, outbox_id: str) -> None:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE outbox_messages SET status='FAILED' WHERE outbox_id=%s",
                (outbox_id,),
            )


def build_outbox_store() -> OutboxStore:
    if settings.INBOX_BACKEND.lower() == "postgres":
        return PostgresOutboxStore(settings.get_database_url())
    return InMemoryOutboxStore()
