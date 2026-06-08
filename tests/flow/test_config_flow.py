"""
Config flow, options flow, and reconfigure flow tests.

Tests use the HA runtime (hass fixture from pytest-homeassistant-custom-component)
and mock AE200Client at the boundary, so they exercise the full flow logic
without requiring a real or fake server.

The existing client connectivity tests (can_connect / bad_host) remain in
test_data_layer.py / test_entities.py where they live close to the client.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ae200.const import (
    CONF_TIMEOUT,
    DEFAULT_TIMEOUT,
    DOMAIN,
    TIMEOUT_MAX,
    TIMEOUT_MIN,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_HOST = "192.168.1.10"
MOCK_HOST_2 = "192.168.1.20"


def _mock_client_ok(groups=None):
    """Return a patched AE200Client whose async_get_groups succeeds."""
    if groups is None:
        from custom_components.ae200.ae200client import GroupInfo
        groups = [GroupInfo(group_id="1", name="Office")]

    mock = MagicMock()
    mock.async_get_groups = AsyncMock(return_value=groups)
    return mock


def _mock_client_fail():
    """Return a patched AE200Client whose async_get_groups raises."""
    mock = MagicMock()
    mock.async_get_groups = AsyncMock(side_effect=Exception("connection refused"))
    return mock


# ---------------------------------------------------------------------------
# Config flow — user step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_flow_user_step_shows_form(hass: HomeAssistant) -> None:
    """Initial step renders a form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_config_flow_user_step_success(hass: HomeAssistant) -> None:
    """Valid host + reachable controller creates entry with correct title."""
    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_ok(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == f"AE-200E ({MOCK_HOST})"
    assert result["data"] == {CONF_HOST: MOCK_HOST}


@pytest.mark.asyncio
async def test_config_flow_user_step_strips_whitespace(hass: HomeAssistant) -> None:
    """Leading/trailing whitespace in host is stripped before use."""
    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_ok(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: f"  {MOCK_HOST}  "},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == MOCK_HOST


@pytest.mark.asyncio
async def test_config_flow_cannot_connect_shows_error(hass: HomeAssistant) -> None:
    """Unreachable controller shows 'cannot_connect' error and re-shows form."""
    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_fail(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_config_flow_invalid_host_shows_error(hass: HomeAssistant) -> None:
    """An obviously malformed host string shows 'invalid_host' without attempting a connection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "not a valid host!!"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_HOST] == "invalid_host"


@pytest.mark.asyncio
async def test_config_flow_duplicate_host_aborts(hass: HomeAssistant) -> None:
    """Adding the same host twice is rejected with already_configured."""
    # First entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_ok(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_config_flow_two_distinct_controllers_allowed(
    hass: HomeAssistant,
) -> None:
    """Two different hosts can be added as separate config entries — no conflict."""
    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_ok(),
    ):
        # First controller
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Second controller on a different host
        result2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            user_input={CONF_HOST: MOCK_HOST_2},
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 2
    hosts = {e.data[CONF_HOST] for e in entries}
    assert hosts == {MOCK_HOST, MOCK_HOST_2}


# ---------------------------------------------------------------------------
# Config flow — various valid host formats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    [
        "192.168.1.10",
        "10.0.0.1",
        "ae200.local",
        "ae200-controller",
        "192.168.1.10:7777",
        "ae200.example.com",
    ],
)
async def test_config_flow_valid_host_formats_accepted(
    hass: HomeAssistant, host: str
) -> None:
    """Various valid host/IP strings should not produce invalid_host errors."""
    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_ok(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: host},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    [
        "not a valid host!!",
        "",
        "   ",
        "host with spaces",
    ],
)
async def test_config_flow_invalid_host_formats_rejected(
    hass: HomeAssistant, host: str
) -> None:
    """Malformed host strings should produce invalid_host error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: host},
    )

    assert result["type"] == FlowResultType.FORM
    assert CONF_HOST in result["errors"] or "base" in result["errors"]


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_options_flow_shows_form_with_defaults(hass: HomeAssistant) -> None:
    """Options form shows with the current timeout value (defaults to DEFAULT_TIMEOUT)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    # The schema default should reflect DEFAULT_TIMEOUT
    schema = result["data_schema"].schema
    timeout_key = next(k for k in schema if str(k) == CONF_TIMEOUT)
    assert timeout_key.default() == DEFAULT_TIMEOUT


@pytest.mark.asyncio
async def test_options_flow_saves_custom_timeout(hass: HomeAssistant) -> None:
    """User-supplied timeout is saved into entry options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_TIMEOUT: 20},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TIMEOUT] == 20


@pytest.mark.asyncio
async def test_options_flow_preserves_existing_timeout(hass: HomeAssistant) -> None:
    """Opening options with existing timeout shows that value as default."""
    existing_timeout = 25
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={CONF_TIMEOUT: existing_timeout},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM

    schema = result["data_schema"].schema
    timeout_key = next(k for k in schema if str(k) == CONF_TIMEOUT)
    assert timeout_key.default() == existing_timeout


@pytest.mark.asyncio
async def test_options_flow_min_timeout_accepted(hass: HomeAssistant) -> None:
    """Minimum allowed timeout (TIMEOUT_MIN) is accepted."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_TIMEOUT: TIMEOUT_MIN},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TIMEOUT] == TIMEOUT_MIN


@pytest.mark.asyncio
async def test_options_flow_max_timeout_accepted(hass: HomeAssistant) -> None:
    """Maximum allowed timeout (TIMEOUT_MAX) is accepted."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_TIMEOUT: TIMEOUT_MAX},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_TIMEOUT] == TIMEOUT_MAX


# ---------------------------------------------------------------------------
# Reconfigure flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconfigure_flow_shows_form_prefilled(hass: HomeAssistant) -> None:
    """Reconfigure form shows with the current host pre-filled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


@pytest.mark.asyncio
async def test_reconfigure_flow_updates_host(hass: HomeAssistant) -> None:
    """Reconfigure with a new reachable host updates the entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_ok(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST_2},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == MOCK_HOST_2


@pytest.mark.asyncio
async def test_reconfigure_flow_cannot_connect_shows_error(
    hass: HomeAssistant,
) -> None:
    """Reconfigure shows 'cannot_connect' when new host is unreachable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_fail(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST_2},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"
    # Original host must be unchanged
    assert entry.data[CONF_HOST] == MOCK_HOST


@pytest.mark.asyncio
async def test_reconfigure_flow_invalid_host_shows_error(
    hass: HomeAssistant,
) -> None:
    """Reconfigure shows 'invalid_host' for a malformed address."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "not valid!!"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_HOST] == "invalid_host"
    assert entry.data[CONF_HOST] == MOCK_HOST


@pytest.mark.asyncio
async def test_reconfigure_flow_same_host_aborts_with_success(
    hass: HomeAssistant,
) -> None:
    """Reconfiguring to the same host still succeeds (no duplicate conflict)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST.lower(),
        data={CONF_HOST: MOCK_HOST},
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ae200.config_flow.AE200Client",
        return_value=_mock_client_ok(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: MOCK_HOST},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
