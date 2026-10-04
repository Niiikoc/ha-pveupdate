"""Base entities and device info."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PveUpdateCoordinator


def host_device(coordinator: PveUpdateCoordinator) -> DeviceInfo:
    entry = coordinator.config_entry
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Proxmox {entry.data[CONF_HOST]}",
        manufacturer="Proxmox",
        model="pveupdate",
        sw_version=(coordinator.data or {}).get("version"),
        configuration_url=f"https://{entry.data[CONF_HOST]}:8006",
    )


# First pveupdate that can update OS packages and the app separately.
MIN_PARTS_VERSION = (0, 7, 0)


def require_parts(coordinator: PveUpdateCoordinator) -> None:
    """Refuse OS-only or app-only updates on hosts that would run both."""
    version = (coordinator.data or {}).get("version") or "0"
    try:
        parsed = tuple(int(x) for x in version.split(".")[:3])
    except ValueError:
        parsed = (0,)
    if parsed < MIN_PARTS_VERSION:
        raise HomeAssistantError(
            f"pveupdate {version} on the host can't update the OS and the app separately. "
            "Update it to 0.7.0 or later."
        )


class HostEntity(CoordinatorEntity[PveUpdateCoordinator]):
    """Entity on the Proxmox host device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PveUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = host_device(coordinator)


class GuestEntity(CoordinatorEntity[PveUpdateCoordinator]):
    """Entity on one guest's device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PveUpdateCoordinator, gid: str, key: str) -> None:
        super().__init__(coordinator)
        self.gid = gid
        entry_id = coordinator.config_entry.entry_id
        guest = coordinator.guest(gid) or {}
        self._attr_unique_id = f"{entry_id}_{gid}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{gid}")},
            name=guest.get("name") or f"Guest {gid}",
            manufacturer="Proxmox",
            model="LXC container" if guest.get("type") == "lxc" else "Virtual machine",
            serial_number=gid,
            via_device=(DOMAIN, entry_id),
        )

    @property
    def guest(self) -> dict:
        return self.coordinator.guest(self.gid) or {}

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.guest(self.gid) is not None
