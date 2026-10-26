from __future__ import annotations

import argparse
import asyncio
import json
import logging

import redis.asyncio as redis

from src.chatbot.core.settings import settings
from src.chatbot.modules.integrations.misa.warmer import amis_warmer

logger = logging.getLogger(__name__)


async def _sync() -> dict:
    client = redis.Redis.from_url(settings.get_redis_url(), decode_responses=True)
    try:
        result = await amis_warmer.warm_cache(redis_client=client)
        return result.model_dump()
    finally:
        await client.aclose()


async def _status() -> dict:
    client = redis.Redis.from_url(settings.get_redis_url(), decode_responses=True)
    try:
        result = await amis_warmer.read_status(client)
        return result or {"status": "pending"}
    finally:
        await client.aclose()


async def _run(interval: int) -> None:
    while True:
        try:
            result = await _sync()
            logger.info("AMIS sync completed: %s", result)
        except Exception:
            logger.exception("AMIS sync failed; last-known-good snapshot was retained")
        await asyncio.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Warm the MISA AMIS Redis snapshot")
    parser.add_argument("command", choices=("sync", "status", "run"))
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.AMIS_SYNC_INTERVAL_SECONDS,
    )
    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(_run(max(60, args.interval)))
        return 0
    result = asyncio.run(_sync() if args.command == "sync" else _status())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
