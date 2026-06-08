"""Config flow for AE-200E / EW-50E integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .ae200client import AE200Client
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(TextSelectorConfig(autocomplete="off")),
    }
)


class AE200ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AE-200E."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            # Prevent duplicate entries for the same host
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()

            client = AE200Client(host)
            try:
                groups = await client.async_get_groups()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Cannot connect to AE-200E at %s", host)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"AE-200E ({host})",
                    data={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
