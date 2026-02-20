"""
EA DLC Unlocker — native Python installer.

Uses a custom-built PandaDLL (version.dll) that reads entitlements from
%APPDATA%\\ToastyToast25\\EA DLC Unlocker\\entitlements.ini.

Detects EA Desktop via registry, copies version.dll, manages entitlements
config, and creates a scheduled task for staged updates.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..constants import get_tools_dir

# ── Constants ────────────────────────────────────────────────────

_COMMON_DIR = r"ToastyToast25\EA DLC Unlocker"
_ENTITLEMENTS_FILE = "entitlements.ini"
_TASK_NAME = "copy_dlc_unlocker"


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
    """Force-stop EA Desktop processes."""
    for name in ("EADesktop", "EABackgroundService", "EALocalHostSvc"):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", f"{name}.exe"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
    log("Client processes stopped.")


# ── Remove Old Unlocker ─────────────────────────────────────────

def _remove_old_unlocker(client_path: Path, log: Callable[[str], None]):
    """Remove old unlocker files (version_o.dll, winhttp.dll, w_*.ini)."""
    for name in ("version_o.dll", "winhttp.dll", "winhttp_o.dll"):
        p = client_path / name
        if p.is_file():
            p.unlink()
            log(f"Removed old file: {name}")

    for f in client_path.iterdir():
        if f.name.endswith(".ini") and f.name.startswith("w_"):
            f.unlink()
            log(f"Removed old config: {f.name}")


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


def install(log: Callable[[str], None]) -> None:
    """Install the DLC Unlocker."""
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

    # Copy entitlements config
    shutil.copy2(src_entitlements, dst_entitlements)
    log("Entitlements config copied.")

    # Copy version.dll to client directory
    shutil.copy2(src_dll, dst_dll)
    log(f"version.dll installed to: {dst_dll}")

    # Staged directory + scheduled task
    if staged_dir.is_dir():
        shutil.copy2(src_dll, dst_dll2)
        log("version.dll copied to staged directory.")

    if _create_task(dst_dll, staged_dir):
        log("Scheduled task created for EA Desktop updates.")
    else:
        log("Warning: Could not create scheduled task. "
            "You may need to reinstall after EA app updates.")

    # Disable background standalone in machine.ini
    machine_ini = (
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "EA Desktop" / "machine.ini"
    )
    try:
        with open(machine_ini, "a", encoding="utf-8") as f:
            f.write("machine.bgsstandaloneenabled=0\n")
        log("Background standalone disabled in machine.ini.")
    except Exception:
        pass

    log("DLC Unlocker installed successfully!")


def uninstall(log: Callable[[str], None]) -> None:
    """Uninstall the DLC Unlocker."""
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

    # Delete version.dll
    if dst_dll.is_file():
        dst_dll.unlink()
        log("version.dll removed from client directory.")

    if dst_dll2.is_file():
        dst_dll2.unlink()
        log("version.dll removed from staged directory.")

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
