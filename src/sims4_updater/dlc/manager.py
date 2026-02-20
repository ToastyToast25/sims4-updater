"""
DLC Manager — unified interface for toggling DLCs across all crack config formats.
"""

import os
import shutil
from pathlib import Path

from .catalog import DLCCatalog, DLCInfo, DLCStatus
from .formats import DLCConfigAdapter, detect_format
from ..core.exceptions import NoCrackConfigError


class DLCManager:
    """Orchestrates DLC management across all config formats."""

    def __init__(self, catalog: DLCCatalog | None = None):
        self.catalog = catalog or DLCCatalog()

    def detect_format(self, game_dir: str | Path) -> DLCConfigAdapter | None:
        return detect_format(Path(game_dir))

    def get_dlc_states(
        self, game_dir: str | Path, locale: str = "en_US"
    ) -> list[DLCStatus]:
        """
        Get full DLC state info for display.

        Returns list of DLCStatus with installed, complete, registered,
        enabled, owned, and file_count fields.
        """
        game_dir = Path(game_dir)
        adapter = detect_format(game_dir)

        # Read config content if adapter found
        config_content = ""
        if adapter:
            config_path = adapter.get_config_path(game_dir)
            if config_path:
                config_content = config_path.read_text(
                    encoding=adapter.get_encoding(), errors="replace"
                )

        results = []
        for dlc in self.catalog.all_dlcs():
            dlc_dir = game_dir / dlc.id
            installed = dlc_dir.is_dir()
            complete = (dlc_dir / "SimulationFullBuild0.package").is_file()

            # Count files in DLC folder
            file_count = 0
            if installed:
                try:
                    file_count = sum(1 for _ in dlc_dir.iterdir() if _.is_file())
                except OSError:
                    pass

            # Check crack config
            registered = False
            enabled = None
            if adapter and config_content:
                states = adapter.read_enabled_dlcs(config_content, dlc.all_codes)
                for code in dlc.all_codes:
                    if code in states:
                        registered = True
                        enabled = states[code]
                        break

            # Owned = installed on disk but NOT in crack config (EA handles it)
            owned = installed and not registered

            results.append(DLCStatus(
                dlc=dlc,
                installed=installed,
                complete=complete,
                registered=registered,
                enabled=enabled,
                owned=owned,
                file_count=file_count,
            ))

        return results

    def apply_changes(
        self,
        game_dir: str | Path,
        enabled_dlcs: set[str],
    ) -> None:
        """
        Write DLC enabled/disabled states to the crack config.

        Args:
            game_dir: Path to game installation.
            enabled_dlcs: Set of DLC IDs (e.g. {"EP01", "GP02"}) to enable.
                          All others will be disabled.
        """
        game_dir = Path(game_dir)
        adapter = detect_format(game_dir)
        if adapter is None:
            raise NoCrackConfigError("No crack config found in game directory.")

        config_path = adapter.get_config_path(game_dir)
        if config_path is None:
            raise NoCrackConfigError("Crack config file not found.")

        content = config_path.read_text(
            encoding=adapter.get_encoding(), errors="replace"
        )

        for dlc in self.catalog.all_dlcs():
            should_enable = dlc.id in enabled_dlcs
            for code in dlc.all_codes:
                content = adapter.set_dlc_state(content, code, should_enable)

        # Write back
        config_path.write_text(content, encoding=adapter.get_encoding())

        # Copy to Bin_LE variant if it exists (matches AutoIt behavior)
        bin_le_path = Path(str(config_path).replace("Bin", "Bin_LE"))
        if bin_le_path.parent.is_dir() and bin_le_path != config_path:
            shutil.copy2(config_path, bin_le_path)

    def auto_toggle(self, game_dir: str | Path) -> dict[str, bool]:
        """
        Auto-enable installed DLCs, disable missing ones.

        Returns dict of {dlc_id: new_enabled_state}.
        """
        game_dir = Path(game_dir)
        states = self.get_dlc_states(game_dir)

        enabled_set = set()
        changes = {}

        for state in states:
            dlc = state.dlc
            if state.installed:
                enabled_set.add(dlc.id)
                if state.enabled is False:
                    changes[dlc.id] = True
            else:
                if state.enabled is True:
                    changes[dlc.id] = False

        if changes:
            self.apply_changes(game_dir, enabled_set)

        return changes

    def export_states(self, game_dir: str | Path) -> dict[str, bool]:
        """Export current DLC states for backup before patching."""
        states = self.get_dlc_states(game_dir)
        return {
            s.dlc.id: s.enabled
            for s in states
            if s.enabled is not None
        }

    def import_states(self, game_dir: str | Path, saved_states: dict[str, bool]) -> None:
        """Restore DLC states from a previous export."""
        enabled_set = {dlc_id for dlc_id, enabled in saved_states.items() if enabled}
        self.apply_changes(game_dir, enabled_set)
