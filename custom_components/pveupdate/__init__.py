"""Proxmox Guest Updates: update entities for LXCs and VMs managed by pveupdate."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PveUpdateApi
from .coordinator import PveUpdateCoordinator

PLATFORMS = [Platform.UPDATE, Platform.BUTTON, Platform.SENSOR]

type PveUpdateConfigEntry = ConfigEntry[PveUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PveUpdateConfigEntry) -> bool:
    api = PveUpdateApi(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_TOKEN]
    )
    coordinator = PveUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PveUpdateConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PveUpdateConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
