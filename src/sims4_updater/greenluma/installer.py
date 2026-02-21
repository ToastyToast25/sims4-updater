"""GreenLuma installation and launch management."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Known GreenLuma file markers
_GL_DLLS = ["GreenLuma_2025_x64.dll", "GreenLuma_2025_x86.dll"]
_GL_INJECTOR = "DLLInjector.exe"
_GL_SETTINGS = "GreenLumaSettings_2025.exe"
_GL_INI = "DLLInjector.ini"

# Files/dirs that belong to GreenLuma (safe to overwrite during install)
_GL_KNOWN_FILES = {
    "GreenLuma_2025_x64.dll",
    "GreenLuma_2025_x86.dll",
    "DLLInjector.exe",
    "DLLInjector.ini",
    "GreenLumaSettings_2025.exe",
    "AchievementUnlocker_2025.exe",
    "User32.dll",
}
_GL_KNOWN_DIRS = {"AppList"}

_INSTALL_MANIFEST_NAME = "greenluma_install.json"


def _get_manifest_path() -> Path:
    from ..config import get_app_dir
    return get_app_dir() / _INSTALL_MANIFEST_NAME


def _save_install_manifest(target_dir: Path, files: list[str]) -> None:
    """Save list of installed file paths relative to target_dir."""
    path = _get_manifest_path()
    data = {
        "install_dir": str(target_dir),
        "files": files,
        "installed_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("Saved install manifest: %d files to %s", len(files), path)


def _load_install_manifest() -> dict | None:
    """Load previously saved install manifest, or None if not found."""
    path = _get_manifest_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("Failed to read install manifest: %s", path)
        return None


def _collect_gl_files(target_dir: Path) -> list[str]:
    """Collect relative paths of GreenLuma files in target_dir."""
    files = []
    for item in target_dir.iterdir():
        if item.is_file() and item.name in _GL_KNOWN_FILES:
            files.append(item.name)
        elif item.is_dir() and item.name in _GL_KNOWN_DIRS:
            for sub in item.rglob("*"):
                if sub.is_file():
                    files.append(str(sub.relative_to(target_dir)))
    return files


@dataclass
class GreenLumaStatus:
    """Detected GreenLuma installation state."""

    installed: bool
    version: str  # "1.7.0" or "unknown"
    mode: str  # "normal" | "stealth" | "not_installed"
    dll_injector_path: Path | None
    steam_path: Path | None


def detect_greenluma(steam_path: Path) -> GreenLumaStatus:
    """Detect GreenLuma installation at the given Steam path."""
    if not steam_path.is_dir():
        return GreenLumaStatus(
            installed=False,
            version="unknown",
            mode="not_installed",
            dll_injector_path=None,
            steam_path=steam_path,
        )

    # Normal mode: DLLs in Steam directory
    dlls_present = all((steam_path / dll).is_file() for dll in _GL_DLLS)
    injector_in_steam = (steam_path / _GL_INJECTOR).is_file()

    if dlls_present and injector_in_steam:
        version = _detect_version(steam_path)
        return GreenLumaStatus(
            installed=True,
            version=version,
            mode="normal",
            dll_injector_path=steam_path / _GL_INJECTOR,
            steam_path=steam_path,
        )

    # Stealth mode: check common stealth locations (sibling dirs named "greenluma")
    for candidate in _stealth_candidates(steam_path):
        ini_path = candidate / _GL_INI
        injector_path = candidate / _GL_INJECTOR
        if ini_path.is_file() and injector_path.is_file():
            version = _detect_version(candidate)
            return GreenLumaStatus(
                installed=True,
                version=version,
                mode="stealth",
                dll_injector_path=injector_path,
                steam_path=steam_path,
            )

    # Check if DLLs present but no injector (partial install)
    if dlls_present:
        return GreenLumaStatus(
            installed=True,
            version=_detect_version(steam_path),
            mode="normal",
            dll_injector_path=None,
            steam_path=steam_path,
        )

    return GreenLumaStatus(
        installed=False,
        version="unknown",
        mode="not_installed",
        dll_injector_path=None,
        steam_path=steam_path,
    )


def _validate_archive_paths(names: list[str], target_dir: Path) -> None:
    """Validate that no archive entry escapes *target_dir* via path traversal.

    Raises:
        ValueError: If any archive entry resolves outside the target directory.
    """
    resolved_target = target_dir.resolve()
    for name in names:
        entry_path = (target_dir / name).resolve()
        if not str(entry_path).startswith(str(resolved_target)):
            raise ValueError(
                f"Archive contains path traversal entry: {name!r}"
            )


def _move_gl_files_up(subdir: Path, target_dir: Path) -> None:
    """Move only GreenLuma-specific files from *subdir* up to *target_dir*.

    Skips any file/directory that isn't in the known GL set to avoid
    destroying existing Steam directories (e.g. config/, steamapps/).
    """
    for item in list(subdir.iterdir()):
        dest = target_dir / item.name

        if item.is_dir():
            if item.name in _GL_KNOWN_DIRS:
                if dest.is_dir():
                    shutil.rmtree(dest)
                shutil.move(str(item), str(dest))
            else:
                log.debug("Skipping non-GL directory: %s", item.name)
        else:
            if item.name in _GL_KNOWN_FILES or not dest.exists():
                if dest.exists():
                    dest.unlink()
                shutil.move(str(item), str(dest))
            else:
                log.debug("Skipping non-GL file: %s", item.name)

    # Clean up subdir if empty
    try:
        subdir.rmdir()
    except OSError:
        log.debug("Subdir not empty after GL file move: %s", subdir)


def install_greenluma(
    archive_path: Path,
    steam_path: Path,
    stealth: bool = False,
) -> GreenLumaStatus:
    """Extract GreenLuma from a 7z archive.

    Args:
        archive_path: Path to the GreenLuma .7z archive.
        steam_path: Steam installation directory.
        stealth: If True, install into a sibling ``GreenLuma/`` directory
            instead of directly into Steam.

    Requires py7zr to be installed.
    """
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    if not steam_path.is_dir():
        raise FileNotFoundError(f"Steam directory not found: {steam_path}")

    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError(
            "py7zr is required for 7z extraction. Install with: pip install py7zr"
        ) from exc

    if stealth:
        target_dir = steam_path.parent / "GreenLuma"
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = steam_path

    log.info(
        "Extracting GreenLuma (%s) from %s to %s",
        "stealth" if stealth else "normal",
        archive_path,
        target_dir,
    )

    with py7zr.SevenZipFile(archive_path, mode="r") as z:
        names = z.getnames()
        log.info("Archive contains %d files", len(names))

        # Validate for path traversal before extracting
        _validate_archive_paths(names, target_dir)

        # Detect single root subdirectory (e.g. "GreenLuma_2025_1.7.0/...")
        prefix = ""
        if names and "/" in names[0]:
            first_dir = names[0].split("/")[0]
            if all(
                n.startswith(first_dir + "/") or n == first_dir
                for n in names
            ):
                prefix = first_dir + "/"

        z.extractall(path=target_dir)

    # If extracted into a subdirectory, move GL files up safely
    if prefix:
        subdir = target_dir / prefix.rstrip("/")
        if subdir.is_dir():
            _move_gl_files_up(subdir, target_dir)

    # Ensure AppList directory exists (always in Steam dir)
    applist_dir = steam_path / "AppList"
    applist_dir.mkdir(exist_ok=True)

    # Save install manifest for clean uninstall later
    try:
        installed_files = _collect_gl_files(target_dir)
        _save_install_manifest(target_dir, installed_files)
    except OSError as e:
        log.warning("Failed to save install manifest: %s", e)

    status = detect_greenluma(steam_path)
    log.info(
        "GreenLuma install result: installed=%s, mode=%s, version=%s",
        status.installed,
        status.mode,
        status.version,
    )
    return status


def uninstall_greenluma(steam_path: Path) -> tuple[int, int]:
    """Remove GreenLuma files from Steam directory.

    Uses the saved install manifest for precise file removal. Falls back to
    scanning for known GL files if no manifest exists.

    Args:
        steam_path: Steam installation directory.

    Returns:
        Tuple of (files_removed, files_failed).
    """
    removed = 0
    failed = 0

    manifest = _load_install_manifest()

    if manifest:
        install_dir = Path(manifest["install_dir"])
        for rel_path in manifest.get("files", []):
            fp = install_dir / rel_path
            if fp.is_file():
                try:
                    fp.unlink()
                    removed += 1
                except OSError as e:
                    log.warning("Failed to remove %s: %s", fp, e)
                    failed += 1
    else:
        # Fallback: scan known GL files in steam_path and stealth dirs
        search_dirs = [steam_path]
        for candidate in _stealth_candidates(steam_path):
            if candidate not in search_dirs:
                search_dirs.append(candidate)

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for fname in _GL_KNOWN_FILES:
                fp = search_dir / fname
                if fp.is_file():
                    try:
                        fp.unlink()
                        removed += 1
                    except OSError as e:
                        log.warning("Failed to remove %s: %s", fp, e)
                        failed += 1

    # Clean AppList contents (keep the directory)
    applist_dir = steam_path / "AppList"
    if applist_dir.is_dir():
        for fp in applist_dir.iterdir():
            if fp.is_file() and fp.suffix.lower() == ".txt":
                try:
                    fp.unlink()
                    removed += 1
                except OSError:
                    failed += 1

    # Remove install manifest
    manifest_path = _get_manifest_path()
    if manifest_path.is_file():
        try:
            manifest_path.unlink()
        except OSError:
            pass

    log.info("Uninstall complete: %d removed, %d failed", removed, failed)
    return removed, failed


def kill_steam() -> bool:
    """Terminate Steam process.

    Returns True if Steam was killed or wasn't running.
    """
    from .steam import is_steam_running

    if not is_steam_running():
        return True

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "steam.exe"],
            capture_output=True,
            timeout=10,
        )
        time.sleep(2)
        return not is_steam_running()
    except Exception as e:
        log.error("Failed to kill Steam: %s", e)
        return False


def launch_steam_via_greenluma(
    dll_injector_path: Path,
    force: bool = False,
) -> bool:
    """Launch Steam via GreenLuma's DLLInjector.

    Args:
        dll_injector_path: Path to DLLInjector.exe.
        force: If True, skip the is_steam_running check (caller already
            handled it, e.g. via kill_steam).

    Returns True if the process was started successfully.
    """
    if not dll_injector_path.is_file():
        log.error("DLLInjector not found: %s", dll_injector_path)
        return False

    if not force:
        from .steam import is_steam_running
        if is_steam_running():
            log.warning("Steam is already running — close it before launching via GreenLuma")
            return False

    try:
        log.info("Launching DLLInjector: %s", dll_injector_path)
        subprocess.Popen(
            [str(dll_injector_path)],
            cwd=str(dll_injector_path.parent),
            creationflags=subprocess.DETACHED_PROCESS,
        )
        return True
    except OSError as e:
        log.error("Failed to launch DLLInjector: %s", e)
        return False


def _detect_version(search_dir: Path) -> str:
    """Try to determine GreenLuma version from file metadata or filenames."""
    # Try reading ProductVersion from the x64 DLL (most reliable)
    dll_path = search_dir / "GreenLuma_2025_x64.dll"
    if dll_path.is_file():
        ver = _get_file_version(dll_path)
        if ver:
            return ver

    # Fallback: scan filenames for version hints
    try:
        for item in search_dir.iterdir():
            name = item.name.lower()
            if "greenluma" in name and "1.7" in name:
                return "1.7.0"
            if "greenluma" in name and "1.6" in name:
                return "1.6.x"
    except OSError:
        log.debug("Cannot read directory for version detection: %s", search_dir)
        return "unknown"

    if dll_path.is_file():
        return "2025"
    return "unknown"


def _get_file_version(file_path: Path) -> str | None:
    """Read the ProductVersion from a Windows PE file's version resource."""
    try:
        import ctypes
        from ctypes import wintypes

        version_dll = ctypes.windll.version
        path_str = str(file_path)

        size = version_dll.GetFileVersionInfoSizeW(path_str, None)
        if not size:
            return None

        data = ctypes.create_string_buffer(size)
        if not version_dll.GetFileVersionInfoW(path_str, 0, size, data):
            return None

        # Query the root block for VS_FIXEDFILEINFO
        p_fixed = ctypes.c_void_p()
        buf_len = wintypes.UINT()
        if not version_dll.VerQueryValueW(
            data, "\\", ctypes.byref(p_fixed), ctypes.byref(buf_len)
        ):
            return None

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD),
                ("dwProductVersionLS", wintypes.DWORD),
            ]

        info = ctypes.cast(
            p_fixed, ctypes.POINTER(VS_FIXEDFILEINFO)
        ).contents
        major = (info.dwProductVersionMS >> 16) & 0xFFFF
        minor = info.dwProductVersionMS & 0xFFFF
        patch = (info.dwProductVersionLS >> 16) & 0xFFFF
        return f"{major}.{minor}.{patch}"
    except Exception:
        return None


def _stealth_candidates(steam_path: Path) -> list[Path]:
    """Return candidate directories for stealth-mode GreenLuma installations."""
    candidates = []
    parent = steam_path.parent
    if parent.is_dir():
        try:
            for item in parent.iterdir():
                if item.is_dir() and item != steam_path:
                    name = item.name.lower()
                    # Only match "greenluma" — not "gl" (too broad: matches opengl etc.)
                    if "greenluma" in name:
                        candidates.append(item)
        except OSError:
            pass
        candidates.append(parent)
    return candidates
