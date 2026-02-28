"""Tests for core.diagnostics — system health checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sims4_updater.core.diagnostics import (
    CheckStatus,
    DiagnosticResult,
    DiagnosticsReport,
    _check_dir_path_issues,
    _check_dir_permissions,
    _check_game_bin_files,
    _check_game_exe_exists,
)

# ── DiagnosticResult / DiagnosticsReport ──────────────────────────


class TestDiagnosticResult:
    def test_fields(self):
        r = DiagnosticResult(name="Test", status=CheckStatus.PASS, message="All good")
        assert r.name == "Test"
        assert r.status == CheckStatus.PASS
        assert r.message == "All good"
        assert r.fix == ""

    def test_with_fix(self):
        r = DiagnosticResult(
            name="Test",
            status=CheckStatus.FAIL,
            message="Bad",
            fix="Do this",
        )
        assert r.fix == "Do this"


class TestDiagnosticsReport:
    def test_counts(self):
        report = DiagnosticsReport(
            results=[
                DiagnosticResult("A", CheckStatus.PASS, "ok"),
                DiagnosticResult("B", CheckStatus.PASS, "ok"),
                DiagnosticResult("C", CheckStatus.WARN, "eh"),
                DiagnosticResult("D", CheckStatus.FAIL, "bad"),
                DiagnosticResult("E", CheckStatus.SKIP, "n/a"),
            ]
        )
        assert report.pass_count == 2
        assert report.warn_count == 1
        assert report.fail_count == 1

    def test_is_healthy_no_failures(self):
        report = DiagnosticsReport(
            results=[
                DiagnosticResult("A", CheckStatus.PASS, "ok"),
                DiagnosticResult("B", CheckStatus.WARN, "eh"),
            ]
        )
        assert report.is_healthy is True

    def test_is_healthy_with_failures(self):
        report = DiagnosticsReport(
            results=[
                DiagnosticResult("A", CheckStatus.FAIL, "bad"),
            ]
        )
        assert report.is_healthy is False

    def test_empty_report(self):
        report = DiagnosticsReport(results=[])
        assert report.pass_count == 0
        assert report.fail_count == 0
        assert report.is_healthy is True


# ── CheckStatus ───────────────────────────────────────────────────


class TestCheckStatus:
    def test_values(self):
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.WARN.value == "warn"
        assert CheckStatus.FAIL.value == "fail"
        assert CheckStatus.SKIP.value == "skip"


# ── _check_dir_path_issues ────────────────────────────────────────


class TestCheckDirPathIssues:
    def test_normal_path(self, tmp_path):
        result = _check_dir_path_issues(tmp_path)
        assert result.status == CheckStatus.PASS

    def test_semicolon_in_path(self):
        result = _check_dir_path_issues(Path("C:\\Games;Bad\\Sims 4"))
        assert result.status == CheckStatus.WARN
        assert "semicolon" in result.message

    def test_non_ascii_path(self):
        result = _check_dir_path_issues(Path("C:\\Jeux\\Les Sims 4\\日本語"))
        assert result.status == CheckStatus.WARN
        assert "non-ASCII" in result.message

    def test_long_path(self):
        long_path = Path("C:\\" + "a" * 250)
        result = _check_dir_path_issues(long_path)
        assert result.status == CheckStatus.WARN
        assert "long" in result.message


# ── _check_dir_permissions ────────────────────────────────────────


class TestCheckDirPermissions:
    def test_nonexistent_dir(self, tmp_path):
        result = _check_dir_permissions(tmp_path / "nope")
        assert result.status == CheckStatus.FAIL
        assert "does not exist" in result.message

    def test_writable_dir(self, tmp_path):
        result = _check_dir_permissions(tmp_path)
        assert result.status == CheckStatus.PASS

    def test_read_only_dir(self, tmp_path):
        with patch("sims4_updater.core.diagnostics.os.access") as mock_access:
            # First call (R_OK) = True, second call (W_OK) = False
            mock_access.side_effect = lambda p, mode: mode != 2  # os.W_OK = 2
            result = _check_dir_permissions(tmp_path)
        assert result.status == CheckStatus.FAIL
        assert "read-only" in result.message


# ── _check_game_exe_exists ────────────────────────────────────────


class TestCheckGameExeExists:
    def test_exe_found(self, tmp_path):
        bin_dir = tmp_path / "Game" / "Bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "TS4_x64.exe").write_bytes(b"exe")

        result = _check_game_exe_exists(tmp_path)

        assert result.status == CheckStatus.PASS

    def test_exe_missing(self, tmp_path):
        result = _check_game_exe_exists(tmp_path)
        assert result.status == CheckStatus.FAIL
        assert "quarantined" in result.message

    def test_cracked_exe_found(self, tmp_path):
        bin_dir = tmp_path / "Game-cracked" / "Bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "TS4_x64.exe").write_bytes(b"exe")

        result = _check_game_exe_exists(tmp_path)

        assert result.status == CheckStatus.PASS


# ── _check_game_bin_files ─────────────────────────────────────────


class TestCheckGameBinFiles:
    def test_no_bin_dir(self, tmp_path):
        result = _check_game_bin_files(tmp_path)
        assert result.status == CheckStatus.SKIP

    def test_all_files_present(self, tmp_path):
        bin_dir = tmp_path / "Game" / "Bin"
        bin_dir.mkdir(parents=True)
        for f in ["anadius64.dll", "anadius32.dll", "OrangeEmu64.dll", "Default.ini"]:
            (bin_dir / f).write_bytes(b"dll")

        result = _check_game_bin_files(tmp_path)

        assert result.status == CheckStatus.PASS
        assert "All critical" in result.message

    def test_default_ini_missing(self, tmp_path):
        bin_dir = tmp_path / "Game" / "Bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "anadius64.dll").write_bytes(b"dll")

        result = _check_game_bin_files(tmp_path)

        assert result.status == CheckStatus.FAIL
        assert "Default.ini" in result.message

    def test_optional_dlls_missing(self, tmp_path):
        bin_dir = tmp_path / "Game" / "Bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "Default.ini").write_bytes(b"ini")

        result = _check_game_bin_files(tmp_path)

        assert result.status == CheckStatus.PASS
        assert "Optional files not found" in result.message
