"""Config-backed support-contact routing.

Business contact data stays outside application logic.  The directory chooses
one stable person for a customer and workflow, then the deterministic composer
renders the approved name and phone number without asking the LLM to reproduce
either value.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.chatbot.shared.enums import PageCode, WorkflowType


def _fold_text(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.casefold())
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return folded.replace("đ", "d")


def normalize_support_phone(value: str) -> str:
    """Return a canonical Vietnamese contact number or reject bad config."""
    digits = re.sub(r"\D", "", value)
    if digits.startswith("84") and len(digits) in {11, 12}:
        digits = "0" + digits[2:]
    if not re.fullmatch(r"(?:0\d{9,10}|1900\d{4})", digits):
        raise ValueError(f"Unsupported support phone format: {value!r}")
    return digits


def display_support_phone(value: str) -> str:
    digits = normalize_support_phone(value)
    if digits.startswith("1900") and len(digits) == 8:
        return f"{digits[:4]} {digits[4:]}"
    if len(digits) == 10:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    if len(digits) == 11:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    return digits


@dataclass(frozen=True)
class SupportContact:
    contact_id: str
    name: str
    title: str
    phone: str

    @property
    def display_phone(self) -> str:
        return display_support_phone(self.phone)


@dataclass(frozen=True)
class SupportContactSelection:
    purpose: str
    label: str
    primary: SupportContact | None
    hotline: SupportContact | None


@dataclass(frozen=True)
class _PageContactConfig:
    contacts: dict[str, SupportContact]
    hotline: SupportContact | None
    purposes: dict[str, dict[str, Any]]
    workflow_purposes: dict[str, str]
    request_routing: tuple[dict[str, Any], ...]


class SupportContactDirectory:
    """Validated, page-scoped contact read model loaded from JSON."""

    def __init__(self, pages: dict[str, _PageContactConfig]) -> None:
        self._pages = pages

    @classmethod
    def from_file(cls, path: str | Path) -> SupportContactDirectory:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Support-contact config must have version=1")
        raw_pages = payload.get("pages")
        if not isinstance(raw_pages, dict):
            raise TypeError("Support-contact config requires a pages object")

        pages: dict[str, _PageContactConfig] = {}
        for raw_page_id, raw_page in raw_pages.items():
            page_id = PageCode(str(raw_page_id)).value
            if not isinstance(raw_page, dict):
                raise TypeError(f"Invalid contact config for page {page_id}")

            contacts: dict[str, SupportContact] = {}
            for raw_contact in raw_page.get("contacts", []):
                contact = cls._parse_contact(raw_contact)
                if contact.contact_id in contacts:
                    raise ValueError(
                        f"Duplicate contact id {contact.contact_id!r} for page {page_id}"
                    )
                contacts[contact.contact_id] = contact

            hotline_payload = raw_page.get("hotline")
            hotline = (
                cls._parse_contact(hotline_payload)
                if isinstance(hotline_payload, dict)
                else None
            )
            purposes = raw_page.get("purposes", {})
            workflow_purposes = raw_page.get("workflow_purposes", {})
            request_routing = raw_page.get("request_routing", [])
            if not isinstance(purposes, dict) or not isinstance(workflow_purposes, dict):
                raise TypeError(f"Invalid routing config for page {page_id}")
            if not isinstance(request_routing, list):
                raise TypeError(f"request_routing must be a list for page {page_id}")

            for purpose, route in purposes.items():
                if not isinstance(route, dict):
                    raise TypeError(f"Invalid purpose {purpose!r} for page {page_id}")
                for contact_id in route.get("contact_ids", []):
                    if contact_id not in contacts:
                        raise ValueError(
                            f"Unknown contact id {contact_id!r} in purpose {purpose!r}"
                        )
            for workflow_name, purpose in workflow_purposes.items():
                WorkflowType(str(workflow_name))
                if purpose not in purposes:
                    raise ValueError(
                        f"Unknown purpose {purpose!r} for workflow {workflow_name!r}"
                    )
            for route in request_routing:
                if not isinstance(route, dict) or route.get("purpose") not in purposes:
                    raise ValueError(f"Invalid request route for page {page_id}")
                if not isinstance(route.get("markers", []), list):
                    raise TypeError(
                        f"Request-route markers must be a list for page {page_id}"
                    )

            pages[page_id] = _PageContactConfig(
                contacts=contacts,
                hotline=hotline,
                purposes=purposes,
                workflow_purposes={
                    str(key): str(value) for key, value in workflow_purposes.items()
                },
                request_routing=tuple(request_routing),
            )
        return cls(pages)

    @staticmethod
    def _parse_contact(raw_contact: object) -> SupportContact:
        if not isinstance(raw_contact, dict):
            raise TypeError("Each support contact must be an object")
        contact_id = str(raw_contact.get("id") or "").strip()
        name = str(raw_contact.get("name") or "").strip()
        title = str(raw_contact.get("title") or "").strip()
        phone = normalize_support_phone(str(raw_contact.get("phone") or ""))
        if not contact_id or not name or not title:
            raise ValueError("Support contacts require id, name, title, and phone")
        return SupportContact(contact_id, name, title, phone)

    def select(
        self,
        page_id: PageCode,
        workflow: WorkflowType,
        *,
        customer_key: str,
        customer_text: str = "",
    ) -> SupportContactSelection | None:
        page = self._pages.get(page_id.value)
        if page is None:
            return None

        purpose = page.workflow_purposes.get(workflow.value)
        if purpose is None:
            return None
        if workflow == WorkflowType.CONTACT_SUPPORT:
            folded_text = _fold_text(customer_text)
            for request_route in page.request_routing:
                markers = (
                    _fold_text(str(marker))
                    for marker in request_route.get("markers", [])
                )
                if any(marker and marker in folded_text for marker in markers):
                    purpose = str(request_route["purpose"])
                    break

        route = page.purposes.get(purpose)
        if route is None:
            return None
        candidates = [
            page.contacts[contact_id]
            for contact_id in route.get("contact_ids", [])
            if contact_id in page.contacts
        ]
        primary: SupportContact | None = None
        if candidates:
            seed = f"{page_id.value}:{purpose}:{customer_key or 'anonymous'}"
            digest = hashlib.sha256(seed.encode("utf-8")).digest()
            primary = candidates[int.from_bytes(digest[:8], "big") % len(candidates)]
        hotline = page.hotline if route.get("include_hotline", False) else None
        if primary is None and hotline is None:
            return None
        return SupportContactSelection(
            purpose=purpose,
            label=str(route.get("label") or "Hỗ trợ khách hàng"),
            primary=primary,
            hotline=hotline,
        )

    @staticmethod
    def render(selection: SupportContactSelection) -> str:
        lines: list[str] = []
        if selection.primary:
            lines.append(
                f"☎️ {selection.primary.title} {selection.primary.name}: "
                f"{selection.primary.display_phone}"
            )
        if selection.hotline and (
            selection.primary is None
            or selection.hotline.phone != selection.primary.phone
        ):
            lines.append(
                f"☎️ {selection.hotline.title}: {selection.hotline.display_phone}"
            )
        return "\n".join(lines)

    def allowed_phones(self, page_id: PageCode) -> set[str]:
        page = self._pages.get(page_id.value)
        if page is None:
            return set()
        phones = {contact.phone for contact in page.contacts.values()}
        if page.hotline:
            phones.add(page.hotline.phone)
        return phones
