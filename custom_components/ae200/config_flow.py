"""Config flow for AE-200E / EW-50E integration.

Supports multiple instances: each controller is a separate config entry,
uniquely identified by the lowercased host string.  Adding a second controller
on a different host creates a second entry without conflict.

Authentication: none — the LAN1 b_xmlproc interface is unauthenticated.
No reauth flow is required or registered.
"""
from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .ae200client import AE200Client
from .const import (
    CONF_TIMEOUT,
    DEFAULT_TIMEOUT,
    DOMAIN,
    TIMEOUT_MAX,
    TIMEOUT_MIN,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

# Matches strings that look like dotted-decimal IPs (to route them through
# ipaddress validation rather than the hostname regex).  Applied to the bare
# host after port stripping.
_IP_LIKE_RE = re.compile(r"^\d+(\.\d+){1,3}$")

# Matches plain hostnames and FQDNs (with optional :port).
# Dotted-IP-like strings are NOT matched here — they are handled by ipaddress.
_HOSTNAME_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?(:\d+)?$"
)


def _is_valid_host(host: str) -> bool:
    """Return True if *host* looks like a valid hostname or IP (with optional port).

    IP addresses (IPv4 and IPv6) are validated using the stdlib ipaddress module
    so that out-of-range octets such as 999.x.x.x are properly rejected.
    Strings that look like dotted-decimal addresses are rejected unless they pass
    ipaddress validation.  Hostnames and FQDNs are accepted if they consist of
    valid label characters.  An optional :port suffix is stripped before
    validation in both cases.
    """
    host = host.strip()
    if not host:
        return False

    # Strip optional :port suffix before IP/hostname checks.
    bare = host.rsplit(":", 1)[0] if ":" in host else host

    # Try strict IP validation first (rejects 999.x.x.x, etc.).
    try:
        ipaddress.ip_address(bare)
        return True
    except ValueError:
        pass

    # If the bare string looks like a dotted IP but failed validation, reject
    # it so that 999.999.999.999 is not silently accepted as a hostname.
    if _IP_LIKE_RE.match(bare):
        return False

    # Fall through to hostname regex for non-IP strings.
    return bool(_HOSTNAME_RE.match(host))


def _step_user_schema(host: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): TextSelector(
                TextSelectorConfig(autocomplete="off")
            ),
        }
    )


def _options_schema(current_timeout: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_TIMEOUT, default=current_timeout): NumberSelector(
                NumberSelectorConfig(
                    min=TIMEOUT_MIN,
                    max=TIMEOUT_MAX,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------


class AE200ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AE-200E / EW-50E.

    Multiple controllers are supported: each host gets its own config entry.
    The unique_id is the lowercased host, preventing duplicate entries for
    the exact same controller while allowing distinct controllers.

    No authentication is needed — LAN1 is unauthenticated.
    No reauth flow is registered.
    """

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AE200OptionsFlow:
        """Return the options flow handler."""
        return AE200OptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            if not _is_valid_host(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                # Prevent duplicate entries for the same host
                await self.async_set_unique_id(host.lower())
                self._abort_if_unique_id_configured()

                client = AE200Client(host)
                try:
                    groups = await client.async_get_groups()
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Cannot connect to AE-200E / EW-50E at %s", host
                    )
                    errors["base"] = "cannot_connect"
                else:
                    _LOGGER.debug(
                        "Connected to %s — found %d group(s)", host, len(groups)
                    )
                    return self.async_create_entry(
                        title=f"AE-200E ({host})",
                        data={CONF_HOST: host},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_step_user_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to change the host/IP without removing the entry.

        Updating the host preserves all entities, automations, and history
        associated with this config entry.
        """
        errors: dict[str, str] = {}
        current_host: str = self._get_reconfigure_entry().data.get(CONF_HOST, "")

        if user_input is not None:
            host = user_input[CONF_HOST].strip()

            if not _is_valid_host(host):
                errors[CONF_HOST] = "invalid_host"
            else:
                reconfigure_entry = self._get_reconfigure_entry()

                # Guard against configuring a host that belongs to a *different*
                # existing entry (duplicate).  Skip the check if the host matches
                # the entry being reconfigured (same host → allowed).
                if host.lower() != reconfigure_entry.unique_id:
                    await self.async_set_unique_id(host.lower())
                    self._abort_if_unique_id_configured()

                client = AE200Client(host)
                try:
                    await client.async_get_groups()
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Cannot connect to AE-200E / EW-50E at %s during reconfigure",
                        host,
                    )
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        title=f"AE-200E ({host})",
                        data_updates={CONF_HOST: host},
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_step_user_schema(host=current_host),
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class AE200OptionsFlow(OptionsFlow):
    """Handle options for an existing AE-200E / EW-50E config entry.

    Configurable options:
      - Connection timeout (seconds): how long to wait for a WebSocket
        response from the controller before treating it as unreachable.
        Useful for controllers on slower/lossy LAN segments.

    Note: poll interval is intentionally NOT user-configurable.  The 30 s
    default is appropriate for HVAC state and aligns with HA quality-scale
    guidance (scan_interval must not be exposed in the UI).
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        current_timeout: int = self._config_entry.options.get(
            CONF_TIMEOUT, DEFAULT_TIMEOUT
        )

        if user_input is not None:
            timeout = int(user_input[CONF_TIMEOUT])
            return self.async_create_entry(
                title="",
                data={CONF_TIMEOUT: timeout},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(current_timeout),
        )
