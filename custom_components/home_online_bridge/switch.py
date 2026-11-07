from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .conversion import is_on, switch_write_args
from .entity import HomeOnlineEntity, mappings_for


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(HomeOnlineSwitch(entry.runtime_data, m) for m in mappings_for(entry, "relay"))


class HomeOnlineSwitch(HomeOnlineEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        return None if self._value is None else is_on(self._value)

    async def async_turn_on(self, **kwargs) -> None:
        await self.hub.async_send(self.slave_id, *switch_write_args(True))

    async def async_turn_off(self, **kwargs) -> None:
        await self.hub.async_send(self.slave_id, *switch_write_args(False))
