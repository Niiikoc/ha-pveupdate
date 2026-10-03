"""Pictures for guests, from the selfh.st icon set (https://selfh.st/icons)."""

from __future__ import annotations

import asyncio
import re

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

ICON_URL = "https://cdn.jsdelivr.net/gh/selfhst/icons/png/{}.png"

# Guest or app names whose icon has a different name in the icon set.
ALIASES = {
    "mqtt": "mosquitto",
    "pihole": "pi-hole",
    "adguard": "adguard-home",
    "homeassistant": "home-assistant",
    "haos": "home-assistant",
    "alpine": "alpine-linux",
}


def slugify(name: str | None) -> str | None:
    if not name:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return ALIASES.get(slug, slug) or None


def candidates(guest: dict) -> list[str]:
    """Icon names to try, best first: the app, the guest's name, then its OS."""
    os_name = (guest.get("os") or "").split(" ")[0]
    names = [slugify(n) for n in (guest.get("app"), guest.get("name"), os_name)]
    return list(dict.fromkeys(n for n in names if n))


async def async_guest_picture(hass: HomeAssistant, guest: dict) -> str | None:
    """URL of the first icon that exists, or None to keep the integration's icon."""
    cache: dict[str, bool] = hass.data.setdefault(f"{DOMAIN}_icons", {})
    session = async_get_clientsession(hass)
    for name in candidates(guest):
        if name not in cache:
            try:
                async with session.head(
                    ICON_URL.format(name), timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    cache[name] = resp.status == 200
            except (aiohttp.ClientError, asyncio.TimeoutError):
                continue  # offline: try again next time
        if cache[name]:
            return ICON_URL.format(name)
    return None
