"""Sensor platform for AE-200E / EW-50E."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AE200Coordinator
from .entity import AE200ControllerEntity, AE200GroupEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: AE200Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = []

    # Per-controller sensors (attached to the controller device)
    entities.append(AE200OutdoorTempSensor(coordinator))

    # Per-group sensors (attached to each group device)
    for group in coordinator.groups:
        entities.append(AE200InletTempSensor(coordinator, group))

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Controller-level sensors
# ---------------------------------------------------------------------------

class AE200OutdoorTempSensor(AE200ControllerEntity, SensorEntity):
    """Outdoor temperature reported by the AE-200E controller.

    The outdoor temp is reported on group-level state records; we take the
    first non-None value across all groups (all report the same outdoor unit).
    Marked diagnostic because it is supplementary context, not primary control.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_name = "Outdoor Temperature"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AE200Coordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_outdoor_temp"

    @property
    def native_value(self) -> float | None:
        """Return outdoor temp from the first group that reports one."""
        if self.coordinator.data is None:
            return None
        for state in self.coordinator.data.states.values():
            t = state.outdoor_temp
            if t is not None:
                return t
        return None

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None


# ---------------------------------------------------------------------------
# Group-level sensors
# ---------------------------------------------------------------------------

class AE200InletTempSensor(AE200GroupEntity, SensorEntity):
    """Return-air inlet temperature for one control group.

    This is the primary measured temperature for the group — not diagnostic.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_name = "Inlet Temperature"

    def __init__(self, coordinator: AE200Coordinator, group) -> None:
        super().__init__(coordinator, group)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{group.group_id}_inlet_temp"

    @property
    def native_value(self) -> float | None:
        s = self._state
        return s.inlet_temp if s else None
