"""Home Online Bridge: Home Assistant side of the ESPHome serial bridge."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import CONF_DEVICE, CONF_MAPPINGS, DOMAIN, PLATFORMS, STORAGE_VERSION
from .hub import HomeOnlineHub
from .mappings import Discovered, orphaned_entities

type HomeOnlineConfigEntry = ConfigEntry[HomeOnlineHub]


async def async_setup_entry(hass: HomeAssistant, entry: HomeOnlineConfigEntry) -> bool:
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.discovered")
    saved = await store.async_load()
    discovered = Discovered.from_dict(saved) if saved else Discovered()
    hub = HomeOnlineHub(hass, entry.data[CONF_DEVICE], discovered)
    hub.store = store
    discovered.on_change = lambda: store.async_delay_save(discovered.to_dict, 10)
    entry.runtime_data = hub

    # Drop entities whose mapping was removed or changed type.
    registry = er.async_get(hass)
    rows = [
        (e.entity_id, e.domain, e.unique_id)
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    ]
    for entity_id in orphaned_entities(rows, entry.options.get(CONF_MAPPINGS, [])):
        registry.async_remove(entity_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await hub.async_start()

    entry.async_on_unload(hub.async_stop)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: HomeOnlineConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HomeOnlineConfigEntry) -> bool:
    hub = entry.runtime_data
    # Write before returning so the reloaded entry reads current data (no race with a pending save).
    await hub.store.async_save(hub.discovered.to_dict())
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
