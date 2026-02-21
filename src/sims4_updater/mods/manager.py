"""
Mod manager for The Sims 4.

Handles bundled mod ZIPs (shipped with the updater) and installed mods
in the game's Mods folder.  Tracks file ownership so mods can be
cleanly uninstalled.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

from ..config import get_app_dir
from ..constants import get_mods_dir

logger = logging.getLogger(__name__)

# File extensions that the game loads as mods
MOD_EXTENSIONS = {".package", ".ts4script", ".bpi"}
DISABLED_SUFFIX = ".disabled"


@dataclass
class ModInfo:
    """Information about a single mod."""

    name: str
    source: str  # "bundled" or "detected"
    zip_path: str | None = None  # Absolute path to bundled ZIP
    installed_files: list[str] = field(default_factory=list)  # Relative to game Mods dir
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ModInfo:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ModManager:
    """Manages bundled and installed Sims 4 mods."""

    def __init__(self, game_mods_dir: str | Path):
        self._mods_dir = get_mods_dir()  # Bundled ZIPs
        self._game_mods_dir = Path(game_mods_dir)
        self._registry_path = get_app_dir() / "mod_registry.json"
        self._registry: dict[str, ModInfo] = {}
        self.load_registry()

    # ── Registry persistence ───────────────────────────────────

    def load_registry(self):
        try:
            with open(self._registry_path, encoding="utf-8") as f:
                data = json.load(f)
            self._registry = {
                name: ModInfo.from_dict(info) for name, info in data.items()
            }
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            self._registry = {}

    def save_registry(self):
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._registry_path.with_suffix(".json_tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {name: info.to_dict() for name, info in self._registry.items()},
                f,
                indent=2,
            )
        os.replace(tmp, self._registry_path)

    # ── Bundled mods ───────────────────────────────────────────

    def get_bundled_mods(self) -> list[ModInfo]:
        """Scan the bundled mods directory for ZIP files."""
        result = []
        if not self._mods_dir.is_dir():
            return result

        for zp in sorted(self._mods_dir.glob("*.zip")):
            name = _zip_display_name(zp.name)
            # Check registry for installed state
            if name in self._registry:
                info = self._registry[name]
                info.zip_path = str(zp)
                # Verify files still exist
                info.enabled = self._check_enabled(info)
                result.append(info)
            else:
                result.append(ModInfo(
                    name=name,
                    source="bundled",
                    zip_path=str(zp),
                    installed_files=[],
                    enabled=True,
                ))
        return result

    def install_mod(
        self, mod_name: str, log: Callable[[str], None] | None = None,
    ) -> bool:
        """Extract a bundled mod ZIP into the game's Mods folder."""
        if log is None:
            log = lambda msg: None

        info = self._find_mod(mod_name)
        if not info or not info.zip_path:
            log(f"Mod not found: {mod_name}")
            return False

        zp = Path(info.zip_path)
        if not zp.is_file():
            log(f"ZIP not found: {zp}")
            return False

        self._game_mods_dir.mkdir(parents=True, exist_ok=True)

        installed_files: list[str] = []
        try:
            with zipfile.ZipFile(zp, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    # Only extract mod files
                    lower = member.filename.lower()
                    if not any(lower.endswith(ext) for ext in MOD_EXTENSIONS):
                        continue

                    # Preserve internal directory structure
                    dest = self._game_mods_dir / member.filename.replace("/", os.sep)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    installed_files.append(member.filename)
                    log(f"  Extracted: {member.filename}")

        except (zipfile.BadZipFile, OSError) as e:
            log(f"Error extracting {zp.name}: {e}")
            return False

        if not installed_files:
            log(f"No mod files found in {zp.name}")
            return False

        # Update registry
        info.installed_files = installed_files
        info.enabled = True
        info.source = "bundled"
        self._registry[mod_name] = info
        self.save_registry()

        log(f"Installed {len(installed_files)} file(s) for {mod_name}")
        return True

    def uninstall_mod(
        self, mod_name: str, log: Callable[[str], None] | None = None,
    ) -> bool:
        """Remove tracked files for a mod from the game Mods folder."""
        if log is None:
            log = lambda msg: None

        info = self._find_mod(mod_name)
        if not info or not info.installed_files:
            log(f"No installed files tracked for: {mod_name}")
            return False

        removed = 0
        for rel_path in info.installed_files:
            # Check both enabled and disabled variants
            for suffix in ("", DISABLED_SUFFIX):
                fp = self._game_mods_dir / rel_path.replace("/", os.sep)
                if suffix:
                    fp = fp.with_name(fp.name + suffix)
                if fp.is_file():
                    try:
                        fp.unlink()
                        removed += 1
                        log(f"  Removed: {fp.name}")
                    except OSError as e:
                        log(f"  Error removing {fp.name}: {e}")

            # Clean up empty parent directories
            parent = (self._game_mods_dir / rel_path.replace("/", os.sep)).parent
            self._cleanup_empty_dirs(parent)

        info.installed_files = []
        info.enabled = True
        # Keep in registry if bundled (so it shows as "not installed")
        if info.source == "detected":
            self._registry.pop(mod_name, None)
        else:
            self._registry[mod_name] = info
        self.save_registry()

        log(f"Uninstalled {removed} file(s) for {mod_name}")
        return True

    def delete_bundled_mod(
        self, mod_name: str, log: Callable[[str], None] | None = None,
    ) -> bool:
        """Delete the bundled ZIP file for a mod."""
        if log is None:
            log = lambda msg: None

        info = self._find_mod(mod_name)
        if not info or not info.zip_path:
            log(f"No bundled ZIP for: {mod_name}")
            return False

        zp = Path(info.zip_path)
        if zp.is_file():
            try:
                zp.unlink()
                log(f"Deleted: {zp.name}")
            except OSError as e:
                log(f"Error deleting {zp.name}: {e}")
                return False

        # Remove from registry entirely
        self._registry.pop(mod_name, None)
        self.save_registry()
        return True

    # ── Enable / Disable ───────────────────────────────────────

    def enable_mod(
        self, mod_name: str, log: Callable[[str], None] | None = None,
    ) -> bool:
        """Enable a mod by removing .disabled suffix from its files."""
        if log is None:
            log = lambda msg: None

        info = self._find_mod(mod_name)
        if not info or not info.installed_files:
            return False

        count = 0
        for rel_path in info.installed_files:
            fp = self._game_mods_dir / rel_path.replace("/", os.sep)
            disabled_fp = fp.with_name(fp.name + DISABLED_SUFFIX)
            if disabled_fp.is_file():
                try:
                    disabled_fp.rename(fp)
                    count += 1
                except OSError as e:
                    log(f"  Error enabling {fp.name}: {e}")

        info.enabled = True
        self._registry[mod_name] = info
        self.save_registry()
        log(f"Enabled {mod_name} ({count} file(s))")
        return True

    def disable_mod(
        self, mod_name: str, log: Callable[[str], None] | None = None,
    ) -> bool:
        """Disable a mod by adding .disabled suffix to its files."""
        if log is None:
            log = lambda msg: None

        info = self._find_mod(mod_name)
        if not info or not info.installed_files:
            return False

        count = 0
        for rel_path in info.installed_files:
            fp = self._game_mods_dir / rel_path.replace("/", os.sep)
            if fp.is_file():
                disabled_fp = fp.with_name(fp.name + DISABLED_SUFFIX)
                try:
                    fp.rename(disabled_fp)
                    count += 1
                except OSError as e:
                    log(f"  Error disabling {fp.name}: {e}")

        info.enabled = False
        self._registry[mod_name] = info
        self.save_registry()
        log(f"Disabled {mod_name} ({count} file(s))")
        return True

    # ── Detection ──────────────────────────────────────────────

    def scan_installed_mods(self) -> list[ModInfo]:
        """Detect all mod files in the game's Mods folder.

        Groups files by top-level folder (or filename stem for root files).
        Merges with registry data — files already tracked by a bundled mod
        are excluded from the detected list.
        """
        if not self._game_mods_dir.is_dir():
            return []

        # Collect all tracked files so we can exclude them
        tracked: set[str] = set()
        for info in self._registry.values():
            for fp in info.installed_files:
                tracked.add(fp.replace("\\", "/").lower())
                # Also track the disabled variant
                tracked.add(fp.replace("\\", "/").lower() + DISABLED_SUFFIX)

        # Group untracked files by mod name
        groups: dict[str, list[str]] = {}
        for root, _dirs, files in os.walk(self._game_mods_dir):
            for fname in files:
                lower = fname.lower()
                # Check if it's a mod file (enabled or disabled)
                is_mod = any(
                    lower.endswith(ext) or lower.endswith(ext + DISABLED_SUFFIX)
                    for ext in MOD_EXTENSIONS
                )
                if not is_mod:
                    continue

                full = Path(root) / fname
                rel = full.relative_to(self._game_mods_dir).as_posix()

                # Skip files we already track
                if rel.lower() in tracked:
                    continue

                # Group by top-level dir or filename stem
                parts = rel.split("/")
                if len(parts) > 1:
                    group_name = parts[0]
                else:
                    # Strip extensions to get a mod name
                    stem = fname
                    for ext in sorted(MOD_EXTENSIONS, key=len, reverse=True):
                        for suffix in (ext + DISABLED_SUFFIX, ext):
                            if stem.lower().endswith(suffix):
                                stem = stem[: -len(suffix)]
                                break
                    group_name = stem or fname

                groups.setdefault(group_name, []).append(rel)

        result = []
        for name, files in sorted(groups.items()):
            # Check enabled state
            enabled = all(
                not f.lower().endswith(DISABLED_SUFFIX) for f in files
            )
            # Normalize installed_files to not include .disabled suffix
            clean_files = []
            for f in files:
                if f.lower().endswith(DISABLED_SUFFIX):
                    clean_files.append(f[: -len(DISABLED_SUFFIX)])
                else:
                    clean_files.append(f)
            result.append(ModInfo(
                name=name,
                source="detected",
                zip_path=None,
                installed_files=clean_files,
                enabled=enabled,
            ))
        return result

    def get_all_mods(self) -> tuple[list[ModInfo], list[ModInfo]]:
        """Return (bundled_mods, detected_mods)."""
        bundled = self.get_bundled_mods()
        detected = self.scan_installed_mods()
        return bundled, detected

    # ── Internal helpers ───────────────────────────────────────

    def _find_mod(self, mod_name: str) -> ModInfo | None:
        """Find a mod by name in the registry or bundled list."""
        if mod_name in self._registry:
            return self._registry[mod_name]
        # Check bundled
        for info in self.get_bundled_mods():
            if info.name == mod_name:
                return info
        return None

    def _check_enabled(self, info: ModInfo) -> bool:
        """Check if all tracked files are in their enabled state."""
        if not info.installed_files:
            return True
        for rel_path in info.installed_files:
            fp = self._game_mods_dir / rel_path.replace("/", os.sep)
            disabled = fp.with_name(fp.name + DISABLED_SUFFIX)
            if disabled.is_file() and not fp.is_file():
                return False
        return True

    def _cleanup_empty_dirs(self, directory: Path):
        """Remove empty directories up to (but not including) the game Mods dir."""
        try:
            while directory != self._game_mods_dir and directory.is_dir():
                if any(directory.iterdir()):
                    break
                directory.rmdir()
                directory = directory.parent
        except OSError:
            pass

    @property
    def game_mods_dir(self) -> Path:
        return self._game_mods_dir

    def get_mod_size(self, mod: ModInfo) -> int:
        """Get total size in bytes for a mod.

        For bundled mods: uses the ZIP file size.
        For installed mods: sums actual file sizes on disk.
        """
        # Bundled: use ZIP size
        if mod.zip_path:
            zp = Path(mod.zip_path)
            if zp.is_file():
                return zp.stat().st_size

        # Installed: sum file sizes
        total = 0
        for rel_path in mod.installed_files:
            for suffix in ("", DISABLED_SUFFIX):
                fp = self._game_mods_dir / rel_path.replace("/", os.sep)
                if suffix:
                    fp = fp.with_name(fp.name + suffix)
                if fp.is_file():
                    try:
                        total += fp.stat().st_size
                    except OSError:
                        pass
                    break
        return total

    def is_installed(self, mod_name: str) -> bool:
        """Check if a mod has installed files in the game directory."""
        info = self._find_mod(mod_name)
        if not info or not info.installed_files:
            return False
        # Verify at least one file actually exists
        for rel_path in info.installed_files:
            fp = self._game_mods_dir / rel_path.replace("/", os.sep)
            if fp.is_file() or fp.with_name(fp.name + DISABLED_SUFFIX).is_file():
                return True
        return False


def _zip_display_name(filename: str) -> str:
    """Derive a display name from a ZIP filename.

    'UI_Cheats_Extension_v1.52.zip' → 'UI Cheats Extension v1.52'
    'sej_FOMO_AiO_260203_NewEventUpdate.zip' → 'sej FOMO AiO 260203 NewEventUpdate'
    """
    name = filename
    if name.lower().endswith(".zip"):
        name = name[:-4]
    return name.replace("_", " ")
