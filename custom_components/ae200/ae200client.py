"""
Low-level async WebSocket XML client for Mitsubishi AE-200E / EW-50E.

Protocol: ws://<host>/b_xmlproc/  subprotocol b_xmlproc  permessage-deflate
All frames are UTF-8 XML.  Commands: getRequest / setRequest.

Requires websockets >= 12.0 (tested on 12–16; uses the stable asyncio API).

CONFIRMED field names (natevoci/ae200 + AE-200 manual reverse-engineering):
  Drive, Mode, SetTemp, FanSpeed, AirDirection, InletTemp, OutdoorTemp,
  FilterSign, ErrorSign, CoolMin, CoolMax, HeatMin, HeatMax, AutoMin, AutoMax,
  GroupNameWeb (on MnetRecord), Group (attribute on Mnet/MnetRecord)

ASSUMED:
  AirDirection values (AUTO/SWING/HORIZONTAL/45/VERTICAL) — tune per hardware.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import websockets

_LOGGER = logging.getLogger(__name__)

# All fields fetched in a single poll — matches natevoci/ae200 getMnetDetails [CONFIRMED]
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


def _build_mnet_read_xml(group_ids: list[str]) -> str:
    attrs = " ".join(f'{f}="*"' for f in _MNET_READ_FIELDS.split())
    mnets = "\n".join(f'<Mnet Group="{gid}" {attrs} />' for gid in group_ids)
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        "<Packet>\n<Command>getRequest</Command>\n"
        f"<DatabaseManager>\n{mnets}\n</DatabaseManager>\n</Packet>\n"
    )


def _build_mnet_set_xml(group_id: str, attributes: dict[str, str]) -> str:
    attrs = " ".join(f'{k}="{v}"' for k, v in attributes.items())
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        "<Packet>\n<Command>setRequest</Command>\n"
        f"<DatabaseManager>\n<Mnet Group=\"{group_id}\" {attrs} />\n"
        "</DatabaseManager>\n</Packet>\n"
    )


@dataclass
class GroupInfo:
    """Metadata for a single AE-200E group."""

    group_id: str
    name: str


@dataclass
class GroupState:
    """Live state for one AE-200E control group."""

    group_id: str
    # Raw attribute dict from the XML Mnet element — all values are strings or None
    attrs: dict[str, str | None] = field(default_factory=dict)

    def _get(self, key: str) -> str | None:
        v = self.attrs.get(key)
        if v is None or v == "" or v == "*":
            return None
        return v

    def _float(self, key: str) -> float | None:
        v = self._get(key)
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    def _bool_sign(self, key: str) -> bool | None:
        """Return True if value indicates a fault/sign, False if clear, None if unknown."""
        v = self._get(key)
        if v is None:
            return None
        return v not in ("0", "NONE", "OFF", "")

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


def _ws_connect_kwargs(host: str, timeout: float) -> dict[str, Any]:
    """Return websockets.connect keyword args compatible with ws>=12."""
    return {
        "origin": f"http://{host}",
        "subprotocols": ["b_xmlproc"],
        "open_timeout": timeout,
        "close_timeout": timeout,
        # compression='deflate' is the default in ws>=13 — leave it
    }


class AE200Client:
    """Async WebSocket XML client for a single AE-200E / EW-50E controller."""

    def __init__(self, host: str, timeout: float = 10.0) -> None:
        self._host = host
        self._timeout = timeout
        self._ws_url = f"ws://{host}/b_xmlproc/"

    async def _send_recv(self, payload: str) -> str:
        """Open a connection, send one message, receive one response."""
        async with websockets.connect(
            self._ws_url, **_ws_connect_kwargs(self._host, self._timeout)
        ) as ws:
            await ws.send(payload)
            return await asyncio.wait_for(ws.recv(), timeout=self._timeout)

    async def async_get_groups(self) -> list[GroupInfo]:
        """Discover all control groups from the AE-200E."""
        raw = await self._send_recv(_GET_GROUPS_XML)
        root = ET.fromstring(raw)
        groups: list[GroupInfo] = []
        for rec in root.findall("./DatabaseManager/ControlGroup/MnetList/MnetRecord"):
            gid = rec.get("Group")
            name = rec.get("GroupNameWeb") or f"Group {gid}"
            if gid:
                groups.append(GroupInfo(group_id=gid, name=name))
        return groups

    async def async_get_states(self, group_ids: list[str]) -> dict[str, GroupState]:
        """Poll all groups in a single WebSocket round-trip."""
        if not group_ids:
            return {}

        raw = await self._send_recv(_build_mnet_read_xml(group_ids))
        root = ET.fromstring(raw)
        states: dict[str, GroupState] = {}
        for mnet in root.findall("./DatabaseManager/Mnet"):
            gid = mnet.get("Group")
            if gid:
                states[gid] = GroupState(group_id=gid, attrs=dict(mnet.attrib))
        return states

    async def async_set(self, group_id: str, attributes: dict[str, str]) -> None:
        """Send a setRequest for one group."""
        xml_payload = _build_mnet_set_xml(group_id, attributes)
        async with websockets.connect(
            self._ws_url, **_ws_connect_kwargs(self._host, self._timeout)
        ) as ws:
            await ws.send(xml_payload)
            try:
                await asyncio.wait_for(ws.recv(), timeout=self._timeout)
            except asyncio.TimeoutError:
                _LOGGER.debug("No response to setRequest for group %s (normal)", group_id)

    async def async_test_connection(self) -> bool:
        """Verify connectivity; returns True on successful contact."""
        try:
            await self.async_get_groups()
            return True
        except Exception:  # noqa: BLE001
            return False
