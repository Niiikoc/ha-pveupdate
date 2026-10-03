"""One update entity per tracked guest."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PveUpdateConfigEntry
from .api import Busy, PveUpdateError
from .entity import GuestEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PveUpdateConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        new = [gid for gid in (coordinator.data or {}).get("guests", {}) if gid not in known]
        known.update(new)
        if new:
            async_add_entities(GuestUpdate(coordinator, gid) for gid in new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class GuestUpdate(GuestEntity, UpdateEntity):
    """OS packages + app of one LXC/VM as a Home Assistant update."""

    _attr_name = None  # use the device (guest) name
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, coordinator, gid: str) -> None:
        super().__init__(coordinator, gid, "update")

    @property
    def title(self) -> str | None:
        return self.guest.get("app") or self.guest.get("name")

    @property
    def installed_version(self) -> str | None:
        g = self.guest
        return g.get("app_installed") or g.get("os") or "current"

    @property
    def latest_version(self) -> str | None:
        g = self.guest
        installed = self.installed_version
        if not g.get("pending"):
            return installed
        base = g.get("app_latest") if g.get("app_update") else installed
        n = g.get("packages", 0)
        return f"{base} + {n} packages" if n else base

    @property
    def release_summary(self) -> str | None:
        g = self.guest
        parts = []
        if g.get("app_update"):
            parts.append(f"{g.get('app')} {g.get('app_installed')} → {g.get('app_latest')}")
        if g.get("packages"):
            parts.append(f"{g['packages']} OS package updates")
        if g.get("reboot_required"):
            parts.append("reboot required")
        if g.get("state") == "error":
            parts.append(f"last check failed: {g.get('error', '')}")
        if g.get("last_result") in ("failed", "skipped"):
            parts.append(f"last update {g['last_result']}: {g.get('last_detail') or 'unknown reason'}")
        return ". ".join(parts)[:255] or None

    @property
    def in_progress(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("updating") == self.gid or self.gid in (data.get("queue") or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        g = self.guest
        return {
            "guest_id": self.gid,
            "guest_type": g.get("type"),
            "state": g.get("state"),
            "os": g.get("os"),
            "packages": g.get("packages", 0),
            "reboot_required": g.get("reboot_required", False),
            "checked_at": g.get("checked_at"),
            "last_update": g.get("last_update"),
            "last_result": g.get("last_result"),
            "last_detail": g.get("last_detail"),
        }

    async def async_release_notes(self) -> str | None:
        g = self.guest
        lines = []
        if g.get("app_update"):
            lines.append(f"**{g.get('app')}**: {g.get('app_installed')} → {g.get('app_latest')}\n")
        names = g.get("package_names") or []
        if names:
            lines.append(f"**{len(names)} OS packages:**\n")
            lines.append(", ".join(f"`{n}`" for n in names))
        lines.append(
            "\nInstalling takes a snapshot first (if enabled for this guest), "
            "then updates OS packages and the app."
        )
        return "\n".join(lines)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        try:
            await self.coordinator.api.update([self.gid])
        except Busy as err:
            raise HomeAssistantError("Another check or update is already running on the host") from err
        except PveUpdateError as err:
            raise HomeAssistantError(f"Could not start the update: {err}") from err
        await self.coordinator.async_request_refresh()
