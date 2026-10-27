from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg2

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
    workflow_for_intent,
)
from src.chatbot.modules.orchestration.pipeline import SafeMessagePipeline
from src.chatbot.modules.workflows.composer import ResponseComposer
from src.chatbot.modules.workflows.support_contacts import SupportContactDirectory
from src.chatbot.shared.enums import IntentType, PageCode
from src.chatbot.shared.events import InboxEvent, NormalizedMessage

DEFAULT_CASES = ROOT / "tests/fixtures/cfc_faq_cases.json"
DEFAULT_HELDOUT = ROOT / "tests/fixtures/cfc_faq_heldout_paraphrases.json"
DEFAULT_BASELINE = ROOT / "tests/fixtures/cfc_faq_f6_baseline.json"
DEFAULT_JSON = ROOT / "reports/cfc_faq_evaluation.json"
DEFAULT_MARKDOWN = ROOT / "reports/cfc_faq_evaluation.md"
FAILURE_CODES = frozenset(
    {"ROUTING", "SLOT", "RETRIEVAL", "WORKFLOW", "GROUNDING", "OUTPUT_POLICY"}
)


def _fold(value: str) -> str:
    value = re.sub(r"[*_`#]", " ", value.casefold())
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", value.replace("đ", "d")).strip()


def _reply_violations(text: str) -> list[str]:
    folded = _fold(text)
    checks = {
        "forbidden_persona": (
            r"\b(?:chao ban|ban oi|cua ban|ban cho em|ban nhan|ban vui long)\b",
            r"\bba con\b",
            r"\bchao em\b",
            r"\bchao chi\s*/\s*em\b",
            r"\bchi\s*/\s*chu\b",
            r"\bco\s*/\s*bac\b",
            r"\banh\s*/\s*chi oi\b",
        ),
        "internal_term": (
            r"\bsnapshot crm\b",
            r"\b(?:database|postgres(?:ql)?|redis|ollama|read model)\b",
        ),
        "numeric_price": (
            r"\b\d+[\s.]*(?:nghin|ngan|trieu|k|d|vnd|dong)\b",
            r"\b(?:gia|khoang)\s*[:=]?\s*\d{4,}\b",
        ),
    }
    violations = [
        code
        for code, patterns in checks.items()
        if any(re.search(pattern, folded) for pattern in patterns)
    ]
    if ResponseComposer.has_unresolved_placeholders(text):
        violations.append("unresolved_placeholder")
    return sorted(set(violations))


def _knowledge_records(catalog: dict[str, Any], *, active_only: bool = False):
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
        if case["status"] == "ANSWERABLE" and (not active_only or case["source_active"])
    ]


def _retrieval_results(catalog: dict[str, Any], store: ApprovedKnowledgeStore):
    results = []
    for case in catalog["cases"]:
        if case["status"] != "ANSWERABLE":
            continue
        expected = f"faq:{case['faq_id']}"
        for index, question in enumerate(case["questions"], 1):
            decision = store.search_with_confidence(
                PageCode.CFC, question, limit=3, record_prefix="faq:"
            )
            ids = [record.record_id for record in decision.records]
            rank = ids.index(expected) + 1 if expected in ids else None
            results.append(
                {
                    "case_id": case["case_id"],
                    "question_index": index,
                    "question": question,
                    "expected_record_id": expected,
                    "retrieved_record_ids": ids,
                    "decision": decision.status,
                    "rank": rank,
                    "top1_pass": rank == 1,
                    "top3_pass": rank is not None,
                    "zeo_isolated": not store.search(
                        PageCode.ZEO, question, limit=1, record_prefix="faq:"
                    ),
                }
            )
    return results


def _heldout_results(heldout, catalog, store):
    expected_ids = {
        case["case_id"]: f"faq:{case['faq_id']}"
        for case in catalog["cases"]
        if case["status"] == "ANSWERABLE"
    }
    results = []
    for item in heldout["cases"]:
        expected = expected_ids[item["case_id"]]
        decision = store.search_with_confidence(
            PageCode.CFC, item["query"], limit=3, record_prefix="faq:"
        )
        ids = [record.record_id for record in decision.records]
        rank = ids.index(expected) + 1 if expected in ids else None
        results.append(
            {
                **item,
                "expected_record_id": expected,
                "retrieved_record_ids": ids,
                "rank": rank,
                "top1_pass": rank == 1,
                "top3_pass": rank is not None,
            }
        )
    return results


class RecordingAnalyzer:
    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.normalizer = analyzer.normalizer
        self.last_result = None

    def analyze(self, page_id, text, context=None):
        self.last_result = self.analyzer.analyze(page_id, text, context)
        return self.last_result


class EvaluationConversationRepository:
    """Durable-contract double used to assert workflow side effects."""

    def __init__(self):
        self.context: dict[str, Any] = {}
        self.tasks: list[dict[str, Any]] = []
        self.version = 0

    def load_understanding_context(self, page_id, conversation_id):
        return dict(self.context)

    def update_context(
        self, page_id, conversation_id, *, workflow, primary_intent, slots
    ):
        self.version += 1
        self.context = {
            "current_workflow": workflow.value,
            "current_intent": primary_intent.value,
            "current_slots": dict(slots),
        }
        return SimpleNamespace(version=self.version)

    def create_handoff_task(self, page_id, conversation_id, **kwargs):
        self.tasks.append({"page_id": page_id.value, **kwargs})
        return f"eval-task-{len(self.tasks)}"


def _event(case_id: str, question_index: int, text: str):
    identity = f"{case_id}-{question_index}"
    return InboxEvent(
        event_id=f"eval-{identity}",
        page_id=PageCode.CFC,
        sender_id=f"eval-{identity}",
        message=NormalizedMessage(
            mid=f"mid-{identity}",
            sender_id=f"eval-{identity}",
            recipient_id="page-cfc-eval",
            timestamp=dt.datetime.now(dt.UTC),
            text=text,
        ),
    )


def _accepted_intents(expected: str):
    if expected == IntentType.PRICE_INQUIRY.value:
        return {IntentType.PRICE_INQUIRY.value, IntentType.PRICE_INQUIRY_DETAIL.value}
    return {expected}


def _outcome_failures(case, *, reply, repository, slots):
    mode, folded = case["response_mode"], _fold(reply)
    failures = []

    def fail(detail):
        failures.append({"code": "WORKFLOW", "detail": detail})

    if mode == "price_handoff" and not repository.tasks:
        fail("price inquiry did not create a durable handoff task")
    elif case["intent"] == IntentType.HUMAN_REQUEST.value and not repository.tasks:
        fail("human request did not create a durable handoff task")
    elif case["intent"] == IntentType.SALES_LEAD.value:
        asks_required = (
            "tinh/huyen" in folded or "khu vuc" in folded
        ) and "so dien thoai" in folded
        if not repository.tasks and not asks_required:
            fail("sales lead neither collected required slots nor created handoff")
    elif mode == "dealer_lookup" and not slots.get("location"):
        if "tinh/huyen" not in folded and "khu vuc" not in folded:
            fail("dealer lookup did not request a location")
    elif mode == "agri_clarify":
        markers = ("loai cay", "giai doan", "tinh trang", "thong tin")
        if not any(marker in folded for marker in markers):
            fail("agronomy workflow did not clarify missing evidence")
    elif case["intent"] == IntentType.CONTACT_REQUEST.value:
        phone = r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){9,10}(?!\d)"
        if not re.search(phone, reply):
            fail("contact workflow returned no approved contact")
    return failures


def _runtime_results(catalog, store, *, client=None):
    if client is None:
        client = OllamaIntentClient(
            settings.OLLAMA_BASE_URL,
            settings.OLLAMA_MODEL_TAG,
            settings.OLLAMA_TIMEOUT_SECONDS,
            prompt_path=settings.INTENT_PROMPT_PATH,
            max_attempts=1,
        )
        if not client.is_ready():
            return "BLOCKED_OLLAMA_NOT_READY", []
    normalizer = VietnameseNormalizer(
        settings.INTENT_NORMALIZATION_PATH, settings.ADMINISTRATIVE_AREAS_PATH
    )
    analyzer = RecordingAnalyzer(HybridInputAnalyzer(client, normalizer))
    composer = ResponseComposer(
        contact_directory=SupportContactDirectory.from_file(
            settings.SUPPORT_CONTACTS_PATH
        )
    )
    results = []
    for case in catalog["cases"]:
        if case["status"] != "ANSWERABLE":
            continue
        for index, question in enumerate(case["questions"], 1):
            repository, outbox = (
                EvaluationConversationRepository(),
                InMemoryOutboxStore(),
            )
            pipeline = SafeMessagePipeline(
                outbox,
                intent_analyzer=analyzer,
                knowledge_store=store,
                conversation_repository=repository,
                composer=composer,
            )
            outbox_id = pipeline.process(
                _event(case["case_id"], index, question), batch_version=1
            )
            actual = outbox.messages[outbox_id].text if outbox_id else ""
            analysis = analyzer.last_result
            actual_intent = analysis.primary_intent.value if analysis else None
            slots = dict(analysis.extracted_slots) if analysis else {}
            failures = []
            if actual_intent not in _accepted_intents(case["intent"]):
                failures.append(
                    {
                        "code": "ROUTING",
                        "detail": f"expected {case['intent']}, got {actual_intent}",
                    }
                )
            if analysis:
                expected_slots = normalizer.deterministic_slots(
                    normalizer.normalize(question)
                )
                missing = sorted(set(expected_slots) - set(slots))
                if missing:
                    failures.append(
                        {
                            "code": "SLOT",
                            "detail": "missing deterministic slots: "
                            + ", ".join(missing),
                        }
                    )
            expected_workflow = workflow_for_intent(IntentType(case["intent"]))
            actual_workflow = (
                workflow_for_intent(analysis.primary_intent) if analysis else None
            )
            if actual_workflow != expected_workflow:
                failures.append(
                    {
                        "code": "WORKFLOW",
                        "detail": f"expected {expected_workflow.value}, got "
                        f"{actual_workflow.value if actual_workflow else 'none'}",
                    }
                )
            failures.extend(
                _outcome_failures(
                    case, reply=actual, repository=repository, slots=slots
                )
            )
            violations = _reply_violations(actual)
            if violations:
                failures.append(
                    {"code": "OUTPUT_POLICY", "detail": ", ".join(violations)}
                )
            if (
                case["response_mode"] == "direct"
                and case["source_active"]
                and _fold(case["expected_answer"]) not in _fold(actual)
            ):
                failures.append(
                    {
                        "code": "GROUNDING",
                        "detail": "active direct answer did not use its approved source",
                    }
                )
            if any(reason["code"] not in FAILURE_CODES for reason in failures):
                raise AssertionError("unknown F6 failure taxonomy code")
            gated = bool(case["source_active"])
            verdict = (
                "PASS" if gated and not failures else "FAIL" if gated else "NOT_GATED"
            )
            results.append(
                {
                    "case_id": case["case_id"],
                    "question_index": index,
                    "question": question,
                    "source_active": gated,
                    "review_status": case["review_status"],
                    "expected_intent": case["intent"],
                    "actual_intent": actual_intent,
                    "expected_workflow": expected_workflow.value,
                    "actual_workflow": actual_workflow.value
                    if actual_workflow
                    else None,
                    "slots": slots,
                    "actual_answer": actual,
                    "handoff_tasks": len(repository.tasks),
                    "violations": violations,
                    "failure_reasons": failures,
                    "verdict": verdict,
                }
            )
    return "COMPLETED", results


def _production_status():
    try:
        dsn = settings.get_database_url().replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
        with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT count(*) FROM knowledge_records
                WHERE page_id='CFC' AND status='APPROVED' AND is_active=true
                  AND source_locator LIKE 'CFC_Co_Bay_FAQ.md:%'""")
            active = int(cursor.fetchone()[0])
            cursor.execute("""SELECT count(*) FROM import_batches
                WHERE page_id='CFC'
                  AND source_file LIKE '%%CFC_Co_Bay_FAQ.md'""")
            batches = int(cursor.fetchone()[0])
        return {
            "status": "CHECKED",
            "active_approved_records": active,
            "import_batches": batches,
        }
    except (psycopg2.Error, OSError, ValueError) as exc:
        return {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}


def _summary(items):
    total = len(items)
    top1, top3 = sum(x["top1_pass"] for x in items), sum(x["top3_pass"] for x in items)
    return {
        "total": total,
        "top1_pass": top1,
        "top3_pass": top3,
        "top1_rate": round(top1 / total, 4) if total else 0.0,
        "top3_rate": round(top3 / total, 4) if total else 0.0,
    }


def _apply_gate(report, baseline, *, live, check_production):
    runtime = report["runtime_summary"]
    values = {
        "source_retrieval_top1_rate": report["retrieval_summary"]["top1_rate"],
        "source_retrieval_top3_rate": report["retrieval_summary"]["top3_rate"],
        "heldout_top1_rate": report["heldout_summary"]["top1_rate"],
        "heldout_top3_rate": report["heldout_summary"]["top3_rate"],
        "active_runtime_pass_rate": runtime["active_pass_rate"],
        "output_policy_violations": float(runtime["output_policy_violations"]),
    }
    comparisons, failures = [], []
    for name, rule in baseline["metrics"].items():
        if name == "active_runtime_pass_rate" and not live:
            continue
        actual = values[name]
        passed = actual >= rule["min"] if "min" in rule else actual <= rule["max"]
        comparisons.append({"metric": name, "actual": actual, **rule, "pass": passed})
        if not passed:
            failures.append(f"BASELINE:{name}")
    retrieval = report["retrieval_summary"]
    if retrieval["zeo_isolated"] != retrieval["total"]:
        failures.append("PAGE_ISOLATION")
    if live and runtime["gate_status"] != "COMPLETED":
        failures.append(runtime["gate_status"])
    if check_production:
        expected = report["source_summary"]["active_answerable_rows"]
        production = report["production"]
        if production.get("status") != "CHECKED":
            failures.append("PRODUCTION_UNAVAILABLE")
        elif production.get("active_approved_records", 0) < expected:
            failures.append("PRODUCTION_ACTIVE_RECORDS_BELOW_GOVERNANCE")
    report["baseline_comparison"] = comparisons
    report["gate"] = {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def evaluate(
    catalog, *, heldout, baseline, live, check_production, runtime_client=None
):
    source_store = ApprovedKnowledgeStore(_knowledge_records(catalog))
    active_store = ApprovedKnowledgeStore(_knowledge_records(catalog, active_only=True))
    retrieval = _retrieval_results(catalog, source_store)
    heldout_results = _heldout_results(heldout, catalog, source_store)
    gate_status, runtime_results = (
        _runtime_results(catalog, active_store, client=runtime_client)
        if live
        else ("NOT_REQUESTED", [])
    )
    active = [item for item in runtime_results if item["source_active"]]
    active_pass = sum(item["verdict"] == "PASS" for item in active)
    taxonomy = Counter(
        reason["code"] for item in runtime_results for reason in item["failure_reasons"]
    )
    source_summary = dict(catalog["summary"])
    source_summary["active_answerable_rows"] = sum(
        c["status"] == "ANSWERABLE" and c["source_active"] for c in catalog["cases"]
    )
    source_summary["active_question_variants"] = sum(
        len(c["questions"])
        for c in catalog["cases"]
        if c["status"] == "ANSWERABLE" and c["source_active"]
    )
    report = {
        "schema_version": 2,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source_file": catalog["source_file"],
        "source_sha256": catalog["source_sha256"],
        "source_summary": source_summary,
        "production": _production_status()
        if check_production
        else {"status": "NOT_REQUESTED"},
        "retrieval_summary": {
            **_summary(retrieval),
            "zeo_isolated": sum(x["zeo_isolated"] for x in retrieval),
        },
        "retrieval_results": retrieval,
        "heldout_summary": _summary(heldout_results),
        "heldout_results": heldout_results,
        "runtime_summary": {
            "gate_status": gate_status,
            "total_variants": len(runtime_results),
            "active_total": len(active),
            "active_pass": active_pass,
            "active_pass_rate": round(active_pass / len(active), 4) if active else 0.0,
            "verdict_counts": dict(Counter(x["verdict"] for x in runtime_results)),
            "failure_taxonomy": dict(sorted(taxonomy.items())),
            "output_policy_violations": sum(bool(x["violations"]) for x in active),
        },
        "runtime_results": runtime_results,
    }
    _apply_gate(report, baseline, live=live, check_production=check_production)
    return report


def _short(value, limit=100):
    if not value:
        return "—"
    compact = re.sub(r"\s+", " ", str(value)).replace("|", "\\|")
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _markdown(report):
    retrieval, heldout, runtime = (
        report["retrieval_summary"],
        report["heldout_summary"],
        report["runtime_summary"],
    )
    lines = [
        "# CFC FAQ Phase F6 evaluation",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Gate: **{report['gate']['status']}**",
        "",
        "## Summary",
        "",
        f"- Source retrieval Top-1: **{retrieval['top1_pass']}/{retrieval['total']}**",
        f"- Source retrieval Top-3: **{retrieval['top3_pass']}/{retrieval['total']}**",
        f"- Held-out Top-1: **{heldout['top1_pass']}/{heldout['total']}**",
        f"- Held-out Top-3: **{heldout['top3_pass']}/{heldout['total']}**",
        f"- Active runtime: **{runtime['active_pass']}/{runtime['active_total']}**",
        f"- Runtime variants executed: **{runtime['total_variants']}**",
        f"- Failure taxonomy: `{runtime['failure_taxonomy']}`",
        f"- Production: `{report['production']}`",
        f"- Gate failures: `{report['gate']['failures']}`",
        "",
        "Inactive rows are executed for audit but stay `NOT_GATED` until signed off.",
        "",
        "## Active runtime cases",
        "",
        "| Case | Q | Expected | Actual | Verdict | Failure | Reply |",
        "|---|---:|---|---|---|---|---|",
    ]
    for item in report["runtime_results"]:
        if not item["source_active"]:
            continue
        failures = (
            "; ".join(
                f"{reason['code']}: {reason['detail']}"
                for reason in item["failure_reasons"]
            )
            or "—"
        )
        lines.append(
            f"| {item['case_id']} | {item['question_index']} | {item['expected_intent']} | "
            f"{item['actual_intent']} | {item['verdict']} | {_short(failures, 140)} | "
            f"{_short(item['actual_answer'], 160)} |"
        )
    lines.extend(["", "## Retrieval/held-out Top-1 failures", ""])
    problems = [
        ("Source", item, item["question"])
        for item in report["retrieval_results"]
        if not item["top1_pass"]
    ] + [
        ("Held-out", item, item["query"])
        for item in report["heldout_results"]
        if not item["top1_pass"]
    ]
    if not problems:
        lines.append("No retrieval failures.")
    for label, item, query in problems:
        lines.append(
            f"- {label} `{item['case_id']}`: `{_short(query, 140)}` -> `{item['retrieved_record_ids']}`"
        )
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Run the Phase F6 CFC FAQ gate.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--heldout", type=Path, default=DEFAULT_HELDOUT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--live", action="store_true", help="Run all 119 variants through Qwen/pipeline"
    )
    parser.add_argument("--check-production", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="Exit non-zero on gate regression"
    )
    args = parser.parse_args()
    report = evaluate(
        json.loads(args.cases.read_text(encoding="utf-8")),
        heldout=json.loads(args.heldout.read_text(encoding="utf-8")),
        baseline=json.loads(args.baseline.read_text(encoding="utf-8")),
        live=args.live,
        check_production=args.check_production,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_markdown.write_text(_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "gate": report["gate"],
                "retrieval": report["retrieval_summary"],
                "heldout": report["heldout_summary"],
                "runtime": report["runtime_summary"],
                "production": report["production"],
                "output_json": str(args.output_json),
                "output_markdown": str(args.output_markdown),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if report["runtime_summary"]["gate_status"] == "BLOCKED_OLLAMA_NOT_READY":
        return 2
    return 1 if args.check and report["gate"]["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
