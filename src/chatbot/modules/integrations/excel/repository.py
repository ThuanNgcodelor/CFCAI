"""PostgreSQL staging, approval, publish and rollback repository."""

from __future__ import annotations

import json
from typing import Any

from src.chatbot.shared.enums import PageCode


class CatalogPublishRepository:
    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self._dsn)

    def stage(
        self,
        report: dict[str, Any],
        faqs: list[dict[str, Any]],
        products: list[dict[str, Any]],
    ) -> str:
        batch_id = str(report["batch_id"])
        batch_status = "CONFLICT" if report["conflict_count"] else "QUARANTINED"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO import_batches(
                batch_id,page_id,source_file,source_checksum,mapping_version,status,
                record_count,conflict_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(page_id,source_checksum,mapping_version) DO UPDATE SET
                record_count=EXCLUDED.record_count,conflict_count=EXCLUDED.conflict_count
                RETURNING batch_id""",
                (
                    batch_id,
                    report["page_id"],
                    report["file"],
                    report["source_checksum"],
                    report["mapping_version"],
                    batch_status,
                    len(faqs) + len(products),
                    report["conflict_count"],
                ),
            )
            stored_batch_id = str(cursor.fetchone()[0])
            if stored_batch_id != batch_id:
                raise ValueError("Idempotency collision for import batch")
            for item in faqs:
                cursor.execute(
                    """INSERT INTO faq_items(
                    faq_id,page_id,import_batch_id,source_file,source_sheet,source_row,
                    intent,category,question_examples,answer,audience,response_mode,
                    risk_level,learning_tags,profile_slots,source_active,content_hash,status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                    ON CONFLICT(import_batch_id,source_sheet,source_row) DO NOTHING""",
                    (
                        item["faq_id"], item["page_id"], batch_id, item["source_file"],
                        item["source_sheet"], item["source_row"], item["intent"],
                        item["category"], json.dumps(item["question_examples"], ensure_ascii=False),
                        item["answer"], item["audience"], item["response_mode"],
                        item["risk_level"], json.dumps(item.get("learning_tags", []), ensure_ascii=False),
                        json.dumps(item.get("profile_slots", []), ensure_ascii=False), item["source_active"], item["content_hash"],
                        item["status"],
                    ),
                )
            for item in products:
                cursor.execute(
                    """INSERT INTO catalog_items(
                    catalog_id,page_id,import_batch_id,source_file,source_sheet,source_row,
                    sku,name,brand,category,specs,keywords,internal_data,source_active,
                    content_hash,status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s)
                    ON CONFLICT(import_batch_id,source_sheet,source_row) DO NOTHING""",
                    (
                        item["catalog_id"], item["page_id"], batch_id, item["source_file"],
                        item["source_sheet"], item["source_row"], item["sku"], item["name"],
                        item["brand"], item["category"], json.dumps(item["specs"], ensure_ascii=False),
                        json.dumps(item["keywords"], ensure_ascii=False),
                        json.dumps(item["internal_data"], ensure_ascii=False), item["source_active"],
                        item["content_hash"], item["status"],
                    ),
                )
        return batch_id

    def approve_batch(self, page_id: PageCode, batch_id: str) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT status,conflict_count FROM import_batches
                WHERE batch_id=%s AND page_id=%s FOR UPDATE""",
                (batch_id, page_id.value),
            )
            batch = cursor.fetchone()
            if batch is None:
                raise ValueError("unknown import batch or page scope mismatch")
            if int(batch[1]) > 0 or batch[0] == "CONFLICT":
                raise ValueError("conflicted batch cannot be approved")
            cursor.execute(
                """UPDATE faq_items SET status='APPROVED'
                WHERE import_batch_id=%s AND page_id=%s AND status='QUARANTINED'""",
                (batch_id, page_id.value),
            )
            approved = cursor.rowcount
            cursor.execute(
                """UPDATE catalog_items SET status='APPROVED'
                WHERE import_batch_id=%s AND page_id=%s AND status='QUARANTINED'""",
                (batch_id, page_id.value),
            )
            approved += cursor.rowcount
            cursor.execute(
                """UPDATE import_batches SET status='APPROVED',approved_at=now()
                WHERE batch_id=%s AND page_id=%s""",
                (batch_id, page_id.value),
            )
        return approved

    def reject_batch(self, page_id: PageCode, batch_id: str) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM import_batches
                WHERE batch_id=%s AND page_id=%s AND status<>'PUBLISHED' FOR UPDATE""",
                (batch_id, page_id.value),
            )
            if cursor.fetchone() is None:
                raise ValueError("unknown, published, or cross-page import batch")
            cursor.execute(
                """UPDATE faq_items SET status='REJECTED'
                WHERE import_batch_id=%s AND page_id=%s AND status IN ('QUARANTINED','APPROVED')""",
                (batch_id, page_id.value),
            )
            rejected = cursor.rowcount
            cursor.execute(
                """UPDATE catalog_items SET status='REJECTED'
                WHERE import_batch_id=%s AND page_id=%s AND status IN ('QUARANTINED','APPROVED')""",
                (batch_id, page_id.value),
            )
            rejected += cursor.rowcount
            cursor.execute(
                """UPDATE import_batches SET status='REJECTED'
                WHERE batch_id=%s AND page_id=%s""",
                (batch_id, page_id.value),
            )
        return rejected

    def review_record(
        self,
        page_id: PageCode,
        batch_id: str,
        *,
        record_type: str,
        record_id: str,
        decision: str,
    ) -> bool:
        table_and_key = {
            "faq": ("faq_items", "faq_id"),
            "product": ("catalog_items", "catalog_id"),
        }.get(record_type)
        if table_and_key is None:
            raise ValueError("record_type must be faq or product")
        status = decision.upper()
        if status not in {"APPROVED", "REJECTED"}:
            raise ValueError("decision must be APPROVED or REJECTED")
        table, key = table_and_key
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE {table} SET status=%s
                WHERE {key}=%s AND import_batch_id=%s AND page_id=%s
                  AND status<>'CONFLICT'""",
                (status, record_id, batch_id, page_id.value),
            )
            return cursor.rowcount == 1

    def list_records(
        self,
        page_id: PageCode,
        batch_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return review-safe fields only; private commerce data is never exposed."""
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("limit must be 1..500 and offset must be non-negative")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM import_batches WHERE batch_id=%s AND page_id=%s""",
                (batch_id, page_id.value),
            )
            if cursor.fetchone() is None:
                raise ValueError("unknown import batch or page scope mismatch")
            cursor.execute(
                """
                SELECT record_type,record_id,source_sheet,source_row,title,content,status
                FROM (
                    SELECT 'faq' AS record_type,faq_id AS record_id,source_sheet,source_row,
                           intent AS title,answer AS content,status
                    FROM faq_items WHERE import_batch_id=%s AND page_id=%s
                    UNION ALL
                    SELECT 'product',catalog_id,source_sheet,source_row,
                           name,concat_ws(' ',sku,brand,category,specs->>'text'),status
                    FROM catalog_items WHERE import_batch_id=%s AND page_id=%s
                ) records
                ORDER BY record_type,source_sheet,source_row
                LIMIT %s OFFSET %s
                """,
                (
                    batch_id,
                    page_id.value,
                    batch_id,
                    page_id.value,
                    limit,
                    offset,
                ),
            )
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def publish_batch(self, page_id: PageCode, batch_id: str) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT status FROM import_batches
                WHERE batch_id=%s AND page_id=%s FOR UPDATE""",
                (batch_id, page_id.value),
            )
            row = cursor.fetchone()
            if row is None or row[0] not in {"APPROVED", "PUBLISHED"}:
                raise ValueError("only an approved batch can be published")
            cursor.execute(
                "SELECT COALESCE(max(version),0)+1 FROM catalog_publications WHERE page_id=%s",
                (page_id.value,),
            )
            version = int(cursor.fetchone()[0])
            cursor.execute(
                "UPDATE catalog_publications SET status='INACTIVE' WHERE page_id=%s AND status='ACTIVE'",
                (page_id.value,),
            )
            cursor.execute(
                """INSERT INTO catalog_publications(page_id,version,import_batch_id,status)
                VALUES (%s,%s,%s,'ACTIVE')""",
                (page_id.value, version, batch_id),
            )
            self._replace_read_model(cursor, page_id, batch_id)
            cursor.execute(
                """UPDATE import_batches SET status='PUBLISHED',published_at=now()
                WHERE batch_id=%s AND page_id=%s""",
                (batch_id, page_id.value),
            )
        return version

    def rollback(self, page_id: PageCode, target_version: int) -> str:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT import_batch_id FROM catalog_publications
                WHERE page_id=%s AND version=%s FOR UPDATE""",
                (page_id.value, target_version),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("unknown publication version or page scope mismatch")
            batch_id = str(row[0])
            cursor.execute(
                "UPDATE catalog_publications SET status='INACTIVE' WHERE page_id=%s AND status='ACTIVE'",
                (page_id.value,),
            )
            cursor.execute(
                """UPDATE catalog_publications SET status='ACTIVE'
                WHERE page_id=%s AND version=%s""",
                (page_id.value, target_version),
            )
            self._replace_read_model(cursor, page_id, batch_id)
        return batch_id

    @staticmethod
    def _replace_read_model(cursor, page_id: PageCode, batch_id: str) -> None:
        cursor.execute(
            """UPDATE knowledge_records SET is_active=false
            WHERE page_id=%s AND source_batch_id IS NOT NULL""",
            (page_id.value,),
        )
        cursor.execute(
            """INSERT INTO knowledge_records(
            record_id,page_id,title,content,status,source_batch_id,audience,is_active,source_locator,
            intent,category,response_mode,risk_level,learning_tags,profile_slots)
            SELECT 'faq:'||faq_id,page_id,
                   array_to_string(ARRAY(SELECT jsonb_array_elements_text(question_examples)), ' | '),
                   answer,'APPROVED',import_batch_id,audience,true,
                   source_file||':'||source_sheet||':'||source_row,
                   intent,category,response_mode,risk_level,learning_tags,profile_slots
            FROM faq_items
            WHERE import_batch_id=%s AND page_id=%s AND status='APPROVED'
              AND source_active=true AND lower(audience)='customer'
            ON CONFLICT(record_id) DO UPDATE SET
              title=EXCLUDED.title,content=EXCLUDED.content,status='APPROVED',
              source_batch_id=EXCLUDED.source_batch_id,audience=EXCLUDED.audience,
              is_active=true,source_locator=EXCLUDED.source_locator,
              intent=EXCLUDED.intent,category=EXCLUDED.category,response_mode=EXCLUDED.response_mode,
              risk_level=EXCLUDED.risk_level,learning_tags=EXCLUDED.learning_tags,
              profile_slots=EXCLUDED.profile_slots""",
            (batch_id, page_id.value),
        )
        cursor.execute(
            """INSERT INTO knowledge_records(
            record_id,page_id,title,content,status,source_batch_id,audience,is_active,source_locator)
            SELECT 'product:'||catalog_id,page_id,name,
                   concat_ws(' ',name,brand,category,specs->>'text',
                             array_to_string(ARRAY(SELECT jsonb_array_elements_text(keywords)), ' ')),
                   'APPROVED',import_batch_id,'customer',true,
                   source_file||':'||source_sheet||':'||source_row
            FROM catalog_items
            WHERE import_batch_id=%s AND page_id=%s AND status='APPROVED' AND source_active=true
            ON CONFLICT(record_id) DO UPDATE SET
              title=EXCLUDED.title,content=EXCLUDED.content,status='APPROVED',
              source_batch_id=EXCLUDED.source_batch_id,audience='customer',
              is_active=true,source_locator=EXCLUDED.source_locator""",
            (batch_id, page_id.value),
        )
