"""
Steam installation detection and process checks for GreenLuma integration.

Detects the Steam install path via registry and filesystem probes, checks
whether Steam is currently running, and gathers GreenLuma-related directory
and DLL information into a SteamInfo dataclass.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# DLLs that indicate GreenLuma 2025 is present
_GREENLUMA_DLLS = ("GreenLuma_2025_x64.dll", "GreenLuma_2025_x86.dll")

# Registry key for the Steam install path
_STEAM_REGISTRY_KEY = r"SOFTWARE\Valve\Steam"
_STEAM_REGISTRY_VALUE = "InstallPath"

# Fallback directories to probe when the registry lookup fails
_FALLBACK_STEAM_PATHS = [
    Path(r"C:\Program Files (x86)\Steam"),
    Path(r"C:\Program Files\Steam"),
    Path(r"D:\Steam"),
]


@dataclass
class SteamInfo:
    """Describes a Steam installation and its GreenLuma state."""

    steam_path: Path
    applist_dir: Path             # steam_path / "AppList"
    config_vdf_path: Path         # steam_path / "config" / "config.vdf"
    depotcache_dir: Path          # steam_path / "depotcache"
    steamapps_dir: Path           # steam_path / "steamapps"
    greenluma_installed: bool
    greenluma_mode: str           # "normal" | "stealth" | "none"


# ── Steam Path Detection ────────────────────────────────────────────


def detect_steam_path() -> Path | None:
    """Detect the Steam installation directory.

    Checks the Windows registry (both 64-bit and 32-bit views) first,
    then falls back to common filesystem locations.  Returns the first
    valid path that contains ``steam.exe``, or ``None`` if Steam cannot
    be found.
    """
    # Try registry first
    registry_path = _read_steam_path_from_registry()
    if registry_path and _has_steam_exe(registry_path):
        logger.debug("Steam found via registry: %s", registry_path)
        return registry_path

    # Fallback to well-known paths
    for candidate in _FALLBACK_STEAM_PATHS:
        if _has_steam_exe(candidate):
            logger.debug("Steam found at fallback path: %s", candidate)
            return candidate

    logger.debug("Steam installation not found")
    return None


def _read_steam_path_from_registry() -> Path | None:
    """Read the Steam install path from the Windows registry."""
    try:
        import winreg
    except ImportError:
        return None

    for view in (
        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
    ):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, _STEAM_REGISTRY_KEY, 0, view,
            ) as key:
                value, _ = winreg.QueryValueEx(key, _STEAM_REGISTRY_VALUE)
                if value:
                    return Path(value)
        except (OSError, FileNotFoundError):
            continue

    return None


def _has_steam_exe(path: Path) -> bool:
    """Return True if the directory exists and contains steam.exe."""
    try:
        return path.is_dir() and (path / "steam.exe").is_file()
    except OSError:
        return False


# ── Process Check ────────────────────────────────────────────────────


def is_steam_running() -> bool:
    """Check whether a ``steam.exe`` process is currently running.

    Uses the Windows ``tasklist`` command to enumerate processes.
    Returns ``False`` on any error (non-Windows, permission denied, etc.).
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "steam.exe" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("Could not check if Steam is running: %s", e)
        return False


# ── Steam Info ───────────────────────────────────────────────────────


def get_steam_info(steam_path: Path) -> SteamInfo:
    """Build a :class:`SteamInfo` for the given Steam directory.

    Inspects the directory tree for GreenLuma DLLs and the DLLInjector
    to determine the GreenLuma mode:

    * ``"normal"`` -- GreenLuma DLLs are present inside the Steam directory.
    * ``"stealth"`` -- A ``DLLInjector.ini`` file exists (typically placed
      in the Steam directory or a parent directory by the stealth loader).
    * ``"none"`` -- No GreenLuma artifacts detected.
    """
    applist_dir = steam_path / "AppList"
    config_vdf_path = steam_path / "config" / "config.vdf"
    depotcache_dir = steam_path / "depotcache"
    steamapps_dir = steam_path / "steamapps"

    greenluma_installed, greenluma_mode = _detect_greenluma(steam_path)

    return SteamInfo(
        steam_path=steam_path,
        applist_dir=applist_dir,
        config_vdf_path=config_vdf_path,
        depotcache_dir=depotcache_dir,
        steamapps_dir=steamapps_dir,
        greenluma_installed=greenluma_installed,
        greenluma_mode=greenluma_mode,
    )


def _detect_greenluma(steam_path: Path) -> tuple[bool, str]:
    """Detect GreenLuma presence and mode.

    Returns:
        A tuple of ``(installed, mode)`` where *mode* is one of
        ``"normal"``, ``"stealth"``, or ``"none"``.
    """
    # Normal mode: GreenLuma DLLs live directly in the Steam directory
    has_dlls = all(
        (steam_path / dll).is_file() for dll in _GREENLUMA_DLLS
    )
    if has_dlls:
        return True, "normal"

    # Stealth mode: DLLInjector.ini in steam dir or parent directories
    for search_dir in (steam_path, steam_path.parent):
        try:
            if (search_dir / "DLLInjector.ini").is_file():
                return True, "stealth"
            if (search_dir / "DLLInjector.exe").is_file():
                return True, "stealth"
        except OSError:
            continue

    return False, "none"


# ── Validation ───────────────────────────────────────────────────────


def validate_steam_path(path: Path) -> bool:
    """Validate that *path* looks like a real Steam installation.

    Checks for:
    * Directory exists
    * ``steam.exe`` present
    * ``config/`` subdirectory exists
    * ``depotcache/`` subdirectory exists
    """
    try:
        if not path.is_dir():
            return False
        if not (path / "steam.exe").is_file():
            return False
        if not (path / "config").is_dir():
            return False
        return (path / "depotcache").is_dir()
    except OSError:
        return False
