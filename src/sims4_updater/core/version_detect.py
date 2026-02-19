"""
Version detection for The Sims 4.

Hashes 1-3 sentinel files and matches against a database of 135 known versions.
Detection takes <2 seconds on SSD.
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .exceptions import VersionDetectionError
from .files import hash_file
from .. import constants


class Confidence(Enum):
    DEFINITIVE = "definitive"  # unique match on all available sentinels
    PROBABLE = "probable"      # matched but some sentinels missing
    UNKNOWN = "unknown"        # no match found


@dataclass
class DetectionResult:
    version: str | None
    confidence: Confidence
    local_hashes: dict[str, str]
    matched_versions: list[str]


class VersionDatabase:
    """In-memory database of version fingerprints."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = constants.get_data_dir() / "version_hashes.json"

        with open(db_path, encoding="utf-8") as f:
            data = json.load(f)

        self.sentinel_files: list[str] = data["sentinel_files"]
        self.versions: dict[str, dict[str, str]] = data["versions"]

    def lookup(self, local_hashes: dict[str, str]) -> DetectionResult:
        """Match local file hashes against the version database."""
        if not local_hashes:
            return DetectionResult(
                version=None,
                confidence=Confidence.UNKNOWN,
                local_hashes=local_hashes,
                matched_versions=[],
            )

        matches = []
        for version, fingerprint in self.versions.items():
            match = True
            matched_count = 0
            for sentinel, expected_hash in fingerprint.items():
                local_hash = local_hashes.get(sentinel)
                if local_hash is None:
                    continue  # sentinel not available locally, skip
                if local_hash != expected_hash:
                    match = False
                    break
                matched_count += 1

            if match and matched_count > 0:
                matches.append((version, matched_count))

        if not matches:
            return DetectionResult(
                version=None,
                confidence=Confidence.UNKNOWN,
                local_hashes=local_hashes,
                matched_versions=[],
            )

        # Sort by number of matched sentinels (more = better)
        matches.sort(key=lambda x: x[1], reverse=True)
        best_version, best_count = matches[0]

        matched_versions = [v for v, _ in matches]

        if len(matches) == 1:
            confidence = Confidence.DEFINITIVE
        elif best_count >= 2:
            confidence = Confidence.PROBABLE
        else:
            confidence = Confidence.PROBABLE

        return DetectionResult(
            version=best_version,
            confidence=confidence,
            local_hashes=local_hashes,
            matched_versions=matched_versions,
        )


class VersionDetector:
    """Detects the installed Sims 4 version by hashing sentinel files."""

    def __init__(self, db: VersionDatabase | None = None):
        self.db = db or VersionDatabase()

    def validate_game_dir(self, game_dir: str | Path) -> bool:
        """Check if the directory looks like a Sims 4 installation."""
        game_dir = Path(game_dir)
        if not game_dir.is_dir():
            return False
        for marker in constants.SIMS4_INSTALL_MARKERS:
            path = game_dir / marker.replace("/", os.sep)
            if not path.exists():
                return False
        return True

    def detect(
        self,
        game_dir: str | Path,
        progress=None,
    ) -> DetectionResult:
        """
        Detect the installed version.

        Args:
            game_dir: Path to the Sims 4 installation directory.
            progress: Optional callback(sentinel_name, current, total).

        Returns:
            DetectionResult with version info and confidence level.
        """
        game_dir = Path(game_dir)

        if not self.validate_game_dir(game_dir):
            raise VersionDetectionError(
                f'"{game_dir}" does not look like a Sims 4 installation. '
                f"Missing expected files."
            )

        sentinels = self.db.sentinel_files
        total = len(sentinels)
        local_hashes = {}

        for i, sentinel in enumerate(sentinels):
            file_path = game_dir / sentinel.replace("/", os.sep)

            if progress:
                progress(sentinel, i, total)

            if not file_path.is_file():
                continue

            md5 = hash_file(str(file_path))
            local_hashes[sentinel] = md5

        if progress:
            progress("done", total, total)

        return self.db.lookup(local_hashes)

    def find_game_dir(self) -> Path | None:
        """Try to auto-detect the Sims 4 installation directory."""
        # Try registry first (Windows)
        if os.name == "nt":
            path = self._find_from_registry()
            if path:
                return path

        # Try default locations
        for default_path in constants.DEFAULT_GAME_PATHS:
            p = Path(default_path)
            if self.validate_game_dir(p):
                return p

        return None

    def _find_from_registry(self) -> Path | None:
        """Read game path from Windows registry."""
        try:
            import winreg
        except ImportError:
            return None

        for reg_path in constants.REGISTRY_PATHS:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, reg_path) as key:
                        install_dir, _ = winreg.QueryValueEx(key, "Install Dir")
                        p = Path(install_dir)
                        if self.validate_game_dir(p):
                            return p
                except (OSError, FileNotFoundError):
                    continue

        return None
