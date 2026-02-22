"""
EA DLC Unlocker — native Python installer.

Uses a custom-built PandaDLL (version.dll) that reads entitlements from
%APPDATA%\\ToastyToast25\\EA DLC Unlocker\\entitlements.ini.

Detects EA Desktop via registry, copies version.dll, manages entitlements
config, and creates a scheduled task for staged updates.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..constants import get_tools_dir

# ── Constants ────────────────────────────────────────────────────

_COMMON_DIR = r"ToastyToast25\EA DLC Unlocker"
_ENTITLEMENTS_FILE = "entitlements.ini"
_TASK_NAME = "copy_dlc_unlocker"


# ── Admin Check ──────────────────────────────────────────────────

def is_admin() -> bool:
    """Check if the current process has administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


# ── Data ─────────────────────────────────────────────────────────

@dataclass
class UnlockerStatus:
    client_name: str  # "EA app"
    client_path: str  # resolved path to client directory
    dll_installed: bool
    config_installed: bool
    task_exists: bool  # scheduled task for EA Desktop staged updates


# ── Registry Detection ───────────────────────────────────────────

def _read_registry_value(key_path: str, value_name: str) -> str | None:
    """Read a string value from the Windows registry."""
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE,):
            for view in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                         winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(root, key_path, 0, view) as key:
                        val, _ = winreg.QueryValueEx(key, value_name)
                        return val
                except OSError:
                    continue
    except ImportError:
        pass
    return None


def _detect_client() -> tuple[str, Path]:
    """Detect EA Desktop. Returns (client_name, client_path)."""
    client_exe = _read_registry_value(
        r"SOFTWARE\Electronic Arts\EA Desktop", "ClientPath"
    )
    if client_exe:
        return "EA app", Path(client_exe).resolve().parent

    raise RuntimeError(
        "EA app not found. Please install the EA app first.\n"
        "Note: Origin is not supported by this unlocker."
    )


# ── Path Helpers ─────────────────────────────────────────────────

def _get_appdata_dir() -> Path:
    return Path(os.environ["APPDATA"]) / _COMMON_DIR


def _get_tools_unlocker_dir() -> Path:
    """Get the bundled DLC Unlocker tools directory."""
    return get_tools_dir() / "DLC Unlocker for Windows"


def _get_staged_dir(client_path: Path) -> Path:
    """EA Desktop staged directory (sibling to client dir)."""
    return client_path.parent / "StagedEADesktop" / "EA Desktop"


# ── Scheduled Task ───────────────────────────────────────────────

def _task_exists() -> bool:
    """Check if the copy_dlc_unlocker scheduled task exists."""
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", _TASK_NAME],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _create_task(dst_dll: Path, staged_dir: Path) -> bool:
    """Create scheduled task that copies version.dll to staged EA Desktop dir."""
    staged_wildcard = str(staged_dir) + "\\*"
    cmd = f'xcopy.exe /Y "{dst_dll}" "{staged_wildcard}"'
    for date_fmt in ("01/01/2000", "2000/01/01"):
        try:
            result = subprocess.run(
                [
                    "schtasks", "/Create", "/F", "/RL", "HIGHEST",
                    "/SC", "ONCE", "/ST", "00:00", "/SD", date_fmt,
                    "/TN", _TASK_NAME, "/TR", cmd,
                ],
                capture_output=True, timeout=15,
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _delete_task():
    """Delete the copy_dlc_unlocker scheduled task."""
    try:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", _TASK_NAME, "/F"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


# ── Kill Processes ───────────────────────────────────────────────

def _stop_client_processes(log: Callable[[str], None]):
    """Force-stop EA Desktop processes and wait for file locks to release."""
    killed_any = False
    for name in ("EADesktop", "EABackgroundService", "EALocalHostSvc"):
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", f"{name}.exe"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                killed_any = True
        except Exception:
            pass
    if killed_any:
        log("Client processes stopped. Waiting for file locks to release...")
        time.sleep(2)
    else:
        log("No running client processes found.")


# ── Remove Old Unlocker ─────────────────────────────────────────

def _remove_old_unlocker(client_path: Path, log: Callable[[str], None]):
    """Remove old unlocker files (version_o.dll, winhttp.dll, w_*.ini)."""
    for name in ("version_o.dll", "winhttp.dll", "winhttp_o.dll"):
        p = client_path / name
        try:
            if p.is_file():
                p.unlink()
                log(f"Removed old file: {name}")
        except PermissionError:
            log(f"Warning: Could not remove {name} (file locked)")

    try:
        for f in client_path.iterdir():
            if f.name.endswith(".ini") and f.name.startswith("w_"):
                try:
                    f.unlink()
                    log(f"Removed old config: {f.name}")
                except PermissionError:
                    log(f"Warning: Could not remove {f.name}")
    except PermissionError:
        log("Warning: Could not scan client directory for old configs")


# ── Copy with Retry ──────────────────────────────────────────────

def _copy_with_retry(src: Path, dst: Path, log: Callable[[str], None],
                     retries: int = 3, delay: float = 2.0):
    """Copy a file with retry logic for locked files."""
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError:
            if attempt < retries - 1:
                log(f"File locked, retrying in {delay}s... "
                    f"(attempt {attempt + 1}/{retries})")
                time.sleep(delay)
            else:
                raise PermissionError(
                    f"Cannot copy to {dst} — file is locked by another process. "
                    f"Close EA Desktop and try again."
                )


# ── Public API ───────────────────────────────────────────────────

def get_status(log: Callable[[str], None] | None = None) -> UnlockerStatus:
    """Detect client and gather current unlocker status."""
    if log is None:
        log = lambda _: None

    client_name, client_path = _detect_client()
    log(f"Detected {client_name} at: {client_path}")

    dst_dll = client_path / "version.dll"
    appdata_dir = _get_appdata_dir()
    dst_entitlements = appdata_dir / _ENTITLEMENTS_FILE

    dll_installed = dst_dll.is_file()
    config_installed = dst_entitlements.is_file()
    task = _task_exists()

    return UnlockerStatus(
        client_name=client_name,
        client_path=str(client_path),
        dll_installed=dll_installed,
        config_installed=config_installed,
        task_exists=task,
    )


def _fetch_cdn_entitlements(dst: Path, log: Callable[[str], None]) -> bool:
    """Try to download entitlements.ini from CDN. Returns True on success."""
    try:
        from ..config import Settings

        settings = Settings.load()
        if not settings.manifest_url:
            return False

        import requests as _req

        resp = _req.get(settings.manifest_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        url = data.get("entitlements_url", "")
        if not url:
            return False

        log(f"Fetching latest entitlements from CDN...")
        ent_resp = _req.get(url, timeout=30)
        ent_resp.raise_for_status()
        if len(ent_resp.content) < 100:
            return False  # Sanity check — too small to be valid

        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(ent_resp.content)
        log(f"Downloaded entitlements.ini from CDN ({len(ent_resp.content):,} bytes).")
        return True
    except Exception:
        return False


def install(log: Callable[[str], None]) -> None:
    """Install the DLC Unlocker."""
    if not is_admin():
        raise PermissionError(
            "Administrator privileges required.\n"
            "Please run the application as Administrator."
        )

    client_name, client_path = _detect_client()
    log(f"Detected {client_name} at: {client_path}")

    tools_dir = _get_tools_unlocker_dir()
    src_dll = tools_dir / "ea_app" / "version.dll"
    src_entitlements = tools_dir / _ENTITLEMENTS_FILE

    dst_dll = client_path / "version.dll"
    appdata_dir = _get_appdata_dir()
    dst_entitlements = appdata_dir / _ENTITLEMENTS_FILE

    staged_dir = _get_staged_dir(client_path)
    dst_dll2 = staged_dir / "version.dll"

    # Validate source files exist
    if not src_dll.is_file():
        raise FileNotFoundError(
            "version.dll missing from tools bundle. "
            "The file may be incomplete or removed by antivirus."
        )
    if not src_entitlements.is_file():
        raise FileNotFoundError(
            "entitlements.ini missing from tools bundle."
        )

    # Stop client processes
    log("Stopping client processes...")
    _stop_client_processes(log)

    # Remove old unlocker remnants
    _remove_old_unlocker(client_path, log)

    # Create appdata config directory
    appdata_dir.mkdir(parents=True, exist_ok=True)
    log(f"Config directory: {appdata_dir}")

    # Try CDN entitlements first, fall back to bundled copy
    if not _fetch_cdn_entitlements(dst_entitlements, log):
        shutil.copy2(src_entitlements, dst_entitlements)
        log("Entitlements config copied from bundled file.")

    # Copy version.dll to client directory (Program Files — needs admin)
    _copy_with_retry(src_dll, dst_dll, log)
    log(f"version.dll installed to: {dst_dll}")

    # Staged directory + scheduled task
    if staged_dir.is_dir():
        _copy_with_retry(src_dll, dst_dll2, log)
        log("version.dll copied to staged directory.")

    if _create_task(dst_dll, staged_dir):
        log("Scheduled task created for EA Desktop updates.")
    else:
        log("Warning: Could not create scheduled task. "
            "You may need to reinstall after EA app updates.")

    # Disable background standalone in machine.ini
    _BG_STANDALONE_LINE = "machine.bgsstandaloneenabled=0"
    machine_ini = (
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "EA Desktop" / "machine.ini"
    )
    try:
        existing = ""
        if machine_ini.is_file():
            existing = machine_ini.read_text(encoding="utf-8", errors="ignore")
        if _BG_STANDALONE_LINE not in existing:
            with open(machine_ini, "a", encoding="utf-8") as f:
                f.write(_BG_STANDALONE_LINE + "\n")
            log("Background standalone disabled in machine.ini.")
        else:
            log("Background standalone already disabled.")
    except Exception:
        log("Warning: Could not update machine.ini.")

    log("DLC Unlocker installed successfully!")


def uninstall(log: Callable[[str], None]) -> None:
    """Uninstall the DLC Unlocker."""
    if not is_admin():
        raise PermissionError(
            "Administrator privileges required.\n"
            "Please run the application as Administrator."
        )

    client_name, client_path = _detect_client()
    log(f"Detected {client_name} at: {client_path}")

    dst_dll = client_path / "version.dll"
    staged_dir = _get_staged_dir(client_path)
    dst_dll2 = staged_dir / "version.dll"
    appdata_dir = _get_appdata_dir()

    # Stop client processes
    log("Stopping client processes...")
    _stop_client_processes(log)

    # Remove old unlocker remnants
    _remove_old_unlocker(client_path, log)

    # Delete config directory
    if appdata_dir.is_dir():
        shutil.rmtree(appdata_dir, ignore_errors=True)
        log("Config directory removed.")
        parent = appdata_dir.parent
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    # Delete version.dll (retry in case file is still locked)
    for dll_path, label in [(dst_dll, "client"), (dst_dll2, "staged")]:
        if dll_path.is_file():
            for attempt in range(3):
                try:
                    dll_path.unlink()
                    log(f"version.dll removed from {label} directory.")
                    break
                except PermissionError:
                    if attempt < 2:
                        log(f"File locked, retrying in 2s... "
                            f"(attempt {attempt + 1}/3)")
                        time.sleep(2)
                    else:
                        log(f"Warning: Could not remove version.dll from "
                            f"{label} directory (file locked)")

    # Delete scheduled task
    _delete_task()
    log("Scheduled task removed.")

    log("DLC Unlocker uninstalled successfully!")


def open_configs_folder() -> bool:
    """Open the configs folder in Windows Explorer."""
    appdata_dir = _get_appdata_dir()
    if appdata_dir.is_dir():
        os.startfile(str(appdata_dir))
        return True
    return False
