"""Safe outbox dispatcher with explicit disabled, shadow, canary and live modes."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Protocol

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.outbox import OutboxStore
from src.chatbot.modules.channels.meta.sender import MetaSender, MetaSendError
from src.chatbot.modules.ops.repository import ShadowDeliveryRecorder
from src.chatbot.shared.events import OutboxMessageSchema

logger = logging.getLogger(__name__)


class ShadowRecorder(Protocol):
    def record(self, message: OutboxMessageSchema) -> None: ...


class OutboxDispatcher:
    def __init__(
        self,
        outbox: OutboxStore,
        sender: MetaSender | None = None,
        shadow_recorder: ShadowRecorder | None = None,
    ) -> None:
        self.outbox = outbox
        self.sender = sender or MetaSender()
        self.shadow_recorder = shadow_recorder
        if (
            self.shadow_recorder is None
            and settings.INBOX_BACKEND.lower() == "postgres"
        ):
            self.shadow_recorder = ShadowDeliveryRecorder(settings.get_database_url())

    @staticmethod
    def _configured_values(value: str) -> set[str]:
        return {item.strip().upper() for item in value.split(",") if item.strip()}

    def _can_send(
        self,
        message: OutboxMessageSchema,
        mode: str,
        *,
        not_before: datetime | None,
    ) -> bool:
        """Deny sends until every release policy predicate is explicit."""
        if not settings.META_SEND_ENABLED:
            return False
        if not_before is None or message.created_at < not_before:
            return False
        if settings.META_TEST_RECIPIENT_ID and (
            message.recipient_id != settings.META_TEST_RECIPIENT_ID
        ):
            return False
        if mode == "live":
            return settings.LIVE_SEND_APPROVED
        if mode != "canary" or not settings.CANARY_SEND_APPROVED:
            return False

        page_ids = self._configured_values(settings.CANARY_PAGE_IDS)
        workflows = self._configured_values(settings.CANARY_WORKFLOWS)
        recipient_ids = self._configured_values(settings.CANARY_RECIPIENT_IDS)
        if not page_ids or not workflows or not 1 <= settings.CANARY_PERCENT <= 100:
            return False
        if message.page_id.value not in page_ids:
            return False
        if message.workflow is None or message.workflow.value.upper() not in workflows:
            return False
        if recipient_ids and message.recipient_id.upper() not in recipient_ids:
            return False
        material = f"{message.page_id.value}\0{message.recipient_id}\0{message.outbox_id}"
        bucket = int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16) % 100
        return bucket < settings.CANARY_PERCENT

    def _shadow(self, message: OutboxMessageSchema) -> None:
        """Persist review evidence before keeping the candidate permanently unsent."""
        self.outbox.suppress(message.outbox_id or "")
        if self.shadow_recorder is None:
            return
        try:
            self.shadow_recorder.record(message)
        except Exception:
            # Suppression happened first; an audit outage can never turn into a send.
            logger.exception("shadow delivery review recording failed")

    def dispatch_one(self, conversation_id: str, batch_version: int) -> bool:
        mode = settings.get_delivery_mode()
        if mode == "disabled":
            return False
        try:
            not_before = settings.get_delivery_not_before()
        except ValueError:
            logger.error("delivery release fence configuration is invalid")
            return False
        if mode != "shadow" and not_before is None:
            logger.error("delivery release fence is required before canary/live dispatch")
            return False
        message = self.outbox.claim_sendable(conversation_id, batch_version)
        if message is None:
            return False
        if mode == "shadow":
            self._shadow(message)
            return False
        if not self._can_send(message, mode, not_before=not_before):
            self.outbox.suppress(message.outbox_id or "")
            return False
        try:
            self.sender.send_text(message.page_id, message.recipient_id, message.text)
        except (MetaSendError, OSError, ValueError):
            self.outbox.mark_failed(message.outbox_id or "", "META_SEND_ERROR")
            logger.warning(
                "outbox delivery failed page=%s outbox_id=%s",
                message.page_id.value,
                message.outbox_id,
            )
            return False
        self.outbox.mark_sent(message.outbox_id or "")
        return True

    def dispatch_pending(self, limit: int = 10) -> int:
        """Process pending messages without allowing release policy bypasses."""
        mode = settings.get_delivery_mode()
        if mode == "disabled":
            return 0
        try:
            not_before = settings.get_delivery_not_before()
        except ValueError:
            logger.error("delivery release fence configuration is invalid")
            return 0
        if mode != "shadow" and not_before is None:
            logger.error("delivery release fence is required before canary/live dispatch")
            return 0
        messages = self.outbox.claim_pending(limit)
        sent = 0
        for message in messages:
            if mode == "shadow":
                self._shadow(message)
                continue
            if not self._can_send(message, mode, not_before=not_before):
                self.outbox.suppress(message.outbox_id or "")
                continue
            try:
                self.sender.send_text(message.page_id, message.recipient_id, message.text)
            except (MetaSendError, OSError, ValueError):
                self.outbox.mark_failed(message.outbox_id or "", "META_SEND_ERROR")
                logger.warning(
                    "outbox delivery failed page=%s outbox_id=%s",
                    message.page_id.value,
                    message.outbox_id,
                )
                continue
            self.outbox.mark_sent(message.outbox_id or "")
            sent += 1
        return sent
