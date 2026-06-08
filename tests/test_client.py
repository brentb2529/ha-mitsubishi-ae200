"""
Tests for AE200Client — run directly against the fake server.

Coverage:
- Group discovery (getRequest -> MnetList)
- State polling (getRequest -> Mnet attrs)
- Set command (setRequest -> state reflected in next poll)
- Setpoint limits parsed (CoolMin/Max, HeatMin/Max, AutoMin/Max)
- FilterSign / ErrorSign parsed correctly
- Comm-loss -> raises exception
"""
from __future__ import annotations

import pytest

# conftest.py installs the stub package; imports below are now safe
from custom_components.ae200.ae200client import AE200Client
from fake.fake_ae200 import STATE


def client(fake_server) -> AE200Client:
    return AE200Client(fake_server, timeout=5.0)


# -----------------------------------------------------------------------
# Group discovery
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_groups_returns_two_groups(fake_server):
    groups = await client(fake_server).async_get_groups()
    assert len(groups) == 2


@pytest.mark.asyncio
async def test_get_groups_names(fake_server):
    groups = await client(fake_server).async_get_groups()
    names = {g.group_id: g.name for g in groups}
    assert names["1"] == "Office"
    assert names["2"] == "Warehouse"


# -----------------------------------------------------------------------
# State polling
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_states_returns_both_groups(fake_server):
    states = await client(fake_server).async_get_states(["1", "2"])
    assert "1" in states
    assert "2" in states


@pytest.mark.asyncio
async def test_state_drive_on(fake_server):
    STATE["1"]["Drive"] = "ON"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].is_on is True


@pytest.mark.asyncio
async def test_state_mode_cool(fake_server):
    STATE["1"]["Mode"] = "COOL"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].mode == "COOL"


@pytest.mark.asyncio
async def test_state_inlet_temp(fake_server):
    STATE["1"]["InletTemp"] = "23.5"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].inlet_temp == pytest.approx(23.5)


@pytest.mark.asyncio
async def test_state_outdoor_temp(fake_server):
    STATE["1"]["OutdoorTemp"] = "31.0"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].outdoor_temp == pytest.approx(31.0)


# -----------------------------------------------------------------------
# Setpoint limits
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setpoint_limits_cool(fake_server):
    STATE["1"]["CoolMin"] = "18.0"
    STATE["1"]["CoolMax"] = "27.0"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].cool_min == pytest.approx(18.0)
    assert states["1"].cool_max == pytest.approx(27.0)


@pytest.mark.asyncio
async def test_setpoint_limits_heat(fake_server):
    STATE["1"]["HeatMin"] = "16.0"
    STATE["1"]["HeatMax"] = "26.0"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].heat_min == pytest.approx(16.0)
    assert states["1"].heat_max == pytest.approx(26.0)


@pytest.mark.asyncio
async def test_setpoint_limits_auto(fake_server):
    STATE["1"]["AutoMin"] = "19.0"
    STATE["1"]["AutoMax"] = "25.0"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].auto_min == pytest.approx(19.0)
    assert states["1"].auto_max == pytest.approx(25.0)


# -----------------------------------------------------------------------
# FilterSign / ErrorSign
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_sign_true(fake_server):
    STATE["2"]["FilterSign"] = "1"
    states = await client(fake_server).async_get_states(["2"])
    assert states["2"].filter_sign is True


@pytest.mark.asyncio
async def test_filter_sign_false(fake_server):
    STATE["1"]["FilterSign"] = "0"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].filter_sign is False


@pytest.mark.asyncio
async def test_error_sign_false(fake_server):
    STATE["1"]["ErrorSign"] = "0"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].error_sign is False


@pytest.mark.asyncio
async def test_error_sign_true(fake_server):
    STATE["1"]["ErrorSign"] = "1"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].error_sign is True
    STATE["1"]["ErrorSign"] = "0"  # reset


# -----------------------------------------------------------------------
# Set commands reflected in next poll
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_drive_off(fake_server):
    STATE["1"]["Drive"] = "ON"
    c = client(fake_server)
    await c.async_set("1", {"Drive": "OFF"})
    states = await c.async_get_states(["1"])
    assert states["1"].is_on is False


@pytest.mark.asyncio
async def test_set_drive_on(fake_server):
    STATE["1"]["Drive"] = "OFF"
    c = client(fake_server)
    await c.async_set("1", {"Drive": "ON"})
    states = await c.async_get_states(["1"])
    assert states["1"].is_on is True


@pytest.mark.asyncio
async def test_set_hvac_mode(fake_server):
    c = client(fake_server)
    await c.async_set("1", {"Drive": "ON", "Mode": "HEAT"})
    states = await c.async_get_states(["1"])
    assert states["1"].mode == "HEAT"


@pytest.mark.asyncio
async def test_set_temperature(fake_server):
    c = client(fake_server)
    await c.async_set("1", {"SetTemp": "21.0"})
    states = await c.async_get_states(["1"])
    assert states["1"].set_temp == pytest.approx(21.0)


@pytest.mark.asyncio
async def test_set_fan_speed(fake_server):
    c = client(fake_server)
    await c.async_set("1", {"FanSpeed": "HIGH"})
    states = await c.async_get_states(["1"])
    assert states["1"].fan_speed == "HIGH"


@pytest.mark.asyncio
async def test_set_air_direction(fake_server):
    c = client(fake_server)
    await c.async_set("1", {"AirDirection": "SWING"})
    states = await c.async_get_states(["1"])
    assert states["1"].air_direction == "SWING"


# -----------------------------------------------------------------------
# Comm-loss
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_comm_loss_raises():
    c = AE200Client("127.0.0.1:19999", timeout=1.0)
    with pytest.raises(Exception):
        await c.async_get_groups()
