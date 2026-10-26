from __future__ import annotations

import logging
import time

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.db.migrations import apply_migrations
from src.chatbot.infrastructure.messaging.inbox import build_inbox_store
from src.chatbot.infrastructure.messaging.outbox import build_outbox_store
from src.chatbot.infrastructure.messaging.worker import InboxWorker
from src.chatbot.modules.aggregation.runtime import DurableAggregationRuntime
from src.chatbot.modules.aggregation.scheduler import RedisDebounceScheduler
from src.chatbot.modules.conversations.repository import PostgresConversationRepository
from src.chatbot.modules.delivery.dispatcher import OutboxDispatcher
from src.chatbot.modules.knowledge.retriever import (
    CompositeKnowledgeStore,
    PostgresKnowledgeStore,
    RedisCrmDealerStore,
    RedisCrmProductStore,
)
from src.chatbot.modules.llm.ollama import OllamaIntentClient
from src.chatbot.modules.ops.controls import build_ops_control_store
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    VietnameseNormalizer,
)
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline

logger = logging.getLogger("cfc.worker")


class WorkerRuntime:
    def __init__(self) -> None:
        conversation_repository: PostgresConversationRepository | None = None
        if settings.INBOX_BACKEND.lower() == "postgres":
            apply_migrations(settings.get_database_url())
            conversation_repository = PostgresConversationRepository(
                settings.get_database_url()
            )
        self.outbox = build_outbox_store()
        ollama_client = OllamaIntentClient(
            settings.OLLAMA_BASE_URL,
            settings.OLLAMA_MODEL_TAG,
            settings.OLLAMA_TIMEOUT_SECONDS,
            prompt_path=settings.INTENT_PROMPT_PATH,
            max_attempts=settings.OLLAMA_MAX_ATTEMPTS,
        )
        intent_analyzer = HybridInputAnalyzer(
            ollama_client,
            VietnameseNormalizer(settings.INTENT_NORMALIZATION_PATH),
        )
        self.pipeline = SafeMessagePipeline(
            self.outbox,
            build_ops_control_store(),
            intent_analyzer,
            knowledge_store=(
                CompositeKnowledgeStore(
                    PostgresKnowledgeStore(),
                    RedisCrmProductStore(),
                    RedisCrmDealerStore(),
                )
                if settings.INBOX_BACKEND.lower() == "postgres"
                else None
            ),
            conversation_repository=conversation_repository,
        )
        self.inbox = build_inbox_store()
        self.dispatcher = OutboxDispatcher(self.outbox)
        self.aggregation: DurableAggregationRuntime | None = None
        if conversation_repository:
            scheduler = RedisDebounceScheduler(settings.get_redis_url())
            self.aggregation = DurableAggregationRuntime(
                conversation_repository,
                debounce_seconds=settings.DEBOUNCE_SECONDS,
                max_batch_seconds=settings.MAX_BATCH_SECONDS,
                scheduler=scheduler,
            )

    def run_once(self) -> int:
        if self.aggregation is None:
            worker = InboxWorker(self.inbox, self.pipeline.process)
            processed = worker.run_once()
        else:
            worker = InboxWorker(self.inbox, self.aggregation.ingest)
            accepted = worker.run_once()
            ready = self.aggregation.process_ready(self.pipeline.process)
            processed = accepted + ready
        dispatched = self.dispatcher.dispatch_pending(limit=5)
        if dispatched:
            logger.info("dispatched outbound messages=%s", dispatched)
        return processed


_runtime: WorkerRuntime | None = None


def run_once() -> int:
    global _runtime
    if _runtime is None:
        _runtime = WorkerRuntime()
    processed = _runtime.run_once()
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
