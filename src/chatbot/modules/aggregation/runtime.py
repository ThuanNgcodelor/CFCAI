"""Durable aggregation coordinator used by the production worker."""

from __future__ import annotations

from datetime import UTC, datetime

from src.chatbot.modules.aggregation.scheduler import RedisDebounceScheduler
from src.chatbot.modules.conversations.repository import PostgresConversationRepository
from src.chatbot.shared.events import InboxEvent, NormalizedMessage


class DurableAggregationRuntime:
    def __init__(
        self,
        repository: PostgresConversationRepository,
        *,
        debounce_seconds: float,
        max_batch_seconds: float,
        scheduler: RedisDebounceScheduler | None = None,
    ) -> None:
        self.repository = repository
        self.debounce_seconds = debounce_seconds
        self.max_batch_seconds = max_batch_seconds
        self.scheduler = scheduler

    def ingest(self, event: InboxEvent) -> None:
        scheduled = self.repository.ingest(
            event,
            debounce_seconds=self.debounce_seconds,
            max_batch_seconds=self.max_batch_seconds,
        )
        if scheduled and self.scheduler:
            conversation_id, _, due_at = scheduled
            self.scheduler.schedule(event.page_id.value, conversation_id, due_at)

    def process_ready(self, handler, *, limit: int = 20) -> int:
        processed = 0
        for batch in self.repository.claim_ready(limit=limit):
            texts = [message.text.strip() for message in batch.messages if message.text]
            last = batch.messages[-1]
            combined = NormalizedMessage(
                mid=f"batch:{batch.batch_id}:{batch.conversation.batch_version}",
                sender_id=batch.conversation.sender_id,
                recipient_id=last.recipient_id,
                timestamp=max(message.timestamp for message in batch.messages),
                text="\n".join(texts) if texts else None,
                attachments=[
                    attachment
                    for message in batch.messages
                    for attachment in message.attachments
                ],
                raw_payload={"source_message_ids": [m.mid for m in batch.messages]},
            )
            event = InboxEvent(
                event_id=combined.mid,
                page_id=batch.conversation.page_id,
                sender_id=batch.conversation.sender_id,
                message=combined,
                received_at=datetime.now(UTC),
            )
            handler(
                event,
                batch_version=batch.conversation.batch_version,
                conversation_version=batch.conversation.version,
            )
            self.repository.complete_batch(
                batch.batch_id,
                expected_batch_version=batch.conversation.batch_version,
            )
            if self.scheduler:
                self.scheduler.acknowledge(
                    batch.conversation.page_id.value,
                    batch.conversation.conversation_id,
                )
            processed += 1
        return processed
