"""Sensors on the Proxmox host device, and pending OS packages per guest."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PveUpdateConfigEntry
from .entity import GuestEntity, HostEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PveUpdateConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            PendingSensor(coordinator, "pending_guests"),
            LastCheckSensor(coordinator, "last_check"),
            ActivitySensor(coordinator, "activity"),
        ]
    )
    known: set[str] = set()

    @callback
    def add_new() -> None:
        guests = (coordinator.data or {}).get("guests", {})
        known.intersection_update(guests)
        new = [gid for gid in guests if gid not in known]
        known.update(new)
        if new:
            async_add_entities(OsUpdatesSensor(coordinator, gid) for gid in new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PendingSensor(HostEntity, SensorEntity):
    """Guests with an app update, the same ones listed under Settings > Updates."""

    _attr_icon = "mdi:package-up"
    _attr_native_unit_of_measurement = "guests"

    def _ids(self) -> list[str]:
        guests = self.coordinator.data.get("guests", {})
        return [gid for gid, g in guests.items() if g.get("app_update")]

    @property
    def native_value(self) -> int:
        return len(self._ids())

    @property
    def extra_state_attributes(self) -> dict:
        return {"guest_ids": self._ids()}


class LastCheckSensor(HostEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        checked = self.coordinator.data.get("checked_at")
        return dt_util.parse_datetime(checked) if checked else None


class ActivitySensor(HostEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "checking", "updating"]
    _attr_icon = "mdi:progress-clock"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        return (data.get("activity") or "idle") if data.get("running") else "idle"


class OsUpdatesSensor(GuestEntity, SensorEntity):
    """Pending OS package updates of one guest."""

    _attr_icon = "mdi:package-variant"
    _attr_native_unit_of_measurement = "packages"
    _attr_translation_key = "os_updates"

    def __init__(self, coordinator, gid: str) -> None:
        super().__init__(coordinator, gid, "os_updates")

    @property
    def native_value(self) -> int | None:
        g = self.guest
        return None if g.get("state") in (None, "unchecked", "stopped", "error") else g.get("packages", 0)

    @property
    def extra_state_attributes(self) -> dict:
        g = self.guest
        data = self.coordinator.data or {}
        return {
            "security_packages": g.get("security_packages", 0),
            "package_names": g.get("package_names", []),
            "os": g.get("os"),
            "os_latest": g.get("os_latest"),
            "reboot_required": g.get("reboot_required", False),
            "updating": data.get("updating") == self.gid and data.get("updating_part") in ("os", "all"),
        }
