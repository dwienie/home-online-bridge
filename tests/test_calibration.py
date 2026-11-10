import asyncio
from types import SimpleNamespace

import pytest

from custom_components.home_online_bridge.hub import HomeOnlineHub
from custom_components.home_online_bridge.mappings import DIMMER_EXTRAS, Discovered, orphaned_entities

MAPS = [
    {"id": 279, "name": "Zit", "type": "dimmer", "min_percent": 40, "max_percent": 90},
    {"id": 280, "name": "Gang", "type": "dimmer"},
    {"id": 1, "name": "Relay", "type": "relay"},
]


def make(maps=MAPS):
    h = HomeOnlineHub(None, "home_online_bridge", Discovered())
    h.load_calibration(maps)
    return h


def test_load_calibration_uses_mapping_values_and_defaults():
    h = make()
    assert h.calibration(279) == (40, 90)
    assert h.calibration(280) == (8, 100)  # defaults
    assert h.calibration(1) == (8, 100)  # not a dimmer: defaults, nothing stored
    assert h.calibration(999) == (8, 100)


def test_set_calibration_updates_and_notifies_subscribers():
    h = make()
    calls = []
    unsub = h.subscribe_calibration(279, lambda: calls.append(1))
    h.set_calibration(279, lo=50)
    assert h.calibration(279) == (50, 90)  # only the minimum changed
    h.set_calibration(279, hi=80)
    assert h.calibration(279) == (50, 80)
    assert len(calls) == 2
    unsub()
    h.set_calibration(279, lo=10)
    assert len(calls) == 2


def test_subscribers_are_per_dimmer():
    h = make()
    calls = []
    h.subscribe_calibration(279, lambda: calls.append(279))
    h.set_calibration(280, lo=20)
    assert calls == []


@pytest.mark.parametrize("lo,hi", [(90, 90), (91, 90), (0, 90), (10, 101)])
def test_invalid_range_is_rejected_and_keeps_old_values(lo, hi):
    h = make()
    with pytest.raises(ValueError):
        h.set_calibration(279, lo, hi)
    assert h.calibration(279) == (40, 90)


def _persist(update_result=True):
    entry = SimpleNamespace(options={"mappings": [dict(m) for m in MAPS], "other": 1})

    def async_update_entry(e, options):
        e.options = options
        return update_result

    h = make()
    h.entry = entry
    h.hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=async_update_entry))
    return h, entry


def test_async_set_calibration_persists_only_that_dimmer():
    h, entry = _persist()
    asyncio.run(h.async_set_calibration(280, lo=33))
    by_id = {m["id"]: m for m in entry.options["mappings"]}
    assert (by_id[280]["min_percent"], by_id[280]["max_percent"]) == (33, 100)
    assert (by_id[279]["min_percent"], by_id[279]["max_percent"]) == (40, 90)  # untouched
    assert "min_percent" not in by_id[1]  # relays never get calibration
    assert entry.options["other"] == 1
    assert h.skip_reload is True  # the update listener must not reload for a live edit


def test_skip_reload_is_cleared_when_nothing_changed():
    h, _entry = _persist(update_result=False)
    asyncio.run(h.async_set_calibration(279, lo=40))
    assert h.skip_reload is False


def test_orphaned_entities_keeps_calibration_helpers_of_dimmers():
    reg = [("light.zit", "light", "home_online_bridge_279")]
    reg += [(f"{p}.zit_{s}", p, f"home_online_bridge_279_{s}") for s, p in DIMMER_EXTRAS]
    assert orphaned_entities(reg, MAPS) == []


def test_orphaned_entities_removes_helpers_when_dimmer_is_removed_or_retyped():
    reg = [(f"{p}.x_{s}", p, f"home_online_bridge_5_{s}") for s, p in DIMMER_EXTRAS]
    assert len(orphaned_entities(reg, MAPS)) == len(DIMMER_EXTRAS)  # no mapping 5
    retyped = MAPS + [{"id": 5, "name": "x", "type": "relay"}]
    assert len(orphaned_entities(reg, retyped)) == len(DIMMER_EXTRAS)  # a relay has no helpers


def test_orphaned_entities_removes_helper_on_wrong_platform():
    reg = [("sensor.zit_min", "sensor", "home_online_bridge_279_min")]
    assert orphaned_entities(reg, MAPS) == ["sensor.zit_min"]
