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
        re.compile(r"\bban kinh doanh\b", re.IGNORECASE),
    )

    _CUSTOMER_BAN_PATTERN = re.compile(r"(?<![\wÀ-ỹ])bạn(?![\wÀ-ỹ])", re.IGNORECASE)

    _HANDOFF_CLAIM_PATTERNS = (
        re.compile(r"\b(?:em|ben em) da (?:chuyen|tao)\b"),
        re.compile(r"\bda tao yeu cau\b"),
        re.compile(
            r"\b(?:nhan vien|bo phan|chuyen vien)\b.{0,60}"
            r"\bse (?:lien he|goi|tiep nhan)\b"
        ),
    )

    _NEAREST_CLAIM_PATTERNS = (
        re.compile(r"\b(?:day|do) la\b.{0,60}\b(?:dai ly|diem ban)\b.{0,30}\bgan nhat\b"),
        re.compile(r"\b(?:dai ly|diem ban)\b.{0,30}\bgan nhat\b\s+(?:la|o|tai)\b"),
        re.compile(r"\btim duoc\b.{0,60}\b(?:dai ly|diem ban)\b.{0,30}\bgan nhat\b"),
        re.compile(r"\b(?:bao|gioi thieu)\b.{0,30}\b(?:dai ly|diem ban)\b.{0,30}\bgan nhat\b"),
    )

    _FORMULA_PATTERN = re.compile(
        r"(?<!\d)(\d{1,2}(?:[.,]\d+)?\s*-\s*\d{1,2}(?:[.,]\d+)?\s*-\s*"
        r"\d{1,2}(?:[.,]\d+)?(?:\s*\+\s*[A-Za-zÀ-ỹ0-9.,%\-]+)*)",
        re.IGNORECASE,
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
        if match := cls._CUSTOMER_BAN_PATTERN.search(text):
            return f"FORBIDDEN_PERSONA: {match.group(0)}"
        folded = cls._fold_text(text)
        for pattern in cls._FORBIDDEN_PERSONA_PATTERNS:
            match = pattern.search(folded)
            if match:
                return f"FORBIDDEN_PERSONA: {match.group(0)}"
        return None

    @classmethod
    def check_handoff_claim(
        cls,
        text: str,
        workflow: WorkflowType,
        handoff_created: bool,
    ) -> str | None:
        if handoff_created or workflow not in {
            WorkflowType.PRICE_HANDOFF,
            WorkflowType.HUMAN_REQUEST,
        }:
            return None
        folded = cls._fold_text(text)
        if any(pattern.search(folded) for pattern in cls._HANDOFF_CLAIM_PATTERNS):
            return "FALSE_HANDOFF_CONFIRMATION"
        return None

    @classmethod
    def check_nearest_groundedness(
        cls,
        text: str,
        workflow: WorkflowType,
        slots: dict[str, Any],
    ) -> str | None:
        folded = cls._fold_text(text)
        if not any(pattern.search(folded) for pattern in cls._NEAREST_CLAIM_PATTERNS):
            return None
        if slots.get("dealer_match_scope") != "GPS_DISTANCE":
            return "UNVERIFIED_NEAREST_DEALER_CLAIM"
        return None

    @classmethod
    def check_named_entity_groundedness(
        cls,
        text: str,
        workflow: WorkflowType,
        slots: dict[str, Any],
        grounding_texts: list[str],
    ) -> str | None:
        """Reject novel capitalized catalog entities introduced by generation.

        This is deliberately domain-agnostic: product names/codes must occur in
        retrieved evidence or customer-provided slots. It catches invented brand
        and ingredient names without maintaining a hardcoded product blacklist.
        """
        if workflow not in {
            WorkflowType.PRODUCT_INQUIRY,
            WorkflowType.AGRICULTURE_ADVICE,
        }:
            return None
        evidence = " ".join([*grounding_texts, *(str(value) for value in slots.values())])
        folded_evidence = cls._fold_text(evidence)
        generic_terms = {
            "dạ",
            "anh",
            "chị",
            "cò",
            "bay",
            "zeo",
            "npk",
            "sđt",
        }
        for match in re.finditer(r"(?<![\wÀ-ỹ])([A-ZĐ][\wÀ-ỹ]{2,})(?![\wÀ-ỹ])", text):
            token = match.group(1)
            if token.casefold() in generic_terms:
                continue
            prefix = text[: match.start()].rstrip()
            if not prefix or prefix[-1:] in ".!?\n":
                continue
            folded_token = cls._fold_text(token)
            if not re.search(
                rf"(?<![a-z0-9]){re.escape(folded_token)}(?![a-z0-9])",
                folded_evidence,
            ):
                return f"UNGROUNDED_NAMED_ENTITY: {token}"
        return None

    @classmethod
    def check_formula_groundedness(
        cls,
        text: str,
        workflow: WorkflowType,
        slots: dict[str, Any],
        grounding_texts: list[str],
    ) -> str | None:
        if workflow not in {
            WorkflowType.PRODUCT_INQUIRY,
            WorkflowType.AGRICULTURE_ADVICE,
        }:
            return None
        formulas = cls._FORMULA_PATTERN.findall(text)
        if not formulas:
            return None
        evidence = " ".join([*grounding_texts, *(str(value) for value in slots.values())])
        folded_evidence = re.sub(r"\s+", "", cls._fold_text(evidence))
        for formula in formulas:
            folded_formula = re.sub(r"\s+", "", cls._fold_text(formula))
            if folded_formula not in folded_evidence:
                return f"UNGROUNDED_PRODUCT_FORMULA: {formula}"
        return None

    @classmethod
    def _default_fallback(
        cls,
        workflow: WorkflowType,
        *,
        handoff_created: bool,
    ) -> str:
        if workflow == WorkflowType.PRICE_HANDOFF:
            if handoff_created:
                return (
                    "Dạ bên em không báo giá cụ thể khi chưa xác nhận khu vực và số lượng. "
                    "Em đã tạo yêu cầu báo giá; anh/chị có thể bổ sung số điện thoại nếu cần liên hệ trực tiếp ạ."
                )
            return (
                "Dạ bên em chưa thể xác nhận giá cụ thể trên chat. Anh/chị vui lòng cung cấp "
                "khu vực, số lượng hoặc liên hệ bộ phận kinh doanh để được báo giá chính xác ạ."
            )
        if workflow == WorkflowType.HUMAN_REQUEST:
            if handoff_created:
                return "Dạ em đã tạo yêu cầu hỗ trợ. Anh/chị vui lòng chờ nhân viên phụ trách tiếp nhận ạ."
            return (
                "Dạ hiện em chưa xác nhận được yêu cầu chuyển nhân viên. "
                "Anh/chị vui lòng thử lại hoặc liên hệ hotline hỗ trợ ạ."
            )
        if workflow == WorkflowType.DEALER_LOOKUP:
            return (
                "Dạ em chưa đủ căn cứ để xác nhận điểm bán phù hợp. "
                "Anh/chị vui lòng cung cấp tỉnh/huyện/xã để em kiểm tra lại ạ."
            )
        if workflow == WorkflowType.PRODUCT_INQUIRY:
            return (
                "Dạ em chưa đủ căn cứ để xác định đúng sản phẩm. Anh/chị vui lòng gửi "
                "tên đầy đủ, mã/công thức trên bao bì hoặc nhu cầu sử dụng ạ."
            )
        if workflow == WorkflowType.AGRICULTURE_ADVICE:
            return (
                "Dạ em chưa đủ dữ liệu đã duyệt để tư vấn chính xác. "
                "Anh/chị vui lòng cho em biết loại cây, giai đoạn và tình trạng hiện tại ạ."
            )
        return (
            "Dạ em chưa đủ căn cứ để trả lời chính xác. "
            "Anh/chị vui lòng cung cấp thêm thông tin hoặc yêu cầu nhân viên hỗ trợ ạ."
        )

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
        handoff_created: bool = False,
        grounding_texts: list[str] | None = None,
    ) -> PolicyValidationResult:
        """Validate candidate response against all output policy constraints.

        If any safety rule fails and a fallback is provided, the safe fallback
        is returned with is_valid=False and the exact reasons logged.
        """
        slots = slots or {}
        allowed = set(allowed_phones or ())
        evidence = list(grounding_texts or ())

        def inspect(candidate: str) -> tuple[str, list[str]]:
            candidate_reasons: list[str] = []
            if placeholder_err := cls.check_placeholders(candidate):
                candidate_reasons.append(placeholder_err)
            sanitized_candidate = cls.sanitize(candidate, deadline_text)
            if not sanitized_candidate:
                candidate_reasons.append("EMPTY_RESPONSE_AFTER_SANITIZATION")
            elif re.search(
                r"\b(?:moc_hen_lien_he|thoi_gian|deadline_text|contact_deadline)\b",
                sanitized_candidate,
                flags=re.IGNORECASE,
            ):
                candidate_reasons.append("RAW_TEMPLATE_VARIABLE_NAME")
            checks = (
                cls.check_price(sanitized_candidate),
                cls.check_internal_jargon(sanitized_candidate),
                cls.check_phone_groundedness(sanitized_candidate, slots, allowed),
                cls.check_persona(sanitized_candidate),
                cls.check_handoff_claim(
                    sanitized_candidate, workflow, handoff_created
                ),
                cls.check_nearest_groundedness(
                    sanitized_candidate, workflow, slots
                ),
                cls.check_formula_groundedness(
                    sanitized_candidate, workflow, slots, evidence
                ),
                cls.check_named_entity_groundedness(
                    sanitized_candidate, workflow, slots, evidence
                ),
            )
            candidate_reasons.extend(reason for reason in checks if reason)
            return sanitized_candidate, candidate_reasons

        sanitized, reasons = inspect(text)
        if not reasons:
            return PolicyValidationResult(is_valid=True, text=sanitized)

        if fallback:
            safe_text, fallback_reasons = inspect(fallback)
            if not fallback_reasons:
                return PolicyValidationResult(
                    is_valid=False,
                    text=safe_text,
                    reasons=tuple(reasons),
                )
            reasons.append("UNSAFE_FALLBACK_REJECTED")

        safe_text = cls._default_fallback(
            workflow,
            handoff_created=handoff_created,
        )
        safe_text, final_reasons = inspect(safe_text)
        if final_reasons:
            # Last-resort text intentionally contains no dynamic facts, claims,
            # contacts, prices or workflow-specific terminology.
            safe_text = "Dạ em chưa đủ căn cứ để trả lời chính xác. Anh/chị vui lòng cung cấp thêm thông tin ạ."
        return PolicyValidationResult(
            is_valid=False,
            text=safe_text,
            reasons=tuple(reasons),
        )
