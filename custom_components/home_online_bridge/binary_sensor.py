from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity

from .conversion import is_on
from .entity import HomeOnlineEntity, mappings_for


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(HomeOnlineSensor(entry.runtime_data, m) for m in mappings_for(entry, "sensor"))


class HomeOnlineSensor(HomeOnlineEntity, BinarySensorEntity):
    """Read-only: the controller input/indicator, non-zero = on."""

    @property
    def is_on(self) -> bool | None:
        return None if self._value is None else is_on(self._value)
