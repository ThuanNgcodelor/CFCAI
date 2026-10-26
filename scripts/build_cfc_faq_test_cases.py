from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.modules.integrations.markdown.importer import (
    MarkdownCatalogImporter,
    _clean_markdown_text,
)

DEFAULT_SOURCE = ROOT / "data/sources/cfc/faq/CFC_Co_Bay_FAQ.md"
DEFAULT_MAPPING = ROOT / "config/data_sources/markdown_mapping.json"
DEFAULT_OUTPUT = ROOT / "tests/fixtures/cfc_faq_cases.json"
SOURCE_ID = "cfc-co-bay-faq"


def _plain_markdown(value: str) -> str:
    value = _clean_markdown_text(value)
    return re.sub(r"[*_`]", "", value).strip()


def build_case_catalog(
    source_path: Path = DEFAULT_SOURCE,
    mapping_path: Path = DEFAULT_MAPPING,
) -> dict[str, Any]:
    """Build deterministic FAQ cases from the configured Markdown table."""
    source_path = source_path.resolve()
    mapping_path = mapping_path.resolve()
    importer = MarkdownCatalogImporter(mapping_path)
    _, source = importer._source(SOURCE_ID)
    columns = importer._column_aliases(source)
    governance = importer._governance(source)
    document = source_path.read_text(encoding="utf-8")
    headers, rows = importer._find_table(document, columns)

    # Reuse the production importer for all answerable rows so the fixture and
    # staged catalog cannot silently disagree about IDs, intents or wording.
    importer.import_source(SOURCE_ID, file_path=str(source_path))
    staged_by_row = {int(item["source_row"]): item for item in importer.staged_faqs}
    skipped_markers = tuple(
        str(item).casefold() for item in source.get("skip_answer_contains", [])
    )

    cases: list[dict[str, Any]] = []
    for source_row, row in rows:
        number_text = _plain_markdown(row[0])
        if not number_text.isdigit():
            raise ValueError(f"FAQ row {source_row} has invalid number {number_text!r}")
        faq_number = int(number_text)
        policy = governance.get(str(faq_number), {})
        topic = _plain_markdown(importer._value(row, headers, columns.get("topic", ())))
        question_text = importer._value(row, headers, columns["question_examples"])
        questions = importer._question_examples(question_text)
        raw_answer = _clean_markdown_text(
            importer._value(row, headers, columns["answer"])
        )
        missing_answer = not raw_answer or any(
            marker in raw_answer.casefold() for marker in skipped_markers
        )
        staged = staged_by_row.get(source_row)
        if not missing_answer and staged is None:
            raise ValueError(f"Answerable FAQ row {source_row} was not staged")
        if missing_answer and staged is not None:
            raise ValueError(f"Missing-answer FAQ row {source_row} was staged")

        cases.append(
            {
                "case_id": f"CFC-FAQ-{faq_number:03d}",
                "faq_number": faq_number,
                "source_row": source_row,
                "topic": topic,
                "status": "MISSING_ANSWER" if missing_answer else "ANSWERABLE",
                "questions": questions,
                "expected_answer": None if missing_answer else staged["answer"],
                "faq_id": None if missing_answer else staged["faq_id"],
                "intent": policy.get("intent") if missing_answer else staged["intent"],
                "category": policy.get("category") if missing_answer else staged["category"],
                "response_mode": (
                    policy.get("response_mode")
                    if missing_answer
                    else staged["response_mode"]
                ),
                "risk_level": (
                    policy.get("risk_level") if missing_answer else staged["risk_level"]
                ),
                "profile_slots": (
                    policy.get("profile_slots", [])
                    if missing_answer
                    else staged["profile_slots"]
                ),
                "source_active": (
                    bool(policy.get("source_active", False))
                    if missing_answer
                    else staged["source_active"]
                ),
                "review_status": policy.get("review_status", "UNSPECIFIED"),
                "source_locator": f"{source_path.name}:FAQ:{source_row}",
            }
        )

    answerable = [case for case in cases if case["status"] == "ANSWERABLE"]
    missing = [case for case in cases if case["status"] == "MISSING_ANSWER"]
    return {
        "schema_version": 2,
        "source_file": source_path.name,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "mapping_file": str(mapping_path.relative_to(ROOT)),
        "source_id": SOURCE_ID,
        "summary": {
            "faq_rows": len(cases),
            "answerable_rows": len(answerable),
            "missing_answer_rows": len(missing),
            "answerable_question_variants": sum(
                len(case["questions"]) for case in answerable
            ),
            "all_question_variants": sum(len(case["questions"]) for case in cases),
        },
        "cases": cases,
    }


def _serialized(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic test cases from CFC_Co_Bay_FAQ.md"
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed fixture is stale; do not rewrite it.",
    )
    args = parser.parse_args()
    expected = _serialized(build_case_catalog(args.source, args.mapping))
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            print(f"STALE: {output}")
            return 1
        print(f"OK: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
