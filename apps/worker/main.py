from __future__ import annotations

import logging
import time

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.inbox import build_inbox_store
from src.chatbot.infrastructure.messaging.outbox import build_outbox_store
from src.chatbot.infrastructure.messaging.worker import InboxWorker
from src.chatbot.modules.delivery.dispatcher import OutboxDispatcher
from src.chatbot.modules.knowledge.retriever import (
    CompositeKnowledgeStore,
    PostgresKnowledgeStore,
    RedisCrmDealerStore,
    RedisCrmProductStore,
)
from src.chatbot.modules.llm.ollama import OllamaIntentClient
from src.chatbot.modules.ops.controls import build_ops_control_store
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline

logger = logging.getLogger("cfc.worker")


def run_once() -> int:
    outbox = build_outbox_store()
    pipeline = SafeMessagePipeline(
        outbox,
        build_ops_control_store(),
        OllamaIntentClient(
            settings.OLLAMA_BASE_URL,
            settings.OLLAMA_MODEL_TAG,
            settings.OLLAMA_TIMEOUT_SECONDS,
        ),
        knowledge_store=(
            CompositeKnowledgeStore(PostgresKnowledgeStore(), RedisCrmProductStore(), RedisCrmDealerStore())
            if settings.INBOX_BACKEND.lower() == "postgres"
            else None
        ),
    )
    worker = InboxWorker(build_inbox_store(), pipeline.process)
    processed = worker.run_once()
    dispatched = OutboxDispatcher(outbox).dispatch_pending(limit=5)
    if dispatched:
        logger.info("dispatched outbound messages=%s", dispatched)
    return processed


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    interval = 2.0
    while True:
        try:
            processed = run_once()
            if processed:
                logger.info("processed inbox events=%s", processed)
        except Exception:
            logger.exception("worker iteration failed; retrying")
        time.sleep(interval)


if __name__ == "__main__":
    main()
