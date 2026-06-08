"""Conftest for HA-runtime config/options/reconfigure flow tests.

This conftest provides a minimal `hass` fixture built directly from
pytest_homeassistant_custom_component.common.async_test_home_assistant,
bypassing the phcc plugins.py file which has a Python 3.14 annotation
incompatibility (NameError: name 'recorder' is not defined at collection time).

The custom-components discovery cache is cleared after hass starts so that
HA's loader re-discovers custom_components/ae200/ from the repo root.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

# Ensure the repo root is importable so custom_components.ae200 resolves.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Register the real custom_components package (not the stub from tests/conftest.py).
import types as _types

if "custom_components" not in sys.modules:
    _pkg = _types.ModuleType("custom_components")
    _pkg.__path__ = [os.path.join(REPO_ROOT, "custom_components")]
    sys.modules["custom_components"] = _pkg
else:
    # Ensure our repo's custom_components path is on the package.__path__.
    _cc = sys.modules["custom_components"]
    _cc_path = os.path.join(REPO_ROOT, "custom_components")
    if hasattr(_cc, "__path__") and _cc_path not in list(_cc.__path__):
        _cc.__path__.insert(0, _cc_path)

# Remove any stub for custom_components.ae200 so the real module is loaded.
sys.modules.pop("custom_components.ae200", None)


@pytest.fixture
async def hass():
    """Home Assistant test instance that can discover custom_components/ae200/.

    The DATA_CUSTOM_COMPONENTS cache is cleared right after hass starts so
    the loader re-scans custom_components.__path__ and finds ae200.
    """
    from homeassistant.loader import DATA_CUSTOM_COMPONENTS
    from pytest_homeassistant_custom_component.common import async_test_home_assistant

    loop = asyncio.get_running_loop()
    async with async_test_home_assistant(loop, config_dir=REPO_ROOT) as hass_instance:
        # Bust the cache so HA re-discovers ae200 on next lookup.
        hass_instance.data.pop(DATA_CUSTOM_COMPONENTS, None)
        yield hass_instance
