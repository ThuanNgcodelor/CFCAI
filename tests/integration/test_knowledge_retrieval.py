from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    KnowledgeRecord,
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
