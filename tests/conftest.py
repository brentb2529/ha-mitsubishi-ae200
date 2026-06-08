"""pytest fixtures for AE-200E tests.

We import ae200client and const directly to avoid pulling in HA core
(homeassistant.*) which is not installed in the test venv.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import os
import sys
import threading

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
import types

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
from fake.fake_ae200 import STATE, GROUPS, _DEFAULT_STATE  # noqa: E402

# ---------------------------------------------------------------------------

FAKE_HOST = "127.0.0.1"
FAKE_PORT = 7778


@pytest.fixture(scope="session")
def fake_server():
    """Start the fake AE-200E WebSocket server for the test session.

    Returns the host:port string to pass to AE200Client.
    """
    import websockets
    from fake.fake_ae200 import handler, _check_path

    # Reset to known state
    for gid in list(STATE.keys()):
        STATE[gid] = copy.deepcopy(_DEFAULT_STATE)
    STATE["2"]["FilterSign"] = "1"

    ready = threading.Event()
    srv_holder: dict = {}

    def _run_server():
        async def _main():
            srv = await websockets.serve(
                handler,
                FAKE_HOST,
                FAKE_PORT,
                subprotocols=["b_xmlproc"],
                process_request=_check_path,
            )
            srv_holder["server"] = srv
            ready.set()
            await asyncio.Future()

        asyncio.run(_main())

    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    assert ready.wait(timeout=5), "Fake server did not start in time"

    yield f"{FAKE_HOST}:{FAKE_PORT}"

    if "server" in srv_holder:
        srv_holder["server"].close()
