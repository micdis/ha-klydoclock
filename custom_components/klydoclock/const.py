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
SERVICE_SET_MODE = "set_mode"
SERVICE_SHOW_VIDEO = "show_video"
SERVICE_SET_VIDEO = "set_video"
ATTR_KLYDO = "klydo"
ATTR_MODE = "mode"
ATTR_VIDEO = "video"

# Each klydo plays /sdcard/gifs2/<mainLoop>/<mainLoop>.mp4. The app keeps no
# checksum of these files, so a klydo can be given another video.
VIDEO_DIR = "/data/media/0/gifs2"
VIDEO_OWNER = "media_rw:media_video"
VIDEO_LABEL = "u:object_r:media_rw_data_file:s0"
# Every uploaded video is also kept here, named by its MD5, so switching a
# klydo between videos it had before is a local copy instead of an upload.
# Outside gifs2, which the app's midnight cleanup prunes.
VIDEO_CACHE = "/data/media/0/klydoclock-ha"
MAX_VIDEO_BYTES = 20 * 1024 * 1024
# Raw bytes per shell call when uploading; adb-shell's file sync push stalls
# against this clock, base64 through the shell does not.
UPLOAD_CHUNK = 24 * 1024

# Playback modes the integration can switch to, keyed by service option.
MODE_FEED = "FEED"
MODE_FAVORITE = "FAVORITE"
MODES = {"feed": MODE_FEED, "favorite": MODE_FAVORITE}

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

# In the home menu (opened by the settings key) left/right turn the selection
# around the ring and the favorite key (Enter) confirms it. The menu opens on
# the current mode and, left alone for about a minute, falls back to FEED, so
# every menu operation must end with Enter.
KEY_MENU = KEY_SETTINGS
KEY_ENTER = KEY_FAVORITE
MENU_MAX_STEPS = 8
MENU_FEED_ANGLE = 0.0  # FEED sits at 12 o'clock, FAVORITES one entry clockwise
MENU_TOLERANCE = 15.0

# The sleep key cycles through these display modes, in this order.
DISPLAY_BRIGHT = "bright"
DISPLAY_MEDIUM = "medium"
DISPLAY_DIM = "dim"
DISPLAY_NIGHT = "night"
DISPLAY_OFF = "off"
DISPLAY_MODES = [DISPLAY_BRIGHT, DISPLAY_MEDIUM, DISPLAY_DIM, DISPLAY_NIGHT, DISPLAY_OFF]
BRIGHTNESS_TO_MODE = {"10": DISPLAY_BRIGHT, "7": DISPLAY_MEDIUM, "4": DISPLAY_DIM}
