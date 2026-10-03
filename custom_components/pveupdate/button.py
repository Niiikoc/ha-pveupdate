"""Buttons on the Proxmox host device: check now, update all pending."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PveUpdateConfigEntry
from .api import Busy, PveUpdateError
from .entity import HostEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PveUpdateConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([CheckButton(coordinator, "check"), UpdatePendingButton(coordinator, "update_pending")])


class _ApiButton(HostEntity, ButtonEntity):
    async def _call(self, coro) -> None:
        try:
            await coro
        except Busy as err:
            raise HomeAssistantError("Another check or update is already running on the host") from err
        except PveUpdateError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class CheckButton(_ApiButton):
    _attr_icon = "mdi:magnify"

    async def async_press(self) -> None:
        await self._call(self.coordinator.api.check())


class UpdatePendingButton(_ApiButton):
    _attr_icon = "mdi:update"

    async def async_press(self) -> None:
        await self._call(self.coordinator.api.update("pending"))
