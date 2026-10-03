"""Client for the pveupdate HTTP API (`pveupdate serve` on the Proxmox host)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class PveUpdateError(Exception):
    """Base error."""


class CannotConnect(PveUpdateError):
    """The host could not be reached."""


class InvalidAuth(PveUpdateError):
    """The token was rejected."""


class Busy(PveUpdateError):
    """A check or update is already running."""


class PveUpdateApi:
    """Talks to `pveupdate serve`."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str) -> None:
        self._session = session
        self._base = f"http://{host}:{port}/api"
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, json: Any = None) -> dict:
        try:
            async with asyncio.timeout(15):
                resp = await self._session.request(
                    method, f"{self._base}/{path}", headers=self._headers, json=json
                )
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CannotConnect(str(err)) from err
        if resp.status == 401:
            raise InvalidAuth(data.get("error", "invalid token"))
        if resp.status == 409:
            raise Busy(data.get("error", "busy"))
        if resp.status >= 400:
            raise PveUpdateError(data.get("error", f"HTTP {resp.status}"))
        return data

    async def get_status(self) -> dict:
        return await self._request("GET", "status")

    async def get_log(self) -> str:
        return (await self._request("GET", "log")).get("log", "")

    async def check(self) -> None:
        await self._request("POST", "check")

    async def update(self, guests: list[str] | str) -> None:
        """guests: a list of guest IDs, or "pending" / "all"."""
        await self._request("POST", "update", json={"guests": guests})
