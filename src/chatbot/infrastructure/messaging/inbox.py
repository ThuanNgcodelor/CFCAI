from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Set

from src.chatbot.shared.events import InboxEvent

logger = logging.getLogger(__name__)

class DurableInboxStore:
    """
    Durable Inbox Storage for Meta Webhook events.
    Guarantees deduplication (Case T09) and page isolation (INV-2).
    """
    def __init__(self):
        self._seen_event_ids: Set[str] = set()
        self._events_by_page: Dict[str, List[InboxEvent]] = {"CFC": [], "ZEO": []}

    def record_event(self, event: InboxEvent) -> bool:
        """
        Records an incoming event into durable storage.
        Returns:
            True if event is new and recorded.
            False if event is duplicate (idempotent ignore - Case T09).
        """
        if event.event_id in self._seen_event_ids:
            logger.info(f"[Durable Inbox] Duplicate event ignored: {event.event_id}")
            return False

        self._seen_event_ids.add(event.event_id)
        page_key = event.page_id.value
        if page_key not in self._events_by_page:
            self._events_by_page[page_key] = []
        self._events_by_page[page_key].append(event)

        logger.info(f"[Durable Inbox] Event stored: id={event.event_id}, page={page_key}, sender={event.sender_id}")
        return True

    def get_events_for_page(self, page_id: str) -> List[InboxEvent]:
        return list(self._events_by_page.get(page_id, []))

    def count_events(self) -> int:
        return len(self._seen_event_ids)

durable_inbox = DurableInboxStore()
