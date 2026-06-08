"""pytest fixtures for AE-200E tests.

We import ae200client and const directly to avoid pulling in HA core
(homeassistant.*) which is not installed in the test venv.
"""
from __future__ import annotations

import asyncio
import copy
import os
import sys
import threading
import types

import pytest

# ---------------------------------------------------------------------------
# Make the repo root importable so both custom_components.ae200.ae200client
# and fake.fake_ae200 resolve correctly.
# We patch sys.modules to short-circuit the HA-importing __init__.py.
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Install a stub package for `custom_components.ae200` so sub-modules
# (ae200client, const) can be imported without touching __init__.py
_pkg = types.ModuleType("custom_components")
_pkg.__path__ = [os.path.join(REPO_ROOT, "custom_components")]
sys.modules.setdefault("custom_components", _pkg)

_sub = types.ModuleType("custom_components.ae200")
_sub.__path__ = [os.path.join(REPO_ROOT, "custom_components", "ae200")]
_sub.__package__ = "custom_components.ae200"
sys.modules["custom_components.ae200"] = _sub

# Now safe to import the modules that don't pull in homeassistant.*
from custom_components.ae200.ae200client import AE200Client, GroupInfo, GroupState  # noqa: E402
from custom_components.ae200.const import (  # noqa: E402
    MODE_COOL, MODE_HEAT, MODE_DRY, MODE_FAN, MODE_AUTO,
    FALLBACK_MIN_TEMP, FALLBACK_MAX_TEMP,
)
from fake.fake_ae200 import STATE, GROUPS, _DEFAULT_STATE, _STATE_2  # noqa: E402

# ---------------------------------------------------------------------------

FAKE_HOST = "127.0.0.1"
FAKE_PORT = 7778


def _start_fake_server(host: str, port: int, state: dict) -> None:
    """Start a fake AE-200E server in a daemon thread.

    Returns the threading.Event that is set when the server is ready.
    """
    import websockets
    from fake.fake_ae200 import _check_path

    # Build a handler that uses the provided state dict (so each server has
    # its own independent mutable state for multi-controller tests).
    import xml.etree.ElementTree as ET

    def _get_groups_response_local() -> str:
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

    def _get_mnet_response_local(group_ids: list[str]) -> str:
        mnets = []
        for gid in group_ids:
            if gid not in state:
                continue
            attrs = " ".join(f'{k}="{v}"' for k, v in state[gid].items())
            mnets.append(f'<Mnet Group="{gid}" {attrs} />')
        return (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            "<Packet><Command>getResponse</Command>"
            f"<DatabaseManager>{''.join(mnets)}</DatabaseManager></Packet>"
        )

    def _set_response_local(group_id: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" ?>'
            "<Packet><Command>setResponse</Command>"
            f'<DatabaseManager><Mnet Group="{group_id}" /></DatabaseManager></Packet>'
        )

    async def local_handler(ws) -> None:
        try:
            async for message in ws:
                try:
                    raw = str(message)
                    root = ET.fromstring(raw)
                    command = root.findtext("Command", "").strip()
                    if command == "getRequest":
                        if root.find("./DatabaseManager/ControlGroup/MnetList") is not None:
                            await ws.send(_get_groups_response_local())
                            continue
                        mnets = root.findall("./DatabaseManager/Mnet")
                        gids = [m.get("Group") for m in mnets if m.get("Group")]
                        await ws.send(_get_mnet_response_local(gids))
                    elif command == "setRequest":
                        for mnet in root.findall("./DatabaseManager/Mnet"):
                            gid = mnet.get("Group")
                            if gid not in state:
                                continue
                            for k, v in mnet.attrib.items():
                                if k == "Group":
                                    continue
                                state[gid][k] = v
                            await ws.send(_set_response_local(gid))
                except Exception:
                    pass
        except websockets.ConnectionClosedOK:
            pass

    ready = threading.Event()

    def _run():
        async def _main():
            srv = await websockets.serve(
                local_handler,
                host,
                port,
                subprotocols=["b_xmlproc"],
                process_request=_check_path,
            )
            ready.set()
            await asyncio.Future()

        asyncio.run(_main())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    assert ready.wait(timeout=5), f"Fake server on port {port} did not start in time"


@pytest.fixture(scope="session")
def fake_server():
    """Start the primary fake AE-200E server for the test session.

    Returns the host:port string to pass to AE200Client.
    """
    # Reset to known state
    for gid in list(STATE.keys()):
        STATE[gid] = copy.deepcopy(_DEFAULT_STATE)
    STATE["2"]["FilterSign"] = "1"

    _start_fake_server(FAKE_HOST, FAKE_PORT, STATE)
    yield f"{FAKE_HOST}:{FAKE_PORT}"


# ---------------------------------------------------------------------------
# Second fake server for multi-controller tests (separate port, separate state)
# ---------------------------------------------------------------------------

FAKE_HOST_2 = "127.0.0.1"
FAKE_PORT_2 = 7779

@pytest.fixture(scope="session")
def fake_server_2():
    """Start a second fake AE-200E server (different port/state) for multi-controller tests."""
    _start_fake_server(FAKE_HOST_2, FAKE_PORT_2, _STATE_2)
    yield f"{FAKE_HOST_2}:{FAKE_PORT_2}"
