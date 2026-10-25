from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import InboxEvent, NormalizedMessage
from src.chatbot.core.settings import settings

logger = logging.getLogger(__name__)

def resolve_page_code(page_id: str) -> PageCode:
    """
    Resolves Meta Page ID to PageCode (CFC or ZEO).
    Defaults to CFC if not explicitly matching ZEO.
    """
    if settings.ZEO_PAGE_ID and page_id == settings.ZEO_PAGE_ID:
        return PageCode.ZEO
    return PageCode.CFC

def normalize_messenger_payload(payload: Dict[str, Any]) -> List[InboxEvent]:
    """
    Parses a Meta Webhook payload into a list of standardized InboxEvents.
    """
    events: List[InboxEvent] = []
    if payload.get("object") != "page":
        return events

    for entry in payload.get("entry", []):
        raw_page_id = str(entry.get("id", ""))
        page_code = resolve_page_code(raw_page_id)

        for messaging_event in entry.get("messaging", []):
            sender = messaging_event.get("sender", {})
            recipient = messaging_event.get("recipient", {})
            sender_id = str(sender.get("id", ""))
            recipient_id = str(recipient.get("id", ""))

            # Handle standard text or media message
            message_obj = messaging_event.get("message")
            if not message_obj:
                continue

            mid = str(message_obj.get("mid", f"mid_{sender_id}_{entry.get('time')}"))
            ts_ms = messaging_event.get("timestamp") or entry.get("time") or 0
            ts_dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)

            normalized_msg = NormalizedMessage(
                mid=mid,
                sender_id=sender_id,
                recipient_id=recipient_id,
                timestamp=ts_dt,
                text=message_obj.get("text"),
                attachments=message_obj.get("attachments", []),
                raw_payload=messaging_event,
            )

            inbox_evt = InboxEvent(
                event_id=mid,
                page_id=page_code,
                sender_id=sender_id,
                message=normalized_msg,
                received_at=datetime.now(timezone.utc),
            )
            events.append(inbox_evt)

    return events
