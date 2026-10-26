from __future__ import annotations

import uuid

import psycopg2

from src.chatbot.modules.integrations.excel.importer import ExcelCatalogImporter
from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.modules.knowledge.retriever import PostgresKnowledgeStore
from src.chatbot.shared.enums import PageCode


def test_excel_import_is_idempotent_quarantined_and_page_scoped(
    isolated_database_url: str,
) -> None:
    repository = CatalogPublishRepository(isolated_database_url)
    first = ExcelCatalogImporter(repository=repository).import_cfc_file()
    second = ExcelCatalogImporter(repository=repository).import_cfc_file()
    assert first["batch_id"] == second["batch_id"]
    with psycopg2.connect(isolated_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM import_batches WHERE page_id='CFC'")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT count(*) FROM faq_items WHERE import_batch_id=%s AND status='QUARANTINED'",
            (first["batch_id"],),
        )
        assert cursor.fetchone()[0] == first["imported_faq_count"]
        cursor.execute("SELECT count(*) FROM faq_items WHERE page_id='ZEO'")
        assert cursor.fetchone()[0] == 0


def test_publish_excludes_private_price_and_non_customer_faq(
    isolated_database_url: str,
) -> None:
    repository = CatalogPublishRepository(isolated_database_url)
    report = ExcelCatalogImporter(repository=repository).import_zeo_file()
    repository.approve_batch(PageCode.ZEO, report["batch_id"])
    version = repository.publish_batch(PageCode.ZEO, report["batch_id"])
    assert version == 1
    with psycopg2.connect(isolated_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM catalog_items WHERE import_batch_id=%s AND internal_data ? 'price'",
            (report["batch_id"],),
        )
        assert cursor.fetchone()[0] > 0
        cursor.execute(
            """SELECT count(*) FROM knowledge_records
            WHERE source_batch_id=%s AND (content ILIKE '%%"price"%%' OR title ILIKE '%%"price"%%')""",
            (report["batch_id"],),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            """SELECT count(*) FROM knowledge_records k JOIN faq_items f
            ON k.record_id='faq:'||f.faq_id
            WHERE k.source_batch_id=%s AND lower(f.audience)<>'customer'""",
            (report["batch_id"],),
        )
        assert cursor.fetchone()[0] == 0


def test_publication_can_rollback_without_cross_page_leakage(
    isolated_database_url: str,
) -> None:
    repository = CatalogPublishRepository(isolated_database_url)
    first = ExcelCatalogImporter(repository=repository).import_cfc_file()
    repository.approve_batch(PageCode.CFC, first["batch_id"])
    first_version = repository.publish_batch(PageCode.CFC, first["batch_id"])

    batch_id = f"synthetic-{uuid.uuid4().hex}"
    faq_id = f"faq-{uuid.uuid4().hex}"
    report = {
        "batch_id": batch_id,
        "page_id": "CFC",
        "file": "synthetic.xlsx",
        "source_checksum": uuid.uuid4().hex,
        "mapping_version": 1,
        "conflict_count": 0,
    }
    faq = {
        "faq_id": faq_id,
        "page_id": "CFC",
        "source_file": "synthetic.xlsx",
        "source_sheet": "FAQ",
        "source_row": 2,
        "intent": "TEST_ONLY",
        "category": "test",
        "question_examples": ["unique rollback question"],
        "answer": "unique rollback answer",
        "audience": "customer",
        "response_mode": "direct",
        "risk_level": "LOW",
        "source_active": True,
        "content_hash": uuid.uuid4().hex,
        "status": "QUARANTINED",
    }
    repository.stage(report, [faq], [])
    repository.approve_batch(PageCode.CFC, batch_id)
    second_version = repository.publish_batch(PageCode.CFC, batch_id)
    assert second_version == first_version + 1
    store = PostgresKnowledgeStore(isolated_database_url)
    assert store.search(PageCode.CFC, "unique rollback")
    assert store.search(PageCode.ZEO, "unique rollback") == []

    assert repository.rollback(PageCode.CFC, first_version) == first["batch_id"]
    assert store.search(PageCode.CFC, "unique rollback") == []


def test_record_review_and_batch_rejection_are_page_scoped(
    isolated_database_url: str,
) -> None:
    repository = CatalogPublishRepository(isolated_database_url)
    report = ExcelCatalogImporter(repository=repository).import_cfc_file()
    with psycopg2.connect(isolated_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT faq_id FROM faq_items WHERE import_batch_id=%s ORDER BY source_row LIMIT 1",
            (report["batch_id"],),
        )
        faq_id = cursor.fetchone()[0]
    assert repository.review_record(
        PageCode.CFC,
        report["batch_id"],
        record_type="faq",
        record_id=faq_id,
        decision="APPROVED",
    )
    assert not repository.review_record(
        PageCode.ZEO,
        report["batch_id"],
        record_type="faq",
        record_id=faq_id,
        decision="REJECTED",
    )
    assert repository.reject_batch(PageCode.CFC, report["batch_id"]) > 0


def test_review_listing_never_exposes_private_commerce_data(
    isolated_database_url: str,
) -> None:
    repository = CatalogPublishRepository(isolated_database_url)
    report = ExcelCatalogImporter(repository=repository).import_zeo_file()
    records = repository.list_records(PageCode.ZEO, report["batch_id"], limit=500)
    assert records
    serialized = str(records).casefold()
    assert "internal_data" not in serialized
    assert "'price'" not in serialized
