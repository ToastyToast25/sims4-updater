"""Backup and restore system for game files before patching."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "sims4_updater_backups"


@dataclass
class BackupInfo:
    """Metadata for a single backup."""

    path: Path
    timestamp: datetime
    version: str
    size: int  # total size in bytes

    @property
    def display_name(self) -> str:
        return f"{self.version} — {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class BackupManager:
    """Manages game file backups before patching."""

    def __init__(self, app_dir: Path, max_count: int = 3):
        self.backup_dir = app_dir / BACKUP_DIR_NAME
        self.max_count = max(0, max_count)

    def estimate_backup_size(
        self,
        game_dir: Path,
        files_to_patch: list[str],
    ) -> int:
        """Sum file sizes of all files that will be modified by the patch.

        Returns size in bytes.
        """
        total = 0
        for rel_path in files_to_patch:
            full = game_dir / rel_path
            if full.is_file():
                with contextlib.suppress(OSError):
                    total += full.stat().st_size
        return total

    def create_backup(
        self,
        game_dir: Path,
        files_to_patch: list[str],
        version_label: str,
    ) -> Path | None:
        """Copy affected files into a timestamped backup folder.

        Structure: backups/<timestamp>_<version>/<relative_path>
        Returns backup folder path, or None if max_count is 0 (backups disabled).
        """
        if self.max_count == 0:
            logger.info("Backups disabled (max_count=0), skipping")
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_version = version_label.replace(" ", "_").replace("/", "-")
        folder_name = f"{ts}_{safe_version}"
        backup_path = self.backup_dir / folder_name
        backup_path.mkdir(parents=True, exist_ok=True)

        game_resolved = game_dir.resolve()
        backup_resolved = backup_path.resolve()
        copied = 0
        for rel_path in files_to_patch:
            src = game_dir / rel_path
            # Validate source stays within game dir (prevent path traversal in file list)
            if not src.resolve().is_relative_to(game_resolved):
                logger.warning("Skipping backup of path-escaping file: %s", rel_path)
                continue
            if not src.is_file() or src.is_symlink():
                continue
            dest = backup_path / rel_path
            # Validate dest stays within backup dir
            if not dest.resolve().is_relative_to(backup_resolved):
                logger.warning("Skipping backup of path-escaping dest: %s", rel_path)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(src), str(dest))
                copied += 1
            except OSError as e:
                logger.warning("Failed to backup %s: %s", rel_path, e)

        logger.info("Backup created: %s (%d files)", backup_path.name, copied)
        return backup_path

    def list_backups(self) -> list[BackupInfo]:
        """List existing backups sorted newest-first."""
        results: list[BackupInfo] = []
        if not self.backup_dir.is_dir():
            return results

        for entry in self.backup_dir.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            # Parse timestamp from folder name: YYYYMMDD_HHMMSS_version
            parts = name.split("_", 2)
            if len(parts) < 3:
                continue
            try:
                ts = datetime.strptime(f"{parts[0]}_{parts[1]}", "%Y%m%d_%H%M%S")
            except ValueError:
                continue
            version = parts[2] if len(parts) > 2 else "unknown"

            # Compute total size
            total_size = 0
            for root, _dirs, files in os.walk(entry):
                for f in files:
                    with contextlib.suppress(OSError):
                        total_size += (Path(root) / f).stat().st_size

            results.append(
                BackupInfo(
                    path=entry,
                    timestamp=ts,
                    version=version,
                    size=total_size,
                )
            )

        results.sort(key=lambda b: b.timestamp, reverse=True)
        return results

    def restore_backup(
        self,
        backup_path: Path,
        game_dir: Path,
        progress_cb=None,
    ) -> int:
        """Copy files from backup back to game dir.

        Returns number of files restored.
        """
        # Validate backup_path is actually within our backup directory
        backup_resolved = backup_path.resolve()
        if not backup_resolved.is_relative_to(self.backup_dir.resolve()):
            logger.error("Backup path outside backup dir: %s", backup_path)
            return 0

        game_resolved = game_dir.resolve()
        restored = 0
        all_files = []
        for root, _dirs, files in os.walk(backup_path):
            for f in files:
                fp = Path(root) / f
                # Skip symlinks — prevent symlink-based path escape
                if fp.is_symlink():
                    logger.warning("Skipping symlink in backup: %s", fp)
                    continue
                all_files.append(fp)

        total = len(all_files)
        for i, src in enumerate(all_files):
            rel = src.relative_to(backup_path)
            dest = game_dir / rel
            # Path traversal protection — ensure dest stays within game dir
            if not dest.resolve().is_relative_to(game_resolved):
                logger.warning("Skipping restore of path-escaping file: %s", rel)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(src), str(dest))
                restored += 1
            except OSError as e:
                logger.warning("Failed to restore %s: %s", rel, e)

            if progress_cb:
                progress_cb(i + 1, total, str(rel))

        logger.info("Restored %d/%d files from %s", restored, total, backup_path.name)
        return restored

    def delete_backup(self, backup_path: Path) -> None:
        """Delete a single backup folder."""
        # Use resolve() for robust containment check
        resolved = backup_path.resolve()
        if resolved.is_dir() and resolved.is_relative_to(self.backup_dir.resolve()):
            shutil.rmtree(resolved, ignore_errors=True)
            logger.info("Deleted backup: %s", backup_path.name)

    def delete_all_backups(self) -> None:
        """Delete all backup folders."""
        if self.backup_dir.is_dir():
            shutil.rmtree(self.backup_dir, ignore_errors=True)
            logger.info("Deleted all backups")

    def prune_old_backups(self) -> None:
        """Keep only max_count newest backups, delete the rest.

        When max_count is 0, all existing backups are deleted.
        """
        backups = self.list_backups()
        if len(backups) <= self.max_count:
            return
        for old in backups[self.max_count :]:
            self.delete_backup(old.path)

    def get_total_size(self) -> int:
        """Get total disk usage of all backups in bytes."""
        if not self.backup_dir.is_dir():
            return 0
        total = 0
        for root, _dirs, files in os.walk(self.backup_dir):
            for f in files:
                with contextlib.suppress(OSError):
                    total += (Path(root) / f).stat().st_size
        return total
