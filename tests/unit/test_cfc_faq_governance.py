from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.normalize_cfc_faq_persona import normalize_document
from src.chatbot.modules.integrations.markdown.importer import MarkdownCatalogImporter
from src.chatbot.shared.enums import IntentType

SOURCE = Path("data/sources/cfc/faq/CFC_Co_Bay_FAQ.md")
MAPPING = Path("config/data_sources/markdown_mapping.json")
GOVERNANCE = Path("config/data_sources/cfc_faq_governance.json")


def test_cfc_faq_governance_covers_every_source_record() -> None:
    policy = json.loads(GOVERNANCE.read_text(encoding="utf-8"))["records"]
    assert list(policy) == [str(number) for number in range(1, 48)]
    assert all("intent" in row and "source_active" in row for row in policy.values())


def test_cfc_faq_source_persona_is_normalized_and_idempotent() -> None:
    document = SOURCE.read_text(encoding="utf-8")
    assert normalize_document(document) == document
    importer = MarkdownCatalogImporter(MAPPING)
    importer.import_source("cfc-co-bay-faq")
    banned = re.compile(r"\b(?:bạn|admin|chúng tôi)\b", re.IGNORECASE)
    assert all(not banned.search(item["answer"]) for item in importer.staged_faqs)


def test_cfc_faq_only_safe_workflow_records_are_active_before_signoff() -> None:
    importer = MarkdownCatalogImporter(MAPPING)
    report = importer.import_source("cfc-co-bay-faq")
    assert report["imported_faq_count"] == 44
    assert report["skipped_row_count"] == 3
    assert sum(item["source_active"] for item in importer.staged_faqs) == 8
    allowed_intents = {intent.value for intent in IntentType}
    assert all(item["intent"] in allowed_intents for item in importer.staged_faqs)
    for item in importer.staged_faqs:
        if "review_status:pending_expert" in item["learning_tags"]:
            assert item["source_active"] is False
