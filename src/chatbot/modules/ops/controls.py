"""Fail-closed per-page operational controls."""

from src.chatbot.shared.enums import PageCode


class OpsControlStore:
    def __init__(self) -> None:
        self._enabled = {PageCode.CFC: True, PageCode.ZEO: True}
        self._paused = {PageCode.CFC: False, PageCode.ZEO: False}

    def set_enabled(self, page_id: PageCode, enabled: bool) -> None:
        self._enabled[page_id] = enabled

    def pause(self, page_id: PageCode) -> None:
        self._paused[page_id] = True

    def resume(self, page_id: PageCode) -> None:
        self._paused[page_id] = False

    def can_auto_reply(self, page_id: PageCode) -> bool:
        return self._enabled[page_id] and not self._paused[page_id]

    def snapshot(self) -> dict[str, dict[str, bool]]:
        return {
            page.value: {"enabled": self._enabled[page], "paused": self._paused[page]}
            for page in PageCode
        }
