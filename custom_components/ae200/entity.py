"""Base entity classes for the AE-200E / EW-50E integration.

Device registry model:
  - One device per controller (AE-200E or EW-50E), identified by (DOMAIN, entry_id).
    Using the config-entry ID (not the host string) means the device survives a host
    rename / IP change without losing history.
  - One device per indoor group, identified by (DOMAIN, f"{entry_id}_{group_id}"),
    with via_device pointing to the controller device.

Unique ID namespacing:
  All unique_ids are prefixed by entry_id so that multiple config entries
  (multiple controllers) never collide even if group_ids happen to be identical
  across controllers.
"""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ae200client import GroupInfo
from .const import DOMAIN, MANUFACTURER, MODEL_CONTROLLER, MODEL_GROUP
from .coordinator import AE200Coordinator


class AE200ControllerEntity(CoordinatorEntity[AE200Coordinator]):
    """Base for entities attached to the controller device (e.g. outdoor temp)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AE200Coordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        host = coordinator.config_entry.data["host"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=f"AE-200E ({host})",
            manufacturer=MANUFACTURER,
            model=MODEL_CONTROLLER,
            configuration_url=f"http://{host}/",
        )


class AE200GroupEntity(CoordinatorEntity[AE200Coordinator]):
    """Base for entities attached to a single indoor group device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AE200Coordinator, group: GroupInfo) -> None:
        super().__init__(coordinator)
        self._group_id = group.group_id
        self._group_name = group.name
        entry_id = coordinator.config_entry.entry_id

        # Device for the group — child of the controller device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{group.group_id}")},
            name=group.name,
            manufacturer=MANUFACTURER,
            model=MODEL_GROUP,
            via_device=(DOMAIN, entry_id),
        )

    @property
    def _state(self):
        """Return the GroupState for this group, or None if unavailable."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.state_for(self._group_id)

    @property
    def available(self) -> bool:
        """Unavailable if the coordinator has no data or our group is absent."""
        return super().available and self._state is not None
