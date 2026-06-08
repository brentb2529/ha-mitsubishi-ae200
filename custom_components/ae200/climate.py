"""Climate platform for AE-200E / EW-50E."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
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

# HA ↔ AE-200E mode translation  [CONFIRMED from natevoci/ae200]
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
    """Set up climate entities from a config entry."""
    coordinator: AE200Coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        AE200Climate(coordinator, group)
        for group in coordinator.groups
    )


class AE200Climate(AE200GroupEntity, ClimateEntity):
    """Climate entity for one AE-200E control group.

    Unique ID is namespaced by config-entry ID so multiple controllers
    with identical group_ids never collide.
    """

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
        entry_id = coordinator.config_entry.entry_id
        # Stable unique_id: entry_id + group_id + platform suffix.
        # entry_id is the config-entry UUID — survives host renames/IP changes.
        self._attr_unique_id = f"{entry_id}_{group.group_id}_climate"
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
        ha_mode = _AE200_TO_HA_MODE.get(s.mode or "")
        if ha_mode is None:
            if s.mode:
                _LOGGER.debug(
                    "Group %s: unknown AE-200E mode %r — defaulting to AUTO",
                    self._group_id, s.mode,
                )
            return HVACMode.AUTO
        return ha_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """Derive running/idle/off from drive + mode.

        Without a direct 'is compressor active' field we derive:
        - OFF  → HVACAction.OFF
        - FAN  → HVACAction.FAN (circulating, no conditioning)
        - DRY  → HVACAction.DRYING
        - HEAT → HVACAction.HEATING (assumes active when Drive=ON)
        - COOL → HVACAction.COOLING
        - AUTO → HVACAction.IDLE (can't determine without runtime data)
        This is the best approximation without a dedicated status bit.
        """
        s = self._state
        if s is None:
            return None
        if not s.is_on:
            return HVACAction.OFF
        mode = s.mode or ""
        if mode == MODE_FAN:
            return HVACAction.FAN
        if mode == MODE_DRY:
            return HVACAction.DRYING
        if mode == MODE_HEAT:
            return HVACAction.HEATING
        if mode == MODE_COOL:
            return HVACAction.COOLING
        # AUTO or unknown — return IDLE as a conservative default
        return HVACAction.IDLE

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
        if s is None:
            return None
        v = s.fan_speed
        if v not in FAN_MODES:
            if v is not None:
                _LOGGER.debug(
                    "Group %s: unknown fan_speed %r — passing through as-is",
                    self._group_id, v,
                )
        return v

    @property
    def swing_mode(self) -> str | None:
        s = self._state
        if s is None:
            return None
        v = s.air_direction
        if v is not None and v not in SWING_MODES:
            _LOGGER.debug(
                "Group %s: air_direction %r not in known swing_modes — "
                "passing through (ASSUMED value set; please report for hardware validation)",
                self._group_id, v,
            )
        return v

    @property
    def min_temp(self) -> float:
        """Return mode-specific minimum setpoint from the controller, with fallback."""
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
        """Return mode-specific maximum setpoint from the controller, with fallback."""
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
        """Set HVAC mode (or turn off)."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.client.async_set(self._group_id, {"Drive": DRIVE_OFF})
        else:
            ae_mode = _HA_TO_AE200_MODE.get(hvac_mode)
            if ae_mode is None:
                _LOGGER.warning("Unknown HVAC mode requested: %s", hvac_mode)
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
        """Set fan speed."""
        await self.coordinator.client.async_set(
            self._group_id, {"FanSpeed": fan_mode}
        )
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set air direction / vane position."""
        await self.coordinator.client.async_set(
            self._group_id, {"AirDirection": swing_mode}
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn on (preserves current mode)."""
        await self.coordinator.client.async_set(self._group_id, {"Drive": DRIVE_ON})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.coordinator.client.async_set(self._group_id, {"Drive": DRIVE_OFF})
        await self.coordinator.async_request_refresh()
