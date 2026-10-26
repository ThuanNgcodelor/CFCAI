"""Hybrid deterministic-safety and Ollama understanding layer."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from src.chatbot.modules.llm.ollama import OllamaUnderstandingError
from src.chatbot.shared.administrative_areas import (
    AdministrativeArea,
    AdministrativeAreaResolver,
    fold_administrative_text,
)
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
    def __init__(
        self,
        config_path: str | Path,
        administrative_areas_path: str | Path | None = None,
    ) -> None:
        config_file = Path(config_path)
        config = json.loads(config_file.read_text(encoding="utf-8"))
        self.aliases: dict[str, str] = config.get("aliases", {})
        self.safety: dict[str, list[str]] = config.get("safety", {})
        self.knowledge_filters: dict[str, dict[str, list[str]]] = config.get(
            "knowledge_filters", {}
        )
        self.contextual_continuation: dict[str, dict[str, Any]] = config.get(
            "contextual_continuation", {}
        )
        self.cross_workflow_slots = tuple(config.get("cross_workflow_slots", []))
        self.location_aliases: dict[str, str] = {}
        fallback_provinces: list[AdministrativeArea] = []
        for entry in config.get("locations", []):
            canonical = str(entry.get("canonical") or "").strip()
            if not canonical:
                continue
            aliases = [canonical, *(str(alias) for alias in entry.get("aliases", []))]
            for alias in aliases:
                self.location_aliases[self._fold_diacritics(alias)] = canonical
            fallback_provinces.append(
                AdministrativeArea(
                    area_id=f"province-{fold_administrative_text(canonical).replace(' ', '-')}",
                    canonical=canonical,
                    level="province",
                    aliases=tuple(aliases),
                )
            )
        source_path = (
            Path(administrative_areas_path)
            if administrative_areas_path is not None
            else config_file.with_name("administrative_areas.json")
        )
        self.area_resolver = AdministrativeAreaResolver.from_file(
            source_path,
            fallback_areas=fallback_provinces,
        )
        location_patterns = sorted(self.location_aliases, key=len, reverse=True)
        self.location_pattern = (
            re.compile(
                rf"(?<!\w)(?:{'|'.join(re.escape(alias) for alias in location_patterns)})(?!\w)",
                re.IGNORECASE,
            )
            if location_patterns
            else None
        )
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

    @staticmethod
    def _fold_diacritics(text: str) -> str:
        folded = unicodedata.normalize("NFD", text.casefold())
        folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
        return folded.replace("đ", "d")

    def contains(self, group: str, text: str) -> bool:
        return any(marker.casefold() in text for marker in self.safety.get(group, []))

    def filters_for_workflow(self, workflow: WorkflowType) -> dict[str, tuple[str, ...]]:
        """Return source-configured retrieval filters, never business answers."""
        config = self.knowledge_filters.get(workflow.value, {})
        intents = tuple(config.get("intents", []))
        prefixes = tuple(config.get("intent_prefixes", []))
        categories = tuple(config.get("categories", []))
        # Prefixes are expanded by the caller only when the store supports it;
        # keeping the source values here makes the mapping data-driven.
        return {
            "intents": intents,
            "intent_prefixes": prefixes,
            "categories": categories,
        }

    def resolve_location(
        self,
        value: str | None,
        *,
        parent_province: str | None = None,
    ) -> AdministrativeArea | None:
        """Resolve user or model location text through the configured gazetteer."""
        return self.area_resolver.resolve(value, parent_province=parent_province)

    def without_location_alias(
        self, text: str, area: AdministrativeArea | None
    ) -> str:
        """Mask the resolved place name before checking lexical intent markers."""
        if area is None:
            return text
        result = text
        aliases = sorted(area.aliases or (area.canonical,), key=len, reverse=True)
        for alias in aliases:
            normalized_alias = self.normalize(alias)
            result = re.sub(
                rf"(?<!\w){re.escape(normalized_alias)}(?!\w)",
                " ",
                result,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", result).strip()

    def continuation_intent(
        self,
        current_intent: object,
        model_intent: IntentType | None = None,
    ) -> IntentType | None:
        """Return a configured workflow continuation, never a content answer."""
        current = str(
            current_intent.value if isinstance(current_intent, IntentType) else current_intent or ""
        )
        rule = self.contextual_continuation.get(current)
        if not isinstance(rule, dict):
            return None
        if model_intent is None:
            should_retain = bool(rule.get("retain_when_model_unavailable"))
        else:
            retained_intents = {
                str(value) for value in rule.get("retain_on_model_intents", [])
            }
            should_retain = model_intent.value in retained_intents
        if not should_retain:
            return None
        try:
            return IntentType(current)
        except ValueError:
            return None

    def deterministic_slots(self, text: str) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        # Generic linguistic extraction, not a crop/product dictionary: the
        # value is copied from the customer and remains subject to workflow
        # confidence/retrieval checks.
        crop_match = re.search(
            r"\b(?:cây|vườn)\s+([^,.!?;\n]{1,40}?)(?=\s+(?:ở|vào|giai|giải)\b|$)",
            text,
            re.IGNORECASE,
        )
        if crop_match:
            crop = re.sub(r"\s+", " ", crop_match.group(1)).strip(" -:")
            crop = re.sub(r"^(?:đang|bị|mình|nhà)\s+", "", crop, flags=re.IGNORECASE)
            if crop and crop.casefold() not in {"gì", "gi", "nào", "nao", "trồng"}:
                slots["crop"] = crop
        elif action_crop_match := re.search(
            r"\b(?:bón|rải|phun|tưới)\s+(?:cho\s+)?(?:cây\s+)?([^,.!?;\n]{1,40})",
            text,
            re.IGNORECASE,
        ):
            crop = re.sub(r"\s+", " ", action_crop_match.group(1)).strip(" -:")
            if crop:
                slots["crop"] = crop
        stage_match = re.search(
            r"\b(?:giai|giải)\s*đoạn\s+([^,.!?;\n]{1,60})",
            text,
            re.IGNORECASE,
        )
        if stage_match:
            slots["stage"] = re.sub(r"\s+", " ", stage_match.group(1)).strip(" -:")
        location_area = self.resolve_location(text)
        if location_area:
            slots.update(location_area.slots())
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
        deterministic_slots = self.normalizer.deterministic_slots(normalized)
        resolved_area = self.normalizer.resolve_location(normalized)
        marker_text = self.normalizer.without_location_alias(normalized, resolved_area)
        is_open_price_context = current_intent in {
            IntentType.PRICE_INQUIRY.value,
            IntentType.PRICE_INQUIRY_DETAIL.value,
        }
        is_open_dealer_context = current_intent in {
            IntentType.DEALER_LOOKUP.value,
            WorkflowType.DEALER_LOOKUP.value,
        }

        if self.normalizer.contains("price_markers", marker_text):
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
        elif self.normalizer.contains("contact_markers", normalized):
            if current_intent in {
                IntentType.PRICE_INQUIRY.value,
                IntentType.PRICE_INQUIRY_DETAIL.value,
            }:
                forced_intent = IntentType.PRICE_INQUIRY_DETAIL
                transition = IntentTransition.CONTINUE
            else:
                forced_intent = IntentType.CONTACT_REQUEST
                transition = (
                    IntentTransition.SWITCH
                    if current_intent
                    else IntentTransition.START
                )
        elif self.normalizer.contains("dealer_markers", normalized):
            forced_intent = IntentType.DEALER_LOOKUP
            transition = IntentTransition.SWITCH if current_intent else IntentTransition.START
        elif self.normalizer.contains("order_markers", normalized):
            forced_intent = IntentType.ORDER_TRACKING
            transition = IntentTransition.SWITCH if current_intent else IntentTransition.START
        elif self.normalizer.contains("product_markers", normalized) and not self.normalizer.contains("price_markers", normalized):
            forced_intent = IntentType.PRODUCT_INQUIRY
            transition = IntentTransition.SWITCH if current_intent else IntentTransition.START

        # Advice markers are configuration-driven. They outrank a generic FAQ
        # result, but an open price workflow is retained unless the customer
        # explicitly asks for usage guidance.
        if (
            forced_intent is None
            and (
                self.normalizer.contains("explicit_advice_markers", normalized)
                or self.normalizer.contains("advice_action_markers", normalized)
            )
        ):
            forced_intent = IntentType.AGRI_ADVICE
            transition = IntentTransition.SWITCH if current_intent else IntentTransition.START

        if (
            forced_intent is None
            and (deterministic_slots.get("location") or deterministic_slots.get("phone"))
            and is_open_dealer_context
        ):
            forced_intent = IntentType.DEALER_LOOKUP
            transition = IntentTransition.CONTINUE
        try:
            result = self.client.analyze(page_id.value, normalized, context)
        except (OllamaUnderstandingError, OSError, ValueError, KeyError, TypeError):
            if forced_intent:
                fallback_intent = forced_intent
                fallback_trans = transition
            elif continuation_intent := self.normalizer.continuation_intent(current_intent):
                fallback_intent = continuation_intent
                fallback_trans = IntentTransition.CONTINUE
            elif is_open_price_context and not self.normalizer.contains("explicit_advice_markers", normalized):
                fallback_intent = IntentType.PRICE_INQUIRY_DETAIL
                fallback_trans = IntentTransition.CONTINUE
            else:
                fallback_intent = IntentType.UNKNOWN
                fallback_trans = IntentTransition.UNCLEAR

            fallback_slots = dict(deterministic_slots)
            if fallback_trans == IntentTransition.CONTINUE:
                fallback_slots = {
                    **context.get("current_slots", {}),
                    **fallback_slots,
                }
            return IntentAnalysisResult(
                primary_intent=fallback_intent,
                intent_transition=fallback_trans,
                extracted_slots=fallback_slots,
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

        if forced_intent is None:
            continuation_intent = self.normalizer.continuation_intent(
                current_intent,
                result.primary_intent,
            )
            if continuation_intent:
                result.primary_intent = continuation_intent
                result.intent_transition = IntentTransition.CONTINUE

        if forced_intent:
            result.primary_intent = forced_intent
            result.intent_transition = transition
        elif is_open_price_context:
            if result.primary_intent in {
                IntentType.DEALER_LOOKUP,
                IntentType.ORDER_TRACKING,
                IntentType.PRODUCT_INQUIRY,
                IntentType.HUMAN_REQUEST,
                IntentType.CONTACT_REQUEST,
                IntentType.AGRI_ADVICE,
            }:
                result.intent_transition = IntentTransition.SWITCH
            elif result.primary_intent in {IntentType.UNKNOWN, IntentType.GENERAL_FAQ}:
                result.primary_intent = IntentType.PRICE_INQUIRY_DETAIL
                result.intent_transition = IntentTransition.CONTINUE

        slot_sources = [result.extracted_slots, deterministic_slots]
        if result.intent_transition != IntentTransition.SWITCH:
            slot_sources.insert(0, context.get("current_slots", {}))
        else:
            transferable = {
                key: value
                for key, value in context.get("current_slots", {}).items()
                if key in self.normalizer.cross_workflow_slots
            }
            slot_sources.insert(0, transferable)
        merged_slots = {
            key: value
            for source in slot_sources
            for key, value in source.items()
            if value is not None and value != ""
        }
        if result.quantity:
            merged_slots["quantity"] = result.quantity
        if result.unit:
            merged_slots["unit"] = result.unit
        if not deterministic_slots.get("location"):
            model_location = result.location or merged_slots.get("location")
            model_parent = result.extracted_slots.get("province") or merged_slots.get("province")
            resolved_model_location = self.normalizer.resolve_location(
                str(model_location) if model_location else None,
                parent_province=str(model_parent) if model_parent else None,
            )
            if resolved_model_location:
                merged_slots.update(resolved_model_location.slots())
            elif result.location:
                # Preserve the raw customer/model location for an exact CRM
                # address match, but do not invent province/district hierarchy.
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
        IntentType.CONTACT_REQUEST: WorkflowType.CONTACT_SUPPORT,
        IntentType.GENERAL_FAQ: WorkflowType.FAQ_ANSWER,
        IntentType.UNKNOWN: WorkflowType.FALLBACK,
    }[intent]
