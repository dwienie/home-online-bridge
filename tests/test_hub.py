from custom_components.home_online_bridge.hub import HomeOnlineHub
from custom_components.home_online_bridge.mappings import Discovered


def make():
    return HomeOnlineHub(None, "home_online_bridge", Discovered())


def test_matching_event():
    h = make()
    assert h.handle_event({"device": "home_online_bridge", "id": "279", "value": "60"}) == (279, 60)
    assert h.state(279) == 60


def test_other_device_ignored():
    h = make()
    assert h.handle_event({"device": "other", "id": "279", "value": "60"}) is None
    assert h.state(279) is None


def test_malformed_events_ignored():
    h = make()
    assert h.handle_event({"device": "home_online_bridge", "id": "x", "value": "1"}) is None
    assert h.handle_event({"device": "home_online_bridge", "value": "1"}) is None
    assert h.handle_event({"device": "home_online_bridge", "id": "5"}) is None
    assert h.handle_event({"device": "home_online_bridge", "id": "5", "value": "1000"}) is None
    assert h.handle_event({}) is None


def test_recorded_in_discovered():
    h = make()
    h.handle_event({"device": "home_online_bridge", "id": "300", "value": "2"})
    assert h.discovered.unmapped(set()) == {300: 2}


def test_subscribe_and_unsubscribe():
    h = make()
    got = []
    unsub = h.subscribe(279, got.append)
    h.handle_event({"device": "home_online_bridge", "id": "279", "value": "10"})
    h.handle_event({"device": "home_online_bridge", "id": "280", "value": "11"})
    assert got == [10]
    unsub()
    h.handle_event({"device": "home_online_bridge", "id": "279", "value": "20"})
    assert got == [10]


def test_available_defaults_true_and_follows_online_state():
    h = make()
    assert h.available is True
    changes = []
    h.subscribe_availability(lambda: changes.append(h.available))
    h.set_online_state("off")
    assert h.available is False
    h.set_online_state("off")          # no change, no callback
    h.set_online_state("on")
    h.set_online_state("unavailable")
    h.set_online_state("unknown")      # unknown: do not claim anything, keep last decision
    h.set_online_state("on")
    assert changes == [False, True, False, True]


def test_unknown_at_start_stays_available():
    h = make()
    h.set_online_state("unknown")
    h.set_online_state(None)
    assert h.available is True
