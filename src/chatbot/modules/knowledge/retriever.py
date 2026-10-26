"""Page-isolated retrieval over approved knowledge records only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.chatbot.core.settings import settings
from src.chatbot.shared.enums import PageCode


@dataclass(frozen=True)
class KnowledgeRecord:
    record_id: str
    page_id: PageCode
    title: str
    content: str
    status: str = "QUARANTINED"


class KnowledgeSearchStore(Protocol):
    def search(
        self,
        page_id: PageCode,
        query: str,
        limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]: ...


class ApprovedKnowledgeStore:
    def __init__(self, records: list[KnowledgeRecord] | None = None) -> None:
        self._records = records or []

    def add(self, record: KnowledgeRecord) -> None:
        self._records.append(record)

    def search(
        self, page_id: PageCode, query: str, limit: int = 5, record_prefix: str | tuple[str, ...] | None = None
    ) -> list[KnowledgeRecord]:
        tokens = {token for token in query.lower().split() if len(token) > 1}
        matches = []
        for record in self._records:
            if record.page_id != page_id or record.status != "APPROVED":
                continue
            if record_prefix and not record.record_id.startswith(record_prefix):
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
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS source_batch_id TEXT;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS audience TEXT NOT NULL DEFAULT 'customer';
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS source_locator TEXT;
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

    def approve(self, record_id: str) -> bool:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_records SET status='APPROVED' WHERE record_id=%s",
                (record_id,),
            )
            return cursor.rowcount == 1

    def approve_page(self, page_id: PageCode) -> int:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_records SET status='APPROVED' WHERE page_id=%s",
                (page_id.value,),
            )
            return cursor.rowcount

    def search(
        self, page_id: PageCode, query: str, limit: int = 5, record_prefix: str | tuple[str, ...] | None = None
    ) -> list[KnowledgeRecord]:
        self._ensure_schema()
        prefix_values = None
        if record_prefix:
            prefix_values = (record_prefix,) if isinstance(record_prefix, str) else record_prefix
        tokens = [token for token in query.lower().split() if len(token) > 1]
        if not tokens:
            return []
        with self._connect() as connection, connection.cursor() as cursor:
            sql = "SELECT record_id,page_id,title,content,status FROM knowledge_records WHERE page_id=%s AND status='APPROVED' AND audience='customer' AND is_active=true"
            params: list[object] = [page_id.value]
            if prefix_values:
                sql += " AND (" + " OR ".join("record_id LIKE %s" for _ in prefix_values) + ")"
                params.extend(f"{prefix}%" for prefix in prefix_values)
            cursor.execute(sql, tuple(params))
            records = [
                KnowledgeRecord(row[0], PageCode(row[1]), row[2], row[3], row[4])
                for row in cursor.fetchall()
            ]
        scored = []
        for record in records:
            haystack = f"{record.title} {record.content}".lower()
            score = sum(token in haystack for token in tokens)
            if score:
                scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], item[1].record_id))
        return [record for _, record in scored[:limit]]


class RedisCrmProductStore:
    """Read the approved CRM product snapshot without exposing prices."""

    def __init__(self, redis_url: str | None = None) -> None:
        import redis

        self._redis = redis.Redis.from_url(
            redis_url or settings.get_redis_url(), decode_responses=True
        )

    def search(
        self, page_id: PageCode, query: str, limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        if page_id != PageCode.CFC or record_prefix and not (
            "crm-product:" in record_prefix if isinstance(record_prefix, tuple) else record_prefix == "crm-product:"
        ):
            return []
        raw = self._redis.get("cfc:products:catalog")
        if not raw:
            return []
        import json

        tokens = [token for token in query.lower().split() if len(token) > 1]
        records = []
        for item in json.loads(raw):
            name = str(item.get("name") or "")
            haystack = f"{name} {item.get('code') or ''}".lower()
            score = sum(token in haystack for token in tokens)
            if score:
                records.append((score, KnowledgeRecord(
                    f"crm-product:{item.get('code') or name}", page_id, name,
                    f"{name} | Mã sản phẩm: {item.get('code') or 'chưa có'} | Đơn vị: {item.get('unit') or 'chưa cập nhật'}",
                    "APPROVED",
                )))
        records.sort(key=lambda item: (-item[0], item[1].record_id))
        return [record for _, record in records[:limit]]


class RedisCrmDealerStore:
    def __init__(self, redis_url: str | None = None) -> None:
        import redis

        self._redis = redis.Redis.from_url(redis_url or settings.get_redis_url(), decode_responses=True)

    def search(
        self, page_id: PageCode, query: str, limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        if page_id != PageCode.CFC:
            return []
        allowed = record_prefix is None or ("dealer:" in record_prefix if isinstance(record_prefix, tuple) else record_prefix == "dealer:")
        if not allowed:
            return []
        raw = self._redis.get("cfc:dealers:locations")
        if not raw:
            return []
        import json

        normalized_query = query.lower()
        stop_words = {
            "tôi", "cho", "mình", "tìm", "đại", "lý", "gần", "nhất", "ở", "tại",
            "đâu", "nào", "xin", "hỏi", "mua", "muốn", "em", "anh", "chị", "ơi",
            "điểm", "bán", "cửa", "hàng", "chỗ", "sản", "phẩm", "phân", "bón",
            "hữu", "cơ", "thuốc", "vật", "tư", "nông", "nghiệp", "vtnn", "công",
            "ty", "tnhh", "hộ", "kinh", "doanh", "trách", "nhiệm", "hữu", "hạn",
            "mtv", "một", "thành", "viên", "cơ", "sở", "bên", "có", "không", "ko",
            "dạ", "vâng", "ạ", "giúp"
        }
        tokens = [token for token in normalized_query.split() if token not in stop_words and len(token) > 1]
        if not tokens:
            return []

        phrase = " ".join(tokens)
        matches = []
        for item in json.loads(raw):
            name = str(item.get("name") or "").strip()
            address = str(item.get("address") or "").strip()
            # Physical dealer lookup requires an address to visit, unless explicitly searching by exact dealer name
            has_valid_address = bool(address and address.lower() not in {"chưa cập nhật địa chỉ", "chưa cập nhật", "null", "none"})
            is_exact_name_query = bool(phrase and phrase in name.lower())
            if not has_valid_address and not is_exact_name_query:
                continue

            haystack = f"{name} {address}".lower()
            score = 0
            if phrase and phrase in haystack:
                score += 10
            matched_tokens = sum(1 for token in tokens if token in haystack)
            if matched_tokens == len(tokens) or (len(tokens) >= 2 and matched_tokens >= len(tokens) * 0.7):
                score += matched_tokens * 2

            if score >= 2:
                content_display = f"{name} — {address}" if has_valid_address else name
                matches.append((score, KnowledgeRecord(
                    f"dealer:{item.get('code') or name}", page_id, name,
                    content_display,
                    "APPROVED",
                )))
        matches.sort(key=lambda item: (-item[0], item[1].record_id))
        return [record for _, record in matches[:limit]]


class RedisCrmOrderStore:
    def __init__(self, redis_url: str | None = None) -> None:
        import redis

        self._redis = redis.Redis.from_url(
            redis_url or settings.get_redis_url(), decode_responses=True
        )

    def find_by_phone(self, phone: str) -> list[dict[str, Any]]:
        import json
        import re

        clean_phone = re.sub(r"\D", "", phone)
        if clean_phone.startswith("84"):
            clean_phone = "0" + clean_phone[2:]
        raw = self._redis.get(f"cfc:orders:phone:{clean_phone}")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def find_by_code(self, order_code: str) -> dict[str, Any] | None:
        import json

        clean_code = order_code.strip().upper()
        raw = self._redis.get(f"cfc:orders:code:{clean_code}")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        return None


class CompositeKnowledgeStore:
    def __init__(self, *stores: KnowledgeSearchStore) -> None:
        self.stores = stores

    def search(
        self, page_id: PageCode, query: str, limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        matches: list[KnowledgeRecord] = []
        for store in self.stores:
            matches.extend(store.search(page_id, query, limit, record_prefix))
        return matches[:limit]
