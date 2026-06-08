"""Base entity for AE-200E."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ae200client import GroupInfo
from .const import DOMAIN
from .coordinator import AE200Coordinator


class AE200ControllerEntity(CoordinatorEntity[AE200Coordinator]):
    """Entity bound to the controller device (e.g. outdoor temp)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AE200Coordinator) -> None:
        super().__init__(coordinator)
        host = coordinator.config_entry.data["host"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=f"AE-200E ({host})",
            manufacturer="Mitsubishi Electric",
            model="AE-200E / EW-50E",
        )


class AE200GroupEntity(CoordinatorEntity[AE200Coordinator]):
    """Entity bound to a single AE-200E control group."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AE200Coordinator, group: GroupInfo) -> None:
        super().__init__(coordinator)
        self._group_id = group.group_id
        self._group_name = group.name
        host = coordinator.config_entry.data["host"]

        # Device for the group — linked to the controller via via_device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}_{group.group_id}")},
            name=group.name,
            manufacturer="Mitsubishi Electric",
            model="City Multi Group",
            via_device=(DOMAIN, host),
        )

    @property
    def _state(self):
        """Return the GroupState for this group, or None if unavailable."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.state_for(self._group_id)

    @property
    def available(self) -> bool:
        return super().available and self._state is not None
