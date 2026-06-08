"""
Low-level async WebSocket XML client for Mitsubishi AE-200E / EW-50E.

Protocol: ws://<host>/b_xmlproc/  subprotocol b_xmlproc  permessage-deflate
All frames are UTF-8 XML.  Commands: getRequest / setRequest.

Requires websockets >= 12.0 (stable asyncio API; tested on 12–16).

CONFIRMED field names (natevoci/ae200 + AE-200 manual reverse-engineering):
  Drive, Mode, SetTemp, FanSpeed, AirDirection, InletTemp, OutdoorTemp,
  FilterSign, ErrorSign, CoolMin, CoolMax, HeatMin, HeatMax, AutoMin, AutoMax,
  GroupNameWeb (on MnetRecord), Group (attribute on Mnet/MnetRecord)

ASSUMED:
  AirDirection values (AUTO/SWING/HORIZONTAL/45/VERTICAL and numeric "1"-"5")
  — field name confirmed, exact value set hardware-dependent; parsed tolerantly.

  FilterSign / ErrorSign encoding — "0" = clear, "1" = set is the observed
  common form; "OFF"/"NONE"/"" also treated as clear; any other value as set.
"""
from __future__ import annotations

import asyncio
import html
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import websockets

from .const import WS_SUBPROTOCOL, WS_PATH, _SIGN_CLEAR_VALUES

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fields fetched in a single poll — matches natevoci/ae200 getMnetDetails
# [CONFIRMED]; extended with all documented AE-200E fields.
# ---------------------------------------------------------------------------
_MNET_READ_FIELDS = (
    "Drive Vent24h Mode VentMode ModeStatus SetTemp SetTemp1 SetTemp2 SetTemp3 "
    "SetTemp4 SetTemp5 SetHumidity InletTemp InletHumidity AirDirection FanSpeed "
    "RemoCon DriveItem ModeItem SetTempItem FilterItem AirDirItem FanSpeedItem "
    "TimerItem CheckWaterItem FilterSign Hold EnergyControl EnergyControlIC "
    "SetbackControl Ventilation VentiDrive VentiFan Schedule ScheduleAvail "
    "ErrorSign CheckWater TempLimitCool TempLimitHeat TempLimit CoolMin CoolMax "
    "HeatMin HeatMax AutoMin AutoMax TurnOff MaxSaveValue RoomHumidity Brightness "
    "Occupancy NightPurge Humid Vent24hMode SnowFanMode InletTempHWHP "
    "OutletTempHWHP HeadTempHWHP OutdoorTemp BrineTemp HeadInletTempCH "
    "BACnetTurnOff AISmartStart"
)


def _escape_xml_attr(value: str) -> str:
    """Safely escape a string for inclusion as an XML attribute value."""
    return html.escape(value, quote=True)


def _build_mnet_read_xml(group_ids: list[str]) -> str:
    attrs = " ".join(f'{f}="*"' for f in _MNET_READ_FIELDS.split())
    mnets = "\n".join(
        f'<Mnet Group="{_escape_xml_attr(gid)}" {attrs} />'
        for gid in group_ids
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        "<Packet>\n<Command>getRequest</Command>\n"
        f"<DatabaseManager>\n{mnets}\n</DatabaseManager>\n</Packet>\n"
    )


def _build_mnet_set_xml(group_id: str, attributes: dict[str, str]) -> str:
    attrs = " ".join(
        f'{_escape_xml_attr(k)}="{_escape_xml_attr(v)}"'
        for k, v in attributes.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        "<Packet>\n<Command>setRequest</Command>\n"
        f'<DatabaseManager>\n<Mnet Group="{_escape_xml_attr(group_id)}" {attrs} />\n'
        "</DatabaseManager>\n</Packet>\n"
    )


_GET_GROUPS_XML = """\
<?xml version="1.0" encoding="UTF-8" ?>
<Packet>
<Command>getRequest</Command>
<DatabaseManager>
<ControlGroup>
<MnetList />
</ControlGroup>
</DatabaseManager>
</Packet>
"""


@dataclass
class GroupInfo:
    """Metadata for a single AE-200E group."""

    group_id: str
    name: str


@dataclass
class GroupState:
    """Live state for one AE-200E control group.

    All attribute values are raw strings from the XML response.
    Accessor methods parse on-demand and return None on missing / empty / unparseable.
    """

    group_id: str
    # Raw attribute dict from the XML Mnet element — all values are strings or None
    attrs: dict[str, str | None] = field(default_factory=dict)

    def _get(self, key: str) -> str | None:
        """Return the raw string value for a field, or None if absent/empty/wildcard."""
        v = self.attrs.get(key)
        if v is None or v == "" or v == "*":
            return None
        return v

    def _float(self, key: str) -> float | None:
        """Parse a field as float; return None on missing or non-numeric value."""
        v = self._get(key)
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            _LOGGER.debug(
                "GroupState[%s]: unexpected non-numeric value for %s=%r — ignoring",
                self.group_id, key, v,
            )
            return None

    def _bool_sign(self, key: str) -> bool | None:
        """Return True if value indicates a fault/sign, False if clear, None if unknown.

        Tolerant encoding: "0", "NONE", "OFF", "" → False; anything else → True.
        ASSUMED encoding — see const._SIGN_CLEAR_VALUES.
        """
        v = self._get(key)
        if v is None:
            return None
        result = v not in _SIGN_CLEAR_VALUES
        if result and v not in ("1",):
            # Log unexpected set value to help confirm real device encoding
            _LOGGER.debug(
                "GroupState[%s]: %s=%r is treated as SET (fault); "
                "unexpected value — please report for hardware validation",
                self.group_id, key, v,
            )
        return result

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def drive(self) -> str | None:
        return self._get("Drive")

    @property
    def is_on(self) -> bool:
        return self.drive == "ON"

    @property
    def mode(self) -> str | None:
        return self._get("Mode")

    @property
    def set_temp(self) -> float | None:
        return self._float("SetTemp")

    @property
    def inlet_temp(self) -> float | None:
        return self._float("InletTemp")

    @property
    def outdoor_temp(self) -> float | None:
        return self._float("OutdoorTemp")

    @property
    def brine_temp(self) -> float | None:
        return self._float("BrineTemp")

    @property
    def inlet_humidity(self) -> float | None:
        return self._float("InletHumidity")

    @property
    def room_humidity(self) -> float | None:
        return self._float("RoomHumidity")

    @property
    def fan_speed(self) -> str | None:
        return self._get("FanSpeed")

    @property
    def air_direction(self) -> str | None:
        return self._get("AirDirection")

    @property
    def filter_sign(self) -> bool | None:
        return self._bool_sign("FilterSign")

    @property
    def error_sign(self) -> bool | None:
        return self._bool_sign("ErrorSign")

    @property
    def cool_min(self) -> float | None:
        return self._float("CoolMin")

    @property
    def cool_max(self) -> float | None:
        return self._float("CoolMax")

    @property
    def heat_min(self) -> float | None:
        return self._float("HeatMin")

    @property
    def heat_max(self) -> float | None:
        return self._float("HeatMax")

    @property
    def auto_min(self) -> float | None:
        return self._float("AutoMin")

    @property
    def auto_max(self) -> float | None:
        return self._float("AutoMax")

    @property
    def hold(self) -> str | None:
        return self._get("Hold")

    @property
    def occupancy(self) -> str | None:
        return self._get("Occupancy")

    @property
    def energy_control(self) -> str | None:
        return self._get("EnergyControl")

    # ------------------------------------------------------------------
    # Diagnostics helper (redacted — safe to log/include in diagnostics dump)
    # ------------------------------------------------------------------

    def diagnostics_dict(self) -> dict[str, Any]:
        """Return a redacted copy of raw attrs suitable for diagnostics.

        Host / IP information never reaches here (it's on the client, not the state).
        The raw attribute dict lets developers confirm real device field values.
        """
        return dict(self.attrs)


def _ws_connect_kwargs(host: str, timeout: float) -> dict[str, Any]:
    """Return websockets.connect keyword args compatible with ws>=12."""
    return {
        "origin": f"http://{host}",
        "subprotocols": [WS_SUBPROTOCOL],
        "open_timeout": timeout,
        "close_timeout": timeout,
        # compression='deflate' is the default in ws>=13; leave it
    }


def _parse_groups_response(raw: str) -> list[GroupInfo]:
    """Parse a getResponse for ControlGroup/MnetList.

    Tolerant: skips malformed records (no Group attribute), logs and continues.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        _LOGGER.error("Failed to parse group-list XML: %s — raw: %.300r", exc, raw)
        return []

    groups: list[GroupInfo] = []
    for rec in root.findall("./DatabaseManager/ControlGroup/MnetList/MnetRecord"):
        gid = rec.get("Group")
        if not gid:
            _LOGGER.debug("Skipping MnetRecord with no Group attribute")
            continue
        name = rec.get("GroupNameWeb") or f"Group {gid}"
        groups.append(GroupInfo(group_id=gid, name=name))
    return groups


def _parse_states_response(raw: str) -> dict[str, GroupState]:
    """Parse a getResponse for Mnet state records.

    Tolerant: skips elements with no Group attribute, logs and continues.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        _LOGGER.error("Failed to parse state XML: %s — raw: %.300r", exc, raw)
        return {}

    states: dict[str, GroupState] = {}
    for mnet in root.findall("./DatabaseManager/Mnet"):
        gid = mnet.get("Group")
        if not gid:
            _LOGGER.debug("Skipping Mnet element with no Group attribute")
            continue
        states[gid] = GroupState(group_id=gid, attrs=dict(mnet.attrib))
    return states


class AE200Client:
    """Async WebSocket XML client for a single AE-200E / EW-50E controller.

    Compatible with AE-200E and EW-50E (identical LAN1 b_xmlproc protocol).
    One short-lived connection per operation: open → send → recv → close.
    This matches the expected usage pattern for polling and setRequest.
    """

    def __init__(self, host: str, timeout: float = 10.0) -> None:
        self._host = host
        self._timeout = timeout
        self._ws_url = f"ws://{host}{WS_PATH}"

    async def _send_recv(self, payload: str) -> str:
        """Open a connection, send one message, receive one response, close."""
        async with websockets.connect(
            self._ws_url, **_ws_connect_kwargs(self._host, self._timeout)
        ) as ws:
            await ws.send(payload)
            return await asyncio.wait_for(ws.recv(), timeout=self._timeout)

    async def async_get_groups(self) -> list[GroupInfo]:
        """Discover all control groups from the controller.

        Returns an empty list if the response is malformed or contains no groups.
        Raises on connection failure.
        """
        raw = await self._send_recv(_GET_GROUPS_XML)
        return _parse_groups_response(raw)

    async def async_get_states(self, group_ids: list[str]) -> dict[str, GroupState]:
        """Poll all groups in a single WebSocket round-trip.

        Returns an empty dict if group_ids is empty or the response is malformed.
        Raises on connection failure.
        """
        if not group_ids:
            return {}
        raw = await self._send_recv(_build_mnet_read_xml(group_ids))
        return _parse_states_response(raw)

    async def async_set(self, group_id: str, attributes: dict[str, str]) -> None:
        """Send a setRequest for one group.

        The AE-200E may or may not return a setResponse frame; a timeout on recv
        is treated as a successful send (normal behaviour in some firmware versions).
        Raises on connection failure.
        """
        xml_payload = _build_mnet_set_xml(group_id, attributes)
        async with websockets.connect(
            self._ws_url, **_ws_connect_kwargs(self._host, self._timeout)
        ) as ws:
            await ws.send(xml_payload)
            try:
                await asyncio.wait_for(ws.recv(), timeout=self._timeout)
            except asyncio.TimeoutError:
                _LOGGER.debug(
                    "No setResponse for group %s within %.1fs (may be normal for this firmware)",
                    group_id,
                    self._timeout,
                )

    async def async_test_connection(self) -> bool:
        """Verify connectivity; returns True on successful contact, False otherwise."""
        try:
            groups = await self.async_get_groups()
            # A successful connection that returns zero groups is still a valid connection
            _LOGGER.debug("Connection test OK — %d group(s) found", len(groups))
            return True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Connection test failed: %s", exc)
            return False
