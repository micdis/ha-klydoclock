"""Config flow for the Klydoclock integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import async_get_adb
from .adb import KlydoConnectionError, KlydoRootError
from .const import CONF_MDNS, DEFAULT_PORT, DOMAIN, PACKAGE, SETTINGS_PATH
from .mdns import name_matches_serial

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_MDNS, default=True): cv.boolean,
    }
)


class KlydoclockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Klydoclock."""

    VERSION = 1

    async def _async_validate(
        self, host: str, port: int, use_mdns: bool
    ) -> tuple[str | None, int, dict[str, str]]:
        """Check that a Klydoclock answers at host:port.

        Return (serial, port, errors); with mDNS, port is the one that answered.
        """
        errors: dict[str, str] = {}
        serial = None
        adb = await async_get_adb(self.hass, host, port, use_mdns)
        try:
            if PACKAGE not in await adb.shell(f"pm path {PACKAGE}"):
                errors["base"] = "not_klydoclock"
            elif not await adb.read_file(SETTINGS_PATH):
                errors["base"] = "no_root"
            else:
                serial = await adb.shell("getprop ro.serialno")
        except KlydoRootError:
            errors["base"] = "no_root"
        except KlydoConnectionError as err:
            _LOGGER.debug("Connection to %s failed: %s", host, err)
            errors["base"] = "cannot_connect"
        finally:
            await adb.close()
        return serial, adb.port, errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address of the clock and verify it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            use_mdns = user_input[CONF_MDNS]
            serial, port, errors = await self._async_validate(
                host, user_input[CONF_PORT], use_mdns
            )
            if not errors:
                data = {CONF_HOST: host, CONF_PORT: port, CONF_MDNS: use_mdns}
                await self.async_set_unique_id(serial or host)
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(title="Klydoclock", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Follow the ADB address a configured clock announces.

        The clock announces itself as ``adb-<serial>``, and the serial is the
        config entry's unique id, so the entry is found by name even if the
        clock's IP address changed; entries without a serial are matched by
        address. Every Android device with network ADB announces itself the
        same way, and probing one would mean connecting (and asking for root)
        to devices that are not clocks. So announcements only update clocks
        that are already set up; new clocks are added by address.
        """
        host = discovery_info.host
        port = discovery_info.port
        for entry in self._async_current_entries(include_ignore=False):
            serial = entry.unique_id
            by_serial = bool(
                serial
                and serial != entry.data.get(CONF_HOST)
                and name_matches_serial(
                    discovery_info.name, discovery_info.type, serial
                )
            )
            if not by_serial and entry.data.get(CONF_HOST) != host:
                continue
            new = {CONF_HOST: host, CONF_PORT: port} if by_serial else {CONF_PORT: port}
            if (
                port
                and entry.data.get(CONF_MDNS)
                and any(entry.data.get(k) != v for k, v in new.items())
            ):
                _LOGGER.debug("%s announces ADB at %s:%s", entry.title, host, port)
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, **new}
                )
                # Takes effect the next time the client connects; it looks the
                # address up itself as well when the stored one stops answering.
            return self.async_abort(reason="already_configured")
        return self.async_abort(reason="not_klydoclock")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of an already configured clock."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            use_mdns = user_input[CONF_MDNS]
            serial, port, errors = await self._async_validate(
                host, user_input[CONF_PORT], use_mdns
            )
            if not errors:
                await self.async_set_unique_id(serial or host)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: host, CONF_PORT: port, CONF_MDNS: use_mdns},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA,
                user_input
                or {
                    CONF_HOST: entry.data[CONF_HOST],
                    CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
                    CONF_MDNS: entry.data.get(CONF_MDNS, False),
                },
            ),
            errors=errors,
        )
