"""Configuration-driven Excel staging for FAQ and product data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.chatbot.modules.integrations.excel.reader import FastExcelReader
from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.shared.enums import CatalogStatus, PageCode


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _boolean(value: Any, *, default: bool = True) -> bool:
    normalized = _text(value).casefold()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "y", "có", "active"}


def _list(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    for separator in ("\r\n", "\n", "|", ";"):
        if separator in text:
            return [item.strip() for item in text.split(separator) if item.strip()]
    return [text]


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExcelCatalogImporter:
    """Imports sources declared in YAML; no Page, sheet or product is embedded in code."""

    def __init__(
        self,
        mapping_path: str | Path = "config/data_sources/excel_mapping.yaml",
        repository: CatalogPublishRepository | None = None,
    ) -> None:
        self.mapping_path = Path(mapping_path)
        self.repository = repository
        self.reader = FastExcelReader()
        self.staged_faqs: list[dict[str, Any]] = []
        self.staged_products: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []

    def _mapping(self) -> dict[str, Any]:
        if not self.mapping_path.exists():
            raise FileNotFoundError(f"Excel mapping not found: {self.mapping_path}")
        data = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
            raise TypeError("Excel mapping must contain a sources list")
        return data

    def _source_for_page(self, page_id: PageCode) -> tuple[int, dict[str, Any]]:
        mapping = self._mapping()
        matches = [
            item for item in mapping["sources"] if item.get("page_id") == page_id.value
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one Excel source for page {page_id.value}"
            )
        return int(mapping.get("mapping_version", 1)), matches[0]

    def import_page(
        self,
        page_id: PageCode,
        file_path: str | None = None,
        *,
        actor: str = "system",
        source_id: str | None = None,
    ) -> dict[str, Any]:
        mapping_version, source = self._source_for_page(page_id)
        path = Path(file_path or source["path"])
        sheets = self.reader.read_sheets(str(path))
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        batch_id = _content_hash(
            {
                "page_id": page_id.value,
                "checksum": checksum,
                "mapping_version": mapping_version,
            }
        )
        faqs: list[dict[str, Any]] = []
        products: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        for sheet_name, sheet_config in source.get("sheets", {}).items():
            rows = sheets.get(sheet_name, [])
            fields = sheet_config.get("fields", {})
            required = sheet_config.get("required_fields", [])
            record_type = sheet_config.get("record_type")
            private_fields = sheet_config.get("private_fields", [])
            for source_row, raw in enumerate(rows, start=2):
                mapped = {
                    target: raw.get(source_column)
                    for target, source_column in fields.items()
                }
                if any(not _text(mapped.get(field)) for field in required):
                    continue
                provenance = {
                    "page_id": page_id.value,
                    "source_file": path.name,
                    "source_sheet": sheet_name,
                    "source_row": source_row,
                    "import_batch_id": batch_id,
                }
                if record_type == "faq":
                    content = {
                        "intent": _text(mapped.get("intent")),
                        "category": _text(mapped.get("category")),
                        "question_examples": _list(mapped.get("question_examples")),
                        "answer": _text(mapped.get("answer")),
                        "audience": _text(mapped.get("audience")) or "customer",
                        "response_mode": _text(mapped.get("response_mode")),
                        "risk_level": _text(mapped.get("risk_level")),
                        "learning_tags": _list(mapped.get("learning_tags")),
                        "profile_slots": _list(mapped.get("profile_slots")),
                        "source_active": _boolean(mapped.get("source_active")),
                    }
                    faqs.append(
                        {
                            **provenance,
                            **content,
                            "faq_id": _content_hash({**provenance, "type": "faq"}),
                            "content_hash": _content_hash(content),
                            "status": CatalogStatus.QUARANTINED.value,
                            "approved": False,
                        }
                    )
                elif record_type == "product":
                    internal_data = {
                        field: raw.get(field)
                        for field in private_fields
                        if raw.get(field) not in (None, "")
                    }
                    content = {
                        "sku": _text(mapped.get("sku")),
                        "name": _text(mapped.get("name")),
                        "brand": _text(mapped.get("brand")),
                        "category": _text(mapped.get("category")),
                        "specs": {"text": _text(mapped.get("specs"))}
                        if _text(mapped.get("specs"))
                        else {},
                        "keywords": _list(mapped.get("keywords")),
                        "source_active": _boolean(mapped.get("source_active")),
                    }
                    products.append(
                        {
                            **provenance,
                            **content,
                            "catalog_id": _content_hash(
                                {**provenance, "type": "product"}
                            ),
                            "internal_data": internal_data,
                            "content_hash": _content_hash(content),
                            "status": CatalogStatus.QUARANTINED.value,
                            "approved": False,
                        }
                    )
                else:
                    raise ValueError(
                        f"Unsupported record_type {record_type!r} in {sheet_name}"
                    )

        by_sku: dict[str, list[dict[str, Any]]] = {}
        for product in products:
            by_sku.setdefault(product["sku"].casefold(), []).append(product)
        for sku_records in by_sku.values():
            signatures = {
                (item["name"].casefold(), json.dumps(item["specs"], sort_keys=True))
                for item in sku_records
            }
            if len(signatures) <= 1:
                continue
            for item in sku_records:
                item["status"] = CatalogStatus.CONFLICT.value
                conflicts.append(
                    {
                        "sku": item["sku"],
                        "source_sheet": item["source_sheet"],
                        "source_row": item["source_row"],
                        "reason": "Conflicting name or specs for the same SKU",
                    }
                )

        self.staged_faqs.extend(faqs)
        self.staged_products.extend(products)
        self.conflicts.extend(conflicts)
        report = {
            "batch_id": batch_id,
            "page_id": page_id.value,
            "file": str(path),
            "source_checksum": checksum,
            "mapping_version": mapping_version,
            "sheets_found": list(sheets),
            "imported_faq_count": len(faqs),
            "imported_product_count": len(products),
            "conflict_count": len(conflicts),
            "actor": actor,
            "source_id": source_id or f"{page_id.value.casefold()}-excel",
        }
        if self.repository:
            self.repository.stage(report, faqs, products)
        return report

    def import_cfc_file(self, file_path: str | None = None) -> dict[str, Any]:
        return self.import_page(PageCode.CFC, file_path)

    def import_zeo_file(self, file_path: str | None = None) -> dict[str, Any]:
        return self.import_page(PageCode.ZEO, file_path)

    def import_all(self) -> list[dict[str, Any]]:
        mapping = self._mapping()
        return [
            self.import_page(PageCode(source["page_id"]))
            for source in mapping["sources"]
        ]

    def persist_staging(self) -> dict[str, int]:
        if self.repository is None:
            raise RuntimeError("A CatalogPublishRepository is required for persistence")
        return {
            "persisted_count": len(self.staged_faqs) + len(self.staged_products),
        }


catalog_importer = ExcelCatalogImporter()
