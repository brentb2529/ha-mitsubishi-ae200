"""Climate platform for AE-200E / EW-50E."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    DRIVE_ON,
    DRIVE_OFF,
    MODE_HEAT,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_AUTO,
    FAN_MODES,
    SWING_MODES,
    FALLBACK_MIN_TEMP,
    FALLBACK_MAX_TEMP,
    TEMP_STEP,
)
from .coordinator import AE200Coordinator
from .entity import AE200GroupEntity

_LOGGER = logging.getLogger(__name__)

# HA -> AE-200E mode translation  [CONFIRMED from natevoci/ae200]
_HA_TO_AE200_MODE: dict[HVACMode, str] = {
    HVACMode.HEAT: MODE_HEAT,
    HVACMode.COOL: MODE_COOL,
    HVACMode.DRY: MODE_DRY,
    HVACMode.FAN_ONLY: MODE_FAN,
    HVACMode.AUTO: MODE_AUTO,
}

_AE200_TO_HA_MODE: dict[str, HVACMode] = {v: k for k, v in _HA_TO_AE200_MODE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities from config entry."""
    coordinator: AE200Coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        AE200Climate(coordinator, group)
        for group in coordinator.groups
    )


class AE200Climate(AE200GroupEntity, ClimateEntity):
    """Climate entity for one AE-200E control group."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.AUTO,
    ]
    _attr_fan_modes = FAN_MODES
    _attr_swing_modes = SWING_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: AE200Coordinator, group) -> None:
        super().__init__(coordinator, group)
        host = coordinator.config_entry.data["host"]
        # Stable unique_id: domain + host + group_id [rename-safe]
        self._attr_unique_id = f"ae200_{host}_{group.group_id}_climate"
        self._attr_name = "Climate"

    # ------------------------------------------------------------------
    # State properties
    # ------------------------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode | None:
        s = self._state
        if s is None:
            return None
        if not s.is_on:
            return HVACMode.OFF
        return _AE200_TO_HA_MODE.get(s.mode or "", HVACMode.AUTO)

    @property
    def current_temperature(self) -> float | None:
        s = self._state
        return s.inlet_temp if s else None

    @property
    def target_temperature(self) -> float | None:
        s = self._state
        return s.set_temp if s else None

    @property
    def fan_mode(self) -> str | None:
        s = self._state
        return s.fan_speed if s else None

    @property
    def swing_mode(self) -> str | None:
        s = self._state
        return s.air_direction if s else None

    @property
    def min_temp(self) -> float:
        """Return mode-specific minimum setpoint from the controller, falling back to default."""
        s = self._state
        if s is None:
            return FALLBACK_MIN_TEMP
        mode = (s.mode or "").upper()
        if mode == MODE_HEAT:
            return s.heat_min or FALLBACK_MIN_TEMP
        if mode == MODE_COOL:
            return s.cool_min or FALLBACK_MIN_TEMP
        if mode == MODE_AUTO:
            return s.auto_min or FALLBACK_MIN_TEMP
        return FALLBACK_MIN_TEMP

    @property
    def max_temp(self) -> float:
        """Return mode-specific maximum setpoint from the controller, falling back to default."""
        s = self._state
        if s is None:
            return FALLBACK_MAX_TEMP
        mode = (s.mode or "").upper()
        if mode == MODE_HEAT:
            return s.heat_max or FALLBACK_MAX_TEMP
        if mode == MODE_COOL:
            return s.cool_max or FALLBACK_MAX_TEMP
        if mode == MODE_AUTO:
            return s.auto_max or FALLBACK_MAX_TEMP
        return FALLBACK_MAX_TEMP

    # ------------------------------------------------------------------
    # Command methods
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.client.async_set(self._group_id, {"Drive": DRIVE_OFF})
        else:
            ae_mode = _HA_TO_AE200_MODE.get(hvac_mode)
            if ae_mode is None:
                _LOGGER.warning("Unknown HVAC mode: %s", hvac_mode)
                return
            await self.coordinator.client.async_set(
                self._group_id,
                {"Drive": DRIVE_ON, "Mode": ae_mode},
            )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.client.async_set(
            self._group_id, {"SetTemp": str(temperature)}
        )
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        await self.coordinator.client.async_set(
            self._group_id, {"FanSpeed": fan_mode}
        )
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set swing / air direction mode."""
        await self.coordinator.client.async_set(
            self._group_id, {"AirDirection": swing_mode}
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn on."""
        await self.coordinator.client.async_set(self._group_id, {"Drive": DRIVE_ON})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.coordinator.client.async_set(self._group_id, {"Drive": DRIVE_OFF})
        await self.coordinator.async_request_refresh()
