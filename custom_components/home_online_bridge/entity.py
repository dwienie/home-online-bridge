"""Shared entity base: one entity per mapping, state pushed by the hub."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .const import CONF_MAPPINGS, DOMAIN
from .hub import HomeOnlineHub


def mappings_for(entry, mapping_type: str) -> list[dict]:
    return [m for m in entry.options.get(CONF_MAPPINGS, []) if m["type"] == mapping_type]


class HomeOnlineEntity(Entity):
    _attr_should_poll = False

    def __init__(self, hub: HomeOnlineHub, mapping: dict) -> None:
        self.hub = hub
        self.slave_id: int = mapping["id"]
        self._attr_name = mapping["name"]
        self._attr_unique_id = f"{DOMAIN}_{self.slave_id}"
        self._value: int | None = hub.state(self.slave_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.subscribe(self.slave_id, self._on_value))
        self.async_on_remove(self.hub.subscribe_availability(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self.hub.available

    @callback
    def _on_value(self, value: int) -> None:
        self._value = value
        self.async_write_ha_state()
