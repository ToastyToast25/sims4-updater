"""
DLC catalog — maps DLC IDs to names, codes, and pack types.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .. import constants


@dataclass
class DLCInfo:
    id: str           # e.g. "EP01"
    code: str         # e.g. "SIMS4.OFF.SOLP.0x0000000000011AC5"
    code2: str        # alternative code (may be empty)
    pack_type: str    # expansion, game_pack, stuff_pack, free_pack, kit
    names: dict[str, str]  # {locale: display_name}

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


class DLCCatalog:
    """Database of all known Sims 4 DLCs."""

    def __init__(self, catalog_path: str | Path | None = None):
        if catalog_path is None:
            catalog_path = constants.get_data_dir() / "dlc_catalog.json"

        with open(catalog_path, encoding="utf-8") as f:
            data = json.load(f)

        self.dlcs: list[DLCInfo] = []
        for entry in data["dlcs"]:
            self.dlcs.append(DLCInfo(
                id=entry["id"],
                code=entry.get("code", ""),
                code2=entry.get("code2", ""),
                pack_type=entry.get("type", "other"),
                names=entry.get("names", {}),
            ))

        self._by_id = {dlc.id: dlc for dlc in self.dlcs}
        self._by_code = {}
        for dlc in self.dlcs:
            if dlc.code:
                self._by_code[dlc.code] = dlc
            if dlc.code2:
                self._by_code[dlc.code2] = dlc

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
