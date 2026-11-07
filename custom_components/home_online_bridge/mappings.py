"""Mapping validation and discovered-ID tracking (no HA imports)."""
from __future__ import annotations

from collections.abc import Callable

from .conversion import DIMMER_MAX_PERCENT, DIMMER_MIN_PERCENT

MAPPING_TYPES = ("dimmer", "cover", "relay", "sensor")
DEFAULT_IGNORED = frozenset(range(1, 9))  # controller internals


class MappingError(ValueError):
    """Raised for an invalid mapping; the message is a translation key."""


def validate_mapping(m: dict, existing: list[dict], editing_id: int | None = None) -> dict:
    try:
        mid = int(m["id"])
    except (KeyError, TypeError, ValueError):
        raise MappingError("invalid_id") from None
    if not 0 <= mid <= 999:
        raise MappingError("invalid_id")
    name = str(m.get("name", "")).strip()
    if not name:
        raise MappingError("empty_name")
    if m.get("type") not in MAPPING_TYPES:
        raise MappingError("invalid_type")
    if any(e["id"] == mid and mid != editing_id for e in existing):
        raise MappingError("duplicate_id")
    result = {"id": mid, "name": name, "type": m["type"]}
    if m["type"] == "dimmer":
        # Calibration: controller range that HA 1-100 % is spread over (lowest level that still lights the lamp).
        try:
            lo = int(m.get("min_percent", DIMMER_MIN_PERCENT))
            hi = int(m.get("max_percent", DIMMER_MAX_PERCENT))
        except (TypeError, ValueError):
            raise MappingError("invalid_range") from None
        if not 1 <= lo < hi <= 100:
            raise MappingError("invalid_range")
        result["min_percent"] = lo
        result["max_percent"] = hi
    return result


class Discovered:
    """IDs seen on serial, with the last value; ignored IDs are never listed."""

    def __init__(self, ignored: set[int] | None = None) -> None:
        self._ignored: set[int] = set(DEFAULT_IGNORED if ignored is None else ignored)
        self._seen: dict[int, int] = {}
        self.on_change: Callable[[], None] | None = None  # called after every real change, to persist

    def record(self, id: int, value: int) -> None:
        if self._seen.get(id) == value:
            return
        self._seen[id] = value
        self._notify()

    def ignore(self, id: int) -> None:
        self._ignored.add(id)
        self._notify()

    def unignore(self, id: int) -> None:
        if id in self._ignored:
            self._ignored.discard(id)
            self._notify()

    @property
    def seen(self) -> dict[int, int]:
        return dict(self._seen)

    @property
    def ignored(self) -> set[int]:
        return set(self._ignored)

    def set_ignored(self, ids: set[int]) -> None:
        if set(ids) != self._ignored:
            self._ignored = set(ids)
            self._notify()

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def unmapped(self, mapped_ids: set[int]) -> dict[int, int]:
        return {i: v for i, v in self._seen.items() if i not in mapped_ids and i not in self._ignored}

    def to_dict(self) -> dict:
        return {"ignored": sorted(self._ignored), "seen": {str(k): v for k, v in self._seen.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "Discovered":
        obj = cls(set(d.get("ignored", DEFAULT_IGNORED)))
        obj._seen = {int(k): v for k, v in d.get("seen", {}).items()}
        return obj


TYPE_PLATFORM = {"dimmer": "light", "cover": "cover", "relay": "switch", "sensor": "binary_sensor"}


def orphaned_entities(registry: list[tuple[str, str, str]], mappings: list[dict]) -> list[str]:
    """registry rows are (entity_id, platform, unique_id); returns entity_ids to remove."""
    expected = {f"home_online_bridge_{m['id']}": TYPE_PLATFORM[m["type"]] for m in mappings}
    return [eid for eid, platform, uid in registry if expected.get(uid) != platform]
