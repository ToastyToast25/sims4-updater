"""
Self-update — check GitHub Releases for new updater versions, download and swap.

Flow:
  1. check_for_app_update() — compare local VERSION against latest GitHub release tag
  2. download_app_update() — stream the new exe to a temp file next to the current exe
  3. apply_app_update() — write a batch script that waits for us to exit, swaps exes, relaunches
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .. import VERSION
from .exceptions import UpdaterError

GITHUB_REPO = "ToastyToast25/sims4-updater"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
EXE_ASSET_NAME = "Sims4Updater.exe"


class SelfUpdateError(UpdaterError):
    pass


@dataclass
class AppUpdateInfo:
    """Result of checking for an app update."""

    current_version: str
    latest_version: str
    update_available: bool
    download_url: str = ""
    download_size: int = 0
    release_notes: str = ""


def check_for_app_update(timeout: int = 15) -> AppUpdateInfo:
    """Check GitHub Releases for a newer version of the updater.

    Returns:
        AppUpdateInfo with comparison result and download URL.

    Raises:
        SelfUpdateError on network or API errors.
    """
    try:
        resp = requests.get(
            GITHUB_API,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
        if resp.status_code == 404:
            # No releases yet — not an error, just no update
            return AppUpdateInfo(
                current_version=VERSION,
                latest_version=VERSION,
                update_available=False,
            )
        resp.raise_for_status()
        data = resp.json()
    except SelfUpdateError:
        raise
    except Exception as e:
        raise SelfUpdateError(f"Failed to check for app updates: {e}") from e

    tag = data.get("tag_name", "")
    # Strip leading 'v' if present (e.g. "v2.1.0" → "2.1.0")
    latest = tag.lstrip("v")

    if not latest:
        raise SelfUpdateError("Could not determine latest version from GitHub.")

    # Find the exe asset
    download_url = ""
    download_size = 0
    for asset in data.get("assets", []):
        if asset.get("name", "").lower() == EXE_ASSET_NAME.lower():
            download_url = asset["browser_download_url"]
            download_size = asset.get("size", 0)
            break

    update_available = _version_newer(latest, VERSION)

    return AppUpdateInfo(
        current_version=VERSION,
        latest_version=latest,
        update_available=update_available,
        download_url=download_url,
        download_size=download_size,
        release_notes=data.get("body", ""),
    )


def download_app_update(
    info: AppUpdateInfo,
    progress=None,
) -> Path:
    """Download the new exe to a temp file next to the running exe.

    Args:
        info: AppUpdateInfo from check_for_app_update().
        progress: Optional callback(bytes_downloaded, total_bytes).

    Returns:
        Path to the downloaded new exe.
    """
    if not info.download_url:
        raise SelfUpdateError(
            "No download URL for the updater exe. "
            "The release may not have a Sims4Updater.exe asset."
        )

    current_exe = _get_current_exe()
    new_path = current_exe.with_name(f"Sims4Updater_v{info.latest_version}.exe")

    try:
        resp = requests.get(info.download_url, stream=True, timeout=(30, 120))
        resp.raise_for_status()

        total = int(resp.headers.get("Content-Length", 0)) or info.download_size
        downloaded = 0

        with open(new_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)

    except Exception as e:
        new_path.unlink(missing_ok=True)
        raise SelfUpdateError(f"Download failed: {e}") from e

    return new_path


def apply_app_update(new_exe: Path):
    """Replace the running exe with the new one and relaunch.

    Creates a batch script that:
      1. Waits for the current process to exit
      2. Replaces the old exe with the new one
      3. Launches the new exe
      4. Deletes itself
    """
    current_exe = _get_current_exe()
    pid = os.getpid()

    # Write the updater batch script next to the exe
    bat_path = current_exe.with_name("_self_update.bat")
    script = f'''@echo off
title Sims 4 Updater - Self Update
echo Waiting for updater to close...
:wait
tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto wait
)
echo Process exited. Waiting for file lock release...
timeout /t 2 /nobreak >NUL
echo Applying update...
set RETRIES=0
:retry
move /Y "{new_exe}" "{current_exe}" >NUL 2>&1
if not errorlevel 1 goto moved
set /a RETRIES+=1
if %RETRIES% GEQ 10 (
    echo ERROR: Failed to replace exe after 10 attempts.
    echo The file may be locked by antivirus or require administrator privileges.
    pause
    exit /b 1
)
echo Retry %RETRIES%/10 - file still locked, waiting...
timeout /t 2 /nobreak >NUL
goto retry
:moved
echo Starting updated Sims 4 Updater...
start "" "{current_exe}"
del "%~f0"
'''

    bat_path.write_text(script, encoding="utf-8")

    # Launch the batch script in a new console window
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        close_fds=True,
    )

    # Force-exit the process so the batch script can replace the exe
    os._exit(0)


def _get_current_exe() -> Path:
    """Get the path to the currently running exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    # Running from source — use a placeholder for testing
    return Path(sys.argv[0]).resolve()


def _version_newer(remote: str, local: str) -> bool:
    """Compare version strings. Returns True if remote > local."""
    try:
        remote_parts = [int(x) for x in remote.split(".")]
        local_parts = [int(x) for x in local.split(".")]
        return remote_parts > local_parts
    except (ValueError, AttributeError):
        return remote != local
