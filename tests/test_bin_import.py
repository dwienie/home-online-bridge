"""Tests for the Domati .bin parser, using a small synthetic file (no real installation data)."""
import pytest

from custom_components.home_online_bridge.bin_import import BinParseError, parse_bin


def _module(start: int, name: str) -> bytes:
    return b"\x01" + start.to_bytes(2, "big") + b"\x0e\x01\x0a" + b"\x00" * 6 + b"\xff\xff\x00\x00" + name.encode() + b"\x00"


def _record(index: int, name: str, direction: int) -> bytes:
    # 01 <id16> <kind> ...filler... 15 00 <direction> ff <flag> <name> 00
    return (
        b"\x01" + index.to_bytes(2, "big") + b"\x00" + b"\x00" * 9 + b"\x15\x00" + bytes([direction])
        + b"\xff\x00" + name.encode() + b"\x00"
    )


def _file(*records: tuple[str, int]) -> bytes:
    data = _module(10, "Module A") + _module(13, "Module B")
    for i, (name, direction) in enumerate(records):
        data += _record(i, name, direction)
    return data


@pytest.fixture
def result():
    return parse_bin(_file(("Lamp hall", 3), ("Sensor hall", 2), ("Input 3", 2), ("Led 1", 1), ("Button 2", 0)))


def test_numbering_starts_at_first_module(result):
    assert [s.id for s in result.slaves] == [10, 11, 12, 13, 14]
    assert [s.name for s in result.slaves] == ["Lamp hall", "Sensor hall", "Input 3", "Led 1", "Button 2"]
    assert result.warnings == []


def test_module_names(result):
    assert [s.module for s in result.slaves] == ["Module A"] * 3 + ["Module B"] * 2


def test_direction_only_when_reliable(result):
    assert [s.direction for s in result.slaves] == ["output", "input", "input", "", ""]


def test_suggested_type(result):
    # inputs and buttons are read-only, so they are suggested as sensors
    assert [s.suggested_type for s in result.slaves] == ["relay", "sensor", "sensor", "relay", "sensor"]


def test_inputs_and_buttons_are_flagged(result):
    assert [s.is_input for s in result.slaves] == [False, False, True, False, True]


@pytest.mark.parametrize("data", [b"", b"this is not a domati bin", _module(10, "Module A")])
def test_unrecognised_files_are_rejected(data):
    with pytest.raises(BinParseError):
        parse_bin(data)
