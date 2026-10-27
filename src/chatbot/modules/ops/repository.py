"""Durable, page-scoped operational audit and shadow-review read models."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.chatbot.core.logging import redact_mapping
from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import OutboxMessageSchema


class OpsAuditRepository:
    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self._dsn)

    def record(
        self,
        *,
        action: str,
        actor: str,
        reason: str,
        page_id: PageCode | None = None,
        conversation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not action.strip() or not actor.strip() or not reason.strip():
            raise ValueError("action, actor and reason are required for audit")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO ops_audit_log(
                page_id,conversation_id,action,actor,reason,details)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                (
                    page_id.value if page_id else None,
                    conversation_id,
                    action,
                    actor,
                    reason,
                    json.dumps(redact_mapping(details or {}), ensure_ascii=False),
                ),
            )

    def list_events(
        self,
        *,
        page_id: PageCode | None = None,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be 1..500")
        clauses: list[str] = []
        params: list[object] = []
        if page_id:
            clauses.append("page_id=%s")
            params.append(page_id.value)
        if conversation_id:
            clauses.append("conversation_id=%s")
            params.append(conversation_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT audit_id,page_id,conversation_id,action,actor,reason,details,created_at
                FROM ops_audit_log"""
                + where
                + " ORDER BY audit_id DESC LIMIT %s",
                tuple(params),
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def summary(self) -> dict[str, dict[str, int]]:
        """Counts only; this endpoint never leaks message text or customer IDs."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT page_id,status,count(*) FROM outbox_messages GROUP BY page_id,status"
            )
            outbox = {
                f"{page_id}:{status}": int(count)
                for page_id, status, count in cursor.fetchall()
            }
            cursor.execute(
                "SELECT page_id,status,count(*) FROM handoff_tasks GROUP BY page_id,status"
            )
            handoffs = {
                f"{page_id}:{status}": int(count)
                for page_id, status, count in cursor.fetchall()
            }
            cursor.execute(
                "SELECT page_id,count(*) FROM delivery_shadow_reviews GROUP BY page_id"
            )
            shadows = {str(page_id): int(count) for page_id, count in cursor.fetchall()}
        return {"outbox": outbox, "handoffs": handoffs, "shadow_reviews": shadows}


class ShadowDeliveryRecorder:
    """Records evidence that a generated response was deliberately not sent."""

    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self._dsn)

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def record(self, message: OutboxMessageSchema) -> None:
        if not message.outbox_id:
            raise ValueError("shadow review requires an outbox_id")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO delivery_shadow_reviews(
                outbox_id,page_id,conversation_id,recipient_digest,response_digest)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT(outbox_id) DO NOTHING""",
                (
                    message.outbox_id,
                    message.page_id.value,
                    message.conversation_id,
                    self._digest(message.recipient_id),
                    self._digest(message.text),
                ),
            )

    def list_reviews(
        self,
        *,
        page_id: PageCode | None = None,
        limit: int = 100,
        include_text: bool = False,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be 1..500")
        text_select = ",o.payload->>'text' AS text" if include_text else ""
        params: list[object] = []
        where = ""
        if page_id:
            where = " WHERE r.page_id=%s"
            params.append(page_id.value)
        params.append(limit)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT r.review_id,r.outbox_id,r.page_id,r.conversation_id,
                r.recipient_digest,r.response_digest,r.created_at"""
                + text_select
                + " FROM delivery_shadow_reviews r"
                + (" LEFT JOIN outbox_messages o ON o.outbox_id=r.outbox_id" if include_text else "")
                + where
                + " ORDER BY r.review_id DESC LIMIT %s",
                tuple(params),
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
