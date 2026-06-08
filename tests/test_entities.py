"""
Entity state shape tests — GroupState unit tests + integration against fake server.
No HA runtime required.
"""
from __future__ import annotations

import pytest
from custom_components.ae200.ae200client import AE200Client, GroupState
from custom_components.ae200.const import (
    MODE_COOL, MODE_HEAT, MODE_DRY, MODE_FAN, MODE_AUTO,
    FALLBACK_MIN_TEMP, FALLBACK_MAX_TEMP,
)
from fake.fake_ae200 import STATE


# -----------------------------------------------------------------------
# GroupState unit tests (no network)
# -----------------------------------------------------------------------

def make_state(group_id="1", **attrs) -> GroupState:
    base = {
        "Drive": "ON", "Mode": "COOL", "SetTemp": "22.0",
        "InletTemp": "24.0", "OutdoorTemp": "31.0",
        "FanSpeed": "AUTO", "AirDirection": "AUTO",
        "FilterSign": "0", "ErrorSign": "0",
        "CoolMin": "17.0", "CoolMax": "28.0",
        "HeatMin": "16.0", "HeatMax": "28.0",
        "AutoMin": "17.0", "AutoMax": "28.0",
    }
    base.update(attrs)
    return GroupState(group_id=group_id, attrs=base)


def test_is_on():
    assert make_state(Drive="ON").is_on is True


def test_is_off():
    assert make_state(Drive="OFF").is_on is False


def test_mode():
    assert make_state(Mode="HEAT").mode == "HEAT"


def test_inlet_temp():
    assert make_state(InletTemp="23.5").inlet_temp == pytest.approx(23.5)


def test_outdoor_temp():
    assert make_state(OutdoorTemp="35.0").outdoor_temp == pytest.approx(35.0)


def test_set_temp():
    assert make_state(SetTemp="21.0").set_temp == pytest.approx(21.0)


def test_filter_false():
    assert make_state(FilterSign="0").filter_sign is False


def test_filter_true():
    assert make_state(FilterSign="1").filter_sign is True


def test_error_false():
    assert make_state(ErrorSign="0").error_sign is False


def test_error_true():
    assert make_state(ErrorSign="1").error_sign is True


def test_cool_limits():
    s = make_state(CoolMin="18.0", CoolMax="27.0")
    assert s.cool_min == pytest.approx(18.0)
    assert s.cool_max == pytest.approx(27.0)


def test_heat_limits():
    s = make_state(HeatMin="16.5", HeatMax="26.5")
    assert s.heat_min == pytest.approx(16.5)
    assert s.heat_max == pytest.approx(26.5)


def test_auto_limits():
    s = make_state(AutoMin="19.0", AutoMax="25.0")
    assert s.auto_min == pytest.approx(19.0)
    assert s.auto_max == pytest.approx(25.0)


def test_empty_string_returns_none():
    assert make_state(OutdoorTemp="").outdoor_temp is None


def test_missing_key_returns_none():
    s = GroupState(group_id="x", attrs={})
    assert s.inlet_temp is None
    assert s.outdoor_temp is None
    assert s.filter_sign is None
    assert s.error_sign is None


# -----------------------------------------------------------------------
# Climate min/max_temp logic (mirrors climate.py — unit test)
# -----------------------------------------------------------------------

def _climate_min(s: GroupState) -> float:
    mode = (s.mode or "").upper()
    if mode == MODE_HEAT:
        return s.heat_min or FALLBACK_MIN_TEMP
    if mode == MODE_COOL:
        return s.cool_min or FALLBACK_MIN_TEMP
    if mode == MODE_AUTO:
        return s.auto_min or FALLBACK_MIN_TEMP
    return FALLBACK_MIN_TEMP


def _climate_max(s: GroupState) -> float:
    mode = (s.mode or "").upper()
    if mode == MODE_HEAT:
        return s.heat_max or FALLBACK_MAX_TEMP
    if mode == MODE_COOL:
        return s.cool_max or FALLBACK_MAX_TEMP
    if mode == MODE_AUTO:
        return s.auto_max or FALLBACK_MAX_TEMP
    return FALLBACK_MAX_TEMP


def test_min_cool():
    assert _climate_min(make_state(Mode=MODE_COOL, CoolMin="18.0")) == pytest.approx(18.0)


def test_max_cool():
    assert _climate_max(make_state(Mode=MODE_COOL, CoolMax="27.0")) == pytest.approx(27.0)


def test_min_heat():
    assert _climate_min(make_state(Mode=MODE_HEAT, HeatMin="17.0")) == pytest.approx(17.0)


def test_min_auto():
    assert _climate_min(make_state(Mode=MODE_AUTO, AutoMin="19.0")) == pytest.approx(19.0)


def test_min_dry_fallback():
    assert _climate_min(make_state(Mode=MODE_DRY)) == FALLBACK_MIN_TEMP


def test_min_fan_fallback():
    assert _climate_min(make_state(Mode=MODE_FAN)) == FALLBACK_MIN_TEMP


def test_min_empty_controller_fallback():
    assert _climate_min(make_state(Mode=MODE_COOL, CoolMin="")) == FALLBACK_MIN_TEMP


# -----------------------------------------------------------------------
# Integration tests against fake server
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_mode_heat_reflected(fake_server):
    c = AE200Client(fake_server, timeout=5.0)
    await c.async_set("1", {"Drive": "ON", "Mode": "HEAT"})
    states = await c.async_get_states(["1"])
    assert states["1"].mode == "HEAT"
    assert states["1"].is_on is True


@pytest.mark.asyncio
async def test_set_mode_off_reflected(fake_server):
    c = AE200Client(fake_server, timeout=5.0)
    await c.async_set("1", {"Drive": "OFF"})
    states = await c.async_get_states(["1"])
    assert states["1"].is_on is False


@pytest.mark.asyncio
async def test_set_temperature_reflected(fake_server):
    c = AE200Client(fake_server, timeout=5.0)
    await c.async_set("1", {"SetTemp": "20.5"})
    states = await c.async_get_states(["1"])
    assert states["1"].set_temp == pytest.approx(20.5)


@pytest.mark.asyncio
async def test_set_fan_reflected(fake_server):
    c = AE200Client(fake_server, timeout=5.0)
    await c.async_set("1", {"FanSpeed": "MID1"})
    states = await c.async_get_states(["1"])
    assert states["1"].fan_speed == "MID1"


@pytest.mark.asyncio
async def test_filter_sensor_group2(fake_server):
    STATE["2"]["FilterSign"] = "1"
    c = AE200Client(fake_server, timeout=5.0)
    states = await c.async_get_states(["2"])
    assert states["2"].filter_sign is True


@pytest.mark.asyncio
async def test_error_sensor_clear(fake_server):
    STATE["1"]["ErrorSign"] = "0"
    c = AE200Client(fake_server, timeout=5.0)
    states = await c.async_get_states(["1"])
    assert states["1"].error_sign is False


@pytest.mark.asyncio
async def test_setpoint_limits_from_server(fake_server):
    STATE["1"]["CoolMin"] = "18.5"
    STATE["1"]["CoolMax"] = "26.5"
    STATE["1"]["Mode"] = "COOL"
    c = AE200Client(fake_server, timeout=5.0)
    states = await c.async_get_states(["1"])
    s = states["1"]
    assert s.cool_min == pytest.approx(18.5)
    assert s.cool_max == pytest.approx(26.5)
    # Verify climate min/max logic picks these up
    assert _climate_min(s) == pytest.approx(18.5)
    assert _climate_max(s) == pytest.approx(26.5)


@pytest.mark.asyncio
async def test_comm_loss_unavailable():
    """A bad host raises — coordinator maps this to UpdateFailed / unavailable."""
    c = AE200Client("127.0.0.1:19999", timeout=1.0)
    with pytest.raises(Exception):
        await c.async_get_states(["1"])
