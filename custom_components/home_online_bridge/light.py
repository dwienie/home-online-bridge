from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity

from .conversion import dimmer_read_percent, is_on, percent_to_brightness, turn_on_percent
from .entity import HomeOnlineEntity, mappings_for


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(HomeOnlineLight(entry.runtime_data, m) for m in mappings_for(entry, "dimmer"))


class HomeOnlineLight(HomeOnlineEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, hub, mapping) -> None:
        super().__init__(hub, mapping)
        self._last_on: int | None = None  # last non-zero percent, restored on a plain turn-on
        self._remember(self._value)

    @property
    def _lo(self) -> int:
        return self.hub.calibration(self.slave_id)[0]

    @property
    def _hi(self) -> int:
        return self.hub.calibration(self.slave_id)[1]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.hub.subscribe_calibration(self.slave_id, self.async_write_ha_state))

    def _remember(self, value: int | None) -> None:
        if value:
            self._last_on = min(value, 100)

    def _on_value(self, value: int) -> None:
        self._remember(value)
        super()._on_value(value)

    @property
    def is_on(self) -> bool | None:
        return None if self._value is None else is_on(self._value)

    @property
    def brightness(self) -> int | None:
        return None if self._value is None else percent_to_brightness(dimmer_read_percent(self._value, self._lo, self._hi))

    async def async_turn_on(self, **kwargs) -> None:
        value = turn_on_percent(kwargs.get(ATTR_BRIGHTNESS), self._last_on, self._lo, self._hi)
        await self.hub.async_send(self.slave_id, value, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hub.async_send(self.slave_id, 0, True)
