"""Pure value conversion between Home Assistant and the controller (no HA imports)."""
from __future__ import annotations

DIMMER_MIN_PERCENT = 8  # default calibration: the controller ignores dimmer values below 8 %
DIMMER_MAX_PERCENT = 100


def brightness_to_percent(brightness: int) -> int:
    return round(brightness * 100 / 255)


def percent_to_brightness(percent: int) -> int:
    return round(percent * 255 / 100)


def dimmer_write_value(percent: int, lo: int = DIMMER_MIN_PERCENT, hi: int = DIMMER_MAX_PERCENT) -> int:
    """HA 1-100 % spread over the calibrated controller range lo-hi; 0 stays off."""
    if percent <= 0:
        return 0
    return lo + round((min(percent, 100) - 1) * (hi - lo) / 99)


def dimmer_read_percent(value: int, lo: int = DIMMER_MIN_PERCENT, hi: int = DIMMER_MAX_PERCENT) -> int:
    """Inverse of dimmer_write_value: controller value to HA percent."""
    if value <= 0:
        return 0
    if value <= lo:
        return 1
    if value >= hi:
        return 100
    return 1 + round((value - lo) * 99 / (hi - lo))


def parse_event_value(raw: str | None) -> int | None:
    """Parse an ESPHome event string; the controller only speaks 0-999."""
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit():
        return None
    value = int(raw)
    return value if value <= 999 else None


def is_on(value: int) -> bool:
    return value != 0


def _brightness_percent(brightness: int) -> int:
    return max(1, brightness_to_percent(brightness)) if brightness > 0 else 0


def light_write_args(brightness: int, lo: int = DIMMER_MIN_PERCENT, hi: int = DIMMER_MAX_PERCENT) -> tuple[int, bool]:
    return dimmer_write_value(_brightness_percent(brightness), lo, hi), True


def turn_on_percent(
    brightness: int | None, last_on: int | None, lo: int = DIMMER_MIN_PERCENT, hi: int = DIMMER_MAX_PERCENT
) -> int:
    """Controller value for a light turn-on: explicit brightness, else the last level, else full."""
    if brightness is not None:
        return dimmer_write_value(_brightness_percent(brightness), lo, hi)
    if last_on is not None and last_on >= lo:
        return last_on
    return hi


def cover_write_args(command: str | int) -> tuple[int, bool]:
    if command == "open":
        return 100, True
    if command == "close":
        return 0, True
    return int(command), True


def switch_write_args(on: bool) -> tuple[int, bool]:
    return (1 if on else 0), False
