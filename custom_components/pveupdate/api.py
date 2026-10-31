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


class TokenWithoutCertificate(InvalidAuth):
    """The token has no certificate fingerprint: it comes from before pveupdate 0.8.0."""


class Busy(PveUpdateError):
    """A check or update is already running."""


class PveUpdateApi:
    """Talks to `pveupdate serve`."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str) -> None:
        # `pveupdate token` prints "<token>.<certificate fingerprint>". The token
        # only ever goes over HTTPS to that certificate, so a fingerprint is required.
        token, _, fingerprint = token.partition(".")
        if not fingerprint:
            raise TokenWithoutCertificate("the token has no certificate fingerprint; pveupdate 0.8.0 or later is needed")
        try:
            self._ssl = aiohttp.Fingerprint(bytes.fromhex(fingerprint))
        except ValueError as err:
            raise InvalidAuth("malformed token") from err
        self._session = session
        self._base = f"https://{host}:{port}/api"
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, json: Any = None) -> dict:
        try:
            async with asyncio.timeout(15):
                resp = await self._session.request(
                    method, f"{self._base}/{path}", headers=self._headers, json=json, ssl=self._ssl
                )
                data = await resp.json(content_type=None)
        except aiohttp.ServerFingerprintMismatch as err:
            raise InvalidAuth("the host's certificate does not match the token") from err
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

    async def update(self, guests: list[str] | str, part: str = "all") -> None:
        """guests: a list of guest IDs, or "pending" / "all". part: "all", "os" or "app"."""
        body: dict[str, Any] = {"guests": guests}
        if part != "all":
            body["part"] = part
        await self._request("POST", "update", json=body)

    async def get_guests(self) -> list[dict]:
        """Every LXC and VM on the node, each with a "tracked" flag."""
        return (await self._request("GET", "guests")).get("guests", [])

    async def set_tracked(self, guests: list[str]) -> None:
        """Track exactly these guest IDs."""
        await self._request("POST", "track", json={"guests": guests})
