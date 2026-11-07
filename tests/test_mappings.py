import pytest

from custom_components.home_online_bridge.mappings import Discovered, MappingError, validate_mapping

EXISTING = [{"id": 279, "name": "Zit", "type": "dimmer"}]


def test_duplicate_id_raises():
    with pytest.raises(MappingError):
        validate_mapping({"id": 279, "name": "x", "type": "relay"}, EXISTING)


def test_edit_same_id_ok():
    m = validate_mapping({"id": 279, "name": "New", "type": "dimmer"}, EXISTING, editing_id=279)
    assert m == {"id": 279, "name": "New", "type": "dimmer", "min_percent": 8, "max_percent": 100}


@pytest.mark.parametrize("bad_id", [1000, -1])
def test_id_out_of_range(bad_id):
    with pytest.raises(MappingError):
        validate_mapping({"id": bad_id, "name": "x", "type": "relay"}, [])


def test_bad_name_and_type():
    with pytest.raises(MappingError):
        validate_mapping({"id": 5, "name": "  ", "type": "relay"}, [])
    with pytest.raises(MappingError):
        validate_mapping({"id": 5, "name": "x", "type": "nope"}, [])


def test_name_stripped_and_id_coerced():
    assert validate_mapping({"id": "12", "name": " Lamp ", "type": "relay"}, []) == {
        "id": 12, "name": "Lamp", "type": "relay"}




def test_discovered_filters():
    d = Discovered()
    d.record(5, 1)       # internal, ignored by default
    d.record(300, 2)
    d.record(279, 50)    # mapped
    assert d.unmapped({279}) == {300: 2}
    d.ignore(300)
    assert d.unmapped({279}) == {}


def test_discovered_roundtrip():
    d = Discovered()
    d.record(300, 2)
    d.ignore(301)
    d2 = Discovered.from_dict(d.to_dict())
    assert d2.unmapped(set()) == {300: 2}
    d2.record(301, 1)
    assert 301 not in d2.unmapped(set())


def test_orphaned_entities():
    from custom_components.home_online_bridge.mappings import orphaned_entities

    maps = [{"id": 1, "name": "a", "type": "relay"}, {"id": 2, "name": "b", "type": "dimmer"}]
    reg = [
        ("switch.a", "switch", "home_online_bridge_1"),    # ok
        ("switch.b", "switch", "home_online_bridge_2"),    # retyped to dimmer -> orphan
        ("light.c", "light", "home_online_bridge_3"),      # removed mapping -> orphan
        ("light.b", "light", "home_online_bridge_2"),      # ok
    ]
    assert sorted(orphaned_entities(reg, maps)) == ["light.c", "switch.b"]


def test_discovered_notifies_on_change():
    d = Discovered()
    calls = []
    d.on_change = lambda: calls.append(1)
    d.record(300, 1)
    assert len(calls) == 1
    d.record(300, 1)          # unchanged value: no write
    assert len(calls) == 1
    d.record(300, 0)
    assert len(calls) == 2
    d.ignore(300)
    assert len(calls) == 3


def test_discovered_unignore_and_set_ignored():
    d = Discovered()
    d.record(300, 1)
    calls = []
    d.on_change = lambda: calls.append(1)
    d.ignore(300)
    assert d.unmapped(set()) == {}
    assert 300 in d.ignored
    d.unignore(300)
    assert d.unmapped(set()) == {300: 1}
    assert len(calls) == 2
    d.unignore(300)                     # already not ignored: no write
    assert len(calls) == 2
    d.set_ignored({5, 301})
    assert d.ignored == {5, 301}
    assert len(calls) == 3
    d.set_ignored({5, 301})             # unchanged: no write
    assert len(calls) == 3


def test_dimmer_calibration_defaults_and_custom():
    m = validate_mapping({"id": 1, "name": "x", "type": "dimmer"}, [])
    assert (m["min_percent"], m["max_percent"]) == (8, 100)
    m = validate_mapping({"id": 1, "name": "x", "type": "dimmer", "min_percent": 30, "max_percent": 90}, [])
    assert (m["min_percent"], m["max_percent"]) == (30, 90)


def test_calibration_dropped_for_other_types():
    assert "min_percent" not in validate_mapping({"id": 1, "name": "x", "type": "relay", "min_percent": 30}, [])


def test_invalid_calibration():
    for lo, hi in ((50, 50), (60, 40), (0, 100), (10, 101)):
        with pytest.raises(MappingError, match="invalid_range"):
            validate_mapping({"id": 1, "name": "x", "type": "dimmer", "min_percent": lo, "max_percent": hi}, [])
