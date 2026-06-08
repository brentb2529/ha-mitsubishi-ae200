"""Diagnostics support for AE-200E / EW-50E.

The diagnostics dump is used for:
- Confirming real AirDirection / FilterSign / ErrorSign field values on hardware.
- Validating that the integration sees all expected groups and fields.
- Troubleshooting connectivity and parsing issues.

Sensitive data redaction:
- The host/IP is redacted (replaced with "**REDACTED**").
- No credentials are stored by this integration (protocol is unauthenticated).
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AE200Coordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: AE200Coordinator = hass.data[DOMAIN][entry.entry_id]

    groups_info = [
        {"group_id": g.group_id, "name": g.name}
        for g in coordinator.groups
    ]

    states_dump: dict[str, Any] = {}
    if coordinator.data is not None:
        for gid, state in coordinator.data.states.items():
            states_dump[gid] = state.diagnostics_dict()

    return {
        "entry": {
            "title": entry.title,
            "host": "**REDACTED**",
            "version": entry.version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        },
        "groups": groups_info,
        "states": states_dump,
        # NOTE: The 'states' section contains raw field values from the controller.
        # Review AirDirection, FilterSign, and ErrorSign values here to confirm
        # the ASSUMED encoding constants in const.py against real hardware.
    }
