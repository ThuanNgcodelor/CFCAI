"""Configuration-driven Markdown FAQ staging importer.

Markdown is a source artifact, never a runtime prompt attachment.  Every
record produced here enters the same quarantine/review/publish lifecycle as
the Excel catalog sources.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from src.chatbot.modules.integrations.excel.repository import CatalogPublishRepository
from src.chatbot.shared.enums import CatalogStatus, PageCode


def _text(value: Any) -> str:
    return str(value or "").strip()


def _boolean(value: Any, *, default: bool = True) -> bool:
    normalized = _text(value).casefold()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "y", "có", "active"}


def _list(value: Any) -> list[str]:
    text = _text(value)
    if not text:
        return []
    return [item.strip() for item in re.split(r"(?:\r?\n|[;|])", text) if item.strip()]


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", normalized.replace("đ", "d")).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _fold(value)).strip("_")


def _clean_markdown_text(value: str) -> str:
    """Remove table escaping while preserving customer-facing answer wording."""
    return re.sub(r"\\([\\|*_`])", r"\1", value).strip()


def _header_key(value: str) -> str:
    plain = re.sub(r"[*_`#]", "", _clean_markdown_text(value))
    return _fold(re.sub(r"\s+", " ", plain)).strip(" :")


def _split_table_row(line: str) -> list[str]:
    """Split a Markdown table row without treating an escaped pipe as a cell."""
    value = line.strip()
    value = value.removeprefix("|")
    if value.endswith("|") and not value.endswith("\\|"):
        value = value[:-1]
    cells: list[str] = []
    buffer: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            buffer.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append(_clean_markdown_text("".join(buffer)))
            buffer = []
        else:
            buffer.append(char)
    if escaped:
        buffer.append("\\")
    cells.append(_clean_markdown_text("".join(buffer)))
    return cells


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in cells)


class MarkdownCatalogImporter:
    """Stage configured Markdown FAQ sources without auto-approving any claim."""

    def __init__(
        self,
        mapping_path: str | Path = "config/data_sources/markdown_mapping.json",
        repository: CatalogPublishRepository | None = None,
    ) -> None:
        self.mapping_path = Path(mapping_path)
        self.repository = repository
        self.staged_faqs: list[dict[str, Any]] = []

    def _mapping(self) -> dict[str, Any]:
        if not self.mapping_path.exists():
            raise FileNotFoundError(f"Markdown mapping not found: {self.mapping_path}")
        mapping = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        if not isinstance(mapping, dict) or not isinstance(
            mapping.get("sources"), list
        ):
            raise TypeError("Markdown mapping must contain a sources list")
        return mapping

    @staticmethod
    def _source_id(source: dict[str, Any]) -> str:
        return _text(source.get("id") or source.get("source_id") or source.get("path"))

    def _source(self, source_id: str) -> tuple[int, dict[str, Any]]:
        mapping = self._mapping()
        matches = [
            source
            for source in mapping["sources"]
            if self._source_id(source) == source_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one Markdown source named {source_id!r}"
            )
        return int(mapping.get("mapping_version", 1)), matches[0]

    @staticmethod
    def _governance(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
        configured_path = _text(source.get("governance_path"))
        if not configured_path:
            return {}
        path = Path(configured_path)
        if not path.exists():
            raise FileNotFoundError(f"Markdown governance file not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, dict):
            raise TypeError("Markdown governance must contain a records object")
        normalized: dict[str, dict[str, Any]] = {}
        for key, value in records.items():
            if not isinstance(value, dict):
                raise TypeError(f"Governance record {key!r} must be an object")
            normalized[str(key).strip()] = value
        return normalized

    @staticmethod
    def _column_aliases(source: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        configured = source.get("columns", {})
        if not isinstance(configured, dict):
            raise TypeError("Markdown source columns must be an object")
        result: dict[str, tuple[str, ...]] = {}
        for field, aliases in configured.items():
            values = aliases if isinstance(aliases, list) else [aliases]
            result[str(field)] = tuple(
                _header_key(_text(alias)) for alias in values if _text(alias)
            )
        return result

    @staticmethod
    def _find_table(
        document: str,
        columns: dict[str, tuple[str, ...]],
    ) -> tuple[list[str], list[tuple[int, list[str]]]]:
        lines = document.splitlines()
        for index, line in enumerate(lines):
            if "|" not in line:
                continue
            header = _split_table_row(line)
            if not header or index + 1 >= len(lines) or "|" not in lines[index + 1]:
                continue
            separator = _split_table_row(lines[index + 1])
            if not _is_table_separator(separator):
                continue
            normalized_headers = [_header_key(cell) for cell in header]
            if not all(
                any(alias in normalized_headers for alias in aliases)
                for field, aliases in columns.items()
                if field in {"question_examples", "answer"}
            ):
                continue

            rows: list[tuple[int, list[str]]] = []
            for row_index in range(index + 2, len(lines)):
                row_line = lines[row_index]
                if "|" not in row_line or not row_line.lstrip().startswith("|"):
                    break
                cells = _split_table_row(row_line)
                if _is_table_separator(cells):
                    continue
                if len(cells) < len(header):
                    break
                rows.append((row_index + 1, cells[: len(header)]))
            return normalized_headers, rows
        raise ValueError(
            "No Markdown table matched the configured question/answer headers"
        )

    @staticmethod
    def _value(row: list[str], headers: list[str], aliases: tuple[str, ...]) -> str:
        for alias in aliases:
            if alias in headers:
                return _text(row[headers.index(alias)])
        return ""

    @staticmethod
    def _question_examples(value: str) -> list[str]:
        cleaned = _clean_markdown_text(value)
        if not cleaned:
            return []
        examples = [
            item.strip(" -")
            for item in re.split(r"(?:\r?\n|;)+|(?<=\?)\s+", cleaned)
            if item.strip(" -")
        ]
        return examples or [cleaned]

    def import_source(
        self,
        source_id: str,
        file_path: str | Path | None = None,
        *,
        actor: str = "system",
    ) -> dict[str, Any]:
        mapping_version, source = self._source(source_id)
        page_id = PageCode(_text(source.get("page_id")))
        path = Path(file_path or _text(source.get("path")))
        if not path.exists():
            raise FileNotFoundError(f"Markdown source not found: {path}")
        document = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(document.encode("utf-8")).hexdigest()
        batch_id = _content_hash(
            {
                "page_id": page_id.value,
                "source_id": source_id,
                "checksum": checksum,
                "mapping_version": mapping_version,
            }
        )
        columns = self._column_aliases(source)
        headers, rows = self._find_table(document, columns)
        governance = self._governance(source)
        row_keys = {
            self._value(row, headers, columns.get("record_key", ())) or str(source_row)
            for source_row, row in rows
        }
        if governance:
            missing = sorted(row_keys - governance.keys())
            extra = sorted(governance.keys() - row_keys)
            if missing or extra:
                raise ValueError(
                    "Markdown governance coverage mismatch: "
                    f"missing={missing or 'none'}, extra={extra or 'none'}"
                )
        defaults = source.get("defaults", {})
        if not isinstance(defaults, dict):
            raise TypeError("Markdown source defaults must be an object")
        skip_patterns = tuple(
            _fold(_text(pattern))
            for pattern in source.get("skip_answer_contains", [])
            if _text(pattern)
        )
        faqs: list[dict[str, Any]] = []
        skipped_count = 0
        source_sheet = _text(source.get("source_sheet")) or "MARKDOWN"
        intent_prefix = _slug(_text(defaults.get("intent_prefix")) or "markdown_faq")

        for source_row, row in rows:
            record_key = self._value(
                row, headers, columns.get("record_key", ())
            ) or str(source_row)
            policy = governance.get(record_key, {})
            answer = self._value(row, headers, columns.get("answer", ()))
            question_examples = self._question_examples(
                self._value(row, headers, columns.get("question_examples", ()))
            )
            if (
                not answer
                or not question_examples
                or any(pattern in _fold(answer) for pattern in skip_patterns)
            ):
                skipped_count += 1
                continue
            topic = self._value(row, headers, columns.get("topic", ()))
            mapped_intent = self._value(row, headers, columns.get("intent", ()))
            intent = (
                _text(policy.get("intent"))
                or mapped_intent
                or f"{intent_prefix}_{_slug(topic) or source_row}"
            )
            provenance = {
                "page_id": page_id.value,
                "source_file": path.name,
                "source_sheet": source_sheet,
                "source_row": source_row,
                "import_batch_id": batch_id,
            }
            content = {
                "intent": intent,
                "category": _text(policy.get("category"))
                or self._value(row, headers, columns.get("category", ()))
                or _text(defaults.get("category")),
                "question_examples": question_examples,
                "answer": answer,
                "audience": self._value(row, headers, columns.get("audience", ()))
                or _text(defaults.get("audience"))
                or "customer",
                "response_mode": _text(policy.get("response_mode"))
                or self._value(row, headers, columns.get("response_mode", ()))
                or _text(defaults.get("response_mode")),
                "risk_level": _text(policy.get("risk_level"))
                or self._value(row, headers, columns.get("risk_level", ()))
                or _text(defaults.get("risk_level")),
                "learning_tags": list(
                    policy.get("learning_tags")
                    or _list(
                        self._value(row, headers, columns.get("learning_tags", ()))
                        or defaults.get("learning_tags")
                    )
                )
                + (
                    [f"review_status:{_text(policy.get('review_status')).casefold()}"]
                    if _text(policy.get("review_status"))
                    else []
                ),
                "profile_slots": list(
                    policy.get("profile_slots")
                    or _list(
                        self._value(row, headers, columns.get("profile_slots", ()))
                        or defaults.get("profile_slots")
                    )
                ),
                "source_active": (
                    bool(policy["source_active"])
                    if "source_active" in policy
                    else _boolean(
                        self._value(row, headers, columns.get("source_active", ()))
                        or defaults.get("source_active"),
                        default=True,
                    )
                ),
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

        self.staged_faqs.extend(faqs)
        report = {
            "batch_id": batch_id,
            "page_id": page_id.value,
            "file": str(path),
            "source_id": source_id,
            "source_checksum": checksum,
            "mapping_version": mapping_version,
            "source_sheet": source_sheet,
            "imported_faq_count": len(faqs),
            "skipped_row_count": skipped_count,
            "conflict_count": 0,
            "actor": actor,
        }
        if self.repository:
            self.repository.stage(report, faqs, [])
        return report

    def import_all(self, *, actor: str = "system") -> list[dict[str, Any]]:
        mapping = self._mapping()
        return [
            self.import_source(self._source_id(source), actor=actor)
            for source in mapping["sources"]
        ]
