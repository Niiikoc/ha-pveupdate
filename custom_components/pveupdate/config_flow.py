"""Config flow: host, port and token of `pveupdate serve`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Busy, CannotConnect, InvalidAuth, PveUpdateApi, PveUpdateError
from .const import CONF_CHECK_INTERVAL, CONF_GUESTS, DEFAULT_CHECK_INTERVAL, DEFAULT_PORT, DOMAIN


async def _validate(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str]:
    api = PveUpdateApi(async_get_clientsession(hass), data[CONF_HOST], data[CONF_PORT], data[CONF_TOKEN])
    try:
        await api.get_status()
    except InvalidAuth:
        return {"base": "invalid_auth"}
    except CannotConnect:
        return {"base": "cannot_connect"}
    except PveUpdateError:
        return {"base": "unknown"}
    return {}


class PveUpdateConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title=f"Proxmox {user_input[CONF_HOST]}", data=user_input)
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
            errors = await _validate(self.hass, data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PveUpdateOptionsFlow()


class PveUpdateOptionsFlow(OptionsFlow):
    """Check interval, and which guests pveupdate tracks (stored on the host)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        api = self.config_entry.runtime_data.api
        errors: dict[str, str] = {}
        try:
            guests = await api.get_guests()
        except PveUpdateError:
            guests = None
            errors["base"] = "cannot_list_guests"

        if user_input is not None and guests is not None:
            chosen = user_input.pop(CONF_GUESTS, None)
            tracked = {g["id"] for g in guests if g["tracked"]}
            if chosen is not None and set(chosen) != tracked:
                try:
                    await api.set_tracked(sorted(chosen, key=int))
                except Busy:
                    errors["base"] = "busy"
                except PveUpdateError:
                    errors["base"] = "unknown"
                else:
                    if set(chosen) - tracked:
                        # Check the new guests right away so they don't sit at "unchecked".
                        try:
                            await api.check()
                        except PveUpdateError:
                            pass
                    await self.config_entry.runtime_data.async_request_refresh()
            if not errors:
                return self.async_create_entry(data=user_input)
        elif user_input is not None:
            # Host unreachable: still save the interval.
            user_input.pop(CONF_GUESTS, None)
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL)
        fields: dict[Any, Any] = {}
        if guests is not None:
            choices = {
                g["id"]: f"{g['id']} {g['name']} ({'LXC' if g['type'] == 'lxc' else 'VM'})" for g in guests
            }
            fields[vol.Optional(CONF_GUESTS, default=[g["id"] for g in guests if g["tracked"]])] = (
                cv.multi_select(choices)
            )
        fields[vol.Required(CONF_CHECK_INTERVAL, default=current)] = vol.All(int, vol.Range(min=0, max=168))
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)
