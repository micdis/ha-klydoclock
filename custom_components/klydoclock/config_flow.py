"""Config flow for the Klydoclock integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv

from . import async_get_adb
from .adb import KlydoConnectionError, KlydoRootError
from .const import DEFAULT_PORT, DOMAIN, PACKAGE, SETTINGS_PATH

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
    }
)


class KlydoclockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Klydoclock."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address of the clock and verify it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            adb = await async_get_adb(self.hass, host, port)
            serial = None
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

            if not errors:
                await self.async_set_unique_id(serial or host)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title="Klydoclock", data={CONF_HOST: host, CONF_PORT: port}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )
