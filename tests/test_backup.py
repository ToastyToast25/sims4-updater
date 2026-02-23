"""Tests for BackupManager — backup/restore/prune operations."""

from __future__ import annotations

from pathlib import Path

from sims4_updater.core.backup import BackupInfo, BackupManager


class TestBackupManager:
    def _make_manager(self, tmp_path: Path, max_count: int = 3) -> BackupManager:
        return BackupManager(app_dir=tmp_path, max_count=max_count)

    def test_create_backup(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        files = ["Game/Bin/TS4_x64.exe", "Game/Bin/Default.ini"]
        path = mgr.create_backup(sample_game_dir, files, "1.100.0.1000")
        assert path.is_dir()
        assert (path / "Game" / "Bin" / "TS4_x64.exe").is_file()
        assert (path / "Game" / "Bin" / "Default.ini").is_file()

    def test_create_backup_skips_missing(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        files = ["nonexistent.txt", "Game/Bin/TS4_x64.exe"]
        path = mgr.create_backup(sample_game_dir, files, "1.0")
        # Only the existing file is backed up
        assert (path / "Game" / "Bin" / "TS4_x64.exe").is_file()
        assert not (path / "nonexistent.txt").exists()

    def test_list_backups_empty(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.list_backups() == []

    def test_list_backups_sorted(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        files = ["Game/Bin/TS4_x64.exe"]

        import time

        mgr.create_backup(sample_game_dir, files, "v1")
        time.sleep(1.1)  # ensure different timestamp
        mgr.create_backup(sample_game_dir, files, "v2")

        backups = mgr.list_backups()
        assert len(backups) == 2
        # Newest first
        assert "v2" in backups[0].version
        assert "v1" in backups[1].version

    def test_restore_backup(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        files = ["Game/Bin/TS4_x64.exe"]
        backup_path = mgr.create_backup(sample_game_dir, files, "1.0")

        # Delete the original file
        original = sample_game_dir / "Game" / "Bin" / "TS4_x64.exe"
        original.unlink()
        assert not original.exists()

        # Restore
        restored = mgr.restore_backup(backup_path, sample_game_dir)
        assert restored == 1
        assert original.is_file()

    def test_delete_backup(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        path = mgr.create_backup(sample_game_dir, ["Game/Bin/TS4_x64.exe"], "1.0")
        assert path.is_dir()
        mgr.delete_backup(path)
        assert not path.exists()

    def test_delete_all_backups(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        mgr.create_backup(sample_game_dir, ["Game/Bin/TS4_x64.exe"], "v1")
        mgr.create_backup(sample_game_dir, ["Game/Bin/TS4_x64.exe"], "v2")
        mgr.delete_all_backups()
        assert mgr.list_backups() == []

    def test_prune_keeps_max(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path, max_count=2)
        files = ["Game/Bin/TS4_x64.exe"]

        import time

        mgr.create_backup(sample_game_dir, files, "v1")
        time.sleep(1.1)
        mgr.create_backup(sample_game_dir, files, "v2")
        time.sleep(1.1)
        mgr.create_backup(sample_game_dir, files, "v3")

        assert len(mgr.list_backups()) == 3
        mgr.prune_old_backups()
        backups = mgr.list_backups()
        assert len(backups) == 2
        # Newest two should remain
        assert "v3" in backups[0].version
        assert "v2" in backups[1].version

    def test_estimate_backup_size(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        size = mgr.estimate_backup_size(
            sample_game_dir, ["Game/Bin/TS4_x64.exe", "nonexistent.txt"]
        )
        assert size > 0  # TS4_x64.exe has content

    def test_get_total_size_empty(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.get_total_size() == 0

    def test_get_total_size_with_backups(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        mgr.create_backup(sample_game_dir, ["Game/Bin/TS4_x64.exe"], "v1")
        assert mgr.get_total_size() > 0

    def test_max_count_clamped_to_one(self, tmp_path):
        mgr = BackupManager(app_dir=tmp_path, max_count=0)
        assert mgr.max_count == 1

    def test_restore_calls_progress(self, tmp_path, sample_game_dir):
        mgr = self._make_manager(tmp_path)
        path = mgr.create_backup(sample_game_dir, ["Game/Bin/TS4_x64.exe"], "1.0")
        calls = []
        mgr.restore_backup(path, sample_game_dir, progress_cb=lambda *a: calls.append(a))
        assert len(calls) > 0
        assert calls[-1][0] == calls[-1][1]  # current == total at end


class TestBackupInfo:
    def test_display_name(self):
        from datetime import datetime

        info = BackupInfo(
            path=Path("/tmp/test"),
            timestamp=datetime(2025, 6, 15, 14, 30),
            version="1.100.0.1000",
            size=1024,
        )
        assert "1.100.0.1000" in info.display_name
        assert "2025-06-15" in info.display_name
