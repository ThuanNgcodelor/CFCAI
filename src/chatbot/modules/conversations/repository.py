"""PostgreSQL source of truth for conversation state and message batches."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.chatbot.shared.enums import IntentType, Ownership, PageCode, WorkflowType
from src.chatbot.shared.events import InboxEvent, NormalizedMessage


@dataclass(frozen=True)
class DurableConversation:
    conversation_id: str
    page_id: PageCode
    sender_id: str
    ownership: Ownership
    version: int
    batch_version: int
    current_workflow: str | None
    primary_intent: str | None


@dataclass(frozen=True)
class DurableReadyBatch:
    batch_id: int
    conversation: DurableConversation
    messages: list[NormalizedMessage]


class PostgresConversationRepository:
    """Transactional repository; all identity and state operations are page scoped."""

    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self._dsn)

    @staticmethod
    def conversation_id(page_id: PageCode, sender_id: str) -> str:
        if not sender_id.strip():
            raise ValueError("sender_id is required")
        return f"{page_id.value}:{sender_id}"

    def ingest(
        self,
        event: InboxEvent,
        *,
        debounce_seconds: float,
        max_batch_seconds: float,
    ) -> tuple[str, int, datetime] | None:
        """Persist one message and atomically schedule/reschedule its durable batch."""
        if debounce_seconds <= 0 or max_batch_seconds <= 0:
            raise ValueError("debounce durations must be positive")
        if debounce_seconds > max_batch_seconds:
            raise ValueError("debounce cannot exceed max batch duration")

        conversation_id = self.conversation_id(event.page_id, event.sender_id)
        now = event.received_at
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversations(conversation_id,page_id,sender_id,last_active_at)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT(page_id,sender_id) DO UPDATE
                SET last_active_at=EXCLUDED.last_active_at
                RETURNING conversation_id, ownership, batch_version
                """,
                (conversation_id, event.page_id.value, event.sender_id, now),
            )
            stored_id, ownership, current_batch_version = cursor.fetchone()
            if stored_id != conversation_id:
                raise ValueError("conversation identity/page scope mismatch")

            cursor.execute(
                """
                INSERT INTO conversation_messages(
                    page_id,conversation_id,provider_message_id,direction,
                    sender_role,text,metadata,received_at
                ) VALUES (%s,%s,%s,'INBOUND','CUSTOMER',%s,%s::jsonb,%s)
                ON CONFLICT(page_id,provider_message_id) DO NOTHING
                RETURNING id
                """,
                (
                    event.page_id.value,
                    conversation_id,
                    event.message.mid,
                    event.message.text,
                    json.dumps(event.message.model_dump(mode="json"), ensure_ascii=False),
                    event.message.timestamp,
                ),
            )
            if cursor.fetchone() is None:
                return None
            if ownership != Ownership.AI.value:
                return conversation_id, int(current_batch_version), now

            cursor.execute(
                """
                UPDATE conversations
                SET batch_version=batch_version+1, last_active_at=%s
                WHERE conversation_id=%s AND page_id=%s
                RETURNING batch_version
                """,
                (now, conversation_id, event.page_id.value),
            )
            batch_version = int(cursor.fetchone()[0])
            cursor.execute(
                """
                SELECT id, first_at FROM message_batches
                WHERE conversation_id=%s AND page_id=%s AND status='OPEN'
                FOR UPDATE
                """,
                (conversation_id, event.page_id.value),
            )
            open_batch = cursor.fetchone()
            if open_batch:
                batch_id, first_at = open_batch
                due_at = min(
                    now + timedelta(seconds=debounce_seconds),
                    first_at + timedelta(seconds=max_batch_seconds),
                )
                cursor.execute(
                    """UPDATE message_batches
                    SET batch_version=%s,last_at=%s,due_at=%s
                    WHERE id=%s""",
                    (batch_version, now, due_at, batch_id),
                )
            else:
                due_at = now + timedelta(
                    seconds=min(debounce_seconds, max_batch_seconds)
                )
                cursor.execute(
                    """INSERT INTO message_batches(
                    page_id,conversation_id,batch_version,first_at,last_at,due_at)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (
                        event.page_id.value,
                        conversation_id,
                        batch_version,
                        now,
                        now,
                        due_at,
                    ),
                )
        return conversation_id, batch_version, due_at

    def claim_ready(self, *, limit: int = 20) -> list[DurableReadyBatch]:
        """Claim due batches atomically; PostgreSQL remains authoritative."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH candidates AS (
                    SELECT b.id FROM message_batches b
                    JOIN conversations c
                      ON c.conversation_id=b.conversation_id AND c.page_id=b.page_id
                    WHERE b.status='OPEN' AND b.due_at<=now() AND c.ownership='AI'
                    ORDER BY b.due_at,b.id
                    FOR UPDATE OF b SKIP LOCKED
                    LIMIT %s
                )
                UPDATE message_batches b SET status='PROCESSING',claimed_at=now()
                FROM candidates x WHERE b.id=x.id
                RETURNING b.id,b.page_id,b.conversation_id,b.batch_version
                """,
                (limit,),
            )
            claimed = cursor.fetchall()
            result: list[DurableReadyBatch] = []
            for batch_id, page_value, conversation_id, batch_version in claimed:
                cursor.execute(
                    """
                    SELECT sender_id,ownership,version,batch_version,current_workflow,primary_intent
                    FROM conversations WHERE conversation_id=%s AND page_id=%s
                    FOR UPDATE
                    """,
                    (conversation_id, page_value),
                )
                state = cursor.fetchone()
                if state is None or state[1] != Ownership.AI.value or int(state[3]) != int(batch_version):
                    cursor.execute(
                        "UPDATE message_batches SET status='CANCELLED' WHERE id=%s",
                        (batch_id,),
                    )
                    continue
                cursor.execute(
                    """
                    UPDATE conversation_messages SET batch_version=%s
                    WHERE conversation_id=%s AND page_id=%s AND batch_version IS NULL
                    RETURNING metadata
                    """,
                    (batch_version, conversation_id, page_value),
                )
                messages = [
                    NormalizedMessage.model_validate(row[0]) for row in cursor.fetchall()
                ]
                if not messages:
                    cursor.execute(
                        "UPDATE message_batches SET status='CANCELLED' WHERE id=%s",
                        (batch_id,),
                    )
                    continue
                conversation = DurableConversation(
                    conversation_id=conversation_id,
                    page_id=PageCode(page_value),
                    sender_id=state[0],
                    ownership=Ownership(state[1]),
                    version=int(state[2]),
                    batch_version=int(state[3]),
                    current_workflow=state[4],
                    primary_intent=state[5],
                )
                result.append(DurableReadyBatch(batch_id, conversation, messages))
        return result

    def complete_batch(self, batch_id: int, *, expected_batch_version: int) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE message_batches SET status='DONE',completed_at=now()
                WHERE id=%s AND batch_version=%s AND status='PROCESSING'""",
                (batch_id, expected_batch_version),
            )
            return cursor.rowcount == 1

    def save_slots(
        self,
        page_id: PageCode,
        conversation_id: str,
        workflow: WorkflowType,
        slots: dict[str, Any],
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_slots(page_id,conversation_id,workflow,slots)
                SELECT %s,%s,%s,%s::jsonb
                WHERE EXISTS (
                    SELECT 1 FROM conversations WHERE conversation_id=%s AND page_id=%s
                )
                ON CONFLICT(conversation_id,workflow) DO UPDATE
                SET slots=EXCLUDED.slots,updated_at=now()
                """,
                (
                    page_id.value,
                    conversation_id,
                    workflow.value,
                    json.dumps(slots, ensure_ascii=False),
                    conversation_id,
                    page_id.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("unknown conversation or page scope mismatch")

    def update_context(
        self,
        page_id: PageCode,
        conversation_id: str,
        *,
        workflow: WorkflowType,
        primary_intent: IntentType,
        slots: dict[str, Any],
    ) -> DurableConversation:
        """Persist the active workflow and its merged slots with page fencing."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE conversations SET current_workflow=%s,primary_intent=%s,
                version=version+1,last_active_at=now()
                WHERE conversation_id=%s AND page_id=%s
                RETURNING sender_id,ownership,version,batch_version,current_workflow,primary_intent""",
                (
                    workflow.value,
                    primary_intent.value,
                    conversation_id,
                    page_id.value,
                ),
            )
            updated = cursor.fetchone()
            if updated is None:
                raise ValueError("unknown conversation or page scope mismatch")
            cursor.execute(
                """INSERT INTO conversation_slots(page_id,conversation_id,workflow,slots)
                VALUES (%s,%s,%s,%s::jsonb)
                ON CONFLICT(conversation_id,workflow) DO UPDATE
                SET slots=conversation_slots.slots || EXCLUDED.slots,updated_at=now()""",
                (
                    page_id.value,
                    conversation_id,
                    workflow.value,
                    json.dumps(slots, ensure_ascii=False),
                ),
            )
        return DurableConversation(
            conversation_id,
            page_id,
            updated[0],
            Ownership(updated[1]),
            int(updated[2]),
            int(updated[3]),
            updated[4],
            updated[5],
        )

    def load_slots(
        self, page_id: PageCode, conversation_id: str, workflow: WorkflowType
    ) -> dict[str, Any]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT slots FROM conversation_slots
                WHERE page_id=%s AND conversation_id=%s AND workflow=%s""",
                (page_id.value, conversation_id, workflow.value),
            )
            row = cursor.fetchone()
            return dict(row[0]) if row else {}

    def load_understanding_context(
        self,
        page_id: PageCode,
        conversation_id: str,
        *,
        recent_limit: int = 6,
    ) -> dict[str, Any]:
        if not 1 <= recent_limit <= 20:
            raise ValueError("recent_limit must be between 1 and 20")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT current_workflow,primary_intent FROM conversations
                WHERE conversation_id=%s AND page_id=%s""",
                (conversation_id, page_id.value),
            )
            conversation = cursor.fetchone()
            if conversation is None:
                raise ValueError("unknown conversation or page scope mismatch")
            workflow, intent = conversation
            slots: dict[str, Any] = {}
            if workflow:
                cursor.execute(
                    """SELECT slots FROM conversation_slots
                    WHERE conversation_id=%s AND page_id=%s AND workflow=%s""",
                    (conversation_id, page_id.value, workflow),
                )
                slot_row = cursor.fetchone()
                if slot_row:
                    slots = dict(slot_row[0])
            cursor.execute(
                """SELECT provider_message_id,text FROM (
                    SELECT id,provider_message_id,text FROM conversation_messages
                    WHERE conversation_id=%s AND page_id=%s
                      AND direction='INBOUND' AND sender_role='CUSTOMER'
                    ORDER BY id DESC LIMIT %s
                ) recent ORDER BY id""",
                (conversation_id, page_id.value, recent_limit),
            )
            recent = [
                {"message_id": row[0], "text": row[1] or ""}
                for row in cursor.fetchall()
            ]
        return {
            "current_workflow": workflow,
            "current_intent": intent,
            "current_slots": slots,
            "recent_customer_messages": recent,
            "message_ids": [item["message_id"] for item in recent],
        }

    def takeover(
        self,
        page_id: PageCode,
        conversation_id: str,
        *,
        actor: str,
        reason: str,
    ) -> DurableConversation:
        """Change ownership, fence batches and suppress queued AI output atomically."""
        if not actor.strip() or not reason.strip():
            raise ValueError("takeover actor and reason are required")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT sender_id,ownership,version,batch_version,current_workflow,primary_intent
                FROM conversations WHERE conversation_id=%s AND page_id=%s FOR UPDATE""",
                (conversation_id, page_id.value),
            )
            current = cursor.fetchone()
            if current is None:
                raise ValueError("unknown conversation or page scope mismatch")
            cursor.execute(
                """UPDATE conversations SET ownership='HUMAN',version=version+1,
                batch_version=batch_version+1,owner_actor=%s,owner_reason=%s,last_active_at=now()
                WHERE conversation_id=%s AND page_id=%s
                RETURNING sender_id,ownership,version,batch_version,current_workflow,primary_intent""",
                (actor, reason, conversation_id, page_id.value),
            )
            updated = cursor.fetchone()
            cursor.execute(
                """UPDATE message_batches SET status='CANCELLED'
                WHERE conversation_id=%s AND page_id=%s AND status IN ('OPEN','PROCESSING')""",
                (conversation_id, page_id.value),
            )
            cursor.execute(
                """UPDATE outbox_messages SET status='SUPPRESSED'
                WHERE conversation_id=%s AND page_id=%s AND status IN ('PENDING','SENDING')""",
                (conversation_id, page_id.value),
            )
            cursor.execute(
                """INSERT INTO handoff_events(
                page_id,conversation_id,from_owner,to_owner,actor,reason)
                VALUES (%s,%s,%s,'HUMAN',%s,%s)""",
                (page_id.value, conversation_id, current[1], actor, reason),
            )
        return DurableConversation(
            conversation_id,
            page_id,
            updated[0],
            Ownership(updated[1]),
            int(updated[2]),
            int(updated[3]),
            updated[4],
            updated[5],
        )

    def resume(
        self,
        page_id: PageCode,
        conversation_id: str,
        *,
        actor: str,
        reason: str,
    ) -> DurableConversation:
        if not actor.strip() or not reason.strip():
            raise ValueError("resume actor and reason are required")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT sender_id,ownership FROM conversations
                WHERE conversation_id=%s AND page_id=%s FOR UPDATE""",
                (conversation_id, page_id.value),
            )
            current = cursor.fetchone()
            if current is None:
                raise ValueError("unknown conversation or page scope mismatch")
            cursor.execute(
                """UPDATE conversations SET ownership='AI',version=version+1,
                batch_version=batch_version+1,owner_actor=%s,owner_reason=%s,last_active_at=now()
                WHERE conversation_id=%s AND page_id=%s
                RETURNING sender_id,ownership,version,batch_version,current_workflow,primary_intent""",
                (actor, reason, conversation_id, page_id.value),
            )
            updated = cursor.fetchone()
            cursor.execute(
                """INSERT INTO handoff_events(
                page_id,conversation_id,from_owner,to_owner,actor,reason)
                VALUES (%s,%s,%s,'AI',%s,%s)""",
                (page_id.value, conversation_id, current[1], actor, reason),
            )
        return DurableConversation(
            conversation_id,
            page_id,
            updated[0],
            Ownership(updated[1]),
            int(updated[2]),
            int(updated[3]),
            updated[4],
            updated[5],
        )
