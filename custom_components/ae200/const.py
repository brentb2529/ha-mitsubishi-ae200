"""Constants for the AE-200E integration."""

DOMAIN = "ae200"

CONF_HOST = "host"

# Coordinator poll interval (seconds)
DEFAULT_SCAN_INTERVAL = 30

# AE-200E WebSocket subprotocol
WS_SUBPROTOCOL = "b_xmlproc"

# XML Drive values  [CONFIRMED from natevoci/ae200 + AE-200 manual]
DRIVE_ON = "ON"
DRIVE_OFF = "OFF"

# XML Mode values  [CONFIRMED from natevoci/ae200 reverse-engineering]
MODE_HEAT = "HEAT"
MODE_COOL = "COOL"
MODE_DRY = "DRY"
MODE_FAN = "FAN"
MODE_AUTO = "AUTO"

# XML FanSpeed values  [CONFIRMED from natevoci/ae200]
FAN_AUTO = "AUTO"
FAN_LOW = "LOW"
FAN_MID2 = "MID2"
FAN_MID1 = "MID1"
FAN_HIGH = "HIGH"

FAN_MODES = [FAN_AUTO, FAN_LOW, FAN_MID2, FAN_MID1, FAN_HIGH]

# AirDirection values  [CONFIRMED field name; exact values ASSUMED — tune per hardware]
AIR_DIR_AUTO = "AUTO"
AIR_DIR_HORIZONTAL = "HORIZONTAL"
AIR_DIR_22 = "22.5"
AIR_DIR_45 = "45"
AIR_DIR_67 = "67.5"
AIR_DIR_VERTICAL = "VERTICAL"
AIR_DIR_SWING = "SWING"

SWING_MODES = [AIR_DIR_AUTO, AIR_DIR_SWING, AIR_DIR_HORIZONTAL, AIR_DIR_45, AIR_DIR_VERTICAL]

# Temperature fallback limits [natevoci/ae200 defaults; replaced by controller values when present]
FALLBACK_MIN_TEMP = 16.0
FALLBACK_MAX_TEMP = 30.0
TEMP_STEP = 0.5
