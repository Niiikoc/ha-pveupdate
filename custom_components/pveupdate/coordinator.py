"""Polls the pveupdate status and starts periodic checks."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import Busy, InvalidAuth, PveUpdateApi, PveUpdateError
from .const import (
    CONF_CHECK_INTERVAL,
    DEFAULT_CHECK_INTERVAL,
    DOMAIN,
    FAST_SCAN_INTERVAL,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class PveUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Fetches /api/status; data is the status dict from pveupdate."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: PveUpdateApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.get_status()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PveUpdateError as err:
            raise UpdateFailed(f"Cannot reach pveupdate: {err}") from err

        self.update_interval = FAST_SCAN_INTERVAL if data.get("running") else SCAN_INTERVAL

        if not data.get("running") and self._check_due(data.get("checked_at")):
            try:
                await self.api.check()
                data["running"] = True
                data["activity"] = "checking"
                self.update_interval = FAST_SCAN_INTERVAL
            except Busy:
                pass
            except PveUpdateError as err:
                _LOGGER.warning("Could not start a check: %s", err)
        return data

    def _check_due(self, checked_at: str | None) -> bool:
        hours = self.config_entry.options.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL)
        if not hours:
            return False
        last = dt_util.parse_datetime(checked_at) if checked_at else None
        return last is None or dt_util.utcnow() - last >= timedelta(hours=hours)

    def guest(self, gid: str) -> dict | None:
        return (self.data or {}).get("guests", {}).get(gid)
