"""High-level GreenLuma operations combining all backend modules.

Provides a single entry point for the GUI to:
  - Check DLC readiness (AppList + keys + manifests)
  - Apply a LUA manifest file (keys, manifests, AppList in one shot)
  - Verify the full GreenLuma configuration
  - Fix common AppList issues
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import applist, config_vdf, lua_parser, manifest_cache
from .steam import SteamInfo, is_steam_running

log = logging.getLogger(__name__)


@dataclass
class DLCReadiness:
    """Readiness state for a single DLC."""

    dlc_id: str
    name: str
    steam_app_id: int
    in_applist: bool = False
    has_key: bool = False
    has_manifest: bool = False

    @property
    def ready(self) -> bool:
        return self.in_applist and self.has_key and self.has_manifest


@dataclass
class ApplyResult:
    """Summary of a LUA apply operation."""

    keys_added: int = 0
    keys_updated: int = 0
    manifests_copied: int = 0
    manifests_skipped: int = 0
    applist_entries_added: int = 0
    lua_total_keys: int = 0
    lua_total_manifests: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


@dataclass
class VerifyResult:
    """Full verification report."""

    keys_in_vdf: int = 0
    keys_expected: int = 0
    keys_matching: int = 0
    keys_mismatched: list[str] = field(default_factory=list)
    keys_missing: list[str] = field(default_factory=list)
    manifests_in_cache: int = 0
    manifests_expected: int = 0
    manifests_missing: list[str] = field(default_factory=list)
    applist_count: int = 0
    applist_duplicates: int = 0
    errors: list[str] = field(default_factory=list)


class GreenLumaOrchestrator:
    """High-level GreenLuma operations for the Sims 4 Updater."""

    def __init__(self, steam_info: SteamInfo):
        self.steam = steam_info

    # ── DLC Readiness ────────────────────────────────────────────

    def check_readiness(self, catalog) -> list[DLCReadiness]:
        """Check DLC readiness against AppList, config.vdf keys, and manifests.

        Args:
            catalog: DLCCatalog instance with all known DLCs.

        Returns:
            List of DLCReadiness, one per DLC that has a steam_app_id.
        """
        # Read current state
        al_state = applist.read_applist(self.steam.applist_dir)
        vdf_state = config_vdf.read_depot_keys(self.steam.config_vdf_path)
        mc_state = manifest_cache.read_depotcache(self.steam.depotcache_dir)

        results = []
        for dlc in catalog.all_dlcs():
            if not dlc.steam_app_id:
                continue

            app_id_str = str(dlc.steam_app_id)
            results.append(DLCReadiness(
                dlc_id=dlc.id,
                name=dlc.name_en,
                steam_app_id=dlc.steam_app_id,
                in_applist=app_id_str in al_state.unique_ids,
                has_key=app_id_str in vdf_state.keys,
                has_manifest=app_id_str in mc_state.depot_ids,
            ))

        return results

    # ── Apply LUA ────────────────────────────────────────────────

    def apply_lua(
        self,
        lua_path: Path,
        manifest_source_dir: Path | None = None,
        auto_backup: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> ApplyResult:
        """Apply a LUA manifest file: add keys, copy manifests, update AppList.

        Args:
            lua_path: Path to the .lua file.
            manifest_source_dir: Directory containing .manifest files to copy.
                If None, manifest copying is skipped.
            auto_backup: Whether to backup config.vdf and AppList before changes.
            progress: Optional callback for progress messages.

        Returns:
            ApplyResult with counts and any errors.
        """
        result = ApplyResult()

        def _log(msg: str):
            log.info(msg)
            if progress:
                progress(msg)

        # Step 0: Check Steam is not running
        if is_steam_running():
            result.errors.append(
                "Steam is running. Close Steam before applying LUA changes."
            )
            return result

        # Step 1: Parse LUA
        _log("Parsing LUA file...")
        try:
            lua = lua_parser.parse_lua_file(lua_path)
        except (ValueError, FileNotFoundError) as e:
            result.errors.append(f"Failed to parse LUA: {e}")
            return result

        result.lua_total_keys = lua.keys_count
        result.lua_total_manifests = lua.manifests_count
        _log(f"LUA parsed: {lua.keys_count} keys, {lua.manifests_count} manifests")

        # Step 2: Backup
        if auto_backup:
            _log("Creating backups...")
            try:
                if self.steam.config_vdf_path.is_file():
                    bk = config_vdf.backup_config_vdf(self.steam.config_vdf_path)
                    _log(f"Backed up config.vdf to {bk.name}")
            except OSError as e:
                _log(f"Warning: config.vdf backup failed: {e}")

            try:
                if self.steam.applist_dir.is_dir():
                    bk = applist.backup_applist(self.steam.applist_dir)
                    _log(f"Backed up AppList to {bk.name}")
            except OSError as e:
                _log(f"Warning: AppList backup failed: {e}")

        # Step 3: Add keys to config.vdf
        keys_to_add = {
            depot_id: entry.decryption_key
            for depot_id, entry in lua.entries.items()
            if entry.decryption_key
        }

        if keys_to_add:
            _log(f"Adding {len(keys_to_add)} decryption keys to config.vdf...")
            try:
                added, updated = config_vdf.add_depot_keys(
                    self.steam.config_vdf_path,
                    keys_to_add,
                    auto_backup=False,  # orchestrator handles backup
                )
                result.keys_added = added
                result.keys_updated = updated
                _log(f"Keys: {added} added, {updated} updated")
            except (RuntimeError, ValueError, OSError) as e:
                result.errors.append(f"Failed to add keys: {e}")
                _log(f"ERROR adding keys: {e}")
        else:
            _log("No decryption keys to add")

        # Step 4: Copy manifests
        if manifest_source_dir and manifest_source_dir.is_dir():
            _log("Copying manifest files to depotcache...")
            try:
                copied, skipped = manifest_cache.copy_manifests(
                    manifest_source_dir, self.steam.depotcache_dir
                )
                result.manifests_copied = copied
                result.manifests_skipped = skipped
                _log(f"Manifests: {copied} copied, {skipped} skipped")
            except OSError as e:
                result.errors.append(f"Failed to copy manifests: {e}")
                _log(f"ERROR copying manifests: {e}")
        elif manifest_source_dir:
            _log(f"Manifest source directory not found: {manifest_source_dir}")

        # Step 5: Update AppList
        # Add all app IDs from the LUA (both keyed and non-keyed)
        new_app_ids = lua.all_app_ids
        if new_app_ids:
            _log(f"Updating AppList with {len(new_app_ids)} IDs...")
            try:
                added = applist.add_ids(self.steam.applist_dir, new_app_ids)
                result.applist_entries_added = added
                _log(f"AppList: {added} new entries added")
            except ValueError as e:
                result.errors.append(f"AppList update failed: {e}")
                _log(f"ERROR updating AppList: {e}")

        if result.success:
            _log("LUA applied successfully!")
        else:
            _log(f"LUA applied with {len(result.errors)} error(s)")

        return result

    # ── Verify ───────────────────────────────────────────────────

    def verify(self, lua_path: Path | None = None) -> VerifyResult:
        """Verify the full GreenLuma configuration.

        Args:
            lua_path: Optional LUA file to verify against. If None, only
                checks structural integrity (AppList, key count, manifest count).

        Returns:
            VerifyResult with detailed status.
        """
        result = VerifyResult()

        # AppList
        try:
            al = applist.read_applist(self.steam.applist_dir)
            result.applist_count = al.count
            result.applist_duplicates = len(al.duplicates)
        except OSError as e:
            result.errors.append(f"Cannot read AppList: {e}")

        # Config VDF keys
        try:
            vdf = config_vdf.read_depot_keys(self.steam.config_vdf_path)
            result.keys_in_vdf = vdf.total_keys
        except (OSError, ValueError) as e:
            result.errors.append(f"Cannot read config.vdf: {e}")

        # Manifests
        try:
            mc = manifest_cache.read_depotcache(self.steam.depotcache_dir)
            result.manifests_in_cache = mc.total_count
        except OSError as e:
            result.errors.append(f"Cannot read depotcache: {e}")

        # If LUA provided, do detailed cross-reference
        if lua_path:
            try:
                lua = lua_parser.parse_lua_file(lua_path)
            except (ValueError, FileNotFoundError) as e:
                result.errors.append(f"Cannot parse LUA for verification: {e}")
                return result

            # Key verification
            expected_keys = {
                depot_id: entry.decryption_key
                for depot_id, entry in lua.entries.items()
                if entry.decryption_key
            }
            result.keys_expected = len(expected_keys)

            if expected_keys and self.steam.config_vdf_path.is_file():
                kv = config_vdf.verify_keys(
                    self.steam.config_vdf_path, expected_keys
                )
                result.keys_matching = kv["matching"]
                result.keys_mismatched = kv["mismatched"]
                result.keys_missing = kv["missing"]

            # Manifest verification
            expected_manifests = {
                depot_id: entry.manifest_id
                for depot_id, entry in lua.entries.items()
                if entry.manifest_id
            }
            result.manifests_expected = len(expected_manifests)

            if expected_manifests and self.steam.depotcache_dir.is_dir():
                result.manifests_missing = manifest_cache.find_missing_manifests(
                    self.steam.depotcache_dir, expected_manifests
                )

        return result

    # ── Fix AppList ──────────────────────────────────────────────

    def fix_applist(self, catalog) -> tuple[int, int]:
        """Fix AppList: remove duplicates, add missing DLC app IDs.

        Args:
            catalog: DLCCatalog instance.

        Returns:
            Tuple of (duplicates_removed, missing_added).
        """
        state = applist.read_applist(self.steam.applist_dir)

        # Collect DLC app IDs that should be in AppList
        expected_ids = set()
        for dlc in catalog.all_dlcs():
            if dlc.steam_app_id:
                expected_ids.add(str(dlc.steam_app_id))

        # Calculate what's missing
        missing = expected_ids - state.unique_ids

        # Remove duplicates by rewriting clean list
        dupes_removed = len(state.duplicates)
        if dupes_removed > 0 or missing:
            ordered = applist.ordered_ids_from_state(state)
            # Add missing IDs
            for mid in sorted(missing):
                if mid not in state.unique_ids:
                    ordered.append(mid)
            applist.write_applist(self.steam.applist_dir, ordered)

        return dupes_removed, len(missing)
