"""F6 replay gate for the four Messenger test waves."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    VietnameseNormalizer,
)
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.modules.workflows.support_contacts import SupportContactDirectory
from src.chatbot.shared.enums import IntentType, PageCode
from src.chatbot.shared.events import (
    InboxEvent,
    IntentAnalysisResult,
    NormalizedMessage,
)

ROOT = Path(__file__).resolve().parents[2]
REPLAYS = json.loads(
    (ROOT / "tests/fixtures/cfc_conversation_replays.json").read_text(encoding="utf-8")
)["transcripts"]


class TurnIntentClient:
    def __init__(self) -> None:
        self.intent = IntentType.GENERAL_FAQ

    def analyze(self, page_id: str, text: str, context=None) -> IntentAnalysisResult:
        return IntentAnalysisResult(primary_intent=self.intent, confidence=0.95)


class ReplayConversationRepository:
    def __init__(self) -> None:
        self.contexts: dict[tuple[str, str], dict] = {}
        self.tasks: list[dict] = []
        self.version = 0

    def load_understanding_context(self, page_id, conversation_id):
        return dict(self.contexts.get((page_id.value, conversation_id), {}))

    def update_context(
        self, page_id, conversation_id, *, workflow, primary_intent, slots
    ):
        self.version += 1
        self.contexts[(page_id.value, conversation_id)] = {
            "current_workflow": workflow.value,
            "current_intent": primary_intent.value,
            "current_slots": dict(slots),
        }
        return SimpleNamespace(version=self.version)

    def create_handoff_task(self, page_id, conversation_id, **kwargs):
        self.tasks.append(
            {"page_id": page_id.value, "conversation_id": conversation_id, **kwargs}
        )
        return f"replay-task-{len(self.tasks)}"


def _event(transcript_id: str, turn_index: int, text: str) -> InboxEvent:
    sender = f"replay-{transcript_id}"
    return InboxEvent(
        event_id=f"{sender}-{turn_index}",
        page_id=PageCode.CFC,
        sender_id=sender,
        message=NormalizedMessage(
            mid=f"mid-{sender}-{turn_index}",
            sender_id=sender,
            recipient_id="page-cfc-replay",
            timestamp=datetime.now(UTC),
            text=text,
        ),
    )


def _assert_safe_reply(reply: str) -> None:
    folded = reply.casefold()
    assert "snapshot crm" not in folded
    assert not re.search(r"\{\{?.+?\}?\}|\$\{.+?\}|\[[a-z_\\]+\]", reply)
    assert not re.search(r"\b(?:chào em|chào chị/em|chị/chú|cô/bác|bạn ơi)\b", folded)
    assert not re.search(r"\b\d+[\s.]*(?:nghìn|ngàn|triệu|vnd|đồng)\b", folded)


@pytest.mark.parametrize("transcript", REPLAYS, ids=lambda item: item["id"])
def test_recorded_messenger_transcript_replays_cleanly(transcript: dict) -> None:
    client = TurnIntentClient()
    normalizer = VietnameseNormalizer(
        ROOT / "config/normalization/vi_intent.json",
        ROOT / "config/normalization/administrative_areas.json",
    )
    repository = ReplayConversationRepository()
    composer = ResponseComposer(
        contact_directory=SupportContactDirectory.from_file(
            ROOT / "config/business/support_contacts.json"
        )
    )
    analyzer = HybridInputAnalyzer(client, normalizer)
    pipeline: SafeMessagePipeline | None = None

    for index, turn in enumerate(transcript["turns"], start=1):
        client.intent = IntentType(turn["model_intent"])
        if pipeline is None or turn.get("restart_before"):
            # Recreate the worker-side objects while retaining repository state.
            pipeline = SafeMessagePipeline(
                InMemoryOutboxStore(),
                intent_analyzer=analyzer,
                conversation_repository=repository,
                composer=composer,
            )
        outbox_id = pipeline.process(
            _event(transcript["id"], index, turn["text"]),
            batch_version=index,
        )
        assert outbox_id is not None
        reply = pipeline.outbox.messages[outbox_id].text
        state = repository.contexts[
            (PageCode.CFC.value, f"CFC:replay-{transcript['id']}")
        ]
        assert state["current_intent"] == turn["expected_intent"]
        _assert_safe_reply(reply)
