"""Tests for version detection — VersionDatabase and VersionDetector."""

from __future__ import annotations

import json
from unittest.mock import patch

from sims4_updater.core.learned_hashes import LearnedHashDB
from sims4_updater.core.version_detect import (
    Confidence,
    DetectionResult,
    VersionDatabase,
    VersionDetector,
)


def _empty_learned(tmp_path):
    """Create an empty LearnedHashDB that doesn't load from disk."""
    return LearnedHashDB(path=tmp_path / "empty_learned.json")


class TestVersionDatabase:
    def test_loads_db(self, version_db_file, tmp_path):
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        assert len(db.versions) == 2
        assert "1.100.0.1000" in db.versions

    def test_sentinel_files(self, version_db_file, tmp_path):
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        assert "Game/Bin/TS4_x64.exe" in db.sentinel_files
        assert "Game/Bin/Default.ini" in db.sentinel_files

    def test_lookup_exact_match(self, version_db_file, tmp_path):
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        result = db.lookup({"Game/Bin/TS4_x64.exe": "aaa111", "Game/Bin/Default.ini": "bbb222"})
        assert result.version == "1.100.0.1000"
        assert result.confidence == Confidence.DEFINITIVE

    def test_lookup_partial_match(self, version_db_file, tmp_path):
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        # Only one sentinel matches — not enough for DEFINITIVE
        result = db.lookup({"Game/Bin/TS4_x64.exe": "ccc333"})
        assert result.version == "1.101.0.1000"
        assert result.confidence == Confidence.UNKNOWN

    def test_lookup_no_match(self, version_db_file, tmp_path):
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        result = db.lookup({"Game/Bin/TS4_x64.exe": "zzz999"})
        assert result.version is None
        assert result.confidence == Confidence.UNKNOWN

    def test_lookup_empty_hashes(self, version_db_file, tmp_path):
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        result = db.lookup({})
        assert result.version is None
        assert result.confidence == Confidence.UNKNOWN

    def test_lookup_multiple_matches_single_sentinel_unknown(self, tmp_path):
        """When multiple versions match on only 1 sentinel each, result is UNKNOWN."""
        db_data = {
            "sentinel_files": ["Game/Bin/TS4_x64.exe"],
            "versions": {
                "1.0": {"Game/Bin/TS4_x64.exe": "same_hash"},
                "2.0": {"Game/Bin/TS4_x64.exe": "same_hash"},
            },
        }
        path = tmp_path / "db.json"
        path.write_text(json.dumps(db_data), encoding="utf-8")
        db = VersionDatabase(db_path=path, learned_db=_empty_learned(tmp_path))
        result = db.lookup({"Game/Bin/TS4_x64.exe": "same_hash"})
        assert result.confidence == Confidence.UNKNOWN
        assert len(result.matched_versions) == 2

    def test_lookup_mismatched_sentinel_skips_version(self, version_db_file, tmp_path):
        """If one sentinel matches but another mismatches, version is excluded."""
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        result = db.lookup({"Game/Bin/TS4_x64.exe": "aaa111", "Game/Bin/Default.ini": "WRONG"})
        assert result.version is None
        assert result.confidence == Confidence.UNKNOWN


class TestDetectionResult:
    def test_dataclass_fields(self):
        r = DetectionResult(
            version="1.0",
            confidence=Confidence.DEFINITIVE,
            local_hashes={"a": "b"},
            matched_versions=["1.0"],
        )
        assert r.version == "1.0"
        assert r.confidence == Confidence.DEFINITIVE
        assert r.local_hashes == {"a": "b"}


class TestVersionDetector:
    def test_validate_game_dir_valid(self, sample_game_dir):
        detector = VersionDetector(db=VersionDatabase.__new__(VersionDatabase))
        detector.db = VersionDatabase.__new__(VersionDatabase)
        detector.db.sentinel_files = []
        detector.db.versions = {}
        assert detector.validate_game_dir(sample_game_dir) is True

    def test_validate_game_dir_missing(self, tmp_path):
        detector = VersionDetector(db=VersionDatabase.__new__(VersionDatabase))
        detector.db = VersionDatabase.__new__(VersionDatabase)
        detector.db.sentinel_files = []
        detector.db.versions = {}
        assert detector.validate_game_dir(tmp_path / "nonexistent") is False

    def test_validate_game_dir_no_markers(self, tmp_path):
        """Empty dir lacks install markers."""
        detector = VersionDetector(db=VersionDatabase.__new__(VersionDatabase))
        detector.db = VersionDatabase.__new__(VersionDatabase)
        detector.db.sentinel_files = []
        detector.db.versions = {}
        assert detector.validate_game_dir(tmp_path) is False

    def test_detect_with_known_hashes(self, sample_game_dir, version_db_file, tmp_path):
        """Detect version when hash_file returns known values."""
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        detector = VersionDetector(db=db)
        with patch(
            "sims4_updater.core.version_detect.hash_file",
            side_effect=lambda path: "aaa111" if "TS4_x64" in path else "bbb222",
        ):
            result = detector.detect(sample_game_dir)
        assert result.version == "1.100.0.1000"
        assert result.confidence == Confidence.DEFINITIVE

    def test_detect_unknown_version(self, sample_game_dir, version_db_file, tmp_path):
        """Unknown hashes yield UNKNOWN confidence."""
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        detector = VersionDetector(db=db)
        with patch(
            "sims4_updater.core.version_detect.hash_file",
            return_value="unknown_hash",
        ):
            result = detector.detect(sample_game_dir)
        assert result.version is None
        assert result.confidence == Confidence.UNKNOWN

    def test_detect_calls_progress(self, sample_game_dir, version_db_file, tmp_path):
        """Progress callback is invoked."""
        db = VersionDatabase(db_path=version_db_file, learned_db=_empty_learned(tmp_path))
        detector = VersionDetector(db=db)
        calls = []
        with patch(
            "sims4_updater.core.version_detect.hash_file",
            return_value="xxx",
        ):
            detector.detect(sample_game_dir, progress=lambda *a: calls.append(a))
        # At least "done" call at the end
        assert any(c[0] == "done" for c in calls)


class TestConfidence:
    def test_values(self):
        assert Confidence.DEFINITIVE.value == "definitive"
        assert Confidence.PROBABLE.value == "probable"
        assert Confidence.UNKNOWN.value == "unknown"
