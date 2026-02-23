"""Tests for GameValidator — game file validation and reporting."""

from __future__ import annotations

from sims4_updater.core.validator import (
    FileState,
    GameValidator,
    ValidationReport,
)


class TestValidationReport:
    def test_is_healthy_true(self):
        r = ValidationReport(game_dir="/test")
        r.ok_count = 5
        assert r.is_healthy is True

    def test_is_healthy_false_missing(self):
        r = ValidationReport(game_dir="/test")
        r.missing_count = 1
        assert r.is_healthy is False

    def test_is_healthy_false_corrupt(self):
        r = ValidationReport(game_dir="/test")
        r.corrupt_count = 1
        assert r.is_healthy is False

    def test_get_problems_empty(self):
        r = ValidationReport(game_dir="/test")
        assert r.get_problems() == []


class TestGameValidator:
    def test_validate_nonexistent_dir(self, tmp_path):
        v = GameValidator()
        report = v.validate(tmp_path / "nonexistent")
        assert len(report.errors) > 0
        assert "does not exist" in report.errors[0]

    def test_validate_base_game(self, sample_game_dir):
        v = GameValidator()
        report = v.validate(sample_game_dir)
        # All 4 critical files exist in sample_game_dir
        assert report.ok_count >= 4
        assert report.missing_count == 0
        assert report.is_healthy is True

    def test_validate_missing_critical_file(self, sample_game_dir):
        # Remove a critical file
        (sample_game_dir / "Data" / "Client" / "ClientFullBuild0.package").unlink()
        v = GameValidator()
        report = v.validate(sample_game_dir)
        assert report.missing_count >= 1
        assert report.is_healthy is False

    def test_validate_dlc_folders(self, sample_dlc_dir):
        v = GameValidator()
        report = v.validate(sample_dlc_dir)
        # EP01, EP02, GP01, SP01 are complete; EP03 is missing its package
        assert report.missing_count >= 1  # EP03/SimulationFullBuild0.package

    def test_validate_calls_progress(self, sample_game_dir):
        v = GameValidator()
        calls = []
        v.validate(sample_game_dir, progress=lambda *a: calls.append(a))
        assert len(calls) > 0

    def test_cancel_stops_validation(self, sample_dlc_dir):
        v = GameValidator()

        def cancel_after_first(*args):
            v.cancel()

        report = v.validate(sample_dlc_dir, progress=cancel_after_first)
        assert any("cancelled" in e.lower() for e in report.errors)

    def test_format_size_bytes(self):
        assert GameValidator.format_size(500) == "500 B"

    def test_format_size_kb(self):
        assert "KB" in GameValidator.format_size(2048)

    def test_format_size_mb(self):
        assert "MB" in GameValidator.format_size(5 * 1024 * 1024)

    def test_format_size_gb(self):
        assert "GB" in GameValidator.format_size(3 * 1024 * 1024 * 1024)

    def test_export_yaml(self, sample_game_dir):
        v = GameValidator()
        report = v.validate(sample_game_dir)
        report.version = "1.100.0.1000"
        yaml_text = v.export_yaml(report)
        assert "game_dir:" in yaml_text
        assert "version: 1.100.0.1000" in yaml_text
        assert "files_scanned:" in yaml_text

    def test_find_dlc_dirs(self, sample_dlc_dir):
        v = GameValidator()
        dirs = v._find_dlc_dirs(sample_dlc_dir)
        names = [d.name for d in dirs]
        assert "EP01" in names
        assert "GP01" in names
        # "Data" and "Game" are not DLC dirs
        assert "Data" not in names
        assert "Game" not in names


class TestFileState:
    def test_values(self):
        assert FileState.OK.value == "ok"
        assert FileState.MISSING.value == "missing"
        assert FileState.CORRUPT.value == "corrupt"
        assert FileState.EXTRA.value == "extra"
