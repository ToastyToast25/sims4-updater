"""
Game file validator — checks all game files against known good states.

Scans the game directory and reports:
  - Missing files (expected but not found)
  - Extra files (found but not expected)
  - Corrupt files (MD5 mismatch)
  - File counts and sizes per DLC folder
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .files import hash_file


class FileState(Enum):
    OK = "ok"
    MISSING = "missing"
    CORRUPT = "corrupt"
    EXTRA = "extra"


@dataclass
class FileResult:
    path: str  # relative to game dir
    state: FileState
    expected_md5: str = ""
    actual_md5: str = ""
    size: int = 0


@dataclass
class FolderSummary:
    name: str
    total_files: int = 0
    total_size: int = 0
    ok_count: int = 0
    missing_count: int = 0
    corrupt_count: int = 0
    extra_count: int = 0


@dataclass
class ValidationReport:
    game_dir: str
    version: str = ""
    total_files_scanned: int = 0
    total_size: int = 0
    ok_count: int = 0
    missing_count: int = 0
    corrupt_count: int = 0
    extra_count: int = 0
    results: list[FileResult] = field(default_factory=list)
    folders: list[FolderSummary] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.missing_count == 0 and self.corrupt_count == 0

    def get_problems(self) -> list[FileResult]:
        return [r for r in self.results if r.state != FileState.OK]


# Known critical game files that should always exist
_CRITICAL_FILES = [
    "Game/Bin/TS4_x64.exe",
    "Game/Bin/Default.ini",
    "Data/Client/ClientFullBuild0.package",
    "Data/Client/ClientDeltaBuild0.package",
]

# Known DLC folder patterns
_DLC_PREFIXES = ("EP", "GP", "SP", "FP")

# Files expected inside a complete DLC folder
_DLC_REQUIRED_FILES = [
    "SimulationFullBuild0.package",
]


class GameValidator:
    """Validates a Sims 4 game installation for completeness and integrity."""

    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def validate(
        self,
        game_dir: str | Path,
        progress=None,
        check_hashes: bool = False,
    ) -> ValidationReport:
        """
        Validate a game installation.

        Args:
            game_dir: Path to The Sims 4 installation directory.
            progress: Optional callback(message, current, total).
            check_hashes: If True, compute MD5 of critical files (slower).

        Returns:
            ValidationReport with findings.
        """
        game_dir = Path(game_dir)
        report = ValidationReport(game_dir=str(game_dir))
        self._cancelled = False

        if not game_dir.is_dir():
            report.errors.append(f"Directory does not exist: {game_dir}")
            return report

        # Phase 1: Check critical base game files
        if progress:
            progress("Checking base game files...", 0, 0)

        for rel_path in _CRITICAL_FILES:
            if self._cancelled:
                report.errors.append("Validation cancelled.")
                return report

            full_path = game_dir / rel_path.replace("/", os.sep)
            if full_path.is_file():
                size = full_path.stat().st_size
                result = FileResult(
                    path=rel_path, state=FileState.OK, size=size,
                )
                if check_hashes:
                    result.actual_md5 = hash_file(str(full_path))
                report.ok_count += 1
                report.total_size += size
            else:
                result = FileResult(path=rel_path, state=FileState.MISSING)
                report.missing_count += 1

            report.results.append(result)
            report.total_files_scanned += 1

        # Phase 2: Scan DLC folders
        if progress:
            progress("Scanning DLC folders...", 0, 0)

        dlc_dirs = self._find_dlc_dirs(game_dir)
        total_dlcs = len(dlc_dirs)

        for i, dlc_dir in enumerate(dlc_dirs):
            if self._cancelled:
                report.errors.append("Validation cancelled.")
                return report

            dlc_name = dlc_dir.name
            if progress:
                progress(f"Checking {dlc_name}...", i + 1, total_dlcs)

            summary = self._validate_dlc_folder(
                game_dir, dlc_dir, report, check_hashes,
            )
            report.folders.append(summary)

        # Phase 3: Check Game/Bin directory
        if progress:
            progress("Checking Game/Bin...", total_dlcs, total_dlcs)

        bin_dir = game_dir / "Game" / "Bin"
        if bin_dir.is_dir():
            bin_summary = self._scan_folder(game_dir, bin_dir, report, check_hashes)
            bin_summary.name = "Game/Bin"
            report.folders.append(bin_summary)

        # Phase 4: Check Data directory
        data_dir = game_dir / "Data"
        if data_dir.is_dir():
            data_summary = self._scan_folder(game_dir, data_dir, report, check_hashes)
            data_summary.name = "Data"
            report.folders.append(data_summary)

        if progress:
            progress("Validation complete.", 1, 1)

        return report

    def _find_dlc_dirs(self, game_dir: Path) -> list[Path]:
        """Find all DLC directories in the game folder."""
        dlc_dirs = []
        try:
            for entry in sorted(game_dir.iterdir()):
                if entry.is_dir() and any(
                    entry.name.startswith(p) for p in _DLC_PREFIXES
                ):
                    dlc_dirs.append(entry)
        except OSError:
            pass
        return dlc_dirs

    def _validate_dlc_folder(
        self,
        game_dir: Path,
        dlc_dir: Path,
        report: ValidationReport,
        check_hashes: bool,
    ) -> FolderSummary:
        """Validate a single DLC folder for completeness."""
        summary = FolderSummary(name=dlc_dir.name)

        # Check required DLC files
        for req_file in _DLC_REQUIRED_FILES:
            full_path = dlc_dir / req_file
            rel_path = str(full_path.relative_to(game_dir)).replace(os.sep, "/")

            if full_path.is_file():
                size = full_path.stat().st_size
                result = FileResult(
                    path=rel_path, state=FileState.OK, size=size,
                )
                if check_hashes:
                    result.actual_md5 = hash_file(str(full_path))
                summary.ok_count += 1
                summary.total_size += size
                report.ok_count += 1
                report.total_size += size
            else:
                result = FileResult(path=rel_path, state=FileState.MISSING)
                summary.missing_count += 1
                report.missing_count += 1

            report.results.append(result)
            report.total_files_scanned += 1

        # Count all files in the DLC folder
        import contextlib

        try:
            for entry in dlc_dir.iterdir():
                if entry.is_file():
                    summary.total_files += 1
                    with contextlib.suppress(OSError):
                        summary.total_size += entry.stat().st_size
        except OSError:
            pass

        return summary

    def _scan_folder(
        self,
        game_dir: Path,
        folder: Path,
        report: ValidationReport,
        check_hashes: bool,
    ) -> FolderSummary:
        """Scan a folder and count files/sizes (non-recursive for top-level scan)."""
        summary = FolderSummary(name=str(folder.relative_to(game_dir)))

        try:
            for root, _dirs, files in os.walk(folder):
                for fname in files:
                    if self._cancelled:
                        return summary

                    full_path = Path(root) / fname
                    try:
                        size = full_path.stat().st_size
                    except OSError:
                        size = 0

                    summary.total_files += 1
                    summary.total_size += size
                    summary.ok_count += 1
        except OSError:
            pass

        return summary

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes into human-readable size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def export_yaml(self, report: ValidationReport) -> str:
        """Export report to YAML-like text format (compatible with anadius validator)."""
        lines = []
        lines.append(f"game_dir: {report.game_dir}")
        if report.version:
            lines.append(f"version: {report.version}")
        lines.append(f"files_scanned: {report.total_files_scanned}")
        lines.append(f"total_size: {self.format_size(report.total_size)}")
        lines.append(f"ok: {report.ok_count}")
        lines.append(f"missing: {report.missing_count}")
        lines.append(f"corrupt: {report.corrupt_count}")
        lines.append(f"extra: {report.extra_count}")
        lines.append("")
        lines.append("folders:")

        for folder in report.folders:
            lines.append(f"  - name: {folder.name}")
            lines.append(f"    files: {folder.total_files}")
            lines.append(f"    size: {self.format_size(folder.total_size)}")
            if folder.missing_count:
                lines.append(f"    missing: {folder.missing_count}")
            if folder.corrupt_count:
                lines.append(f"    corrupt: {folder.corrupt_count}")

        problems = report.get_problems()
        if problems:
            lines.append("")
            lines.append("problems:")
            for p in problems:
                lines.append(f"  - path: {p.path}")
                lines.append(f"    state: {p.state.value}")
                if p.expected_md5:
                    lines.append(f"    expected_md5: {p.expected_md5}")
                if p.actual_md5:
                    lines.append(f"    actual_md5: {p.actual_md5}")

        if report.errors:
            lines.append("")
            lines.append("errors:")
            for err in report.errors:
                lines.append(f"  - {err}")

        return "\n".join(lines)
