"""Constants for the AE-200E / EW-50E integration."""

DOMAIN = "ae200"

# Config-entry key (re-exported from HA's const for convenience within the package)
CONF_HOST = "host"

# Coordinator poll interval (seconds) — not user-configurable
DEFAULT_SCAN_INTERVAL = 30

# AE-200E WebSocket path and subprotocol  [CONFIRMED from natevoci/ae200 + AE-200 manual p.83]
WS_SUBPROTOCOL = "b_xmlproc"
WS_PATH = "/b_xmlproc/"

# ---------------------------------------------------------------------------
# XML Drive values  [CONFIRMED from natevoci/ae200 + AE-200 manual]
# ---------------------------------------------------------------------------
DRIVE_ON = "ON"
DRIVE_OFF = "OFF"

# ---------------------------------------------------------------------------
# XML Mode values  [CONFIRMED from natevoci/ae200 reverse-engineering]
# ---------------------------------------------------------------------------
MODE_HEAT = "HEAT"
MODE_COOL = "COOL"
MODE_DRY = "DRY"
MODE_FAN = "FAN"
MODE_AUTO = "AUTO"

# ---------------------------------------------------------------------------
# XML FanSpeed values  [CONFIRMED from natevoci/ae200]
# ---------------------------------------------------------------------------
FAN_AUTO = "AUTO"
FAN_LOW = "LOW"
FAN_MID2 = "MID2"
FAN_MID1 = "MID1"
FAN_HIGH = "HIGH"

FAN_MODES: list[str] = [FAN_AUTO, FAN_LOW, FAN_MID2, FAN_MID1, FAN_HIGH]

# ---------------------------------------------------------------------------
# AirDirection / swing mode values
#
# CONFIRMED field name; values ASSUMED — tune per hardware.
# The AE-200E returns string values for vane position.  Known observations:
#   natevoci/ae200: no hard constants but "AUTO" / "SWING" present in code.
#   Mitsubishi BACnet IB: positions named HORIZONTAL, mid-1, mid-2, VERTICAL.
#   Numeric ("1"–"5") variants also appear in some firmware revisions.
# Rule: accept any value the controller returns; never crash; log unknown.
# ---------------------------------------------------------------------------
AIR_DIR_AUTO = "AUTO"
AIR_DIR_HORIZONTAL = "HORIZONTAL"
AIR_DIR_22 = "22.5"
AIR_DIR_45 = "45"
AIR_DIR_67 = "67.5"
AIR_DIR_VERTICAL = "VERTICAL"
AIR_DIR_SWING = "SWING"

# Numeric position variants (some firmware versions use "1"–"5")
AIR_DIR_POS_1 = "1"
AIR_DIR_POS_2 = "2"
AIR_DIR_POS_3 = "3"
AIR_DIR_POS_4 = "4"
AIR_DIR_POS_5 = "5"

# Swing modes offered to HA — the CONFIRMED set sent to the controller.
# The receive side accepts any string; unknown values are preserved as-is.
SWING_MODES: list[str] = [
    AIR_DIR_AUTO,
    AIR_DIR_SWING,
    AIR_DIR_HORIZONTAL,
    AIR_DIR_45,
    AIR_DIR_VERTICAL,
]

# ---------------------------------------------------------------------------
# FilterSign / ErrorSign encoding
#
# ASSUMED — no official documentation for the exact value set.
# Observed values: "0" = clear, "1" = set.
# Additional safe-fallback aliases: "OFF", "NONE", "" = clear.
# Any non-zero / non-"NONE" / non-"OFF" value is treated as set.
# ---------------------------------------------------------------------------

# Values that mean "sign is clear / no fault".
# Note: "" is included defensively but _get() returns None before _bool_sign sees it,
# so an empty field → None (unknown), not False (clear).  This matches the HA
# convention: return None when the device hasn't populated a field.
_SIGN_CLEAR_VALUES: frozenset[str] = frozenset({"0", "NONE", "OFF", ""})

# ---------------------------------------------------------------------------
# Temperature fallback limits
# [natevoci/ae200 defaults; replaced by controller per-mode values when present]
# ---------------------------------------------------------------------------
FALLBACK_MIN_TEMP = 16.0
FALLBACK_MAX_TEMP = 30.0
TEMP_STEP = 0.5

# ---------------------------------------------------------------------------
# Device registry strings
# ---------------------------------------------------------------------------
MANUFACTURER = "Mitsubishi Electric"
MODEL_CONTROLLER = "AE-200E / EW-50E"
MODEL_GROUP = "City Multi Indoor Group"
