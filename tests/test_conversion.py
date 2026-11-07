from custom_components.home_online_bridge.conversion import (
    brightness_to_percent,
    dimmer_read_percent,
    dimmer_write_value,
    is_on,
    parse_event_value,
    percent_to_brightness,
)


def test_dimmer_calibration_default():
    assert dimmer_write_value(0) == 0
    assert dimmer_write_value(1) == 8  # lowest level the controller accepts
    assert dimmer_write_value(100) == 100


def test_dimmer_calibration_custom_range():
    assert dimmer_write_value(0, 30, 90) == 0
    assert dimmer_write_value(1, 30, 90) == 30
    assert dimmer_write_value(100, 30, 90) == 90
    assert dimmer_read_percent(0, 30, 90) == 0
    assert dimmer_read_percent(30, 30, 90) == 1
    assert dimmer_read_percent(20, 30, 90) == 1  # below range: lowest step
    assert dimmer_read_percent(90, 30, 90) == 100
    assert dimmer_read_percent(95, 30, 90) == 100


def test_dimmer_calibration_roundtrip():
    for lo, hi in ((8, 100), (30, 90), (20, 60)):
        for p in range(1, 101):
            assert abs(dimmer_read_percent(dimmer_write_value(p, lo, hi), lo, hi) - p) <= 2


def test_brightness_roundtrip():
    for p in range(0, 101):
        assert brightness_to_percent(percent_to_brightness(p)) == p


def test_brightness_extremes():
    assert percent_to_brightness(100) == 255
    assert percent_to_brightness(0) == 0
    assert brightness_to_percent(255) == 100
    assert brightness_to_percent(0) == 0


def test_parse_event_value():
    assert parse_event_value("60") == 60
    assert parse_event_value("0") == 0
    assert parse_event_value("999") == 999
    for bad in ("abc", "", "1000", "-1", " 5", "5 ", None, "1.5"):
        assert parse_event_value(bad) is None


def test_is_on():
    assert is_on(1) and is_on(100)
    assert not is_on(0)


def test_turn_on_percent():
    from custom_components.home_online_bridge.conversion import turn_on_percent

    assert turn_on_percent(255, None) == 100        # explicit brightness wins
    assert turn_on_percent(10, 40) == 11            # explicit, spread over 8-100
    assert turn_on_percent(10, 40, 30, 90) == 32    # explicit, spread over 30-90
    assert turn_on_percent(None, 40) == 40          # restore last level
    assert turn_on_percent(None, None) == 100       # nothing known
    assert turn_on_percent(None, 5) == 100          # remembered level below range: full
    assert turn_on_percent(None, 40, 50, 80) == 80  # remembered level below custom min: max
    assert turn_on_percent(None, 0) == 100
