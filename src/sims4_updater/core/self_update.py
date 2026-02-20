"""
Self-update — check GitHub Releases for new updater versions, download and swap.

Flow:
  1. check_for_app_update() — compare local VERSION against latest GitHub release tag
  2. download_app_update() — stream the new exe to a temp file next to the current exe
  3. apply_app_update() — write a batch script that waits for us to exit, swaps exes, relaunches
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from .. import VERSION
from ..config import get_app_dir
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
    """Download the new exe to the app data updates directory.

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

    updates_dir = get_app_dir() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    new_path = updates_dir / f"Sims4Updater_v{info.latest_version}.exe"

    try:
        resp = requests.get(info.download_url, stream=True, timeout=(30, 300))
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

    # Verify download integrity — a truncated exe will crash on launch
    actual_size = new_path.stat().st_size
    if total and actual_size != total:
        new_path.unlink(missing_ok=True)
        raise SelfUpdateError(
            f"Download incomplete: got {actual_size:,} bytes, "
            f"expected {total:,} bytes. Please try again."
        )
    # Minimum size sanity check (PyInstaller onefile exes are typically >10MB)
    if actual_size < 5_000_000:
        new_path.unlink(missing_ok=True)
        raise SelfUpdateError(
            f"Downloaded file is too small ({actual_size:,} bytes). "
            f"The download may have been corrupted."
        )

    return new_path


def apply_app_update(new_exe: Path):
    """Replace the running exe with the new one and relaunch.

    Writes a batch script + VBScript wrapper to the app data updates directory.
    The VBScript launches the batch with a hidden window (no console flash).
    The batch:
      1. Waits for our process to exit (with 60s timeout)
      2. Validates the downloaded exe (exists, size, PE header)
      3. Renames the old exe out of the way (NTFS allows rename on locked files)
      4. Moves the new exe into place
      5. Cleans up and relaunches
      6. Logs everything to the updates directory

    On failure, attempts to restore the old exe so the user isn't stranded.
    """
    current_exe = _get_current_exe()
    old_exe = current_exe.with_name(current_exe.stem + "_old" + current_exe.suffix)
    pid = os.getpid()
    ppid = os.getppid()  # PyInstaller bootloader parent PID
    expected_size = new_exe.stat().st_size

    # Use full absolute paths — batch script runs from the updates directory
    cur = str(current_exe)
    cur_dir = str(current_exe.parent)
    old = str(old_exe)
    new = str(new_exe)
    updates_dir = get_app_dir() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(updates_dir / "_self_update.log")

    bat_path = updates_dir / "_self_update.bat"
    vbs_path = updates_dir / "_self_update.vbs"

    script = f'''@echo off
setlocal EnableDelayedExpansion
set "LOG={log_path}"

call :log "===== Self-update started ====="
call :log "PID to wait for: {pid}"
call :log "Current exe: {cur}"
call :log "New exe:     {new}"
call :log "Old backup:  {old}"

rem ── Clean up stale files from previous attempts ──
del /F "{old}" >NUL 2>&1

rem ── Clean up stale _MEI extraction dirs from previous os._exit() calls ──
call :log "Cleaning stale _MEI directories..."
for /d %%D in ("%TEMP%\\_MEI*") do (
    rd /s /q "%%D" >NUL 2>&1
)
call :log "Stale _MEI cleanup done."

rem ── Step 1: Wait for the updater process to exit (60s timeout) ──
call :log "Waiting for process {pid} to exit..."
set WAIT=0
:wait
tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL
if not errorlevel 1 (
    set /a WAIT+=1
    if !WAIT! GEQ 60 (
        call :log "ERROR: Process did not exit within 60 seconds."
        goto fail_no_restore
    )
    timeout /t 1 /nobreak >NUL
    goto wait
)
call :log "Process exited after !WAIT!s."

rem ── Kill the PyInstaller bootloader parent to prevent cleanup warning dialog ──
call :log "Killing bootloader parent (PID {ppid})..."
taskkill /F /PID {ppid} >NUL 2>&1
call :log "Waiting for file handle release..."
timeout /t 3 /nobreak >NUL

rem ── Step 2: Validate the downloaded exe ──
if not exist "{new}" (
    call :log "ERROR: Downloaded file not found: {new}"
    goto fail_no_restore
)

for %%A in ("{new}") do set "NEW_SIZE=%%~zA"
call :log "Downloaded file size: !NEW_SIZE! bytes (expected: {expected_size})"

if !NEW_SIZE! LSS 1000000 (
    call :log "ERROR: File too small (!NEW_SIZE! bytes) - likely corrupt or incomplete."
    goto fail_no_restore
)

rem Check PE header (first 2 bytes should be MZ)
set "HEADER="
for /f "usebackq" %%H in (`powershell -NoProfile -Command "[System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes('{new}')[0..1])"`) do set "HEADER=%%H"
if /I not "!HEADER!"=="MZ" (
    call :log "ERROR: File is not a valid Windows executable (missing MZ header)."
    goto fail_no_restore
)
call :log "PE header validated OK."

rem ── Step 3: Rename current exe out of the way ──
call :log "Renaming current exe to backup..."
set RETRIES=0
:rename_old
if exist "{cur}" (
    move /Y "{cur}" "{old}" >NUL 2>&1
    if errorlevel 1 (
        set /a RETRIES+=1
        if !RETRIES! GEQ 30 (
            call :log "ERROR: Cannot rename exe after 30 attempts."
            call :log "The file may be locked by antivirus or another program."
            call :log "Try: (1) Disable real-time antivirus  (2) Run as administrator  (3) Close other programs"
            goto fail_no_restore
        )
        call :log "  Rename attempt !RETRIES!/30 failed, retrying in 1s..."
        timeout /t 1 /nobreak >NUL
        goto rename_old
    )
)
call :log "Renamed OK (took !RETRIES! retries)."

rem ── Step 4: Move new exe into place ──
call :log "Moving new exe into place..."
move /Y "{new}" "{cur}" >NUL 2>&1
if errorlevel 1 (
    call :log "ERROR: Failed to move new exe into place."
    call :log "Check disk space and directory permissions."
    goto fail_restore
)
call :log "Move OK."

rem ── Step 5: Clean up backup (best effort) ──
del /F "{old}" >NUL 2>&1
if exist "{old}" (
    call :log "Note: Could not delete backup (still locked). Will be cleaned up next update."
) else (
    call :log "Backup cleaned up."
)

rem ── Step 6: Verify and Relaunch ──
call :log "Verifying updated exe before launch..."
for %%A in ("{cur}") do set "FINAL_SIZE=%%~zA"
call :log "Final exe size: !FINAL_SIZE! bytes"

rem Verify the final exe matches expected size
if !FINAL_SIZE! NEQ {expected_size} (
    call :log "ERROR: Final exe size mismatch (!FINAL_SIZE! vs {expected_size}). File may be corrupt."
    goto fail_restore
)

rem ── Pre-launch: trigger antivirus scan and wait for it to complete ──
call :log "Pre-scanning exe to trigger Defender cache..."
powershell -NoProfile -Command "[System.IO.File]::ReadAllBytes('{cur}').Length" >NUL 2>&1
call :log "Waiting 5 seconds for antivirus scan to complete..."
timeout /t 5 /nobreak >NUL

call :log "Launching updated version from: {cur_dir}"
cd /d "{cur_dir}"
call :log "Using explorer.exe to launch in user session..."
explorer.exe "{cur}"

rem Wait and check if the new process is running
timeout /t 5 /nobreak >NUL
tasklist /FI "IMAGENAME eq Sims4Updater.exe" 2>NUL | find /I "Sims4Updater" >NUL
if errorlevel 1 (
    call :log "WARNING: Updated exe does not appear to be running after launch."
    call :log "Retrying launch..."
    timeout /t 3 /nobreak >NUL
    start "" "{cur}"
    timeout /t 5 /nobreak >NUL
    tasklist /FI "IMAGENAME eq Sims4Updater.exe" 2>NUL | find /I "Sims4Updater" >NUL
    if errorlevel 1 (
        call :log "ERROR: Updated exe failed to start after retry."
        call :log "Try running it manually from: {cur}"
    ) else (
        call :log "Updated exe is running (after retry)."
    )
) else (
    call :log "Updated exe is running."
)
call :log "===== Self-update completed ====="
goto cleanup

:fail_restore
call :log "Attempting to restore previous version..."
if exist "{old}" (
    move /Y "{old}" "{cur}" >NUL 2>&1
    if not errorlevel 1 (
        call :log "Previous version restored. You can try updating again."
    ) else (
        call :log "CRITICAL: Could not restore previous version either!"
        call :log "You may need to re-download the application."
    )
)
goto cleanup

:fail_no_restore
call :log "Update failed. Your current version should still be intact."
goto cleanup

:cleanup
call :log "Log saved to: {log_path}"
rem Delete the VBS launcher
del /F "{vbs_path}" >NUL 2>&1
rem Self-delete
del "%~f0"
exit /b 0

:log
echo [%date% %time%] %~1 >> "%LOG%"
exit /b 0
'''

    bat_path.write_text(script, encoding="utf-8")

    # VBScript wrapper — launches the bat with a hidden window (no console flash)
    vbs_script = (
        'CreateObject("Wscript.Shell").Run '
        f'"cmd.exe /c ""{bat_path}""", 0, False'
    )
    vbs_path.write_text(vbs_script, encoding="utf-8")

    # Launch via wscript.exe — the VBS runs the bat silently
    subprocess.Popen(
        ["wscript.exe", str(vbs_path)],
        close_fds=True,
    )

    # Force-exit the Python child. The batch script will kill the bootloader
    # parent (via ppid) to prevent the "Failed to remove temporary directory" dialog.
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
