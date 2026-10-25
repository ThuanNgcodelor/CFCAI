"""Fail-closed per-page operational controls."""

import logging

from src.chatbot.core.settings import settings
from src.chatbot.shared.enums import PageCode

logger = logging.getLogger(__name__)


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


class RedisOpsControlStore(OpsControlStore):
    """Shared control state visible to API and worker processes."""

    def __init__(self, redis_url: str) -> None:
        import redis

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def _key(self, page_id: PageCode, field: str) -> str:
        return f"cfc:ops:{page_id.value}:{field}"

    def set_enabled(self, page_id: PageCode, enabled: bool) -> None:
        self._redis.set(self._key(page_id, "enabled"), "1" if enabled else "0")

    def pause(self, page_id: PageCode) -> None:
        self._redis.set(self._key(page_id, "paused"), "1")

    def resume(self, page_id: PageCode) -> None:
        self._redis.set(self._key(page_id, "paused"), "0")

    def can_auto_reply(self, page_id: PageCode) -> bool:
        enabled = self._redis.get(self._key(page_id, "enabled"))
        paused = self._redis.get(self._key(page_id, "paused"))
        return enabled != "0" and paused != "1"

    def snapshot(self) -> dict[str, dict[str, bool]]:
        return {
            page.value: {
                "enabled": self._redis.get(self._key(page, "enabled")) != "0",
                "paused": self._redis.get(self._key(page, "paused")) == "1",
            }
            for page in PageCode
        }


def build_ops_control_store() -> OpsControlStore:
    if settings.REDIS_URL or settings.REDIS_HOST:
        try:
            store = RedisOpsControlStore(settings.get_redis_url())
            store.snapshot()
            return store
        except (OSError, ConnectionError) as exc:
            logger.warning("Redis ops controls unavailable; using local fallback: %s", exc)
    return OpsControlStore()
