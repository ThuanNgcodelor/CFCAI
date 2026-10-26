"""Manifest-driven source validation and staging orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import yaml

from src.chatbot.modules.integrations.excel.importer import ExcelCatalogImporter
from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.modules.integrations.markdown.importer import MarkdownCatalogImporter
from src.chatbot.shared.enums import PageCode


@dataclass(frozen=True)
class DataSource:
    source_id: str
    page_id: PageCode
    kind: str
    path: Path
    mapping: Path
    importer_source: str | None
    auto_stage: bool
    auto_publish: bool


class DataSourceLoader:
    ALLOWED_KINDS: ClassVar[set[str]] = {"markdown_faq", "excel_catalog"}

    def __init__(
        self,
        manifest_path: str | Path,
        repository: CatalogPublishRepository | None = None,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.repository = repository

    def sources(self) -> list[DataSource]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(
                f"Data source manifest not found: {self.manifest_path}"
            )
        payload = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))
        configured = payload.get("sources") if isinstance(payload, dict) else None
        if not isinstance(configured, list) or not configured:
            raise TypeError(
                "Data source manifest must contain a non-empty sources list"
            )
        sources: list[DataSource] = []
        seen: set[str] = set()
        for raw in configured:
            if not isinstance(raw, dict):
                raise TypeError("Every data source must be an object")
            source_id = str(raw.get("id") or "").strip()
            if not source_id or source_id in seen:
                raise ValueError(f"Missing or duplicate data source id: {source_id!r}")
            seen.add(source_id)
            kind = str(raw.get("kind") or "").strip()
            if kind not in self.ALLOWED_KINDS:
                raise ValueError(f"Unsupported data source kind: {kind!r}")
            source = DataSource(
                source_id=source_id,
                page_id=PageCode(str(raw.get("page_id") or "")),
                kind=kind,
                path=Path(str(raw.get("path") or "")),
                mapping=Path(str(raw.get("mapping") or "")),
                importer_source=(
                    str(raw["importer_source"]).strip()
                    if raw.get("importer_source")
                    else None
                ),
                auto_stage=bool(raw.get("auto_stage", False)),
                auto_publish=bool(raw.get("auto_publish", False)),
            )
            if source.auto_publish:
                raise ValueError(
                    f"Source {source.source_id!r} cannot enable auto_publish"
                )
            sources.append(source)
        return sources

    @staticmethod
    def _mapping_version(path: Path) -> int:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Mapping must be an object: {path}")
        return int(payload.get("mapping_version", 1))

    def validate(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for source in self.sources():
            if not source.path.is_file():
                raise FileNotFoundError(f"Source file not found: {source.path}")
            if not source.mapping.is_file():
                raise FileNotFoundError(f"Source mapping not found: {source.mapping}")
            if source.kind == "markdown_faq":
                if not source.importer_source:
                    raise ValueError(
                        f"Markdown source {source.source_id!r} needs importer_source"
                    )
                importer = MarkdownCatalogImporter(source.mapping)
                report = importer.import_source(
                    source.importer_source, file_path=source.path
                )
                count = report["imported_faq_count"]
            else:
                importer = ExcelCatalogImporter(source.mapping)
                report = importer.import_page(source.page_id, str(source.path))
                count = report["imported_faq_count"] + report["imported_product_count"]
            if report["page_id"] != source.page_id.value:
                raise ValueError(
                    f"Manifest page mismatch for {source.source_id}: "
                    f"{source.page_id.value} != {report['page_id']}"
                )
            results.append(
                {
                    "source_id": source.source_id,
                    "page_id": source.page_id.value,
                    "kind": source.kind,
                    "path": str(source.path),
                    "mapping_version": self._mapping_version(source.mapping),
                    "checksum": hashlib.sha256(source.path.read_bytes()).hexdigest(),
                    "record_count": count,
                    "conflict_count": report["conflict_count"],
                    "valid": True,
                }
            )
        return results

    def stage_changed(self, *, actor: str) -> list[dict[str, Any]]:
        if self.repository is None:
            raise RuntimeError("A CatalogPublishRepository is required for staging")
        results: list[dict[str, Any]] = []
        for source in self.sources():
            if not source.auto_stage:
                results.append({"source_id": source.source_id, "status": "DISABLED"})
                continue
            checksum = hashlib.sha256(source.path.read_bytes()).hexdigest()
            mapping_version = self._mapping_version(source.mapping)
            existing = self.repository.find_batch(
                source.page_id, checksum, mapping_version
            )
            if existing:
                results.append(
                    {
                        "source_id": source.source_id,
                        "page_id": source.page_id.value,
                        "status": "UNCHANGED",
                        "batch": existing,
                    }
                )
                continue
            if source.kind == "markdown_faq":
                importer = MarkdownCatalogImporter(source.mapping, self.repository)
                report = importer.import_source(
                    source.importer_source or source.source_id,
                    file_path=source.path,
                    actor=actor,
                )
            else:
                importer = ExcelCatalogImporter(source.mapping, self.repository)
                report = importer.import_page(
                    source.page_id,
                    str(source.path),
                    actor=actor,
                    source_id=source.source_id,
                )
            results.append(
                {
                    "source_id": source.source_id,
                    "page_id": source.page_id.value,
                    "status": "STAGED",
                    "batch_id": report["batch_id"],
                    "record_count": report.get("imported_faq_count", 0)
                    + report.get("imported_product_count", 0),
                    "conflict_count": report["conflict_count"],
                }
            )
        return results


def json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))
