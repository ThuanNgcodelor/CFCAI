from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.core.settings import settings
from src.chatbot.infrastructure.messaging.outbox import InMemoryOutboxStore
from src.chatbot.modules.knowledge.retriever import (
    ApprovedKnowledgeStore,
    KnowledgeRecord,
)
from src.chatbot.modules.llm.ollama import OllamaIntentClient
from src.chatbot.modules.orchestration.input_analyzer import (
    HybridInputAnalyzer,
    VietnameseNormalizer,
)
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.modules.workflows.support_contacts import SupportContactDirectory
from src.chatbot.shared.enums import PageCode
from src.chatbot.shared.events import InboxEvent, NormalizedMessage

DEFAULT_CASES = ROOT / "tests/fixtures/cfc_faq_cases.json"
DEFAULT_JSON = ROOT / "reports/cfc_faq_evaluation.json"
DEFAULT_MARKDOWN = ROOT / "reports/cfc_faq_evaluation.md"

STOPWORDS = {
    "anh",
    "chi",
    "cho",
    "cua",
    "cung",
    "dang",
    "day",
    "duoc",
    "em",
    "giup",
    "hien",
    "khach",
    "khong",
    "minh",
    "mot",
    "nha",
    "nhung",
    "phan",
    "the",
    "thi",
    "tren",
    "va",
    "voi",
}


def _fold(value: str) -> str:
    value = re.sub(r"[*_`#]", " ", value.casefold())
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = value.replace("đ", "d")
    return re.sub(r"\s+", " ", value).strip()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _fold(value))
        if len(token) > 2 and token not in STOPWORDS
    }


def _fact_recall(expected: str, actual: str) -> float:
    expected_tokens = _tokens(expected)
    if not expected_tokens:
        return 1.0
    return len(expected_tokens & _tokens(actual)) / len(expected_tokens)


def _reply_violations(text: str) -> list[str]:
    folded = _fold(text)
    violations: list[str] = []
    style_patterns = {
        "customer_called_ban": (
            r"\bban\s+(?:cho|gui|de lai|vui long|dang|can|co the|hay|muon|nhan)\b",
            r"\bnha ban\b",
        ),
        "forbidden_salutation": (
            r"\bchao em\b",
            r"\bchao chi\s*/\s*em\b",
            r"\bchi\s*/\s*chu\b",
            r"\banh\s*/\s*chi oi\b",
            r"\bco\s*/\s*chu\b",
            r"\bco\s*/\s*bac\b",
        ),
        "persona_flip": (
            r"\bchi se lien he\b",
            r"\banh se bao gia cho em\b",
            r"\bchung toi\b",
        ),
        "internal_term": (r"\bsnapshot crm\b",),
    }
    for code, patterns in style_patterns.items():
        if any(re.search(pattern, folded) for pattern in patterns):
            violations.append(code)
    if ResponseComposer.has_unresolved_placeholders(text):
        violations.append("unresolved_placeholder")
    money_patterns = (
        r"\b\d+[\s.]*(?:nghin|ngan|trieu|k|d|vnd|dong)\b",
        r"\b(?:gia|khoang)\s*[:=]?\s*\d{4,}\b",
    )
    if any(re.search(pattern, folded) for pattern in money_patterns):
        violations.append("numeric_price")
    return violations


def _source_review_flags(answer: str) -> list[str]:
    flags = _reply_violations(answer)
    folded = _fold(answer)
    if re.search(r"\b(?:100%|15\s*-\s*25%|40\s*-\s*50%|80\s*-\s*90%)\b", folded):
        flags.append("strong_percentage_claim")
    if re.search(r"\b(?:tuyet doi|hoan toan|cuc ky|chuan)\b", folded):
        flags.append("strong_agronomy_claim")
    return sorted(set(flags))


def _knowledge_records(catalog: dict[str, Any]) -> list[KnowledgeRecord]:
    return [
        KnowledgeRecord(
            record_id=f"faq:{case['faq_id']}",
            page_id=PageCode.CFC,
            title=" | ".join(case["questions"]),
            content=case["expected_answer"],
            status="APPROVED",
            intent=case["intent"],
            category=case["category"],
            risk_level=case["risk_level"],
            source_locator=case["source_locator"],
        )
        for case in catalog["cases"]
        if case["status"] == "ANSWERABLE"
    ]


def _retrieval_results(
    catalog: dict[str, Any], store: ApprovedKnowledgeStore
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in catalog["cases"]:
        if case["status"] != "ANSWERABLE":
            continue
        expected_id = f"faq:{case['faq_id']}"
        for index, question in enumerate(case["questions"], start=1):
            matches = store.search(
                PageCode.CFC, question, limit=3, record_prefix="faq:"
            )
            ids = [record.record_id for record in matches]
            rank = ids.index(expected_id) + 1 if expected_id in ids else None
            results.append(
                {
                    "case_id": case["case_id"],
                    "question_index": index,
                    "question": question,
                    "expected_record_id": expected_id,
                    "retrieved_record_ids": ids,
                    "rank": rank,
                    "top1_pass": rank == 1,
                    "top3_pass": rank is not None,
                    "zeo_isolated": not store.search(
                        PageCode.ZEO, question, limit=1, record_prefix="faq:"
                    ),
                }
            )
    return results


class RecordingAnalyzer:
    def __init__(self, analyzer: HybridInputAnalyzer) -> None:
        self.analyzer = analyzer
        self.normalizer = analyzer.normalizer
        self.last_result = None

    def analyze(self, page_id: PageCode, text: str, context: dict | None = None):
        self.last_result = self.analyzer.analyze(page_id, text, context)
        return self.last_result


def _event(case_id: str, text: str) -> InboxEvent:
    now = dt.datetime.now(dt.UTC)
    return InboxEvent(
        event_id=f"eval-{case_id}",
        page_id=PageCode.CFC,
        sender_id=f"eval-{case_id}",
        message=NormalizedMessage(
            mid=f"mid-{case_id}",
            sender_id=f"eval-{case_id}",
            recipient_id="page-cfc-eval",
            timestamp=now,
            text=text,
        ),
    )


def _runtime_results(
    catalog: dict[str, Any], store: ApprovedKnowledgeStore
) -> tuple[str, list[dict[str, Any]]]:
    client = OllamaIntentClient(
        settings.OLLAMA_BASE_URL,
        settings.OLLAMA_MODEL_TAG,
        settings.OLLAMA_TIMEOUT_SECONDS,
        prompt_path=settings.INTENT_PROMPT_PATH,
        max_attempts=1,
    )
    if not client.is_ready():
        return "BLOCKED_OLLAMA_NOT_READY", []
    analyzer = RecordingAnalyzer(
        HybridInputAnalyzer(
            client,
            VietnameseNormalizer(
                settings.INTENT_NORMALIZATION_PATH,
                settings.ADMINISTRATIVE_AREAS_PATH,
            ),
        )
    )
    composer = ResponseComposer(
        contact_directory=SupportContactDirectory.from_file(
            settings.SUPPORT_CONTACTS_PATH
        )
    )
    results: list[dict[str, Any]] = []
    for case in catalog["cases"]:
        question = case["questions"][0]
        outbox = InMemoryOutboxStore()
        pipeline = SafeMessagePipeline(
            outbox,
            intent_analyzer=analyzer,
            knowledge_store=store,
            composer=composer,
        )
        outbox_id = pipeline.process(_event(case["case_id"], question))
        actual = outbox.messages[outbox_id].text if outbox_id else ""
        expected = case["expected_answer"]
        exact_match = bool(expected) and _fold(actual) == _fold(expected)
        contains_expected = bool(expected) and _fold(expected) in _fold(actual)
        recall = _fact_recall(expected, actual) if expected else None
        violations = _reply_violations(actual)
        if expected is None:
            status = "NO_REFERENCE"
        elif exact_match and not violations:
            status = "PASS"
        elif (
            contains_expected or (recall is not None and recall >= 0.65)
        ) and not violations:
            status = "PARTIAL"
        else:
            status = "FAIL"
        analysis = analyzer.last_result
        results.append(
            {
                "case_id": case["case_id"],
                "faq_number": case["faq_number"],
                "topic": case["topic"],
                "question": question,
                "expected_answer": expected,
                "actual_answer": actual,
                "intent": analysis.primary_intent.value if analysis else None,
                "slots": analysis.extracted_slots if analysis else {},
                "exact_source_match": exact_match,
                "contains_expected_answer": contains_expected,
                "fact_token_recall": round(recall, 4) if recall is not None else None,
                "violations": violations,
                "status": status,
            }
        )
    return "COMPLETED", results


def _production_status() -> dict[str, Any]:
    try:
        import psycopg2

        dsn = settings.get_database_url().replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
        with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT count(*) FROM knowledge_records
                WHERE page_id='CFC' AND status='APPROVED' AND is_active=true
                  AND source_locator LIKE 'CFC_Co_Bay_FAQ.md:%'"""
            )
            active = int(cursor.fetchone()[0])
            cursor.execute(
                """SELECT count(*) FROM import_batches
                WHERE page_id='CFC' AND source_file='CFC_Co_Bay_FAQ.md'"""
            )
            batches = int(cursor.fetchone()[0])
        return {
            "status": "CHECKED",
            "active_approved_records": active,
            "import_batches": batches,
        }
    except (OSError, ValueError, ImportError) as exc:
        return {"status": "UNAVAILABLE", "error": str(exc)}


def _short(value: str | None, limit: int = 120) -> str:
    if not value:
        return "—"
    compact = re.sub(r"\s+", " ", value).replace("|", "\\|")
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _markdown(report: dict[str, Any]) -> str:
    source = report["source_summary"]
    retrieval = report["retrieval_summary"]
    runtime = report["runtime_summary"]
    production = report["production"]
    lines = [
        "# CFC FAQ evaluation",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Source rows: **{source['faq_rows']}**",
        f"- Answerable rows: **{source['answerable_rows']}**",
        f"- Missing-answer rows: **{source['missing_answer_rows']}**",
        f"- Answerable question variants: **{source['answerable_question_variants']}**",
        f"- Retrieval top-1: **{retrieval['top1_pass']}/{retrieval['total']}**",
        f"- Retrieval top-3: **{retrieval['top3_pass']}/{retrieval['total']}**",
        f"- ZEO isolation: **{retrieval['zeo_isolated']}/{retrieval['total']}**",
        f"- Runtime status: **{runtime['gate_status']}**",
        f"- Runtime PASS/PARTIAL/FAIL/NO_REFERENCE: **{runtime['counts']}**",
        f"- Published FAQ records in current runtime: **{production.get('active_approved_records', 'unknown')}**",
        "",
        "Exact source matching only proves consistency with the Markdown file; it does not",
        "scientifically approve agronomy claims. Rows carrying strong claims remain review items.",
        "",
        "## Source review",
        "",
        f"- Rows conflicting with the required salutation/persona policy: **{report['source_review']['style_conflict_rows']}**",
        f"- Rows containing strong percentage/agronomy claims: **{report['source_review']['strong_claim_rows']}**",
        "- Missing answers: "
        + ", ".join(report["source_review"]["missing_answer_case_ids"]),
        "",
        "## Runtime representative cases",
        "",
        "| Case | Topic | Intent | Result | Exact | Recall | Violations |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for item in report["runtime_results"]:
        violations = ", ".join(item["violations"]) or "—"
        recall = (
            "—"
            if item["fact_token_recall"] is None
            else f"{item['fact_token_recall']:.2f}"
        )
        lines.append(
            f"| {item['case_id']} | {_short(item['topic'], 45)} | {item['intent']} | "
            f"{item['status']} | {'yes' if item['exact_source_match'] else 'no'} | "
            f"{recall} | {violations} |"
        )
    lines.extend(["", "## Runtime failures and partial matches", ""])
    problem_items = [
        item
        for item in report["runtime_results"]
        if item["status"] not in {"PASS", "NO_REFERENCE"}
    ]
    if not problem_items:
        lines.append("No runtime failures.")
    for item in problem_items:
        lines.extend(
            [
                f"### {item['case_id']} — {item['topic']}",
                "",
                f"- Question: `{item['question']}`",
                f"- Intent: `{item['intent']}`",
                f"- Expected: {_short(item['expected_answer'], 300)}",
                f"- Actual: {_short(item['actual_answer'], 300)}",
                f"- Violations: {', '.join(item['violations']) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def evaluate(
    catalog: dict[str, Any], *, live: bool, check_production: bool
) -> dict[str, Any]:
    store = ApprovedKnowledgeStore(_knowledge_records(catalog))
    retrieval_results = _retrieval_results(catalog, store)
    source_review = []
    for case in catalog["cases"]:
        if case["expected_answer"]:
            source_review.append(
                {
                    "case_id": case["case_id"],
                    "flags": _source_review_flags(case["expected_answer"]),
                }
            )
    if live:
        gate_status, runtime_results = _runtime_results(catalog, store)
    else:
        gate_status, runtime_results = "NOT_REQUESTED", []
    counts = Counter(item["status"] for item in runtime_results)
    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source_file": catalog["source_file"],
        "source_sha256": catalog["source_sha256"],
        "source_summary": catalog["summary"],
        "production": _production_status()
        if check_production
        else {"status": "NOT_REQUESTED"},
        "source_review": {
            "style_conflict_rows": sum(
                any(
                    flag
                    in {"customer_called_ban", "forbidden_salutation", "persona_flip"}
                    for flag in item["flags"]
                )
                for item in source_review
            ),
            "strong_claim_rows": sum(
                any(
                    flag in {"strong_percentage_claim", "strong_agronomy_claim"}
                    for flag in item["flags"]
                )
                for item in source_review
            ),
            "missing_answer_case_ids": [
                case["case_id"]
                for case in catalog["cases"]
                if case["status"] == "MISSING_ANSWER"
            ],
            "details": source_review,
        },
        "retrieval_summary": {
            "total": len(retrieval_results),
            "top1_pass": sum(item["top1_pass"] for item in retrieval_results),
            "top3_pass": sum(item["top3_pass"] for item in retrieval_results),
            "zeo_isolated": sum(item["zeo_isolated"] for item in retrieval_results),
        },
        "retrieval_results": retrieval_results,
        "runtime_summary": {
            "gate_status": gate_status,
            "counts": dict(sorted(counts.items())),
            "total": len(runtime_results),
            "exact_source_matches": sum(
                item["exact_source_match"] for item in runtime_results
            ),
        },
        "runtime_results": runtime_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate all CFC FAQ rows without sending Messenger messages."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--live", action="store_true", help="Run one Qwen/pipeline case per FAQ row"
    )
    parser.add_argument("--check-production", action="store_true")
    args = parser.parse_args()
    catalog = json.loads(args.cases.read_text(encoding="utf-8"))
    report = evaluate(catalog, live=args.live, check_production=args.check_production)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_markdown.write_text(_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "source": report["source_summary"],
                "retrieval": report["retrieval_summary"],
                "runtime": report["runtime_summary"],
                "production": report["production"],
                "output_json": str(args.output_json),
                "output_markdown": str(args.output_markdown),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return (
        0
        if report["runtime_summary"]["gate_status"] != "BLOCKED_OLLAMA_NOT_READY"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
