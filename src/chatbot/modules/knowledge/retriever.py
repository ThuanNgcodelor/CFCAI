"""Page-isolated retrieval over approved knowledge records only."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol

from src.chatbot.core.settings import settings
from src.chatbot.shared.administrative_areas import (
    AdministrativeArea,
    fold_administrative_text,
)
from src.chatbot.shared.enums import PageCode


@dataclass(frozen=True)
class KnowledgeRecord:
    record_id: str
    page_id: PageCode
    title: str
    content: str
    status: str = "QUARANTINED"
    intent: str | None = None
    category: str | None = None
    response_mode: str | None = None
    risk_level: str | None = None
    learning_tags: tuple[str, ...] = ()
    profile_slots: tuple[str, ...] = ()
    source_locator: str | None = None
    audience: str = "customer"
    is_active: bool = True


@dataclass(frozen=True)
class KnowledgeSearchResult:
    """Auditable retrieval outcome; ambiguous results are never used as answers."""

    status: str
    records: tuple[KnowledgeRecord, ...] = ()
    top_score: float = 0.0
    margin: float | None = None
    strategy: str = "faq"


@dataclass(frozen=True)
class DealerCandidate:
    """A dealer record whose visible address passed the lookup evidence gate."""

    record: KnowledgeRecord
    distance_km: float | None = None


@dataclass(frozen=True)
class DealerLookupResult:
    """Explicit outcome used for both reply composition and durable dialogue state."""

    status: str
    area_label: str | None = None
    parent_province: str | None = None
    match_scope: str | None = None
    candidates: tuple[DealerCandidate, ...] = ()

    @property
    def records(self) -> list[KnowledgeRecord]:
        return [candidate.record for candidate in self.candidates]

    def state_slots(self) -> dict[str, str]:
        slots = {"dealer_search_status": self.status}
        if self.area_label:
            slots["dealer_search_area"] = self.area_label
        if self.parent_province:
            slots["dealer_parent_province"] = self.parent_province
        if self.match_scope:
            slots["dealer_match_scope"] = self.match_scope
        return slots


class KnowledgeSearchStore(Protocol):
    def search(
        self,
        page_id: PageCode,
        query: str,
        limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
        intents: tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]: ...


def _fold_search_text(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    folded = folded.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


class KnowledgeRanker:
    """Configuration-backed exact-alias and lexical ranker by data domain."""

    def __init__(self, config_path: str | Path = "config/retrieval/ranking.json") -> None:
        payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self._ignored_queries = {
            _fold_search_text(value)
            for value in payload.get("ignored_query_terms", [])
            if _fold_search_text(value)
        }
        self._stop_words = {
            _fold_search_text(value)
            for value in payload.get("stop_words", [])
            if _fold_search_text(value)
        }
        self._synonyms = {
            _fold_search_text(phrase): tuple(
                _fold_search_text(value)
                for value in values
                if _fold_search_text(value)
            )
            for phrase, values in payload.get("synonyms", {}).items()
        }
        self._strategies = payload.get("strategies", {})
        self._prefix_domains = payload.get("prefix_domains", {})

    def _domain(
        self,
        record_prefix: str | tuple[str, ...] | None,
        categories: tuple[str, ...] | None,
    ) -> str:
        prefixes = (record_prefix,) if isinstance(record_prefix, str) else record_prefix or ()
        for prefix in prefixes:
            for configured_prefix, domain in self._prefix_domains.items():
                if prefix.startswith(configured_prefix):
                    return str(domain)
        if categories and any(category.casefold() in {"agronomy", "soil_weather"} for category in categories):
            return "agronomy"
        return "faq"

    def _tokens(self, text: str) -> set[str]:
        normalized = _fold_search_text(text)
        tokens = {
            token
            for token in normalized.split()
            if len(token) > 1 and token not in self._stop_words
        }
        for phrase, synonyms in self._synonyms.items():
            if re.search(
                rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized
            ):
                for synonym in synonyms:
                    tokens.update(
                        token
                        for token in synonym.split()
                        if len(token) > 1 and token not in self._stop_words
                    )
        return tokens

    @staticmethod
    def _aliases(record: KnowledgeRecord) -> tuple[str, ...]:
        return tuple(
            normalized
            for value in record.title.split("|")
            if (normalized := _fold_search_text(value))
        )

    def rank(
        self,
        records: list[KnowledgeRecord],
        query: str,
        *,
        limit: int,
        record_prefix: str | tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> KnowledgeSearchResult:
        domain = self._domain(record_prefix, categories)
        policy = self._strategies.get(domain, self._strategies["faq"])
        normalized_query = _fold_search_text(query)
        query_tokens = self._tokens(query)
        if (
            not normalized_query
            or normalized_query in self._ignored_queries
            or not query_tokens
        ):
            return KnowledgeSearchResult("NO_MATCH", strategy=domain)

        exact_score = float(policy.get("exact_alias_score", 1.0))
        alias_weight = float(policy.get("alias_weight", 0.8))
        content_weight = float(policy.get("content_weight", 0.2))
        scored: list[tuple[float, bool, KnowledgeRecord]] = []
        for record in records:
            aliases = self._aliases(record)
            exact = normalized_query in aliases
            if exact:
                scored.append((exact_score, True, record))
                continue

            alias_score = 0.0
            for alias in aliases:
                alias_tokens = self._tokens(alias)
                overlap = query_tokens & alias_tokens
                if not overlap:
                    continue
                recall = len(overlap) / len(query_tokens)
                precision = len(overlap) / len(alias_tokens)
                alias_score = max(alias_score, alias_weight * (0.7 * recall + 0.3 * precision))
            content_tokens = self._tokens(record.content)
            content_score = content_weight * len(query_tokens & content_tokens) / len(query_tokens)
            score = max(alias_score, content_score)
            if score > 0:
                scored.append((score, False, record))

        scored.sort(key=lambda item: (-item[0], item[2].record_id))
        if not scored:
            return KnowledgeSearchResult("NO_MATCH", strategy=domain)
        top_score, top_exact, _ = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else None
        margin = top_score - second_score if second_score is not None else None
        minimum = float(policy.get("minimum_score", 0.2))
        minimum_margin = float(policy.get("minimum_margin", 0.08))
        if top_score < minimum:
            return KnowledgeSearchResult("NO_MATCH", top_score=top_score, margin=margin, strategy=domain)
        if not top_exact and margin is not None and margin < minimum_margin:
            return KnowledgeSearchResult(
                "AMBIGUOUS",
                tuple(item[2] for item in scored[:limit]),
                top_score,
                margin,
                domain,
            )
        return KnowledgeSearchResult(
            "CONFIDENT",
            tuple(item[2] for item in scored[:limit]),
            top_score,
            margin,
            domain,
        )


class ApprovedKnowledgeStore:
    def __init__(
        self,
        records: list[KnowledgeRecord] | None = None,
        *,
        ranker: KnowledgeRanker | None = None,
    ) -> None:
        self._records = records or []
        self._ranker = ranker or KnowledgeRanker()

    def add(self, record: KnowledgeRecord) -> None:
        self._records.append(record)

    def search(
        self,
        page_id: PageCode,
        query: str,
        limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
        intents: tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        result = self.search_with_confidence(
            page_id, query, limit=limit, record_prefix=record_prefix,
            intents=intents, categories=categories,
        )
        return list(result.records) if result.status == "CONFIDENT" else []

    def search_with_confidence(
        self,
        page_id: PageCode,
        query: str,
        limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
        intents: tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> KnowledgeSearchResult:
        normalized_intents = {item.casefold() for item in intents or ()}
        normalized_categories = {item.casefold() for item in categories or ()}
        eligible = []
        for record in self._records:
            if (
                record.page_id != page_id
                or record.status != "APPROVED"
                or record.audience != "customer"
                or not record.is_active
            ):
                continue
            if record_prefix and not record.record_id.startswith(record_prefix):
                continue
            if normalized_intents and (record.intent or "").casefold() not in normalized_intents:
                continue
            if normalized_categories and (record.category or "").casefold() not in normalized_categories:
                continue
            eligible.append(record)
        return self._ranker.rank(
            eligible,
            query,
            limit=limit,
            record_prefix=record_prefix,
            categories=categories,
        )


class PostgresKnowledgeStore:
    _schema = """
    CREATE TABLE IF NOT EXISTS knowledge_records (
        record_id TEXT PRIMARY KEY, page_id TEXT NOT NULL, title TEXT NOT NULL,
        content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'QUARANTINED',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_knowledge_page_status ON knowledge_records(page_id, status);
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS source_batch_id TEXT;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS audience TEXT NOT NULL DEFAULT 'customer';
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS source_locator TEXT;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS intent TEXT;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS category TEXT;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS response_mode TEXT;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS risk_level TEXT;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS learning_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE knowledge_records ADD COLUMN IF NOT EXISTS profile_slots JSONB NOT NULL DEFAULT '[]'::jsonb;
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        ranker: KnowledgeRanker | None = None,
    ) -> None:
        self._dsn = (database_url or settings.get_database_url()).replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
        self._ready = False
        self._ranker = ranker or KnowledgeRanker()

    def _connect(self):
        import psycopg2  # type: ignore[import-untyped]

        return psycopg2.connect(self._dsn)

    def _ensure_schema(self) -> None:
        if not self._ready:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(self._schema)
            self._ready = True

    def add(self, record: KnowledgeRecord) -> None:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_records(
                    record_id,page_id,title,content,status,audience,is_active
                ) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(record_id) DO UPDATE SET
                title=EXCLUDED.title, content=EXCLUDED.content, status=EXCLUDED.status,
                audience=EXCLUDED.audience, is_active=EXCLUDED.is_active""",
                (
                    record.record_id,
                    record.page_id.value,
                    record.title,
                    record.content,
                    record.status,
                    record.audience,
                    record.is_active,
                ),
            )

    def approve(self, record_id: str) -> bool:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_records SET status='APPROVED' WHERE record_id=%s",
                (record_id,),
            )
            return cursor.rowcount == 1

    def approve_page(self, page_id: PageCode) -> int:
        self._ensure_schema()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_records SET status='APPROVED' WHERE page_id=%s",
                (page_id.value,),
            )
            return cursor.rowcount

    def search(
        self,
        page_id: PageCode,
        query: str,
        limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
        intents: tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        self._ensure_schema()
        prefix_values = None
        if record_prefix:
            prefix_values = (record_prefix,) if isinstance(record_prefix, str) else record_prefix
        with self._connect() as connection, connection.cursor() as cursor:
            sql = "SELECT record_id,page_id,title,content,status,intent,category,response_mode,risk_level,learning_tags,profile_slots,source_locator FROM knowledge_records WHERE page_id=%s AND status='APPROVED' AND audience='customer' AND is_active=true"
            params: list[object] = [page_id.value]
            if prefix_values:
                sql += " AND (" + " OR ".join("record_id LIKE %s" for _ in prefix_values) + ")"
                params.extend(f"{prefix}%" for prefix in prefix_values)
            if intents:
                sql += " AND lower(intent) = ANY(%s)"
                params.append([item.casefold() for item in intents])
            if categories:
                sql += " AND lower(category) = ANY(%s)"
                params.append([item.casefold() for item in categories])
            cursor.execute(sql, tuple(params))
            records = [
                KnowledgeRecord(
                    row[0], PageCode(row[1]), row[2], row[3], row[4],
                    row[5], row[6], row[7], row[8], tuple(row[9] or ()),
                    tuple(row[10] or ()), row[11],
                )
                for row in cursor.fetchall()
            ]
        return list(self._ranker.rank(
            records,
            query,
            limit=limit,
            record_prefix=record_prefix,
            categories=categories,
        ).records)


class RedisCrmProductStore:
    """Read the approved CRM product snapshot without exposing prices."""

    def __init__(self, redis_url: str | None = None) -> None:
        # pyrefly: ignore[missing-import]
        import redis

        self._redis = redis.Redis.from_url(
            redis_url or settings.get_redis_url(), decode_responses=True
        )

    def search(
        self, page_id: PageCode, query: str, limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
        intents: tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        if page_id != PageCode.CFC or record_prefix and not (
            "crm-product:" in record_prefix if isinstance(record_prefix, tuple) else record_prefix == "crm-product:"
        ):
            return []
        raw = self._redis.get("cfc:products:catalog")
        if not raw:
            return []
        import json

        tokens = [token for token in query.lower().split() if len(token) > 1]
        records = []
        for item in json.loads(raw):
            name = str(item.get("name") or "")
            haystack = f"{name} {item.get('code') or ''}".lower()
            score = sum(token in haystack for token in tokens)
            if score:
                records.append((score, KnowledgeRecord(
                    f"crm-product:{item.get('code') or name}", page_id, name,
                    f"{name} | Mã sản phẩm: {item.get('code') or 'chưa có'} | Đơn vị: {item.get('unit') or 'chưa cập nhật'}",
                    "APPROVED",
                )))
        records.sort(key=lambda item: (-item[0], item[1].record_id))
        return [record for _, record in records[:limit]]


class RedisCrmDealerStore:
    """Resolve dealers from the CRM snapshot using geographic evidence only.

    A province-level text hit is not proof that a dealer is nearest to a
    district.  This store therefore returns an explicit no-match result until
    an exact administrative address match or a GPS distance comparison exists.
    """

    _MISSING_ADDRESS_VALUES: ClassVar[frozenset[str]] = frozenset(
        fold_administrative_text(value)
        for value in ("chưa cập nhật địa chỉ", "chưa cập nhật", "null", "none")
    )

    def __init__(self, redis_url: str | None = None) -> None:
        # pyrefly: ignore[missing-import]
        import redis

        self._redis = redis.Redis.from_url(redis_url or settings.get_redis_url(), decode_responses=True)

    @staticmethod
    def _coordinates(item: dict[str, Any]) -> tuple[float, float] | None:
        def number(*keys: str) -> float | None:
            for key in keys:
                value = item.get(key)
                if value in (None, ""):
                    continue
                try:
                    candidate = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(candidate):
                    return candidate
            return None

        latitude = number("latitude", "lat")
        longitude = number("longitude", "lng", "lon")
        if latitude is None or longitude is None:
            return None
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return None
        return latitude, longitude

    @classmethod
    def _valid_address(cls, value: Any) -> str | None:
        address = str(value or "").strip()
        if not address or fold_administrative_text(address) in cls._MISSING_ADDRESS_VALUES:
            return None
        return address

    @staticmethod
    def _location_evidence(item: dict[str, Any], address: str) -> str:
        """Use CRM location fields, never a dealer name, as geographic proof."""
        location_fields = (
            "province",
            "province_name",
            "district",
            "district_name",
            "ward",
            "ward_name",
            "commune",
            "commune_name",
            "city",
            "city_name",
        )
        values = [address]
        values.extend(str(item.get(field) or "") for field in location_fields)
        return fold_administrative_text(" ".join(values))

    @staticmethod
    def _has_alias(text: str, aliases: tuple[str, ...]) -> bool:
        for alias in aliases:
            normalized = fold_administrative_text(alias)
            if normalized and re.search(
                rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text
            ):
                return True
        return False

    @staticmethod
    def _distance_km(
        origin: tuple[float, float], destination: tuple[float, float]
    ) -> float:
        origin_lat, origin_lon = map(math.radians, origin)
        destination_lat, destination_lon = map(math.radians, destination)
        distance_lat = destination_lat - origin_lat
        distance_lon = destination_lon - origin_lon
        a = (
            math.sin(distance_lat / 2) ** 2
            + math.cos(origin_lat)
            * math.cos(destination_lat)
            * math.sin(distance_lon / 2) ** 2
        )
        return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _record(item: dict[str, Any], address: str) -> KnowledgeRecord | None:
        name = str(item.get("name") or item.get("account_name") or "").strip()
        if not name:
            return None
        identifier = str(
            item.get("code") or item.get("account_code") or item.get("account_id") or ""
        ).strip()
        if not identifier:
            identifier = hashlib.sha256(
                f"{fold_administrative_text(name)}|{fold_administrative_text(address)}".encode()
            ).hexdigest()[:16]
        return KnowledgeRecord(
            record_id=f"dealer:{identifier}",
            page_id=PageCode.CFC,
            title=name,
            content=f"{name} — {address}",
            status="APPROVED",
        )

    def _load_candidates(
        self,
    ) -> list[tuple[dict[str, Any], KnowledgeRecord, tuple[float, float] | None, str]]:
        raw = self._redis.get("cfc:dealers:locations")
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        candidates = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            address = self._valid_address(item.get("address") or item.get("billing_address"))
            if not address:
                # A GPS-only CRM row is insufficient for a customer-facing
                # address result when the reply intentionally has no map link.
                continue
            record = self._record(item, address)
            if not record:
                continue
            candidates.append(
                (
                    item,
                    record,
                    self._coordinates(item),
                    self._location_evidence(item, address),
                )
            )
        return candidates

    @staticmethod
    def _ordered_candidates(
        candidates: list[tuple[dict[str, Any], KnowledgeRecord, tuple[float, float] | None, str]],
        *,
        origin: tuple[float, float] | None = None,
        require_coordinates: bool = False,
        limit: int,
    ) -> tuple[DealerCandidate, ...]:
        ordered: list[DealerCandidate] = []
        for _, record, coordinates, _ in candidates:
            if require_coordinates and coordinates is None:
                continue
            distance = (
                RedisCrmDealerStore._distance_km(origin, coordinates)
                if origin is not None and coordinates is not None
                else None
            )
            ordered.append(DealerCandidate(record=record, distance_km=distance))
        ordered.sort(
            key=lambda candidate: (
                candidate.distance_km is None,
                candidate.distance_km if candidate.distance_km is not None else math.inf,
                candidate.record.title.casefold(),
                candidate.record.record_id,
            )
        )
        return tuple(ordered[:limit])

    def resolve_dealers(
        self,
        page_id: PageCode,
        location: str | None,
        *,
        area: AdministrativeArea | None = None,
        limit: int = 3,
    ) -> DealerLookupResult:
        """Find up to three dealers backed by exact address or GPS evidence."""
        limit = max(1, min(int(limit), 3))
        requested_location = str(location or "").strip()
        area_label = area.canonical if area else requested_location or None
        parent_province = (
            area.parent_province
            if area and area.level != "province"
            else (area.canonical if area else None)
        )
        if not requested_location and area is None:
            return DealerLookupResult(status="LOCATION_REQUIRED")
        if page_id != PageCode.CFC:
            return DealerLookupResult(
                status="NO_CONFIRMED_MATCH",
                area_label=area_label,
                parent_province=parent_province,
            )

        candidates = self._load_candidates()
        if not candidates:
            return DealerLookupResult(
                status="NO_CONFIRMED_MATCH",
                area_label=area_label,
                parent_province=parent_province,
            )

        if area:
            exact_matches = [
                candidate
                for candidate in candidates
                if self._has_alias(candidate[3], area.aliases)
            ]
            exact_result = self._ordered_candidates(
                exact_matches,
                origin=(area.latitude, area.longitude) if area.has_coordinates else None,
                limit=limit,
            )
            if exact_result:
                return DealerLookupResult(
                    status="CONFIRMED_MATCH",
                    area_label=area.canonical,
                    parent_province=parent_province,
                    match_scope=(
                        "PROVINCE" if area.level == "province" else "EXACT_ADMIN_AREA"
                    ),
                    candidates=exact_result,
                )

            if area.level == "province":
                return DealerLookupResult(
                    status="NO_CONFIRMED_MATCH",
                    area_label=area.canonical,
                    parent_province=area.canonical,
                )

            # A district/ward may fall back to parent-province results only
            # where both the requested area and CRM dealer have coordinates.
            if area.parent_province and area.has_coordinates:
                province_matches = [
                    candidate
                    for candidate in candidates
                    if self._has_alias(candidate[3], (area.parent_province,))
                ]
                gps_result = self._ordered_candidates(
                    province_matches,
                    origin=(area.latitude, area.longitude),
                    require_coordinates=True,
                    limit=limit,
                )
                if gps_result:
                    return DealerLookupResult(
                        status="CONFIRMED_MATCH",
                        area_label=area.canonical,
                        parent_province=area.parent_province,
                        match_scope="GPS_DISTANCE",
                        candidates=gps_result,
                    )

            return DealerLookupResult(
                status="NO_CONFIRMED_MATCH",
                area_label=area.canonical,
                parent_province=area.parent_province,
            )

        # An unrecognised locality may still match a literal CRM address.  It
        # never gets a parent-province or "nearest" fallback automatically.
        raw_matches = [
            candidate
            for candidate in candidates
            if self._has_alias(candidate[3], (requested_location,))
        ]
        raw_result = self._ordered_candidates(raw_matches, limit=limit)
        if raw_result:
            return DealerLookupResult(
                status="CONFIRMED_MATCH",
                area_label=requested_location,
                match_scope="EXACT_ADDRESS_TEXT",
                candidates=raw_result,
            )
        return DealerLookupResult(
            status="NO_CONFIRMED_MATCH",
            area_label=requested_location,
        )

    def search(
        self, page_id: PageCode, query: str, limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
        intents: tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        allowed = record_prefix is None or ("dealer:" in record_prefix if isinstance(record_prefix, tuple) else record_prefix == "dealer:")
        if not allowed:
            return []
        return self.resolve_dealers(page_id, query, limit=limit).records


class RedisCrmOrderStore:
    def __init__(self, redis_url: str | None = None) -> None:
        # pyrefly: ignore[missing-import]
        import redis

        self._redis = redis.Redis.from_url(
            redis_url or settings.get_redis_url(), decode_responses=True
        )

    def find_by_phone(self, phone: str) -> list[dict[str, Any]]:
        import json
        import re

        clean_phone = re.sub(r"\D", "", phone)
        if clean_phone.startswith("84"):
            clean_phone = "0" + clean_phone[2:]
        raw = self._redis.get(f"cfc:orders:phone:{clean_phone}")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def find_by_code(self, order_code: str) -> dict[str, Any] | None:
        import json

        clean_code = order_code.strip().upper()
        raw = self._redis.get(f"cfc:orders:code:{clean_code}")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        return None


class CompositeKnowledgeStore:
    def __init__(self, *stores: KnowledgeSearchStore) -> None:
        self.stores = stores

    def search(
        self, page_id: PageCode, query: str, limit: int = 5,
        record_prefix: str | tuple[str, ...] | None = None,
        intents: tuple[str, ...] | None = None,
        categories: tuple[str, ...] | None = None,
    ) -> list[KnowledgeRecord]:
        matches: list[KnowledgeRecord] = []
        for store in self.stores:
            matches.extend(
                store.search(
                    page_id, query, limit, record_prefix,
                    intents=intents, categories=categories,
                )
            )
        return matches[:limit]

    def resolve_dealers(
        self,
        page_id: PageCode,
        location: str | None,
        *,
        area: AdministrativeArea | None = None,
        limit: int = 3,
    ) -> DealerLookupResult:
        """Delegate to the CRM-backed resolver without crossing page scope."""
        fallback = DealerLookupResult(
            status="LOCATION_REQUIRED" if not str(location or "").strip() and area is None else "NO_CONFIRMED_MATCH",
            area_label=area.canonical if area else str(location or "").strip() or None,
            parent_province=(
                area.parent_province
                if area and area.level != "province"
                else (area.canonical if area else None)
            ),
        )
        for store in self.stores:
            resolver = getattr(store, "resolve_dealers", None)
            if not callable(resolver):
                continue
            result = resolver(page_id, location, area=area, limit=limit)
            if result.status == "CONFIRMED_MATCH":
                return result
            fallback = result
        return fallback
