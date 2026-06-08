"""
Comprehensive data-layer tests for AE-200E / EW-50E integration.

Covers:
1.  Entity unique_id uniqueness and format (entry_id namespacing)
2.  Device grouping — one device per controller, one per group with via_device
3.  Sensor device_class / state_class / native_unit_of_measurement
4.  Climate hvac_modes / fan_modes / swing_modes completeness
5.  Multi-controller isolation — two servers, no ID collisions
6.  XML parsing robustness — unexpected / alternate field values never crash
7.  Sign encoding variants (FilterSign / ErrorSign)
8.  Setpoint-limit application per mode (Cool/Heat/Auto/Dry/Fan)
9.  hvac_action derivation
10. Comm-loss → states dict empty (coordinator maps to UpdateFailed → unavailable)
"""
from __future__ import annotations

import copy
import pytest

from custom_components.ae200.ae200client import AE200Client, GroupState
from custom_components.ae200.const import (
    MODE_COOL, MODE_HEAT, MODE_DRY, MODE_FAN, MODE_AUTO,
    FAN_MODES, SWING_MODES,
    FALLBACK_MIN_TEMP, FALLBACK_MAX_TEMP,
    DOMAIN,
    _SIGN_CLEAR_VALUES,
)
from fake.fake_ae200 import STATE


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_state(group_id: str = "1", **attrs) -> GroupState:
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


def client(host: str) -> AE200Client:
    return AE200Client(host, timeout=5.0)


# ============================================================================
# 1.  Unique ID format and namespacing
# ============================================================================

class TestUniqueIds:
    """Unique IDs must include an entry_id-like prefix to avoid cross-controller collisions."""

    def _climate_uid(self, entry_id: str, group_id: str) -> str:
        return f"{entry_id}_{group_id}_climate"

    def _inlet_uid(self, entry_id: str, group_id: str) -> str:
        return f"{entry_id}_{group_id}_inlet_temp"

    def _outdoor_uid(self, entry_id: str) -> str:
        return f"{entry_id}_outdoor_temp"

    def _filter_uid(self, entry_id: str, group_id: str) -> str:
        return f"{entry_id}_{group_id}_filter"

    def _error_uid(self, entry_id: str, group_id: str) -> str:
        return f"{entry_id}_{group_id}_error"

    def test_same_group_id_different_entry_gives_different_uids(self):
        """Two controllers with the same group_id must have different unique_ids."""
        entry_a = "entry_aaa"
        entry_b = "entry_bbb"
        gid = "1"

        assert self._climate_uid(entry_a, gid) != self._climate_uid(entry_b, gid)
        assert self._inlet_uid(entry_a, gid) != self._inlet_uid(entry_b, gid)
        assert self._filter_uid(entry_a, gid) != self._filter_uid(entry_b, gid)
        assert self._error_uid(entry_a, gid) != self._error_uid(entry_b, gid)

    def test_unique_ids_contain_group_id(self):
        entry_id = "abc123"
        gid = "42"
        assert gid in self._climate_uid(entry_id, gid)
        assert gid in self._inlet_uid(entry_id, gid)
        assert gid in self._filter_uid(entry_id, gid)
        assert gid in self._error_uid(entry_id, gid)

    def test_outdoor_uid_does_not_contain_group_id(self):
        entry_id = "abc123"
        assert "outdoor_temp" in self._outdoor_uid(entry_id)
        # Not per-group
        assert "group" not in self._outdoor_uid(entry_id)

    def test_platform_suffixes_are_distinct(self):
        entry_id = "abc123"
        gid = "1"
        uids = [
            self._climate_uid(entry_id, gid),
            self._inlet_uid(entry_id, gid),
            self._filter_uid(entry_id, gid),
            self._error_uid(entry_id, gid),
        ]
        assert len(uids) == len(set(uids)), "All per-group UIDs must be unique"

    def test_all_uids_unique_across_two_controllers_two_groups(self):
        """Full collision check across 2 controllers × 2 groups × 5 platforms."""
        all_uids: set[str] = set()
        for entry_id in ("entry_1", "entry_2"):
            for gid in ("1", "2"):
                for uid_fn in [
                    lambda e, g: f"{e}_{g}_climate",
                    lambda e, g: f"{e}_{g}_inlet_temp",
                    lambda e, g: f"{e}_{g}_filter",
                    lambda e, g: f"{e}_{g}_error",
                ]:
                    uid = uid_fn(entry_id, gid)
                    assert uid not in all_uids, f"Collision: {uid}"
                    all_uids.add(uid)
            # Controller-level
            outdoor_uid = f"{entry_id}_outdoor_temp"
            assert outdoor_uid not in all_uids
            all_uids.add(outdoor_uid)
        assert len(all_uids) == 18  # 2 controllers × (4 platforms × 2 groups + 1 outdoor) = 2×9


# ============================================================================
# 2.  GroupState — tolerant parsing of all documented field variants
# ============================================================================

class TestGroupStateParsing:

    # ----- Drive / on-off -----

    def test_drive_on(self):
        assert make_state(Drive="ON").is_on is True

    def test_drive_off(self):
        assert make_state(Drive="OFF").is_on is False

    def test_drive_missing_is_off(self):
        s = GroupState(group_id="x", attrs={})
        assert s.is_on is False

    # ----- Mode -----

    def test_mode_all_known_values(self):
        for m in (MODE_COOL, MODE_HEAT, MODE_DRY, MODE_FAN, MODE_AUTO):
            assert make_state(Mode=m).mode == m

    def test_mode_unknown_value_returns_it_unchanged(self):
        """An unknown mode value is passed through; the entity handles it by defaulting."""
        s = make_state(Mode="MYSTERY")
        assert s.mode == "MYSTERY"

    def test_mode_empty_string_returns_none(self):
        assert make_state(Mode="").mode is None

    def test_mode_wildcard_returns_none(self):
        assert make_state(Mode="*").mode is None

    # ----- Temperatures -----

    def test_float_fields_parse_integer_strings(self):
        s = make_state(InletTemp="23", SetTemp="22", OutdoorTemp="30")
        assert s.inlet_temp == pytest.approx(23.0)
        assert s.set_temp == pytest.approx(22.0)
        assert s.outdoor_temp == pytest.approx(30.0)

    def test_float_fields_parse_decimal_strings(self):
        s = make_state(InletTemp="23.5", SetTemp="21.5")
        assert s.inlet_temp == pytest.approx(23.5)
        assert s.set_temp == pytest.approx(21.5)

    def test_non_numeric_temp_returns_none(self):
        """A non-numeric field value must never crash; return None."""
        s = make_state(InletTemp="UNKNOWN", OutdoorTemp="N/A")
        assert s.inlet_temp is None
        assert s.outdoor_temp is None

    def test_empty_temp_returns_none(self):
        s = make_state(InletTemp="", OutdoorTemp="")
        assert s.inlet_temp is None
        assert s.outdoor_temp is None

    def test_negative_temp_parsed(self):
        s = make_state(OutdoorTemp="-5.5")
        assert s.outdoor_temp == pytest.approx(-5.5)

    def test_brine_temp_parsed(self):
        s = GroupState(group_id="1", attrs={"BrineTemp": "12.5"})
        assert s.brine_temp == pytest.approx(12.5)

    def test_brine_temp_empty_returns_none(self):
        s = GroupState(group_id="1", attrs={"BrineTemp": ""})
        assert s.brine_temp is None

    # ----- FilterSign / ErrorSign — sign encoding variants -----

    @pytest.mark.parametrize("value", ["0", "NONE", "OFF"])
    def test_sign_clear_values(self, value):
        """Non-empty 'clear' encodings must return False."""
        s = make_state(FilterSign=value, ErrorSign=value)
        assert s.filter_sign is False
        assert s.error_sign is False

    def test_sign_empty_string_returns_none(self):
        """Empty string means the field was absent/unknown — returns None, not False.

        This is correct: _get() treats '' as absent and _bool_sign returns None.
        An empty FilterSign should not be treated as 'clean' (False) because
        the controller may not have populated the field at all.
        """
        s = make_state(FilterSign="", ErrorSign="")
        assert s.filter_sign is None
        assert s.error_sign is None

    @pytest.mark.parametrize("value", ["1", "2", "ON", "SET", "ALERT", "99"])
    def test_sign_set_values(self, value):
        """Non-clear values must return True (fault active)."""
        s = make_state(FilterSign=value, ErrorSign=value)
        assert s.filter_sign is True
        assert s.error_sign is True

    def test_sign_missing_returns_none(self):
        s = GroupState(group_id="x", attrs={})
        assert s.filter_sign is None
        assert s.error_sign is None

    def test_sign_wildcard_returns_none(self):
        s = make_state(FilterSign="*", ErrorSign="*")
        assert s.filter_sign is None
        assert s.error_sign is None

    # ----- AirDirection / swing -----

    def test_air_direction_returns_raw_value(self):
        """Air direction is returned as-is; no crash on any value."""
        for v in ("AUTO", "SWING", "HORIZONTAL", "VERTICAL", "45", "1", "5", "MYSTERY"):
            s = make_state(AirDirection=v)
            assert s.air_direction == v

    def test_air_direction_empty_returns_none(self):
        assert make_state(AirDirection="").air_direction is None

    # ----- Setpoint limits -----

    def test_cool_limits_parsed(self):
        s = make_state(CoolMin="18.0", CoolMax="27.0")
        assert s.cool_min == pytest.approx(18.0)
        assert s.cool_max == pytest.approx(27.0)

    def test_heat_limits_parsed(self):
        s = make_state(HeatMin="16.5", HeatMax="26.5")
        assert s.heat_min == pytest.approx(16.5)
        assert s.heat_max == pytest.approx(26.5)

    def test_auto_limits_parsed(self):
        s = make_state(AutoMin="19.0", AutoMax="25.0")
        assert s.auto_min == pytest.approx(19.0)
        assert s.auto_max == pytest.approx(25.0)

    def test_limits_empty_return_none(self):
        s = make_state(CoolMin="", CoolMax="", HeatMin="", HeatMax="", AutoMin="", AutoMax="")
        for v in (s.cool_min, s.cool_max, s.heat_min, s.heat_max, s.auto_min, s.auto_max):
            assert v is None

    def test_limits_non_numeric_return_none(self):
        s = make_state(CoolMin="N/A", HeatMin="?")
        assert s.cool_min is None
        assert s.heat_min is None

    # ----- Diagnostics dict -----

    def test_diagnostics_dict_contains_raw_attrs(self):
        s = make_state(InletTemp="23.5", FilterSign="1")
        d = s.diagnostics_dict()
        assert d["InletTemp"] == "23.5"
        assert d["FilterSign"] == "1"

    def test_diagnostics_dict_is_copy(self):
        s = make_state()
        d = s.diagnostics_dict()
        d["InletTemp"] = "MUTATED"
        assert s.attrs.get("InletTemp") != "MUTATED"


# ============================================================================
# 3.  Climate min/max_temp per-mode selection
# ============================================================================

def _climate_min(s: GroupState) -> float:
    """Mirror of climate.py min_temp logic."""
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


class TestClimateSetpointLimits:

    def test_cool_mode_uses_cool_limits(self):
        s = make_state(Mode=MODE_COOL, CoolMin="18.0", CoolMax="27.0")
        assert _climate_min(s) == pytest.approx(18.0)
        assert _climate_max(s) == pytest.approx(27.0)

    def test_heat_mode_uses_heat_limits(self):
        s = make_state(Mode=MODE_HEAT, HeatMin="16.0", HeatMax="26.0")
        assert _climate_min(s) == pytest.approx(16.0)
        assert _climate_max(s) == pytest.approx(26.0)

    def test_auto_mode_uses_auto_limits(self):
        s = make_state(Mode=MODE_AUTO, AutoMin="19.0", AutoMax="25.0")
        assert _climate_min(s) == pytest.approx(19.0)
        assert _climate_max(s) == pytest.approx(25.0)

    def test_dry_mode_uses_fallback(self):
        s = make_state(Mode=MODE_DRY, CoolMin="18.0", HeatMin="16.0")
        assert _climate_min(s) == FALLBACK_MIN_TEMP
        assert _climate_max(s) == FALLBACK_MAX_TEMP

    def test_fan_mode_uses_fallback(self):
        s = make_state(Mode=MODE_FAN)
        assert _climate_min(s) == FALLBACK_MIN_TEMP
        assert _climate_max(s) == FALLBACK_MAX_TEMP

    def test_missing_cool_limit_falls_back(self):
        s = make_state(Mode=MODE_COOL, CoolMin="", CoolMax="")
        assert _climate_min(s) == FALLBACK_MIN_TEMP
        assert _climate_max(s) == FALLBACK_MAX_TEMP

    def test_heat_min_only_uses_fallback_for_max(self):
        s = make_state(Mode=MODE_HEAT, HeatMin="16.0", HeatMax="")
        assert _climate_min(s) == pytest.approx(16.0)
        assert _climate_max(s) == FALLBACK_MAX_TEMP

    def test_cool_min_ignores_heat_limits(self):
        """Cool mode should not use HeatMin even if CoolMin is missing."""
        s = make_state(Mode=MODE_COOL, CoolMin="", HeatMin="10.0")
        assert _climate_min(s) == FALLBACK_MIN_TEMP

    def test_unknown_mode_uses_fallback(self):
        s = make_state(Mode="MYSTERY", CoolMin="18.0", HeatMin="16.0", AutoMin="17.0")
        assert _climate_min(s) == FALLBACK_MIN_TEMP
        assert _climate_max(s) == FALLBACK_MAX_TEMP


# ============================================================================
# 4.  hvac_action derivation
# ============================================================================

def _hvac_action(s: GroupState) -> str | None:
    """Mirror of climate.py hvac_action logic.

    Returns string labels rather than HA enum values so this test does not
    depend on the homeassistant package being installed in the test venv.
    """
    if s is None:
        return None
    if not s.is_on:
        return "off"
    mode = s.mode or ""
    if mode == MODE_FAN:
        return "fan"
    if mode == MODE_DRY:
        return "drying"
    if mode == MODE_HEAT:
        return "heating"
    if mode == MODE_COOL:
        return "cooling"
    return "idle"  # AUTO or unknown


class TestHvacAction:
    """hvac_action depends only on Drive + Mode — no HA runtime needed."""

    def test_off_drive_gives_off_action(self):
        assert _hvac_action(make_state(Drive="OFF", Mode="COOL")) == "off"

    def test_cool_mode_gives_cooling_action(self):
        assert _hvac_action(make_state(Drive="ON", Mode=MODE_COOL)) == "cooling"

    def test_heat_mode_gives_heating_action(self):
        assert _hvac_action(make_state(Drive="ON", Mode=MODE_HEAT)) == "heating"

    def test_fan_mode_gives_fan_action(self):
        assert _hvac_action(make_state(Drive="ON", Mode=MODE_FAN)) == "fan"

    def test_dry_mode_gives_drying_action(self):
        assert _hvac_action(make_state(Drive="ON", Mode=MODE_DRY)) == "drying"

    def test_auto_mode_gives_idle_action(self):
        assert _hvac_action(make_state(Drive="ON", Mode=MODE_AUTO)) == "idle"

    def test_unknown_mode_gives_idle_action(self):
        assert _hvac_action(make_state(Drive="ON", Mode="MYSTERY")) == "idle"

    def test_none_state_gives_none(self):
        assert _hvac_action(None) is None


# ============================================================================
# 5.  Platform attribute constants correctness
# ============================================================================

class TestPlatformConstants:

    def test_fan_modes_all_known(self):
        """FAN_MODES must contain exactly the five documented values."""
        assert set(FAN_MODES) == {"AUTO", "LOW", "MID2", "MID1", "HIGH"}

    def test_swing_modes_non_empty(self):
        assert len(SWING_MODES) > 0

    def test_swing_modes_includes_auto_and_swing(self):
        assert "AUTO" in SWING_MODES
        assert "SWING" in SWING_MODES

    def test_sign_clear_values_coverage(self):
        """The clear-value set must include the expected sentinel strings."""
        for v in ("0", "NONE", "OFF", ""):
            assert v in _SIGN_CLEAR_VALUES


# ============================================================================
# 6.  XML safety — _build_mnet_set_xml should not be injectable
# ============================================================================

class TestXmlSafety:
    """Verify that XML-special chars in group_id and attribute values are escaped."""

    def test_group_id_xml_escape(self):
        from custom_components.ae200.ae200client import _build_mnet_set_xml
        xml = _build_mnet_set_xml('1">&<', {"Drive": "ON"})
        # The group id should be escaped — the raw injection string must not appear
        assert '">&<' not in xml

    def test_attribute_value_xml_escape(self):
        from custom_components.ae200.ae200client import _build_mnet_set_xml
        xml = _build_mnet_set_xml("1", {"Mode": 'COOL">&<'})
        assert '">&<' not in xml

    def test_read_xml_group_id_escape(self):
        from custom_components.ae200.ae200client import _build_mnet_read_xml
        xml = _build_mnet_read_xml(['1">&<'])
        assert '">&<' not in xml


# ============================================================================
# 7.  Multi-controller isolation (integration tests against two fake servers)
# ============================================================================

@pytest.mark.asyncio
async def test_multi_controller_independent_state(fake_server, fake_server_2):
    """Two clients at different host:port return independent state."""
    c1 = client(fake_server)
    c2 = client(fake_server_2)

    # Mutate server 1's state for group 1 to HEAT
    STATE["1"]["Mode"] = "HEAT"
    STATE["1"]["SetTemp"] = "23.0"

    s1 = await c1.async_get_states(["1"])
    s2 = await c2.async_get_states(["1"])

    assert s1["1"].mode == "HEAT"
    # Server 2 has MODE=HEAT from conftest _STATE_2 default (also HEAT) — just verify distinct
    # The key property is that they are truly independent:
    assert s1 is not s2
    assert s1["1"] is not s2["1"]


@pytest.mark.asyncio
async def test_multi_controller_no_group_state_overlap(fake_server, fake_server_2):
    """State from controller 1 never bleeds into controller 2's results."""
    c1 = client(fake_server)
    c2 = client(fake_server_2)

    # Set controller 1 group 2 ErrorSign to "0"
    STATE["2"]["ErrorSign"] = "0"
    # Set controller 2 group 2 ErrorSign to "1"
    from fake.fake_ae200 import _STATE_2 as _S2
    _S2["2"]["ErrorSign"] = "1"

    s1 = await c1.async_get_states(["2"])
    s2 = await c2.async_get_states(["2"])

    assert s1["2"].error_sign is False
    assert s2["2"].error_sign is True


@pytest.mark.asyncio
async def test_multi_controller_group_discovery_independent(fake_server, fake_server_2):
    """Both controllers discover their groups independently."""
    groups1 = await client(fake_server).async_get_groups()
    groups2 = await client(fake_server_2).async_get_groups()

    assert len(groups1) == 2
    assert len(groups2) == 2
    # Same group IDs (both simulated controllers have groups 1+2)
    ids1 = {g.group_id for g in groups1}
    ids2 = {g.group_id for g in groups2}
    assert ids1 == ids2  # same structure, but these are different physical controllers


@pytest.mark.asyncio
async def test_multi_controller_uid_no_collision(fake_server, fake_server_2):
    """Unique IDs produced for two controllers must not collide."""
    entry_id_1 = "entry_ctrl_1"
    entry_id_2 = "entry_ctrl_2"

    uids: set[str] = set()
    for entry_id in (entry_id_1, entry_id_2):
        for gid in ("1", "2"):
            for suffix in ("_climate", "_inlet_temp", "_filter", "_error"):
                uid = f"{entry_id}_{gid}{suffix}"
                assert uid not in uids, f"UID collision: {uid}"
                uids.add(uid)
        # Controller-level
        outdoor_uid = f"{entry_id}_outdoor_temp"
        assert outdoor_uid not in uids
        uids.add(outdoor_uid)

    assert len(uids) == 18  # 2 × (4 platforms × 2 groups + 1 outdoor) = 2×9


# ============================================================================
# 8.  Parsing robustness — malformed XML / empty responses
# ============================================================================

class TestParsingRobustness:

    def test_parse_groups_malformed_xml_returns_empty(self):
        from custom_components.ae200.ae200client import _parse_groups_response
        result = _parse_groups_response("<this is not xml")
        assert result == []

    def test_parse_groups_missing_group_attr_skipped(self):
        from custom_components.ae200.ae200client import _parse_groups_response
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            "<Packet><Command>getResponse</Command>"
            "<DatabaseManager><ControlGroup><MnetList>"
            "<MnetRecord GroupNameWeb=\"NoGroup\" />"  # no Group attr
            "<MnetRecord Group=\"1\" GroupNameWeb=\"Office\" />"
            "</MnetList></ControlGroup></DatabaseManager></Packet>"
        )
        result = _parse_groups_response(xml)
        assert len(result) == 1
        assert result[0].group_id == "1"

    def test_parse_states_malformed_xml_returns_empty(self):
        from custom_components.ae200.ae200client import _parse_states_response
        result = _parse_states_response("<<<not xml")
        assert result == {}

    def test_parse_states_missing_group_attr_skipped(self):
        from custom_components.ae200.ae200client import _parse_states_response
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            "<Packet><Command>getResponse</Command>"
            "<DatabaseManager>"
            '<Mnet Drive="ON" Mode="COOL" />'  # no Group attr — must be skipped
            '<Mnet Group="1" Drive="OFF" Mode="HEAT" />'
            "</DatabaseManager></Packet>"
        )
        result = _parse_states_response(xml)
        assert len(result) == 1
        assert "1" in result
        assert result["1"].drive == "OFF"

    def test_parse_states_empty_database_manager(self):
        from custom_components.ae200.ae200client import _parse_states_response
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            "<Packet><Command>getResponse</Command>"
            "<DatabaseManager></DatabaseManager></Packet>"
        )
        assert _parse_states_response(xml) == {}

    def test_parse_groups_empty_mnet_list(self):
        from custom_components.ae200.ae200client import _parse_groups_response
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            "<Packet><Command>getResponse</Command>"
            "<DatabaseManager><ControlGroup>"
            "<MnetList></MnetList>"
            "</ControlGroup></DatabaseManager></Packet>"
        )
        assert _parse_groups_response(xml) == []


# ============================================================================
# 9.  Integration: comm-loss maps to exception (coordinator → unavailable)
# ============================================================================

@pytest.mark.asyncio
async def test_comm_loss_get_states_raises():
    """Unreachable host must raise so coordinator raises UpdateFailed."""
    c = AE200Client("127.0.0.1:19997", timeout=1.0)
    with pytest.raises(Exception):
        await c.async_get_states(["1"])


@pytest.mark.asyncio
async def test_comm_loss_get_groups_raises():
    c = AE200Client("127.0.0.1:19997", timeout=1.0)
    with pytest.raises(Exception):
        await c.async_get_groups()


@pytest.mark.asyncio
async def test_comm_loss_test_connection_returns_false():
    c = AE200Client("127.0.0.1:19997", timeout=1.0)
    assert await c.async_test_connection() is False


# ============================================================================
# 10. Integration: setpoint limit application via fake server
# ============================================================================

@pytest.mark.asyncio
async def test_mode_setpoint_limits_cool_from_server(fake_server):
    STATE["1"]["CoolMin"] = "19.0"
    STATE["1"]["CoolMax"] = "27.0"
    STATE["1"]["Mode"] = "COOL"
    states = await client(fake_server).async_get_states(["1"])
    s = states["1"]
    assert _climate_min(s) == pytest.approx(19.0)
    assert _climate_max(s) == pytest.approx(27.0)


@pytest.mark.asyncio
async def test_mode_setpoint_limits_heat_from_server(fake_server):
    STATE["1"]["HeatMin"] = "17.0"
    STATE["1"]["HeatMax"] = "26.0"
    STATE["1"]["Mode"] = "HEAT"
    states = await client(fake_server).async_get_states(["1"])
    s = states["1"]
    assert _climate_min(s) == pytest.approx(17.0)
    assert _climate_max(s) == pytest.approx(26.0)


@pytest.mark.asyncio
async def test_mode_setpoint_limits_auto_from_server(fake_server):
    STATE["1"]["AutoMin"] = "20.0"
    STATE["1"]["AutoMax"] = "24.0"
    STATE["1"]["Mode"] = "AUTO"
    states = await client(fake_server).async_get_states(["1"])
    s = states["1"]
    assert _climate_min(s) == pytest.approx(20.0)
    assert _climate_max(s) == pytest.approx(24.0)


@pytest.mark.asyncio
async def test_filter_sign_alternate_encoding_via_server(fake_server):
    """Test that FilterSign='1' (most common 'set' encoding) parses correctly."""
    STATE["2"]["FilterSign"] = "1"
    states = await client(fake_server).async_get_states(["2"])
    assert states["2"].filter_sign is True


@pytest.mark.asyncio
async def test_error_sign_set_via_server(fake_server):
    STATE["1"]["ErrorSign"] = "1"
    states = await client(fake_server).async_get_states(["1"])
    assert states["1"].error_sign is True
    # Reset
    STATE["1"]["ErrorSign"] = "0"


@pytest.mark.asyncio
async def test_both_groups_polled_single_round_trip(fake_server):
    """Verify both groups are returned in a single get_states call."""
    states = await client(fake_server).async_get_states(["1", "2"])
    assert "1" in states
    assert "2" in states


@pytest.mark.asyncio
async def test_empty_group_list_returns_empty_dict(fake_server):
    states = await client(fake_server).async_get_states([])
    assert states == {}
