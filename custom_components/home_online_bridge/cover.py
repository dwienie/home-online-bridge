from __future__ import annotations

from homeassistant.components.cover import ATTR_POSITION, CoverEntity, CoverEntityFeature

from .conversion import cover_write_args
from .entity import HomeOnlineEntity, mappings_for


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(HomeOnlineCover(entry.runtime_data, m) for m in mappings_for(entry, "cover"))


class HomeOnlineCover(HomeOnlineEntity, CoverEntity):
    """100 = open, 0 = closed; set-position only (no stop)."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
    )

    @property
    def current_cover_position(self) -> int | None:
        return None if self._value is None else min(self._value, 100)

    @property
    def is_closed(self) -> bool | None:
        return None if self._value is None else self._value == 0

    async def async_open_cover(self, **kwargs) -> None:
        await self.hub.async_send(self.slave_id, *cover_write_args("open"))

    async def async_close_cover(self, **kwargs) -> None:
        await self.hub.async_send(self.slave_id, *cover_write_args("close"))

    async def async_set_cover_position(self, **kwargs) -> None:
        await self.hub.async_send(self.slave_id, *cover_write_args(kwargs[ATTR_POSITION]))
