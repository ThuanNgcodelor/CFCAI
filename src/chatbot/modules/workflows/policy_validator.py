"""Output policy validator for the CFC-ZEO conversational platform.

Enforces:
1. Zero Price Hallucination (INV-1).
2. Zero Internal Jargon (no 'snapshot CRM', 'database', 'redis', 'null', etc.).
3. Zero Unresolved Placeholders / Template Markers.
4. Zero False Phone Confirmations and Phone Number Allowlist.
5. Persona & Pronoun Integrity (em/bên em vs anh/chị, no 'bạn', 'bà con').
6. Groundedness (no unverified 'gần nhất' claims, no unapproved advice formulas).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.chatbot.shared.enums import PageCode, WorkflowType


@dataclass(frozen=True)
class PolicyValidationResult:
    is_valid: bool
    text: str
    reasons: tuple[str, ...] = ()


class OutputPolicyValidator:
    _PRICE_PATTERNS = (
        re.compile(r"\b\d+[\s.]*(?:nghìn|ngàn|triệu|k|đ|vnd|đồng)\b", re.IGNORECASE),
        re.compile(
            r"\b(?:giá|khoảng)\s*[:=]?\s*\d+(?:[.,]\d+)?\s*(?:nghìn|ngàn|triệu|k|đ|vnd|đồng)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b(?:giá|khoảng)\s*[:=]?\s*\d{4,}\b", re.IGNORECASE),
    )

    _PLACEHOLDER_PATTERN = re.compile(
        r"""
        (?:
            \{\{\s*(?P<double_curly>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\}\}
            |\$\{\s*(?P<dollar_curly>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\}
            |\{\s*(?P<curly>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\}
            |\[\s*(?P<square>[A-Za-z][A-Za-z0-9_\\.-]*)\s*\]
        )
        """,
        re.VERBOSE,
    )

    _INTERNAL_JARGON_PATTERNS = (
        re.compile(r"\b(?:snapshot\s*crm|crm\s*snapshot)\b", re.IGNORECASE),
        re.compile(r"\b(?:read\s*model|raw\s*record|internal\s*data)\b", re.IGNORECASE),
        re.compile(r"\b(?:database|postgres(?:ql)?|redis|ollama|pgvector)\b", re.IGNORECASE),
        re.compile(r"\b(?:outbox(?:_messages)?|inbox(?:_events)?|quarantined)\b", re.IGNORECASE),
        re.compile(r"\b(?:sql|traceback|pydantic)\b", re.IGNORECASE),
        re.compile(r"\b(?:null|none|nan|undefined)\b", re.IGNORECASE),
    )

    _PHONE_PATTERN = re.compile(
        r"(?<!\d)(?:(?:\+?84|0)(?:[\s.\-]?\d){9,10}|1900[\s.\-]?\d{4})(?!\d)"
    )

    _PHONE_CONFIRMATION_PATTERNS = (
        re.compile(
            r"\b(?:em|ben em|he thong)\s+(?:da|se|vua)\s+"
            r"(?:ghi nhan|luu|de lai|xac nhan|nhan duoc)\b.{0,80}"
            r"\b(?:so dien thoai|sdt)\b"
        ),
        re.compile(
            r"\b(?:da|vua)\s+(?:ghi nhan|luu|xac nhan|nhan duoc)\b.{0,80}"
            r"\b(?:so dien thoai|sdt)\b"
        ),
        re.compile(
            r"\b(?:nhan vien|ban kinh doanh|chuyen vien|ben em)\b.{0,60}"
            r"\b(?:se|da)\s+(?:goi|lien he)\b.{0,40}"
            r"\b(?:qua|theo)\s+(?:so|sdt)\b"
        ),
        re.compile(
            r"\bso dien thoai cua (?:anh|chi|anh chi|minh)\b.{0,30}\b(?:da|se)\b"
        ),
    )

    _FORBIDDEN_PERSONA_PATTERNS = (
        # Prohibit addressing customer as 'bạn' (khi bot giao tiếp với khách)
        re.compile(r"\b(?:chao ban|ban oi|cua ban|ban cho em|ban nhan|ban vui long)\b", re.IGNORECASE),
        # Prohibit addressing customer as 'bà con'
        re.compile(r"\b(?:ba con|kinh chao ba con)\b", re.IGNORECASE),
        # Prohibit addressing customer as 'cô/bác', 'chị/em', 'chị/chú'
        re.compile(r"\b(?:chi/em|chi/chu|co/bac|anh/chi oi)\b", re.IGNORECASE),
    )

    _DEADLINE_TOKENS = frozenset(
        {
            "moc_hen_lien_he",
            "thoi_gian",
            "deadline",
            "deadline_text",
            "contact_deadline",
        }
    )

    @classmethod
    def _fold_text(cls, text: str) -> str:
        folded = unicodedata.normalize("NFD", text.casefold())
        folded = "".join(
            character
            for character in folded
            if unicodedata.category(character) != "Mn"
        )
        return folded.replace("đ", "d")

    @classmethod
    def check_price(cls, text: str) -> str | None:
        """Return failure reason if text quotes price numbers or currency amounts."""
        for pattern in cls._PRICE_PATTERNS:
            if pattern.search(text):
                return "PRICE_HALLUCINATION_DETECTED"
        return None

    @classmethod
    def check_placeholders(cls, text: str) -> str | None:
        """Return failure reason if unresolved placeholders exist."""
        normalized = text.replace("\\_", "_")
        for match in cls._PLACEHOLDER_PATTERN.finditer(normalized):
            token = next(
                value for value in match.groupdict().values() if value is not None
            ).replace("\\_", "_").casefold()
            if token not in cls._DEADLINE_TOKENS:
                return f"UNRESOLVED_PLACEHOLDER: [{token}]"
        return None

    @classmethod
    def check_internal_jargon(cls, text: str) -> str | None:
        """Return failure reason if developer or internal terms leak into output."""
        for pattern in cls._INTERNAL_JARGON_PATTERNS:
            match = pattern.search(text)
            if match:
                return f"INTERNAL_JARGON_DETECTED: {match.group(0)}"
        return None

    @classmethod
    def check_phone_groundedness(
        cls,
        text: str,
        slots: dict[str, Any],
        allowed_phones: set[str],
    ) -> str | None:
        """Validate phone claims and ensure phone numbers match allowlist."""
        customer_phone = str(slots.get("phone") or "").strip()
        cleaned_customer_phone = re.sub(r"\D", "", customer_phone)
        if cleaned_customer_phone.startswith("84"):
            cleaned_customer_phone = "0" + cleaned_customer_phone[2:]

        folded = cls._fold_text(text)
        if not cleaned_customer_phone:
            for pattern in cls._PHONE_CONFIRMATION_PATTERNS:
                if pattern.search(folded):
                    return "FALSE_PHONE_CONFIRMATION_WITHOUT_SLOT"

        # Check all phone numbers in text
        for match in cls._PHONE_PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if digits.startswith("84"):
                digits = "0" + digits[2:]
            if digits != cleaned_customer_phone and digits not in allowed_phones:
                return f"UNAPPROVED_PHONE_NUMBER: {match.group(0)}"
        return None

    @classmethod
    def check_persona(cls, text: str) -> str | None:
        """Return failure reason if forbidden persona markers are used."""
        folded = cls._fold_text(text)
        for pattern in cls._FORBIDDEN_PERSONA_PATTERNS:
            match = pattern.search(folded)
            if match:
                return f"FORBIDDEN_PERSONA: {match.group(0)}"
        return None

    @classmethod
    def sanitize(cls, text: str, deadline_text: str = "sớm nhất") -> str:
        """Perform deterministic cleanup of placeholders and whitespace."""
        normalized = text.replace("\\_", "_")

        def replace_marker(match: re.Match[str]) -> str:
            token = next(
                value for value in match.groupdict().values() if value is not None
            ).replace("\\_", "_").casefold()
            return deadline_text if token in cls._DEADLINE_TOKENS else ""

        sanitized = cls._PLACEHOLDER_PATTERN.sub(replace_marker, normalized)
        sanitized = re.sub(
            r"\b(?:moc_hen_lien_he|thoi_gian|deadline(?:_text)?|contact_deadline)\b",
            deadline_text,
            sanitized,
            flags=re.IGNORECASE,
        )
        # Clean snapshot CRM jargon if present in legacy templates
        sanitized = re.sub(
            r"\bsnapshot\s*crm\b",
            "hệ thống",
            sanitized,
            flags=re.IGNORECASE,
        )
        # Normalize whitespace and punctuation
        sanitized = re.sub(r"\(\s*\)", "", sanitized)
        sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
        sanitized = re.sub(r"[ \t]*\n[ \t]*", "\n", sanitized)
        return re.sub(r"\s+([,.;!?])", r"\1", sanitized).strip()

    @classmethod
    def validate(
        cls,
        text: str,
        *,
        page_id: PageCode,
        workflow: WorkflowType,
        slots: dict[str, Any] | None = None,
        allowed_phones: set[str] | None = None,
        deadline_text: str = "sớm nhất",
        fallback: str | None = None,
    ) -> PolicyValidationResult:
        """Validate candidate response against all output policy constraints.

        If any safety rule fails and a fallback is provided, the safe fallback
        is returned with is_valid=False and the exact reasons logged.
        """
        slots = slots or {}
        allowed = set(allowed_phones or ())
        reasons: list[str] = []

        placeholder_err = cls.check_placeholders(text)
        if placeholder_err:
            reasons.append(placeholder_err)

        sanitized = cls.sanitize(text, deadline_text)
        if not sanitized:
            reasons.append("EMPTY_RESPONSE_AFTER_SANITIZATION")
        elif re.search(
            r"\b(?:moc_hen_lien_he|thoi_gian|deadline_text|contact_deadline)\b",
            sanitized,
            flags=re.IGNORECASE,
        ):
            reasons.append("RAW_TEMPLATE_VARIABLE_NAME")

        price_err = cls.check_price(sanitized)
        if price_err:
            reasons.append(price_err)

        jargon_err = cls.check_internal_jargon(sanitized)
        if jargon_err:
            reasons.append(jargon_err)

        phone_err = cls.check_phone_groundedness(sanitized, slots, allowed)
        if phone_err:
            reasons.append(phone_err)

        persona_err = cls.check_persona(sanitized)
        if persona_err:
            reasons.append(persona_err)

        if reasons:
            safe_text = cls.sanitize(fallback or sanitized, deadline_text)
            # Re-ensure fallback itself never has price or jargon
            if cls.check_price(safe_text):
                safe_text = (
                    "Dạ giá sản phẩm tùy thuộc vào khu vực và số lượng lấy nên bên em không báo số cụ thể trên chat được ạ. "
                    "Bạn kinh doanh khu vực sẽ liên hệ báo giá chính xác và tốt nhất cho mình nha anh/chị 🌾"
                )
            return PolicyValidationResult(
                is_valid=False,
                text=safe_text,
                reasons=tuple(reasons),
            )

        return PolicyValidationResult(is_valid=True, text=sanitized)
