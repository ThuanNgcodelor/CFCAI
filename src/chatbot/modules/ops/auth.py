"""Small, configuration-backed role check for internal admin endpoints."""

from __future__ import annotations

import hmac
import json

_KNOWN_ROLES = frozenset({"viewer", "operator", "publisher", "admin"})
_ROLE_PATH_PREFIXES = {
    "viewer": (
        "/admin/ops/status",
        "/admin/ops/summary",
        "/admin/ops/audit",
        "/admin/shadow-reviews",
    ),
    "operator": (
        "/admin/ops/",
        "/admin/conversations/",
        "/admin/handoffs",
        "/admin/shadow-reviews",
    ),
    "publisher": ("/admin/catalog/",),
}


def parse_role_tokens(raw: str) -> dict[str, str]:
    """Parse `{role: token}` JSON without ever including a token in an error."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ADMIN_ROLE_TOKENS_JSON must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise TypeError("ADMIN_ROLE_TOKENS_JSON must be a JSON object")
    result: dict[str, str] = {}
    for role, token in parsed.items():
        normalized_role = str(role).strip().casefold()
        if (
            normalized_role not in _KNOWN_ROLES
            or not isinstance(token, str)
            or not token
        ):
            raise ValueError("ADMIN_ROLE_TOKENS_JSON contains an invalid role or token")
        result[normalized_role] = token
    return result


def role_for_token(
    supplied_token: str,
    *,
    administrator_token: str,
    role_tokens_json: str,
) -> str | None:
    if administrator_token and hmac.compare_digest(supplied_token, administrator_token):
        return "admin"
    for role, token in parse_role_tokens(role_tokens_json).items():
        if hmac.compare_digest(supplied_token, token):
            return role
    return None


def role_allows_path(role: str, path: str) -> bool:
    if role == "admin":
        return True
    return any(path.startswith(prefix) for prefix in _ROLE_PATH_PREFIXES.get(role, ()))
