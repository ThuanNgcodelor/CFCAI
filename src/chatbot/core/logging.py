"""Logging helpers that keep credentials and customer identifiers out of logs."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:(?:\+?84|0)(?:[\s.\-]?\d){9,10}|1900[\s.\-]?\d{4})(?!\d)"
)
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[^\s,;]+")
_URL_TOKEN_PATTERN = re.compile(r"(?i)(access_token=)[^&#\s]+")
_SECRET_VALUE_PATTERN = re.compile(
    r"(?ix)\b("
    r"client_secret|app_secret|access_token|api[_-]?key|"
    r"password|authorization|x-admin-token|x-internal-token"
    r")\b\s*([:=])\s*([^,\s}\]]+)"
)
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "secret",
        "token",
        "password",
        "authorization",
        "api_key",
        "access_key",
    }
)
_IDENTIFIER_KEY_PARTS = frozenset(
    {"phone", "mobile", "sender", "recipient", "psid"}
)


def mask_identifier(value: object) -> str:
    """Keep a small suffix for correlation without exposing the full value."""
    text = str(value)
    if len(text) <= 4:
        return "[REDACTED]"
    return f"***{text[-4:]}"


def redact_text(value: object) -> str:
    """Redact common secret and Vietnamese phone-number representations."""
    text = str(value)
    text = _BEARER_PATTERN.sub(r"\1[REDACTED]", text)
    text = _URL_TOKEN_PATTERN.sub(r"\1[REDACTED]", text)
    text = _SECRET_VALUE_PATTERN.sub(r"\1\2[REDACTED]", text)
    return _PHONE_PATTERN.sub("[PHONE_REDACTED]", text)


def redact_mapping(value: Any) -> Any:
    """Return a log/audit-safe deep copy of a JSON-like value."""
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).casefold().replace("-", "_")
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                safe[str(key)] = "[REDACTED]"
            elif any(part in normalized_key for part in _IDENTIFIER_KEY_PARTS):
                safe[str(key)] = mask_identifier(item)
            else:
                safe[str(key)] = redact_mapping(item)
        return safe
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_mapping(item) for item in value)
    return value


class SensitiveDataFilter(logging.Filter):
    """Mutate a log record after formatting arguments, before it reaches a sink."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    def formatException(self, exc_info) -> str:  # type: ignore[no-untyped-def]
        return redact_text(super().formatException(exc_info))


def configure_logging(level: str = "INFO") -> None:
    """Configure one redacting root handler without adding duplicate handlers."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    if any(getattr(handler, "_cfc_redacting", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler._cfc_redacting = True  # type: ignore[attr-defined]
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
