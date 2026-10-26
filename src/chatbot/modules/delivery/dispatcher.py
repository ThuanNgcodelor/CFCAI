"""Safe Outbox dispatcher; disabled by default."""

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.outbox import OutboxStore
from src.chatbot.modules.channels.meta.sender import MetaSender, MetaSendError


class OutboxDispatcher:
    def __init__(self, outbox: OutboxStore, sender: MetaSender | None = None) -> None:
        self.outbox = outbox
        self.sender = sender or MetaSender()

    def dispatch_one(self, conversation_id: str, batch_version: int) -> bool:
        if not settings.META_SEND_ENABLED:
            return False
        message = self.outbox.claim_sendable(conversation_id, batch_version)
        if message is None or (
            settings.META_TEST_RECIPIENT_ID
            and message.recipient_id != settings.META_TEST_RECIPIENT_ID
        ):
            return False
        try:
            self.sender.send_text(message.page_id, message.recipient_id, message.text)
        except (MetaSendError, OSError, ValueError):
            self.outbox.mark_failed(message.outbox_id or "")
            return False
        self.outbox.mark_sent(message.outbox_id or "")
        return True

    def dispatch_pending(self, limit: int = 10) -> int:
        """Send only allowlisted pending messages; safe no-op unless explicitly enabled."""
        if not settings.META_SEND_ENABLED or not settings.META_TEST_RECIPIENT_ID:
            return 0
        messages = self.outbox.claim_pending(limit, settings.META_TEST_RECIPIENT_ID)
        sent = 0
        for message in messages:
            try:
                self.sender.send_text(message.page_id, message.recipient_id, message.text)
            except (MetaSendError, OSError, ValueError):
                self.outbox.mark_failed(message.outbox_id or "")
                continue
            self.outbox.mark_sent(message.outbox_id or "")
            sent += 1
        return sent
