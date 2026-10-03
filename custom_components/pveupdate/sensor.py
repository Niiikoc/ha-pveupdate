"""Sensors on the Proxmox host device."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PveUpdateConfigEntry
from .entity import HostEntity


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


class PendingSensor(HostEntity, SensorEntity):
    _attr_icon = "mdi:package-up"
    _attr_native_unit_of_measurement = "guests"

    @property
    def native_value(self) -> int:
        return self.coordinator.data.get("pending_guests", 0)

    @property
    def extra_state_attributes(self) -> dict:
        return {"guest_ids": self.coordinator.data.get("pending_ids", "").split()}


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
