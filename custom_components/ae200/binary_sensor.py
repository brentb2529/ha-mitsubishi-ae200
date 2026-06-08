"""Binary sensor platform for AE-200E / EW-50E."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AE200Coordinator
from .entity import AE200GroupEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: AE200Coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for group in coordinator.groups:
        entities.append(AE200FilterSensor(coordinator, group))
        entities.append(AE200ErrorSensor(coordinator, group))

    async_add_entities(entities)


class AE200FilterSensor(AE200GroupEntity, BinarySensorEntity):
    """Filter maintenance required for a control group."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Filter"

    def __init__(self, coordinator: AE200Coordinator, group) -> None:
        super().__init__(coordinator, group)
        host = coordinator.config_entry.data["host"]
        self._attr_unique_id = f"ae200_{host}_{group.group_id}_filter"

    @property
    def is_on(self) -> bool | None:
        s = self._state
        return s.filter_sign if s else None


class AE200ErrorSensor(AE200GroupEntity, BinarySensorEntity):
    """Active fault/error for a control group."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Error"

    def __init__(self, coordinator: AE200Coordinator, group) -> None:
        super().__init__(coordinator, group)
        host = coordinator.config_entry.data["host"]
        self._attr_unique_id = f"ae200_{host}_{group.group_id}_error"

    @property
    def is_on(self) -> bool | None:
        s = self._state
        return s.error_sign if s else None
