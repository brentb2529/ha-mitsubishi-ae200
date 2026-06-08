"""DataUpdateCoordinator for AE-200E."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ae200client import AE200Client, GroupInfo, GroupState
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class AE200CoordinatorData:
    """Container for coordinator data snapshot."""

    def __init__(
        self,
        groups: list[GroupInfo],
        states: dict[str, GroupState],
    ) -> None:
        self.groups = groups
        self.states = states  # keyed by group_id

    def state_for(self, group_id: str) -> GroupState | None:
        return self.states.get(group_id)


class AE200Coordinator(DataUpdateCoordinator[AE200CoordinatorData]):
    """Polls all groups on the AE-200E in a single round-trip per interval."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._client = AE200Client(entry.data[CONF_HOST])
        self._groups: list[GroupInfo] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_HOST]}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    @property
    def client(self) -> AE200Client:
        return self._client

    @property
    def groups(self) -> list[GroupInfo]:
        return self._groups or []

    async def _async_update_data(self) -> AE200CoordinatorData:
        """Fetch latest state from the controller."""
        try:
            # Discover groups on first run; cache for subsequent polls
            if self._groups is None:
                self._groups = await self._client.async_get_groups()
                _LOGGER.debug(
                    "Discovered %d groups: %s",
                    len(self._groups),
                    [g.group_id for g in self._groups],
                )

            group_ids = [g.group_id for g in self._groups]
            states = await self._client.async_get_states(group_ids)

        except Exception as err:
            raise UpdateFailed(f"AE-200E communication error: {err}") from err

        return AE200CoordinatorData(groups=self._groups, states=states)
