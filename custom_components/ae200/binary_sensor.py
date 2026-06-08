"""Binary sensor platform for AE-200E / EW-50E."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up binary sensor entities from a config entry."""
    coordinator: AE200Coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for group in coordinator.groups:
        entities.append(AE200FilterSensor(coordinator, group))
        entities.append(AE200ErrorSensor(coordinator, group))

    async_add_entities(entities)


class AE200FilterSensor(AE200GroupEntity, BinarySensorEntity):
    """Filter maintenance required for a control group.

    True = filter cleaning is due (FilterSign is set).
    Marked diagnostic — it is maintenance context, not control state.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Filter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AE200Coordinator, group) -> None:
        super().__init__(coordinator, group)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{group.group_id}_filter"

    @property
    def is_on(self) -> bool | None:
        s = self._state
        return s.filter_sign if s else None


class AE200ErrorSensor(AE200GroupEntity, BinarySensorEntity):
    """Active fault / error code for a control group.

    True = an error is active (ErrorSign is set).
    Marked diagnostic — it is fault context, not control state.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Error"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AE200Coordinator, group) -> None:
        super().__init__(coordinator, group)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{group.group_id}_error"

    @property
    def is_on(self) -> bool | None:
        s = self._state
        return s.error_sign if s else None
