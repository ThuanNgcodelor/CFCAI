"""Page-isolated retrieval over approved knowledge records only."""

from __future__ import annotations

from dataclasses import dataclass

from src.chatbot.shared.enums import PageCode


@dataclass(frozen=True)
class KnowledgeRecord:
    record_id: str
    page_id: PageCode
    title: str
    content: str
    status: str = "QUARANTINED"


class ApprovedKnowledgeStore:
    def __init__(self, records: list[KnowledgeRecord] | None = None) -> None:
        self._records = records or []

    def add(self, record: KnowledgeRecord) -> None:
        self._records.append(record)

    def search(
        self, page_id: PageCode, query: str, limit: int = 5
    ) -> list[KnowledgeRecord]:
        tokens = {token for token in query.lower().split() if len(token) > 1}
        matches = []
        for record in self._records:
            if record.page_id != page_id or record.status != "APPROVED":
                continue
            haystack = f"{record.title} {record.content}".lower()
            score = sum(token in haystack for token in tokens)
            if score:
                matches.append((score, record))
        matches.sort(key=lambda item: (-item[0], item[1].record_id))
        return [record for _, record in matches[:limit]]
