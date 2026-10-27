"""Read-only production preflight; it never enables Messenger delivery."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

# Support both `python scripts/verify_go_live.py` and module execution from a
# clean checkout, matching the operational commands in the runbook.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.chatbot.core.settings import Settings, settings


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def delivery_checks(config: Settings) -> list[Check]:
    mode = config.get_delivery_mode()
    checks = [
        Check(
            "admin_auth",
            "PASS" if config.ADMIN_API_TOKEN else "BLOCKED",
            "ADMIN_API_TOKEN configured" if config.ADMIN_API_TOKEN else "configure ADMIN_API_TOKEN before staging/production",
        ),
        Check(
            "delivery_mode",
            "PASS" if mode in {"shadow", "canary", "live"} else "BLOCKED",
            f"configured mode: {mode}",
        ),
    ]
    if mode == "canary":
        scoped = bool(config.CANARY_PAGE_IDS and config.CANARY_WORKFLOWS)
        approved = config.CANARY_SEND_APPROVED and config.CANARY_PERCENT > 0
        checks.append(
            Check(
                "canary_scope",
                "PASS" if scoped and approved else "BLOCKED",
                "page/workflow scope and explicit approval required",
            )
        )
    if mode in {"canary", "live"}:
        try:
            release_fence = config.get_delivery_not_before()
        except ValueError:
            release_fence = None
        checks.append(
            Check(
                "release_fence",
                "PASS" if release_fence is not None else "BLOCKED",
                "DELIVERY_NOT_BEFORE prevents delayed pending outbox messages",
            )
        )
    if mode == "live":
        checks.append(
            Check(
                "live_approval",
                "PASS" if config.LIVE_SEND_APPROVED else "BLOCKED",
                "LIVE_SEND_APPROVED=true is required; business sign-off remains external",
            )
        )
    return checks


def http_check(name: str, url: str) -> Check:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if 200 <= response.status < 300:
                return Check(name, "PASS", f"HTTP {response.status}")
            return Check(name, "BLOCKED", f"HTTP {response.status}")
    except (OSError, urllib.error.URLError) as exc:
        return Check(name, "BLOCKED", f"unreachable: {type(exc).__name__}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--offline", action="store_true", help="only validate configuration")
    args = parser.parse_args()

    checks = delivery_checks(settings)
    if not args.offline:
        checks.append(http_check("api_health", f"{args.api_url.rstrip('/')}/health"))
        checks.append(http_check("ollama_readiness", f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"))
    report = {"checks": [asdict(check) for check in checks]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(check.status == "PASS" for check in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
