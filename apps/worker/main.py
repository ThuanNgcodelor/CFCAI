from __future__ import annotations

import time

from src.chatbot.infrastructure.messaging.inbox import build_inbox_store
from src.chatbot.infrastructure.messaging.outbox import build_outbox_store
from src.chatbot.infrastructure.messaging.worker import InboxWorker
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline


def run_once() -> int:
    outbox = build_outbox_store()
    pipeline = SafeMessagePipeline(outbox)
    worker = InboxWorker(build_inbox_store(), pipeline.process)
    return worker.run_once()


def main() -> None:
    interval = 2.0
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
