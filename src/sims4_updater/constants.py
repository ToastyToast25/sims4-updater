import sys
from pathlib import Path

APP_NAME = "Sims 4 Updater"
APP_VERSION = "2.0.0"

# Manifest URL - configurable, backend-agnostic
MANIFEST_URL = ""
FALLBACK_MANIFEST_URLS = []

# EA OAuth2
EA_CLIENT_ID = "JUNO_PC_CLIENT"
EA_AUTH_URL = "https://accounts.ea.com/connect/auth"
EA_TOKEN_URL = "https://accounts.ea.com/connect/token"

# The Sims 4 registry keys for auto-detection
REGISTRY_PATHS = [
    r"SOFTWARE\Maxis\The Sims 4",
    r"SOFTWARE\WOW6432Node\Maxis\The Sims 4",
]

# Default install locations to probe
DEFAULT_GAME_PATHS = [
    r"C:\Program Files\EA Games\The Sims 4",
    r"C:\Program Files (x86)\EA Games\The Sims 4",
    r"D:\Games\The Sims 4",
]

# Sentinel files used for version fingerprinting
SENTINEL_FILES = [
    "Game/Bin/TS4_x64.exe",
    "Game/Bin/Default.ini",
    "delta/EP01/version.ini",
]

# Markers that confirm a directory is a Sims 4 install
SIMS4_INSTALL_MARKERS = [
    "Game/Bin/TS4_x64.exe",
    "Data/Client",
]


def get_data_dir():
    """Get the bundled data directory (works frozen and from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "data"
    return Path(__file__).resolve().parent.parent.parent / "data"


def get_tools_dir():
    """Get the bundled tools directory (works frozen and from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "tools"
    return Path(__file__).resolve().parent.parent.parent / "tools"


def get_mods_dir():
    """Get the bundled mods directory (works frozen and from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "mods"
    return Path(__file__).resolve().parent.parent.parent / "mods"


def get_icon_path():
    """Get path to the application icon (works frozen and from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "sims4.png"
    return Path(__file__).resolve().parent.parent.parent / "sims4.png"
