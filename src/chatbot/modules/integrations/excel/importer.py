import logging
from typing import Any

from src.chatbot.modules.integrations.excel.reader import FastExcelReader
from src.chatbot.modules.knowledge.retriever import (
    KnowledgeRecord,
    PostgresKnowledgeStore,
)
from src.chatbot.shared.enums import CatalogStatus, PageCode

logger = logging.getLogger(__name__)


class ExcelCatalogImporter:
    """
    Excel Catalog & FAQ Importer.
    Enforces Data Staging (INV-5), Zero-Price Hallucination (INV-1),
    and Conflict Detection (Case T11).
    """

    def __init__(self):
        self.reader = FastExcelReader()
        self.staged_faqs: list[dict[str, Any]] = []
        self.staged_products: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []

    def import_cfc_file(
        self, file_path: str = "docs/CfcCoBayN8n.xlsx"
    ) -> dict[str, Any]:
        sheets = self.reader.read_sheets(file_path)
        faq_rows = sheets.get("FAQ", [])

        imported_faq = 0
        for idx, row in enumerate(faq_rows):
            intent = row.get("intent", "").strip()
            answer = row.get("answer", "").strip()
            if not intent or not answer:
                continue

            record = {
                "page_id": PageCode.CFC.value,
                "source_file": "CfcCoBayN8n.xlsx",
                "source_sheet": "FAQ",
                "source_row": idx + 2,
                "intent": intent,
                "category": row.get("category", ""),
                "question_examples": row.get("question_examples", ""),
                "answer": answer,
                "status": CatalogStatus.QUARANTINED.value,  # Default QUARANTINED
                "approved": False,
            }
            self.staged_faqs.append(record)
            imported_faq += 1

        return {
            "file": file_path,
            "sheets_found": list(sheets.keys()),
            "imported_faq_count": imported_faq,
        }

    def import_zeo_file(self, file_path: str = "docs/ZeoN8n.xlsx") -> dict[str, Any]:
        sheets = self.reader.read_sheets(file_path)

        # 1. Import FAQ
        faq_rows = sheets.get("FAQ", [])
        imported_faq = 0
        for idx, row in enumerate(faq_rows):
            intent = row.get("intent", "").strip()
            answer = row.get("answer", "").strip()
            if not intent or not answer:
                continue
            self.staged_faqs.append(
                {
                    "page_id": PageCode.ZEO.value,
                    "source_file": "ZeoN8n.xlsx",
                    "source_sheet": "FAQ",
                    "source_row": idx + 2,
                    "intent": intent,
                    "category": row.get("category", ""),
                    "question_examples": row.get("question_examples", ""),
                    "answer": answer,
                    "status": CatalogStatus.QUARANTINED.value,
                    "approved": False,
                }
            )
            imported_faq += 1

        # 2. Import Products from Shopee, Web, Lazada
        imported_products = 0
        seen_skus: dict[str, dict[str, Any]] = {}

        for sheet_name in ["Shopee", "Web", "Lazada"]:
            rows = sheets.get(sheet_name, [])
            for idx, r in enumerate(rows):
                item_id = (r.get("item_id") or "").strip()
                name = (r.get("name") or "").strip()
                if not item_id or not name:
                    continue

                # Check for conflicting SKU data (Case T11)
                if item_id in seen_skus:
                    existing = seen_skus[item_id]
                    if existing["name"] != name:
                        conflict_rec = {
                            "item_id": item_id,
                            "existing_name": existing["name"],
                            "conflicting_name": name,
                            "sheet": sheet_name,
                            "row": idx + 2,
                            "reason": "Conflicting product names for same SKU",
                        }
                        self.conflicts.append(conflict_rec)
                        logger.warning(
                            f"[Catalog Importer] Conflict detected for SKU {item_id}: {name} vs {existing['name']}"
                        )
                        continue

                prod_rec = {
                    "page_id": PageCode.ZEO.value,
                    "source_file": "ZeoN8n.xlsx",
                    "source_sheet": sheet_name,
                    "source_row": idx + 2,
                    "sku": item_id,
                    "name": name,
                    "brand": r.get("brand", "Zeolite"),
                    "category": r.get("category", ""),
                    "specs": r.get("specs", ""),
                    "keywords": r.get("keywords", ""),
                    "status": CatalogStatus.QUARANTINED.value,
                    "approved": False,
                }
                seen_skus[item_id] = prod_rec
                self.staged_products.append(prod_rec)
                imported_products += 1

        return {
            "file": file_path,
            "sheets_found": list(sheets.keys()),
            "imported_faq_count": imported_faq,
            "imported_product_count": imported_products,
            "conflict_count": len(self.conflicts),
        }

    def persist_staging(self) -> dict[str, int]:
        """Persist staged FAQ/product text into the quarantine read model."""
        store = PostgresKnowledgeStore()
        count = 0
        for index, record in enumerate(self.staged_faqs):
            record_id = f"faq:{record['page_id']}:{record['source_row']}"
            questions = str(record.get("question_examples", ""))
            store.add(KnowledgeRecord(record_id, PageCode(record["page_id"]), questions, record["answer"], record["status"]))
            count += 1
        for index, record in enumerate(self.staged_products):
            record_id = f"product:{record['page_id']}:{record['sku']}"
            content = f"{record['name']} {record.get('brand', '')} {record.get('category', '')} {record.get('specs', '')} {record.get('keywords', '')}"
            store.add(KnowledgeRecord(record_id, PageCode(record["page_id"]), record["name"], content, record["status"]))
            count += 1
        return {"persisted_count": count}


catalog_importer = ExcelCatalogImporter()
