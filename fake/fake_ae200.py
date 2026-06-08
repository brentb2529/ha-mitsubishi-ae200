"""
Fake AE-200E WebSocket XML server for testing / dev demo.

Serves the b_xmlproc subprotocol on ws://127.0.0.1:7777/b_xmlproc/
Simulates two groups: group 1 "Office" and group 2 "Warehouse".

Compatible with websockets >= 12, including 14+ new asyncio API.

Usage:
    python fake_ae200.py [--host 127.0.0.1] [--port 7777]
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import logging
import xml.etree.ElementTree as ET

import websockets
import websockets.asyncio.server as ws_server

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simulated device state
# ---------------------------------------------------------------------------

GROUPS: dict[str, dict[str, str]] = {
    "1": {"Group": "1", "GroupNameWeb": "Office"},
    "2": {"Group": "2", "GroupNameWeb": "Warehouse"},
}

_DEFAULT_STATE: dict[str, str] = {
    "Drive": "ON",
    "Mode": "COOL",
    "SetTemp": "22.0",
    "InletTemp": "24.5",
    "OutdoorTemp": "32.0",
    "FanSpeed": "AUTO",
    "AirDirection": "AUTO",
    "FilterSign": "0",
    "ErrorSign": "0",
    "CoolMin": "17.0",
    "CoolMax": "28.0",
    "HeatMin": "16.0",
    "HeatMax": "28.0",
    "AutoMin": "17.0",
    "AutoMax": "28.0",
    "Hold": "0",
    "EnergyControl": "0",
    "SetbackControl": "0",
    "Occupancy": "0",
    "RoomHumidity": "",
    "InletHumidity": "",
    "BrineTemp": "",
    "VentMode": "",
    "Schedule": "0",
}

# Mutable in-memory state store — deep-copied per group
STATE: dict[str, dict[str, str]] = {
    gid: copy.deepcopy(_DEFAULT_STATE) for gid in GROUPS
}
STATE["2"]["FilterSign"] = "1"  # group 2 has filter sign set


# ---------------------------------------------------------------------------
# XML builders
# ---------------------------------------------------------------------------

def _get_groups_response() -> str:
    records = "".join(
        f'<MnetRecord Group="{gid}" GroupNameWeb="{info["GroupNameWeb"]}" />'
        for gid, info in GROUPS.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>'
        "<Packet><Command>getResponse</Command>"
        "<DatabaseManager><ControlGroup><MnetList>"
        f"{records}"
        "</MnetList></ControlGroup></DatabaseManager></Packet>"
    )


def _get_mnet_response(group_ids: list[str]) -> str:
    mnets = []
    for gid in group_ids:
        if gid not in STATE:
            continue
        attrs = " ".join(f'{k}="{v}"' for k, v in STATE[gid].items())
        mnets.append(f'<Mnet Group="{gid}" {attrs} />')
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>'
        "<Packet><Command>getResponse</Command>"
        f"<DatabaseManager>{''.join(mnets)}</DatabaseManager></Packet>"
    )


def _set_response(group_id: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>'
        "<Packet><Command>setResponse</Command>"
        f"<DatabaseManager><Mnet Group=\"{group_id}\" /></DatabaseManager></Packet>"
    )


# ---------------------------------------------------------------------------
# Handler — websockets 14+ asyncio API
# ---------------------------------------------------------------------------

async def handler(ws) -> None:  # ws is ServerConnection in ws>=14
    _LOGGER.debug("Client connected")
    try:
        async for message in ws:
            try:
                await _handle_message(ws, str(message))
            except Exception as exc:
                _LOGGER.exception("Error handling message: %s", exc)
    except websockets.ConnectionClosedOK:
        pass
    _LOGGER.debug("Client disconnected")


async def _handle_message(ws, raw: str) -> None:
    _LOGGER.debug("RX: %s", raw[:300])
    root = ET.fromstring(raw)
    command = root.findtext("Command", "").strip()

    if command == "getRequest":
        if root.find("./DatabaseManager/ControlGroup/MnetList") is not None:
            resp = _get_groups_response()
            _LOGGER.debug("TX groups response")
            await ws.send(resp)
            return

        mnets = root.findall("./DatabaseManager/Mnet")
        group_ids = [m.get("Group") for m in mnets if m.get("Group")]
        resp = _get_mnet_response(group_ids)
        _LOGGER.debug("TX state for groups: %s", group_ids)
        await ws.send(resp)

    elif command == "setRequest":
        for mnet in root.findall("./DatabaseManager/Mnet"):
            gid = mnet.get("Group")
            if gid not in STATE:
                continue
            for k, v in mnet.attrib.items():
                if k == "Group":
                    continue
                _LOGGER.debug("SET group=%s %s=%s", gid, k, v)
                STATE[gid][k] = v
            await ws.send(_set_response(gid))
    else:
        _LOGGER.warning("Unknown command: %s", command)


# ---------------------------------------------------------------------------
# process_request: reject paths other than /b_xmlproc/
# ---------------------------------------------------------------------------

def _check_path(ws, request):
    """Return a 404 response for non-b_xmlproc paths."""
    if request.path != "/b_xmlproc/":
        return ws.respond(404, "Not found\n")
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(host: str, port: int) -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _LOGGER.info("Fake AE-200E starting on ws://%s:%d/b_xmlproc/", host, port)
    async with websockets.serve(
        handler,
        host,
        port,
        subprotocols=["b_xmlproc"],
        process_request=_check_path,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fake AE-200E WebSocket server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port))
