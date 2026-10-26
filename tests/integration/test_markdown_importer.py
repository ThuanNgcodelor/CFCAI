from __future__ import annotations

import psycopg2

from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.modules.integrations.markdown.importer import MarkdownCatalogImporter
from src.chatbot.modules.knowledge.retriever import PostgresKnowledgeStore
from src.chatbot.shared.enums import PageCode


def test_markdown_import_stages_then_publishes_only_after_review(
    isolated_database_url: str,
) -> None:
    repository = CatalogPublishRepository(isolated_database_url)
    importer = MarkdownCatalogImporter(
        "tests/fixtures/markdown_mapping.json",
        repository=repository,
    )

    report = importer.import_source("fixture-cfc-faq")

    with psycopg2.connect(isolated_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status, source_file FROM import_batches WHERE batch_id=%s",
            (report["batch_id"],),
        )
        assert cursor.fetchone() == ("QUARANTINED", "tests/fixtures/markdown_faq_legacy.md")
        cursor.execute(
            "SELECT status, source_sheet, source_row FROM faq_items WHERE import_batch_id=%s",
            (report["batch_id"],),
        )
        assert cursor.fetchone()[0] == "QUARANTINED"

    assert repository.approve_batch(PageCode.CFC, report["batch_id"]) == 1
    assert repository.publish_batch(PageCode.CFC, report["batch_id"]) == 1
    store = PostgresKnowledgeStore(isolated_database_url)
    records = store.search(PageCode.CFC, "câu trả lời duyệt")
    assert len(records) == 1
    assert records[0].source_locator is not None
    assert "markdown_faq_legacy.md:FAQ:" in records[0].source_locator
    assert store.search(PageCode.ZEO, "câu trả lời duyệt") == []
