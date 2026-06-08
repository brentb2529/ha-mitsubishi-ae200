# Mitsubishi City Multi — AE-200E / EW-50E Integration

Home Assistant custom integration for Mitsubishi Electric City Multi commercial VRF systems
via the **AE-200E** or **EW-50E** central controller's LAN1 WebSocket XML API.

## Supported Controllers

| Model | Notes |
|---|---|
| AE-200E | Touchscreen + web server. Up to 50 indoor units. |
| AE-50E | Expansion unit. Identical LAN1 protocol to AE-200E. |
| EW-50E | DIN-rail form. Identical LAN1 protocol to AE-200E. |

Multiple controllers are supported: each controller is added as a separate config entry.

## Protocol

Uses the LAN1 **WebSocket XML** (`b_xmlproc`) interface — Mitsubishi's "XML BMS Interface".
No extra hardware, no license key, no cloud required. Runs entirely on your LAN.

- WebSocket URL: `ws://<controller-ip>/b_xmlproc/`
- Subprotocol: `b_xmlproc`
- Authentication: none (unauthenticated on LAN1)

## Prerequisites

- AE-200E / EW-50E reachable on your LAN (LAN1 port)
- Home Assistant 2024.1.0 or later
- HACS (for installation from this repository)

## Installation

### Via HACS (recommended)

1. Add this repository as a **custom repository** in HACS:
   - Type: Integration
   - URL: `https://github.com/bensten/ae200`
2. Install **Mitsubishi City Multi (AE-200E / EW-50E)**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/ae200/` into your HA `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Mitsubishi City Multi**.
3. Enter the LAN1 IP address or hostname of your controller.
4. HA will connect, discover all groups, and create entities automatically.

To add a second controller, repeat from step 1 — each controller is its own entry.

## Entities

### Per controller (one set per AE-200E / EW-50E)

| Entity | Platform | Notes |
|---|---|---|
| Outdoor Temperature | `sensor` | Outdoor unit temperature in °C. Diagnostic. |

### Per indoor group (one set per group defined in the controller)

| Entity | Platform | Notes |
|---|---|---|
| Climate | `climate` | HVAC mode, setpoint, fan speed, swing/vane |
| Inlet Temperature | `sensor` | Return-air sensor in °C |
| Filter | `binary_sensor` | `problem` class. True = filter cleaning due |
| Error | `binary_sensor` | `problem` class. True = active fault |

### Climate entity details

- **HVAC modes:** `off`, `heat`, `cool`, `dry`, `fan_only`, `auto`
- **Fan modes:** `AUTO`, `LOW`, `MID2`, `MID1`, `HIGH`
- **Swing modes (vane):** `AUTO`, `SWING`, `HORIZONTAL`, `45`, `VERTICAL`
  (exact values are hardware-dependent; pass-through values from the controller are preserved)
- **Temperature unit:** Celsius (HA converts to Fahrenheit if your HA unit is °F)
- **Temperature step:** 0.5°C
- **Setpoint limits:** Pulled from the controller per mode (CoolMin/Max, HeatMin/Max, AutoMin/Max)

## Device Registry

- One **controller device** per config entry (manufacturer: Mitsubishi Electric, model: AE-200E / EW-50E)
- One **group device** per indoor group, linked to the controller via `via_device`

## Known Limitations / Hardware-Dependent Behaviour

- **AirDirection values** — the vane position field name is confirmed but the exact value
  strings vary by hardware/firmware. The integration passes through raw values without crashing.
  Unknown swing modes are accepted and sent to the controller as-is. Run the diagnostics
  dump (`Developer Tools → Diagnostics`) to confirm the values your hardware uses.
- **FilterSign / ErrorSign encoding** — observed as `"0"` = clear, `"1"` = set.
  Alternative clear values (`"NONE"`, `"OFF"`) are also accepted. Any other non-zero value
  is treated as set. Confirm via diagnostics on real hardware.
- **Outdoor temperature** — reported per-group; the integration uses the first non-None value
  across all groups (all report the same outdoor unit).
- **hvac_action** — derived from Drive + Mode. No direct "compressor active" bit in the protocol;
  `AUTO` mode returns `idle` as a conservative default.

## Diagnostics

Under **Settings → Devices → [Your AE-200E] → Diagnostics**, the dump contains the raw
XML field values returned by the controller. This is the primary tool for validating
the ASSUMED field encodings (AirDirection, FilterSign, ErrorSign) against real hardware.

The host/IP address is redacted in the diagnostics output.

## Development / Testing

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/pytest tests/ -v

# Run the fake server standalone for manual testing:
python fake/fake_ae200.py --host 127.0.0.1 --port 7777
```

## Quality Scale

This integration targets **Bronze** HACS/HA quality scale.
See `custom_components/ae200/quality_scale.yaml` for per-rule status.

Silver gaps: dynamic device add/remove without reload, exception translation strings,
parallel-updates guard, repair issues, stale-device pruning.

## Brands / Icons

Brand icon submission to the Home Assistant brands repository is pending.
Local brand files (HA >= 2026.3) would go in `custom_components/ae200/brand/`.

## License

MIT — see [LICENSE](LICENSE).
