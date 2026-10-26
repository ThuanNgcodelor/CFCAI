from __future__ import annotations

from pathlib import Path

import psycopg2

from src.chatbot.modules.integrations.data_loader import DataSourceLoader
from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.shared.enums import PageCode


def test_loader_stages_changed_source_once_and_audits_actor(
    isolated_database_url: str, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        """version: 1
sources:
  - id: fixture-faq
    page_id: CFC
    kind: markdown_faq
    path: tests/fixtures/markdown_faq_legacy.md
    mapping: tests/fixtures/markdown_mapping.json
    importer_source: fixture-cfc-faq
    auto_stage: true
    auto_publish: false
""",
        encoding="utf-8",
    )
    repository = CatalogPublishRepository(isolated_database_url)
    loader = DataSourceLoader(manifest, repository)

    first = loader.stage_changed(actor="integration-test")
    second = loader.stage_changed(actor="integration-test")

    assert first[0]["status"] == "STAGED"
    assert second[0]["status"] == "UNCHANGED"
    batch_id = first[0]["batch_id"]
    assert repository.approve_batch(PageCode.CFC, batch_id, actor="reviewer") == 1
    assert repository.publish_batch(PageCode.CFC, batch_id, actor="publisher") == 1

    with (
        psycopg2.connect(isolated_database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """SELECT action,actor FROM data_ingestion_audit
            WHERE batch_id=%s ORDER BY audit_id""",
            (batch_id,),
        )
        assert cursor.fetchall() == [
            ("STAGE", "integration-test"),
            ("APPROVE_BATCH", "reviewer"),
            ("PUBLISH", "publisher"),
        ]
