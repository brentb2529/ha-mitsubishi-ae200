"""DataUpdateCoordinator for AE-200E / EW-50E."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ae200client import AE200Client, GroupInfo, GroupState
from .const import CONF_TIMEOUT, DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AE200CoordinatorData:
    """Immutable snapshot of one poll cycle."""

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
    """Polls all groups on one AE-200E / EW-50E in a single round-trip per interval.

    Each config entry has its own coordinator instance.  Multiple entries
    (multiple controllers) therefore never share state.
    """

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        timeout: int = entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        self._client = AE200Client(entry.data[CONF_HOST], timeout=float(timeout))
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
        """Fetch latest state from the controller.

        Raises UpdateFailed on communication error, which causes the coordinator
        to mark all entities unavailable until the next successful poll.
        """
        try:
            # Discover groups on first run; cache for subsequent polls.
            # Re-discover if the cache is empty (e.g. after a reload).
            if self._groups is None:
                self._groups = await self._client.async_get_groups()
                _LOGGER.debug(
                    "Discovered %d group(s) on %s: %s",
                    len(self._groups),
                    self.config_entry.data[CONF_HOST],
                    [g.group_id for g in self._groups],
                )

            group_ids = [g.group_id for g in self._groups]
            states = await self._client.async_get_states(group_ids)

        except Exception as err:
            raise UpdateFailed(
                f"AE-200E / EW-50E communication error on "
                f"{self.config_entry.data[CONF_HOST]}: {err}"
            ) from err

        return AE200CoordinatorData(groups=self._groups, states=states)
