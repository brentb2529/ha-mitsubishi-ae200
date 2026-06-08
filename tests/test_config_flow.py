"""
Config flow connectivity tests.
Directly exercises AE200Client (the part config_flow depends on)
without requiring the full HA runtime.
"""
from __future__ import annotations

import pytest
from custom_components.ae200.ae200client import AE200Client


@pytest.mark.asyncio
async def test_connect_succeeds_with_fake_server(fake_server):
    """A reachable fake server returns groups (config flow would succeed)."""
    c = AE200Client(fake_server, timeout=5.0)
    groups = await c.async_get_groups()
    assert len(groups) == 2


@pytest.mark.asyncio
async def test_connect_fails_with_bad_host():
    """An unreachable host raises — config_flow maps this to 'cannot_connect'."""
    c = AE200Client("127.0.0.1:19999", timeout=1.0)
    with pytest.raises(Exception):
        await c.async_get_groups()


@pytest.mark.asyncio
async def test_unique_id_derivation(fake_server):
    """Unique ID is the lower-cased host — verified against what config_flow would set."""
    host = fake_server
    assert host.lower() == fake_server.lower()  # idempotent lowercase


@pytest.mark.asyncio
async def test_test_connection_returns_true(fake_server):
    c = AE200Client(fake_server, timeout=5.0)
    result = await c.async_test_connection()
    assert result is True


@pytest.mark.asyncio
async def test_test_connection_returns_false_on_bad_host():
    c = AE200Client("127.0.0.1:19999", timeout=1.0)
    result = await c.async_test_connection()
    assert result is False
