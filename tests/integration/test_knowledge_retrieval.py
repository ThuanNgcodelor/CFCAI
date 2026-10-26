import os

import psycopg2
import pytest

from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    KnowledgeRecord,
    KnowledgeSearchResult,
    PostgresKnowledgeStore,
)
from src.chatbot.shared.enums import PageCode


def test_retrieval_is_approved_and_page_isolated() -> None:
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord(
                "cfc-1", PageCode.CFC, "Coban", "Hướng dẫn sử dụng", "APPROVED"
            ),
            KnowledgeRecord(
                "zeo-1", PageCode.ZEO, "Zeolite", "Hướng dẫn sử dụng", "APPROVED"
            ),
            KnowledgeRecord(
                "cfc-q", PageCode.CFC, "Coban", "Nội dung mới", "QUARANTINED"
            ),
        ]
    )
    result = store.search(PageCode.CFC, "hướng dẫn")
    assert [item.record_id for item in result] == ["cfc-1"]


def test_retrieval_never_returns_quarantined_records() -> None:
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord("q", PageCode.CFC, "FAQ", "secret", "QUARANTINED"),
        ]
    )
    assert store.search(PageCode.CFC, "secret") == []


def test_retrieval_never_returns_inactive_or_internal_records() -> None:
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord(
                "inactive", PageCode.CFC, "Alias inactive", "hidden", "APPROVED",
                is_active=False,
            ),
            KnowledgeRecord(
                "internal", PageCode.CFC, "Alias internal", "hidden", "APPROVED",
                audience="internal",
            ),
        ]
    )
    assert store.search(PageCode.CFC, "Alias inactive") == []
    assert store.search(PageCode.CFC, "Alias internal") == []


@pytest.mark.parametrize("query", ["giá", "sản phẩm", "gần nhất", "Giang"])
def test_common_terms_do_not_select_an_arbitrary_record(query: str) -> None:
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord(
                "faq:one", PageCode.CFC, "Giá sản phẩm gần nhất An Giang",
                "Nội dung một", "APPROVED",
            ),
            KnowledgeRecord(
                "faq:two", PageCode.CFC, "Sản phẩm tại Kiên Giang",
                "Nội dung hai", "APPROVED",
            ),
        ]
    )
    assert store.search(PageCode.CFC, query, record_prefix="faq:") == []


def test_ambiguous_lexical_match_is_explicit_and_returns_no_answer() -> None:
    store = ApprovedKnowledgeStore(
        [
            KnowledgeRecord("faq:one", PageCode.CFC, "bón cây mít", "A", "APPROVED"),
            KnowledgeRecord("faq:two", PageCode.CFC, "bón cây xoài", "B", "APPROVED"),
        ]
    )
    decision = store.search_with_confidence(
        PageCode.CFC, "cách bón cây", record_prefix="faq:"
    )
    assert isinstance(decision, KnowledgeSearchResult)
    assert decision.status == "AMBIGUOUS"
    assert decision.records == ()


def test_postgres_knowledge_store_is_page_scoped() -> None:
    dsn = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://cfc_admin:cfc_secret_password@localhost:5432/cfc_zeo_db",
    )
    store = PostgresKnowledgeStore(dsn)
    try:
        store.add(
            KnowledgeRecord(
                "integration-cfc",
                PageCode.CFC,
                "Coban FAQ",
                "approved answer",
                "APPROVED",
            )
        )
        store.add(
            KnowledgeRecord(
                "integration-zeo",
                PageCode.ZEO,
                "Zeo FAQ",
                "approved answer",
                "APPROVED",
            )
        )
    except psycopg2.Error as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    assert [item.record_id for item in store.search(PageCode.CFC, "approved")] == [
        "integration-cfc"
    ]
