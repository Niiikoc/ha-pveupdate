"""Buttons: check now and update all pending on the host, Update OS on each guest."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PveUpdateConfigEntry
from .api import Busy, PveUpdateError
from .entity import GuestEntity, HostEntity, require_parts


async def async_setup_entry(
    hass: HomeAssistant, entry: PveUpdateConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([CheckButton(coordinator, "check"), UpdatePendingButton(coordinator, "update_pending")])
    known: set[str] = set()

    @callback
    def add_new() -> None:
        guests = (coordinator.data or {}).get("guests", {})
        known.intersection_update(guests)
        new = [gid for gid in guests if gid not in known]
        known.update(new)
        if new:
            async_add_entities(UpdateOsButton(coordinator, gid) for gid in new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class _ApiButton(ButtonEntity):
    async def _call(self, coro) -> None:
        try:
            await coro
        except Busy as err:
            raise HomeAssistantError("Another check or update is already running on the host") from err
        except PveUpdateError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class CheckButton(HostEntity, _ApiButton):
    _attr_icon = "mdi:magnify"

    async def async_press(self) -> None:
        await self._call(self.coordinator.api.check())


class UpdatePendingButton(HostEntity, _ApiButton):
    """OS packages and apps of every guest with updates."""

    _attr_icon = "mdi:update"

    async def async_press(self) -> None:
        await self._call(self.coordinator.api.update("pending"))


class UpdateOsButton(GuestEntity, _ApiButton):
    """OS packages of one guest (snapshot first); the app is left alone."""

    _attr_icon = "mdi:package-up"
    _attr_translation_key = "update_os"

    def __init__(self, coordinator, gid: str) -> None:
        super().__init__(coordinator, gid, "update_os")

    async def async_press(self) -> None:
        require_parts(self.coordinator)
        await self._call(self.coordinator.api.update([self.gid], part="os"))
