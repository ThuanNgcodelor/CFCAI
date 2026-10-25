"""Page-isolated retrieval over approved knowledge records only."""

from __future__ import annotations

from dataclasses import dataclass

from src.chatbot.core.settings import settings
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


class PostgresKnowledgeStore:
    _schema = """
    CREATE TABLE IF NOT EXISTS knowledge_records (
        record_id TEXT PRIMARY KEY, page_id TEXT NOT NULL, title TEXT NOT NULL,
        content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'QUARANTINED',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_knowledge_page_status ON knowledge_records(page_id, status);
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._dsn = (database_url or settings.get_database_url()).replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
        self._ready = False

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self._dsn)

    def _ensure_schema(self) -> None:
        if not self._ready:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(self._schema)
            self._ready = True

    def add(self, record: KnowledgeRecord) -> None:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_records(record_id,page_id,title,content,status)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT(record_id) DO UPDATE SET
                title=EXCLUDED.title, content=EXCLUDED.content, status=EXCLUDED.status""",
                (
                    record.record_id,
                    record.page_id.value,
                    record.title,
                    record.content,
                    record.status,
                ),
            )

    def search(
        self, page_id: PageCode, query: str, limit: int = 5
    ) -> list[KnowledgeRecord]:
        self._ensure_schema()
        pattern = f"%{query}%"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT record_id,page_id,title,content,status FROM knowledge_records
                WHERE page_id=%s AND status='APPROVED' AND (title ILIKE %s OR content ILIKE %s)
                ORDER BY record_id LIMIT %s""",
                (page_id.value, pattern, pattern, limit),
            )
            return [
                KnowledgeRecord(row[0], PageCode(row[1]), row[2], row[3], row[4])
                for row in cursor.fetchall()
            ]
