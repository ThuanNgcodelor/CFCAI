"""Durable inbox worker primitives.

The worker deliberately only owns claiming and acknowledging inbox records;
business orchestration is injected so page isolation and ownership guards stay
in their respective modules.
"""

from collections.abc import Callable

from src.chatbot.infrastructure.messaging.inbox import InboxStore
from src.chatbot.shared.events import InboxEvent


class InboxWorker:
    def __init__(
        self, store: InboxStore, handler: Callable[[InboxEvent], object]
    ) -> None:
        self.store = store
        self.handler = handler

    def run_once(self, limit: int = 20, lease_seconds: int = 60) -> int:
        events = self.store.claim_pending_events(
            limit=limit, lease_seconds=lease_seconds
        )
        processed: list[str] = []
        for event in events:
            self.handler(event)
            processed.append(event.event_id)
        self.store.mark_processed(processed)
        return len(processed)
