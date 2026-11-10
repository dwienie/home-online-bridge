"""Per dimmer: take the current raw (calibration) level as the new minimum or maximum."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .entity import HomeOnlineEntity, mappings_for


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    entities = []
    for m in mappings_for(entry, "dimmer"):
        entities += [UseAsMinimum(hub, m), UseAsMaximum(hub, m)]
    async_add_entities(entities)


class _UseRaw(HomeOnlineEntity, ButtonEntity):
    _suffix = ""
    _label = ""
    _field = ""
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hub, mapping) -> None:
        super().__init__(hub, mapping)
        self._attr_name = f"{mapping['name']} {self._label}"
        self._attr_unique_id = f"{DOMAIN}_{mapping['id']}_{self._suffix}"

    async def async_press(self) -> None:
        raw = self.hub.state(self.slave_id)
        if raw is None or raw < 1:
            raise ServiceValidationError("Set the calibration slider to a level first")
        try:
            await self.hub.async_set_calibration(self.slave_id, **{self._field: min(raw, 100)})
        except ValueError:
            raise ServiceValidationError("Minimum must be lower than maximum") from None


class UseAsMinimum(_UseRaw):
    _suffix, _label, _field = "setmin", "calibration as minimum", "lo"
    _attr_icon = "mdi:arrow-collapse-down"


class UseAsMaximum(_UseRaw):
    _suffix, _label, _field = "setmax", "calibration as maximum", "hi"
    _attr_icon = "mdi:arrow-collapse-up"
