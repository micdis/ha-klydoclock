"""Constants for the Klydoclock integration."""

from datetime import timedelta

DOMAIN = "klydoclock"

DEFAULT_PORT = 5555
SCAN_INTERVAL = timedelta(seconds=10)
CATALOG_MIN_REFRESH = timedelta(minutes=10)

PACKAGE = "com.klydoclock"
DATA_DIR = f"/data/data/{PACKAGE}"
SETTINGS_PATH = f"{DATA_DIR}/files/datastore/synced_settings.preferences_pb"
DATABASE_PATH = f"{DATA_DIR}/databases/klydo_database"
ARTISTS_PATH = f"{DATA_DIR}/files/datastore/cache_artists.preferences_pb"

ADB_KEY_FILE = "klydoclock_adbkey"

SERVICE_SHOW_KLYDO = "show_klydo"
ATTR_KLYDO = "klydo"

# Several keys sent in one `input keyevent` call cost barely more than one;
# the app may skip ahead under rapid input, so batches are verified afterwards.
NAV_BATCH = 15

# Key codes sent by the original remote ("Klydoremote"), captured from the clock.
KEY_SLEEP = 42
KEY_INFO = 19
KEY_SETTINGS = 20
KEY_PREVIOUS = 21
KEY_NEXT = 22
KEY_FAVORITE = 66

# The sleep key cycles through these display modes, in this order.
DISPLAY_BRIGHT = "bright"
DISPLAY_MEDIUM = "medium"
DISPLAY_DIM = "dim"
DISPLAY_NIGHT = "night"
DISPLAY_OFF = "off"
DISPLAY_MODES = [DISPLAY_BRIGHT, DISPLAY_MEDIUM, DISPLAY_DIM, DISPLAY_NIGHT, DISPLAY_OFF]
BRIGHTNESS_TO_MODE = {"10": DISPLAY_BRIGHT, "7": DISPLAY_MEDIUM, "4": DISPLAY_DIM}
