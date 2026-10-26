"""Redis acceleration for debounce deadlines; PostgreSQL remains authoritative."""

from __future__ import annotations

from datetime import datetime


class RedisDebounceScheduler:
    def __init__(self, redis_url: str, *, namespace: str = "chatbot:debounce") -> None:
        # pyrefly: ignore[missing-import]
        import redis

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._namespace = namespace

    def schedule(self, page_id: str, conversation_id: str, due_at: datetime) -> None:
        key = f"{self._namespace}:{page_id}"
        self._redis.zadd(key, {conversation_id: due_at.timestamp()})

    def acknowledge(self, page_id: str, conversation_id: str) -> None:
        self._redis.zrem(f"{self._namespace}:{page_id}", conversation_id)
