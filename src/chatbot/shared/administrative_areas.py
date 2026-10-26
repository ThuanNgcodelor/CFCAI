"""Configuration-backed Vietnamese administrative-area resolution.

The chatbot must not guess a parent province or a nearby dealer from an
unstructured place name.  This module turns a maintained administrative data
source into explicit, auditable slots that the dealer workflow can use.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def fold_administrative_text(value: str) -> str:
    """Case-fold Vietnamese text while keeping matching independent of accents."""
    folded = unicodedata.normalize("NFD", value.casefold())
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", folded.replace("đ", "d")).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold_administrative_text(value)).strip("-")


def _coordinate(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class AdministrativeArea:
    """One maintained province, district, ward, or equivalent locality."""

    area_id: str
    canonical: str
    level: str
    parent_province: str | None = None
    aliases: tuple[str, ...] = ()
    latitude: float | None = None
    longitude: float | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def slots(self) -> dict[str, str]:
        """Return workflow slots without inventing hierarchy fields."""
        result = {
            "location": self.canonical,
            "admin_area_id": self.area_id,
            "admin_level": self.level,
        }
        if self.level == "province":
            result["province"] = self.canonical
        elif self.parent_province:
            result["province"] = self.parent_province
            result["parent_province"] = self.parent_province
            if self.level == "district":
                result["district"] = self.canonical
            elif self.level in {"ward", "commune", "town"}:
                result["ward"] = self.canonical
        return result

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> AdministrativeArea:
        canonical = str(value.get("canonical") or "").strip()
        level = str(value.get("level") or "").strip().casefold()
        area_id = str(value.get("id") or value.get("area_id") or "").strip()
        if not canonical or not level:
            raise ValueError("administrative areas require canonical and level")
        if not area_id:
            area_id = f"{level}-{_slug(canonical)}"

        aliases = [canonical]
        aliases.extend(str(alias).strip() for alias in value.get("aliases", []) if str(alias).strip())
        aliases = list(dict.fromkeys(aliases))
        coordinates = value.get("coordinates")
        if not isinstance(coordinates, dict):
            coordinates = {}
        latitude = _coordinate(value.get("latitude", coordinates.get("latitude")))
        longitude = _coordinate(value.get("longitude", coordinates.get("longitude")))
        if (latitude is None) != (longitude is None):
            raise ValueError(f"administrative area {area_id!r} needs both latitude and longitude")
        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError(f"administrative area {area_id!r} has invalid latitude")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError(f"administrative area {area_id!r} has invalid longitude")

        parent = str(value.get("parent_province") or "").strip() or None
        return cls(
            area_id=area_id,
            canonical=canonical,
            level=level,
            parent_province=parent,
            aliases=tuple(aliases),
            latitude=latitude,
            longitude=longitude,
        )


class AdministrativeAreaResolver:
    """Resolve configured aliases deterministically and fail closed on ambiguity."""

    def __init__(self, areas: Iterable[AdministrativeArea]) -> None:
        by_id: dict[str, AdministrativeArea] = {}
        alias_index: dict[str, list[AdministrativeArea]] = {}
        for area in areas:
            if area.area_id in by_id:
                raise ValueError(f"duplicate administrative area id: {area.area_id}")
            by_id[area.area_id] = area
            for alias in area.aliases or (area.canonical,):
                normalized_alias = fold_administrative_text(alias)
                if normalized_alias:
                    alias_index.setdefault(normalized_alias, []).append(area)
        self._by_id = by_id
        self._alias_index = alias_index
        self._aliases = tuple(sorted(alias_index, key=lambda item: (-len(item), item)))

    @classmethod
    def from_file(
        cls,
        path: str | Path | None,
        *,
        fallback_areas: Iterable[AdministrativeArea] = (),
    ) -> AdministrativeAreaResolver:
        configured: list[AdministrativeArea] = []
        if path is not None:
            source = Path(path)
            if source.exists():
                payload = json.loads(source.read_text(encoding="utf-8"))
                raw_areas = payload.get("areas", []) if isinstance(payload, dict) else None
                if not isinstance(raw_areas, list):
                    raise TypeError("administrative-area source must contain an areas list")
                configured = [
                    AdministrativeArea.from_mapping(item)
                    for item in raw_areas
                    if isinstance(item, dict)
                ]
            elif path:
                raise FileNotFoundError(f"administrative-area source not found: {source}")

        configured_ids = {area.area_id for area in configured}
        configured_places = {
            (area.level, fold_administrative_text(area.canonical)) for area in configured
        }
        fallback = [
            area
            for area in fallback_areas
            if area.area_id not in configured_ids
            and (area.level, fold_administrative_text(area.canonical))
            not in configured_places
        ]
        return cls([*configured, *fallback])

    def by_id(self, area_id: str | None) -> AdministrativeArea | None:
        return self._by_id.get(str(area_id or ""))

    def resolve(
        self,
        value: str | None,
        *,
        parent_province: str | None = None,
    ) -> AdministrativeArea | None:
        """Return one area only when its alias is unambiguous in the input."""
        normalized = fold_administrative_text(str(value or ""))
        if not normalized:
            return None
        candidates: list[tuple[int, AdministrativeArea]] = []
        for alias in self._aliases:
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
            if re.search(pattern, normalized):
                candidates.extend((len(alias), area) for area in self._alias_index[alias])
        if not candidates:
            return None

        longest = max(length for length, _ in candidates)
        unique = {area.area_id: area for length, area in candidates if length == longest}
        if len(unique) == 1:
            return next(iter(unique.values()))

        parent_hint = fold_administrative_text(parent_province or "")
        parent_matched = {
            area_id: area
            for area_id, area in unique.items()
            if area.parent_province
            and (
                fold_administrative_text(area.parent_province) == parent_hint
                or fold_administrative_text(area.parent_province) in normalized
            )
        }
        if len(parent_matched) == 1:
            return next(iter(parent_matched.values()))
        return None
