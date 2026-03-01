"""Game process detection and management utilities."""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)

_NO_WINDOW = subprocess.CREATE_NO_WINDOW

# Executable names the game can run as
_GAME_EXES = ("TS4_x64.exe", "TS4_DX9_x64.exe")


def is_game_running() -> bool:
    """Check whether a Sims 4 game process is currently running.

    Uses the Windows ``tasklist`` command to enumerate processes.
    Returns ``False`` on any error (non-Windows, permission denied, etc.).
    """
    for exe in _GAME_EXES:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {exe}"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_NO_WINDOW,
            )
            if exe.lower() in result.stdout.lower():
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug("Could not check for %s: %s", exe, e)
    return False


def get_game_pid() -> int | None:
    """Get the PID of a running Sims 4 process, or None if not running."""
    for exe in _GAME_EXES:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_NO_WINDOW,
            )
            for line in result.stdout.strip().splitlines():
                if exe.lower() in line.lower():
                    # CSV format: "image_name","pid","session","session#","mem"
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid_str = parts[1].strip().strip('"')
                        if pid_str.isdigit():
                            return int(pid_str)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug("Could not get PID for %s: %s", exe, e)
    return None


def kill_game_process() -> bool:
    """Kill any running Sims 4 game process. Returns True on success."""
    killed = False
    for exe in _GAME_EXES:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", exe],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=_NO_WINDOW,
            )
            if result.returncode == 0:
                killed = True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug("Could not kill %s: %s", exe, e)
    return killed
