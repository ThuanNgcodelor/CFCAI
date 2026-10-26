"""Hybrid deterministic-safety and Ollama understanding layer."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from src.chatbot.modules.llm.ollama import OllamaUnderstandingError
from src.chatbot.shared.enums import (
    IntentTransition,
    IntentType,
    PageCode,
    WorkflowType,
)
from src.chatbot.shared.events import IntentAnalysisResult


class StructuredIntentClient(Protocol):
    def analyze(
        self, page_id: str, text: str, context: dict[str, Any] | None = None
    ) -> IntentAnalysisResult: ...


class VietnameseNormalizer:
    def __init__(self, config_path: str | Path) -> None:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.aliases: dict[str, str] = config.get("aliases", {})
        self.safety: dict[str, list[str]] = config.get("safety", {})
        units = [re.escape(unit) for unit in config.get("quantity_units", [])]
        self.quantity_pattern = re.compile(
            rf"(?P<quantity>\d+(?:[.,]\d+)?)\s*(?P<unit>{'|'.join(units)})\b",
            re.IGNORECASE,
        ) if units else None

    def normalize(self, text: str) -> str:
        # Separate dots/underscores between alphanumeric characters (e.g. gia.bao.nhieu1bao -> gia bao nhieu1bao)
        cleaned = re.sub(r"(?<=[a-zA-Z0-9À-ỹ])[._]+(?=[a-zA-Z0-9À-ỹ])", " ", text)
        # Separate letters glued to numbers (e.g. nhieu1 -> nhieu 1, 1bao -> 1 bao)
        cleaned = re.sub(r"(?<=[a-zA-ZÀ-ỹ])(?=\d)|(?<=\d)(?=[a-zA-ZÀ-ỹ])", " ", cleaned)
        normalized = unicodedata.normalize("NFKC", cleaned).casefold()
        normalized = re.sub(r"\s+", " ", normalized).strip()
        for alias, replacement in self.aliases.items():
            normalized = re.sub(
                rf"(?<!\w){re.escape(alias.casefold())}(?!\w)",
                replacement.casefold(),
                normalized,
            )
        return normalized

    def contains(self, group: str, text: str) -> bool:
        return any(marker.casefold() in text for marker in self.safety.get(group, []))

    def deterministic_slots(self, text: str) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        if self.quantity_pattern:
            match = self.quantity_pattern.search(text)
            if match:
                slots["quantity"] = match.group("quantity").replace(",", ".")
                slots["unit"] = match.group("unit")
        formulas = re.findall(r"\b\d{1,3}(?:\s*[-.]\s*\d{1,3}){1,3}\b", text)
        if formulas:
            slots["detected_formulas"] = [re.sub(r"\s+", "", item) for item in formulas]
        # Extract Vietnamese mobile/landline phone
        phone_match = re.search(r"(?:\+?84|0)(?:[\s.\-]?\d){9,10}(?!\d)", text)
        if phone_match:
            digits = re.sub(r"\D", "", phone_match.group(0))
            if digits.startswith("84"):
                digits = "0" + digits[2:]
            if re.match(r"^0[235789]\d{8}$|^02\d{9}$", digits):
                slots["phone"] = digits

        # Extract Order Code if present
        order_pat = re.compile(
            r"\b(?:đơn\s*hàng|đơn|mã\s*đơn|mã|don\s*hang|don|ma\s*don|ma)\s*[:#\-]?\s*([A-Za-z0-9_-]{3,20})\b",
            re.IGNORECASE,
        )
        m = order_pat.search(text)
        if m:
            extracted = m.group(1).strip()
            if extracted != slots.get("phone"):
                slots["order_code"] = extracted
        if not slots.get("order_code"):
            standalone = re.search(r"\b(?:[A-Za-z]{2,6}[0-9\-_]{2,12}|00\d{4,8})\b", text)
            if standalone and standalone.group(0) != slots.get("phone"):
                slots["order_code"] = standalone.group(0)

        return slots


class HybridInputAnalyzer:
    def __init__(self, client: StructuredIntentClient, normalizer: VietnameseNormalizer) -> None:
        self.client = client
        self.normalizer = normalizer

    def analyze(
        self,
        page_id: PageCode,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> IntentAnalysisResult:
        normalized = self.normalizer.normalize(text)
        context = context or {}
        forced_intent: IntentType | None = None
        transition = IntentTransition.START
        current_intent = context.get("current_intent")

        if self.normalizer.contains("price_markers", normalized):
            forced_intent = IntentType.PRICE_INQUIRY
            transition = (
                IntentTransition.CONTINUE
                if current_intent in {
                    IntentType.PRICE_INQUIRY.value,
                    IntentType.PRICE_INQUIRY_DETAIL.value,
                }
                else IntentTransition.SWITCH if current_intent else IntentTransition.START
            )
        elif self.normalizer.contains("human_markers", normalized):
            forced_intent = IntentType.HUMAN_REQUEST
            transition = IntentTransition.SWITCH if current_intent else IntentTransition.START
        elif self.normalizer.contains("dealer_markers", normalized):
            forced_intent = IntentType.DEALER_LOOKUP
            transition = IntentTransition.SWITCH if current_intent else IntentTransition.START
        elif self.normalizer.contains("order_markers", normalized):
            forced_intent = IntentType.ORDER_TRACKING
            transition = IntentTransition.SWITCH if current_intent else IntentTransition.START

        is_open_price_context = current_intent in {
            IntentType.PRICE_INQUIRY.value,
            IntentType.PRICE_INQUIRY_DETAIL.value,
        }

        deterministic_slots = self.normalizer.deterministic_slots(normalized)
        try:
            result = self.client.analyze(page_id.value, normalized, context)
        except (OllamaUnderstandingError, OSError, ValueError, KeyError, TypeError):
            if forced_intent:
                fallback_intent = forced_intent
                fallback_trans = transition
            elif is_open_price_context and not self.normalizer.contains("explicit_advice_markers", normalized):
                fallback_intent = IntentType.PRICE_INQUIRY_DETAIL
                fallback_trans = IntentTransition.CONTINUE
            else:
                fallback_intent = IntentType.UNKNOWN
                fallback_trans = IntentTransition.UNCLEAR

            return IntentAnalysisResult(
                primary_intent=fallback_intent,
                intent_transition=fallback_trans,
                extracted_slots=deterministic_slots,
                quantity=deterministic_slots.get("quantity"),
                unit=deterministic_slots.get("unit"),
                needs_clarification=forced_intent is None,
                clarification_needed=forced_intent is None,
                requires_human_handoff=fallback_intent
                in {
                    IntentType.PRICE_INQUIRY,
                    IntentType.PRICE_INQUIRY_DETAIL,
                    IntentType.HUMAN_REQUEST,
                    IntentType.UNKNOWN,
                },
                evidence_message_ids=list(context.get("message_ids", [])),
            )

        merged_slots = {**context.get("current_slots", {}), **result.extracted_slots, **deterministic_slots}
        if result.quantity:
            merged_slots["quantity"] = result.quantity
        if result.unit:
            merged_slots["unit"] = result.unit
        if result.location:
            merged_slots["location"] = result.location
        if result.crop:
            merged_slots["crop"] = result.crop
        if result.stage:
            merged_slots["stage"] = result.stage
        if result.problem:
            merged_slots["problem"] = result.problem
        if result.product_mentions:
            merged_slots["product_mentions"] = result.product_mentions
        if result.detected_skus:
            merged_slots["detected_skus"] = result.detected_skus
        result.extracted_slots = merged_slots

        if forced_intent:
            result.primary_intent = forced_intent
            result.intent_transition = transition
        elif is_open_price_context:
            # If model identified a distinct switch to a new domain workflow, honor the switch
            if result.primary_intent in {
                IntentType.DEALER_LOOKUP,
                IntentType.ORDER_TRACKING,
                IntentType.PRODUCT_INQUIRY,
                IntentType.HUMAN_REQUEST,
            }:
                result.intent_transition = IntentTransition.SWITCH
            elif result.primary_intent == IntentType.AGRI_ADVICE and not self.normalizer.contains("explicit_advice_markers", normalized):
                # Short follow-ups like "rải mít" in a price workflow are context details, not standalone advice
                result.primary_intent = IntentType.PRICE_INQUIRY_DETAIL
                result.intent_transition = IntentTransition.CONTINUE
            elif result.primary_intent in {IntentType.UNKNOWN, IntentType.GENERAL_FAQ}:
                result.primary_intent = IntentType.PRICE_INQUIRY_DETAIL
                result.intent_transition = IntentTransition.CONTINUE

        if result.primary_intent in {
            IntentType.PRICE_INQUIRY,
            IntentType.PRICE_INQUIRY_DETAIL,
            IntentType.HUMAN_REQUEST,
        }:
            result.requires_human_handoff = True
        return result


def workflow_for_intent(intent: IntentType) -> WorkflowType:
    return {
        IntentType.PRICE_INQUIRY: WorkflowType.PRICE_HANDOFF,
        IntentType.PRICE_INQUIRY_DETAIL: WorkflowType.PRICE_HANDOFF,
        IntentType.DEALER_LOOKUP: WorkflowType.DEALER_LOOKUP,
        IntentType.PRODUCT_INQUIRY: WorkflowType.PRODUCT_INQUIRY,
        IntentType.ORDER_TRACKING: WorkflowType.ORDER_TRACKING,
        IntentType.AGRI_ADVICE: WorkflowType.AGRICULTURE_ADVICE,
        IntentType.SALES_LEAD: WorkflowType.SALES_LEAD,
        IntentType.HUMAN_REQUEST: WorkflowType.HUMAN_REQUEST,
        IntentType.GENERAL_FAQ: WorkflowType.FAQ_ANSWER,
        IntentType.UNKNOWN: WorkflowType.FALLBACK,
    }[intent]
