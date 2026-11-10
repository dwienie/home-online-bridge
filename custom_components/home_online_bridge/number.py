"""Per dimmer: minimum, maximum and a raw 'calibration' slider that bypasses the calibration."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .entity import HomeOnlineEntity, mappings_for


async def async_setup_entry(hass, entry, async_add_entities):
    hub = entry.runtime_data
    entities = []
    for m in mappings_for(entry, "dimmer"):
        entities += [DimmerMinimum(hub, m), DimmerMaximum(hub, m), DimmerRaw(hub, m)]
    async_add_entities(entities)


class _DimmerNumber(HomeOnlineEntity, NumberEntity):
    _suffix = ""
    _label = ""
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hub, mapping) -> None:
        super().__init__(hub, mapping)
        self._attr_name = f"{mapping['name']} {self._label}"
        self._attr_unique_id = f"{DOMAIN}_{mapping['id']}_{self._suffix}"


class _Limit(_DimmerNumber):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:brightness-percent"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.hub.subscribe_calibration(self.slave_id, self.async_write_ha_state))

    async def _set(self, **kwargs) -> None:
        try:
            await self.hub.async_set_calibration(self.slave_id, **kwargs)
        except ValueError:
            raise ServiceValidationError("Minimum must be lower than maximum") from None


class DimmerMinimum(_Limit):
    _suffix, _label = "min", "minimum"
    _attr_native_min_value, _attr_native_max_value = 1, 99

    @property
    def native_value(self) -> float:
        return self.hub.calibration(self.slave_id)[0]

    async def async_set_native_value(self, value: float) -> None:
        await self._set(lo=int(value))


class DimmerMaximum(_Limit):
    _suffix, _label = "max", "maximum"
    _attr_native_min_value, _attr_native_max_value = 2, 100

    @property
    def native_value(self) -> float:
        return self.hub.calibration(self.slave_id)[1]

    async def async_set_native_value(self, value: float) -> None:
        await self._set(hi=int(value))


class DimmerRaw(_DimmerNumber):
    """Raw controller level 0-100: drag it down until the lamp is no longer visible, then use it as minimum."""

    _suffix, _label = "raw", "calibration"
    _attr_native_min_value, _attr_native_max_value = 0, 100
    _attr_icon = "mdi:brightness-6"

    @property
    def native_value(self) -> float | None:
        return None if self._value is None else min(self._value, 100)

    async def async_set_native_value(self, value: float) -> None:
        await self.hub.async_send(self.slave_id, int(value), True)
