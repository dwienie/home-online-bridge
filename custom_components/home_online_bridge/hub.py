"""Link between the ESPHome node and the entities. Pure core, HA calls only in async_* methods."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .const import CONF_MAPPINGS, EVENT_STATE
from .conversion import DIMMER_MAX_PERCENT, DIMMER_MIN_PERCENT, parse_event_value
from .mappings import Discovered

_LOGGER = logging.getLogger(__name__)


class HomeOnlineHub:
    def __init__(self, hass: Any, device: str, discovered: Discovered) -> None:
        self.hass = hass
        self.device = device
        self.discovered = discovered
        self._state: dict[int, int] = {}
        self._subs: dict[int, list[Callable[[int], None]]] = {}
        self._unsub_event: Callable[[], None] | None = None
        self._available = True
        self._avail_subs: list[Callable[[], None]] = []
        self.store: Any = None  # set by the integration, used to persist `discovered`
        self.entry: Any = None  # config entry, set by the integration; dimmer calibration is persisted in it
        self.skip_reload = False  # set while persisting a calibration so the update listener does not reload
        self._calib: dict[int, tuple[int, int]] = {}
        self._calib_subs: dict[int, list[Callable[[], None]]] = {}

    # --- pure core -------------------------------------------------------
    def handle_event(self, data: dict) -> tuple[int, int] | None:
        if data.get("device") != self.device:
            return None
        id_ = parse_event_value(data.get("id"))
        value = parse_event_value(data.get("value"))
        if id_ is None or value is None:
            return None
        self._state[id_] = value
        self.discovered.record(id_, value)
        for cb in list(self._subs.get(id_, ())):
            cb(value)
        return id_, value

    def state(self, id_: int) -> int | None:
        return self._state.get(id_)

    def subscribe(self, id_: int, callback: Callable[[int], None]) -> Callable[[], None]:
        self._subs.setdefault(id_, []).append(callback)

        def unsubscribe() -> None:
            if callback in self._subs.get(id_, []):
                self._subs[id_].remove(callback)

        return unsubscribe

    # --- dimmer calibration (min/max percent), live-editable without a reload --
    def load_calibration(self, mappings: list[dict]) -> None:
        self._calib = {
            m["id"]: (m.get("min_percent", DIMMER_MIN_PERCENT), m.get("max_percent", DIMMER_MAX_PERCENT))
            for m in mappings
            if m["type"] == "dimmer"
        }

    def calibration(self, id_: int) -> tuple[int, int]:
        return self._calib.get(id_, (DIMMER_MIN_PERCENT, DIMMER_MAX_PERCENT))

    def subscribe_calibration(self, id_: int, callback: Callable[[], None]) -> Callable[[], None]:
        self._calib_subs.setdefault(id_, []).append(callback)

        def unsubscribe() -> None:
            if callback in self._calib_subs.get(id_, []):
                self._calib_subs[id_].remove(callback)

        return unsubscribe

    def set_calibration(self, id_: int, lo: int | None = None, hi: int | None = None) -> None:
        cur_lo, cur_hi = self.calibration(id_)
        lo = cur_lo if lo is None else lo
        hi = cur_hi if hi is None else hi
        if not 1 <= lo < hi <= 100:
            raise ValueError("invalid_range")
        self._calib[id_] = (lo, hi)
        for cb in list(self._calib_subs.get(id_, ())):
            cb()

    async def async_set_calibration(self, id_: int, lo: int | None = None, hi: int | None = None) -> None:
        self.set_calibration(id_, lo, hi)
        lo, hi = self.calibration(id_)
        mappings = [dict(m) for m in self.entry.options.get(CONF_MAPPINGS, [])]
        for m in mappings:
            if m["id"] == id_ and m["type"] == "dimmer":
                m["min_percent"], m["max_percent"] = lo, hi
        self.skip_reload = True
        if not self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_MAPPINGS: mappings}
        ):
            self.skip_reload = False  # nothing changed, so the update listener will not run

    @property
    def available(self) -> bool:
        return self._available

    def subscribe_availability(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._avail_subs.append(callback)

        def unsubscribe() -> None:
            if callback in self._avail_subs:
                self._avail_subs.remove(callback)

        return unsubscribe

    def set_online_state(self, state: str | None) -> None:
        """State of the node's "Controller online" entity. Unknown states change nothing."""
        if state == "on":
            new = True
        elif state in ("off", "unavailable"):
            new = False
        else:
            return
        if new != self._available:
            self._available = new
            for cb in list(self._avail_subs):
                cb()

    # --- Home Assistant side ---------------------------------------------
    async def async_send(self, id_: int, value: int, percent: bool) -> None:
        await self.hass.services.async_call(
            "esphome", f"{self.device}_send", {"id": id_, "value": value, "percent": percent}, blocking=True
        )

    async def async_resync(self) -> None:
        try:
            await self.hass.services.async_call("esphome", f"{self.device}_resync", {}, blocking=True)
        except Exception:  # node not connected yet; retried on reconnect
            _LOGGER.debug("resync failed, node probably offline", exc_info=True)

    async def async_start(self) -> None:
        """Listen for node events and ask the node to replay its cache.

        The node also replays on every API (re)connect (api: on_client_connected), so this only
        covers HA starting or the integration being reloaded while the node stays connected.
        """
        from homeassistant.core import callback
        from homeassistant.helpers.event import async_call_later, async_track_state_change_event

        @callback
        def _on_event(event: Any) -> None:
            self.handle_event(dict(event.data))

        @callback
        def _initial_resync(_now: Any) -> None:
            self.hass.async_create_task(self.async_resync())

        unsubs = [
            self.hass.bus.async_listen(EVENT_STATE, _on_event),
            async_call_later(self.hass, 10, _initial_resync),
        ]
        online_entity = self._find_online_entity()
        if online_entity is not None:
            @callback
            def _on_online(event: Any) -> None:
                new = event.data.get("new_state")
                self.set_online_state(new.state if new is not None else "unavailable")

            unsubs.append(async_track_state_change_event(self.hass, [online_entity], _on_online))
            current = self.hass.states.get(online_entity)
            self.set_online_state(current.state if current is not None else None)
        self._unsub_event = lambda: [u() for u in unsubs]
        await self.async_resync()

    def _find_online_entity(self) -> str | None:
        """The node's "Controller online" binary sensor, found via the registries (no guessed entity_id)."""
        from homeassistant.helpers import device_registry as dr, entity_registry as er

        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        for ent in ent_reg.entities.values():
            if ent.platform != "esphome" or ent.domain != "binary_sensor" or not ent.device_id:
                continue
            if "controller online" not in (ent.original_name or ent.name or "").lower() and (
                "controller_online" not in (ent.unique_id or "")
            ):
                continue
            dev = dev_reg.async_get(ent.device_id)
            if dev and (dev.name or "").lower().replace("-", "_") == self.device:
                return ent.entity_id
        _LOGGER.warning("No 'Controller online' entity found for %s; entities stay available", self.device)
        return None

    def async_stop(self) -> None:
        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None
