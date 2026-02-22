"""
DLC catalog — maps DLC IDs to names, codes, and pack types.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .. import constants


@dataclass
class DLCStatus:
    """Rich status info for a single DLC."""

    dlc: "DLCInfo"
    installed: bool = False       # folder exists on disk
    complete: bool = False        # SimulationFullBuild0.package present
    registered: bool = False      # has entry in crack config
    enabled: bool | None = None   # enabled in crack config (None if not registered)
    owned: bool = False           # installed AND not in crack config = legit EA copy
    file_count: int = 0           # number of files in DLC folder

    @property
    def status_label(self) -> str:
        if self.owned and self.complete:
            return "Owned"
        if self.installed and not self.complete:
            return "Incomplete"
        if self.installed and self.registered and self.enabled:
            return "Patched"
        if self.installed and self.registered and not self.enabled:
            return "Patched (disabled)"
        if not self.installed and self.registered:
            return "Missing files"
        return "Not installed"


@dataclass
class DLCInfo:
    id: str           # e.g. "EP01"
    code: str         # e.g. "SIMS4.OFF.SOLP.0x0000000000011AC5"
    code2: str        # alternative code (may be empty)
    pack_type: str    # expansion, game_pack, stuff_pack, free_pack, kit
    names: dict[str, str]  # {locale: display_name}
    description: str = ""  # short English description of the pack
    steam_app_id: int | None = None  # Steam store app ID

    @property
    def name_en(self) -> str:
        return self.names.get("en_us", self.names.get("en_US", self.id))

    def get_name(self, locale: str = "en_US") -> str:
        key = locale.lower()
        return self.names.get(key, self.names.get("en_us", self.id))

    @property
    def all_codes(self) -> list[str]:
        codes = [self.code] if self.code else []
        if self.code2:
            codes.append(self.code2)
        return codes


def _parse_dlc_entry(entry: dict) -> DLCInfo:
    """Parse a single DLC entry from JSON."""
    return DLCInfo(
        id=entry["id"],
        code=entry.get("code", ""),
        code2=entry.get("code2", ""),
        pack_type=entry.get("type", "other"),
        names=entry.get("names", {}),
        description=entry.get("description", ""),
        steam_app_id=entry.get("steam_app_id"),
    )


class DLCCatalog:
    """Database of all known Sims 4 DLCs.

    Loads the bundled catalog, then merges any custom DLCs saved
    from remote manifest updates.
    """

    def __init__(self, catalog_path: str | Path | None = None):
        if catalog_path is None:
            catalog_path = constants.get_data_dir() / "dlc_catalog.json"

        with open(catalog_path, encoding="utf-8") as f:
            data = json.load(f)

        self.dlcs: list[DLCInfo] = []
        for entry in data["dlcs"]:
            self.dlcs.append(_parse_dlc_entry(entry))

        # Merge custom DLCs from app data dir (added via manifest)
        self._custom_path = self._get_custom_path()
        if self._custom_path and self._custom_path.is_file():
            try:
                with open(self._custom_path, encoding="utf-8") as f:
                    custom = json.load(f)
                existing_ids = {d.id for d in self.dlcs}
                for entry in custom.get("dlcs", []):
                    if entry.get("id") and entry["id"] not in existing_ids:
                        self.dlcs.append(_parse_dlc_entry(entry))
                        existing_ids.add(entry["id"])
            except (OSError, json.JSONDecodeError):
                pass

        self._by_id = {dlc.id: dlc for dlc in self.dlcs}
        self._by_code = {}
        for dlc in self.dlcs:
            if dlc.code:
                self._by_code[dlc.code] = dlc
            if dlc.code2:
                self._by_code[dlc.code2] = dlc

    @staticmethod
    def _get_custom_path() -> Path | None:
        """Path to the custom DLCs file in app data."""
        try:
            from ..config import get_app_dir
            return get_app_dir() / "custom_dlcs.json"
        except Exception:
            return None

    def merge_remote(self, remote_dlcs) -> int:
        """Merge DLC entries from a remote manifest into the catalog.

        Args:
            remote_dlcs: List of ManifestDLC objects from the manifest.

        Returns:
            Number of new DLCs added.
        """
        added = 0
        for rdlc in remote_dlcs:
            if rdlc.id in self._by_id:
                # Update fields on existing entry if remote has them and local is empty
                existing = self._by_id[rdlc.id]
                if rdlc.code and not existing.code:
                    existing.code = rdlc.code
                    self._by_code[rdlc.code] = existing
                if rdlc.code2 and not existing.code2:
                    existing.code2 = rdlc.code2
                    self._by_code[rdlc.code2] = existing
                if getattr(rdlc, "steam_app_id", None) and not existing.steam_app_id:
                    existing.steam_app_id = rdlc.steam_app_id
                if rdlc.description and not existing.description:
                    existing.description = rdlc.description
                if rdlc.names:
                    for k, v in rdlc.names.items():
                        if k not in existing.names:
                            existing.names[k] = v
                continue

            dlc = DLCInfo(
                id=rdlc.id,
                code=rdlc.code,
                code2=rdlc.code2,
                pack_type=rdlc.pack_type,
                names=dict(rdlc.names),
                description=rdlc.description,
                steam_app_id=getattr(rdlc, "steam_app_id", None),
            )
            self.dlcs.append(dlc)
            self._by_id[dlc.id] = dlc
            if dlc.code:
                self._by_code[dlc.code] = dlc
            if dlc.code2:
                self._by_code[dlc.code2] = dlc
            added += 1

        if added:
            self._save_custom()

        return added

    def _save_custom(self):
        """Save non-bundled DLCs to app data for persistence across restarts."""
        if not self._custom_path:
            return

        # Load bundled IDs to know which are custom
        try:
            bundled_path = constants.get_data_dir() / "dlc_catalog.json"
            with open(bundled_path, encoding="utf-8") as f:
                bundled_ids = {e["id"] for e in json.load(f).get("dlcs", [])}
        except (OSError, json.JSONDecodeError):
            bundled_ids = set()

        custom_entries = []
        for dlc in self.dlcs:
            if dlc.id not in bundled_ids:
                entry = {
                    "id": dlc.id,
                    "code": dlc.code,
                    "code2": dlc.code2,
                    "type": dlc.pack_type,
                    "names": dlc.names,
                    "description": dlc.description,
                }
                if dlc.steam_app_id is not None:
                    entry["steam_app_id"] = dlc.steam_app_id
                custom_entries.append(entry)

        if not custom_entries:
            return

        try:
            self._custom_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._custom_path, "w", encoding="utf-8") as f:
                json.dump({"dlcs": custom_entries}, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get_by_id(self, dlc_id: str) -> DLCInfo | None:
        return self._by_id.get(dlc_id)

    def get_by_code(self, code: str) -> DLCInfo | None:
        return self._by_code.get(code)

    def all_dlcs(self) -> list[DLCInfo]:
        return self.dlcs

    def by_type(self, pack_type: str) -> list[DLCInfo]:
        return [d for d in self.dlcs if d.pack_type == pack_type]

    def get_installed(self, game_dir: str | Path) -> list[DLCInfo]:
        """Return DLCs that have folders present in the game directory."""
        game_dir = Path(game_dir)
        installed = []
        for dlc in self.dlcs:
            dlc_dir = game_dir / dlc.id
            if dlc_dir.is_dir():
                installed.append(dlc)
        return installed

    def get_missing(self, game_dir: str | Path) -> list[DLCInfo]:
        """Return DLCs whose SimulationFullBuild0.package is not found."""
        game_dir = Path(game_dir)
        missing = []
        for dlc in self.dlcs:
            pkg = game_dir / dlc.id / "SimulationFullBuild0.package"
            if not pkg.is_file():
                missing.append(dlc)
        return missing
