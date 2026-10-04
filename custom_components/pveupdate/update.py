"""One update entity per tracked guest that has an app: app updates only.

OS packages are updated with the guest's "Update OS" button instead, so they
never show up under Settings > Updates.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PveUpdateConfigEntry
from .api import Busy, PveUpdateError
from .const import DOMAIN
from .entity import GuestEntity, require_parts
from .icons import async_guest_picture


async def async_setup_entry(
    hass: HomeAssistant, entry: PveUpdateConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        guests = (coordinator.data or {}).get("guests", {})
        with_app = {gid for gid, g in guests.items() if g.get("app")}
        # Guests without an app had an update entity in 0.2.x; drop it.
        registry = er.async_get(hass)
        for gid in set(guests) - with_app:
            entity_id = registry.async_get_entity_id("update", DOMAIN, f"{entry.entry_id}_{gid}_update")
            if entity_id:
                registry.async_remove(entity_id)
        # Forget the rest so they get a new entity if they come back.
        known.intersection_update(with_app)
        new = [gid for gid in guests if gid in with_app and gid not in known]
        known.update(new)
        if new:
            async_add_entities(GuestUpdate(coordinator, gid) for gid in new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class GuestUpdate(GuestEntity, UpdateEntity):
    """The app of one LXC/VM as a Home Assistant update."""

    _attr_name = None  # use the device (guest) name
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, coordinator, gid: str) -> None:
        super().__init__(coordinator, gid, "update")
        self._picture: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Looked up in the background so a slow or offline CDN never delays setup.
        self.hass.async_create_task(self._async_load_picture())

    async def _async_load_picture(self) -> None:
        self._picture = await async_guest_picture(self.hass, self.guest)
        if self._picture:
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return super().available and bool(self.guest.get("app"))

    @property
    def entity_picture(self) -> str | None:
        # Falls back to the integration's own icon.
        return self._picture or super().entity_picture

    @property
    def title(self) -> str | None:
        return self.guest.get("app") or self.guest.get("name")

    @property
    def installed_version(self) -> str | None:
        # Apps whose version can't be read show the guest's OS version instead.
        g = self.guest
        return g.get("app_installed") or g.get("os") or "unknown"

    @property
    def latest_version(self) -> str | None:
        g = self.guest
        if g.get("app_update") and g.get("app_latest"):
            return g["app_latest"]
        return self.installed_version

    @property
    def release_summary(self) -> str | None:
        g = self.guest
        parts = []
        if g.get("app_update"):
            parts.append(f"{g.get('app')} {g.get('app_installed')} → {g.get('app_latest')}")
        if g.get("state") == "error":
            parts.append(f"last check failed: {g.get('error', '')}")
        if g.get("last_result") in ("failed", "skipped"):
            parts.append(f"last update {g['last_result']}: {g.get('last_detail') or 'unknown reason'}")
        return ". ".join(parts)[:255] or None

    def _covers_app(self) -> bool:
        # An OS-only update of this guest isn't shown here.
        return (self.coordinator.data or {}).get("updating_part") != "os"

    @property
    def in_progress(self) -> bool:
        data = self.coordinator.data or {}
        running = data.get("updating") == self.gid or self.gid in (data.get("queue") or [])
        return running and self._covers_app()

    @property
    def update_percentage(self) -> int | None:
        """Progress of this guest's update; None while queued (or on older hosts)."""
        data = self.coordinator.data or {}
        if data.get("updating") != self.gid or not self._covers_app():
            return None
        return data.get("progress")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        g = self.guest
        return {
            "guest_id": self.gid,
            "guest_type": g.get("type"),
            "state": g.get("state"),
            "checked_at": g.get("checked_at"),
            "last_update": g.get("last_update"),
            "last_result": g.get("last_result"),
            "last_detail": g.get("last_detail"),
            "update_step": (self.coordinator.data or {}).get("step") if self.in_progress else None,
        }

    async def async_release_notes(self) -> str | None:
        g = self.guest
        lines = []
        if g.get("app_update"):
            lines.append(f"**{g.get('app')}**: {g.get('app_installed')} → {g.get('app_latest')}\n")
        lines.append(
            "Installing takes a snapshot first (if enabled for this guest), then runs the app's update. "
            "OS packages are not touched; use the guest's *Update OS* button for those."
        )
        return "\n".join(lines)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        require_parts(self.coordinator)
        try:
            await self.coordinator.api.update([self.gid], part="app")
        except Busy as err:
            raise HomeAssistantError("Another check or update is already running on the host") from err
        except PveUpdateError as err:
            raise HomeAssistantError(f"Could not start the update: {err}") from err
        await self.coordinator.async_request_refresh()
