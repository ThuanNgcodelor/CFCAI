"""Meta Graph API sender with page-scoped credentials."""

from __future__ import annotations

import json
import urllib.request

from src.chatbot.core.settings import settings
from src.chatbot.shared.enums import PageCode


class MetaSendError(RuntimeError):
    pass


class MetaSender:
    def __init__(
        self, graph_base_url: str = "https://graph.facebook.com/v21.0"
    ) -> None:
        self.graph_base_url = graph_base_url.rstrip("/")

    def _credentials(self, page_id: PageCode) -> tuple[str, str]:
        if page_id == PageCode.CFC:
            return settings.CFC_PAGE_ID, settings.CFC_PAGE_ACCESS_TOKEN
        return settings.ZEO_PAGE_ID, settings.ZEO_PAGE_ACCESS_TOKEN

    def send_text(self, page_id: PageCode, recipient_id: str, text: str) -> str:
        configured_page_id, access_token = self._credentials(page_id)
        if not configured_page_id or not access_token:
            raise MetaSendError(f"Missing Meta credentials for page {page_id.value}")
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text},
            "messaging_type": "RESPONSE",
        }
        request = urllib.request.Request(
            f"{self.graph_base_url}/{configured_page_id}/messages?access_token={access_token}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise MetaSendError("Meta Send API request failed") from exc
        if "message_id" not in body:
            raise MetaSendError(f"Meta Send API rejected request: {body}")
        return str(body["message_id"])
