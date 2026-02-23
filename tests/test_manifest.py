"""Tests for patch manifest parsing."""

from __future__ import annotations

import pytest

from sims4_updater.core.exceptions import ManifestError
from sims4_updater.patch.manifest import (
    DLCDownloadEntry,
    FileEntry,
    LanguageDownloadEntry,
    Manifest,
    PatchEntry,
    parse_manifest,
)

# -- FileEntry -----------------------------------------------------------------


class TestFileEntry:
    def test_filename_derived_from_url(self):
        fe = FileEntry(url="https://cdn.example.com/patches/1_to_2.zip", size=100, md5="abc")
        assert fe.filename == "1_to_2.zip"

    def test_filename_strips_query_string(self):
        fe = FileEntry(url="https://cdn.example.com/EP01.zip?v=2&t=123", size=50, md5="def")
        assert fe.filename == "EP01.zip"

    def test_explicit_filename_not_overwritten(self):
        fe = FileEntry(url="https://cdn.example.com/file.zip", size=10, md5="a", filename="my.zip")
        assert fe.filename == "my.zip"

    def test_url_with_no_path(self):
        fe = FileEntry(url="https://cdn.example.com", size=0, md5="")
        assert fe.filename == "cdn.example.com"


# -- PatchEntry ----------------------------------------------------------------


class TestPatchEntry:
    def test_total_size_files_only(self):
        pe = PatchEntry(
            version_from="1.0",
            version_to="2.0",
            files=[
                FileEntry(url="a.zip", size=100, md5="a"),
                FileEntry(url="b.zip", size=200, md5="b"),
            ],
        )
        assert pe.total_size == 300

    def test_total_size_with_crack(self):
        pe = PatchEntry(
            version_from="1.0",
            version_to="2.0",
            files=[FileEntry(url="a.zip", size=100, md5="a")],
            crack=FileEntry(url="crack.zip", size=50, md5="c"),
        )
        assert pe.total_size == 150

    def test_total_size_empty(self):
        pe = PatchEntry(version_from="1.0", version_to="2.0")
        assert pe.total_size == 0


# -- Manifest ------------------------------------------------------------------


class TestManifest:
    def test_patch_pending_true(self):
        m = Manifest(latest="1.0", game_latest="1.1")
        assert m.patch_pending is True

    def test_patch_pending_false_same_version(self):
        m = Manifest(latest="1.0", game_latest="1.0")
        assert m.patch_pending is False

    def test_patch_pending_false_no_game_latest(self):
        m = Manifest(latest="1.0")
        assert m.patch_pending is False

    def test_all_versions(self):
        m = Manifest(
            latest="3.0",
            patches=[
                PatchEntry(version_from="1.0", version_to="2.0"),
                PatchEntry(version_from="2.0", version_to="3.0"),
            ],
        )
        assert m.all_versions == {"1.0", "2.0", "3.0"}

    def test_get_patch_found(self):
        pe = PatchEntry(version_from="1.0", version_to="2.0")
        m = Manifest(latest="2.0", patches=[pe])
        assert m.get_patch("1.0", "2.0") is pe

    def test_get_patch_not_found(self):
        m = Manifest(latest="2.0", patches=[])
        assert m.get_patch("1.0", "2.0") is None


# -- parse_manifest ------------------------------------------------------------


class TestParseManifest:
    def test_minimal_manifest(self):
        m = parse_manifest({"latest": "1.0"})
        assert m.latest == "1.0"
        assert m.patches == []
        assert m.dlc_downloads == {}
        assert m.language_downloads == {}

    def test_empty_dict_returns_defaults(self):
        m = parse_manifest({})
        assert m.latest == ""
        assert m.patches == []

    def test_non_dict_raises(self):
        with pytest.raises(ManifestError, match="must be a JSON object"):
            parse_manifest("not a dict")

    def test_non_string_latest_raises(self):
        with pytest.raises(ManifestError, match="'latest' must be a string"):
            parse_manifest({"latest": 123})

    def test_non_list_patches_raises(self):
        with pytest.raises(ManifestError, match="'patches' must be a list"):
            parse_manifest({"latest": "1.0", "patches": "bad"})

    def test_invalid_patch_entry_raises(self):
        with pytest.raises(ManifestError, match="Invalid patch entry at index 0"):
            parse_manifest({"latest": "1.0", "patches": [{"bad": "data"}]})

    def test_full_patch_entry(self):
        data = {
            "latest": "2.0",
            "patches": [
                {
                    "from": "1.0",
                    "to": "2.0",
                    "files": [{"url": "https://cdn/patch.zip", "size": 1000, "md5": "abc123"}],
                    "crack": {"url": "https://cdn/crack.zip", "size": 50, "md5": "def456"},
                }
            ],
        }
        m = parse_manifest(data)
        assert len(m.patches) == 1
        assert m.patches[0].version_from == "1.0"
        assert m.patches[0].version_to == "2.0"
        assert m.patches[0].total_size == 1050
        assert m.patches[0].crack.filename == "crack.zip"

    def test_dlc_downloads(self):
        data = {
            "latest": "1.0",
            "dlc_downloads": {
                "EP01": {"url": "https://cdn/EP01.zip", "size": 500, "md5": "aaa"},
            },
        }
        m = parse_manifest(data)
        assert "EP01" in m.dlc_downloads
        assert m.dlc_downloads["EP01"].size == 500

    def test_language_downloads(self):
        data = {
            "latest": "1.0",
            "language_downloads": {
                "da_DK": {"url": "https://cdn/da_DK.zip", "size": 200, "md5": "bbb"},
            },
        }
        m = parse_manifest(data)
        assert "da_DK" in m.language_downloads
        assert m.language_downloads["da_DK"].locale_code == "da_DK"

    def test_greenluma_entries(self):
        data = {
            "latest": "1.0",
            "greenluma": {
                "12345": {"key": "AABBCC", "dlc_id": "EP01", "manifest_id": "999"},
            },
        }
        m = parse_manifest(data)
        assert "12345" in m.greenluma
        assert m.greenluma["12345"].key == "AABBCC"
        assert m.greenluma["12345"].dlc_id == "EP01"

    def test_source_url_stored(self):
        m = parse_manifest({"latest": "1.0"}, source_url="https://cdn/manifest.json")
        assert m.manifest_url == "https://cdn/manifest.json"

    def test_fingerprints(self):
        data = {
            "latest": "1.0",
            "fingerprints": {
                "1.0.0": {"file1.exe": "AABB", "file2.dll": "CCDD"},
            },
        }
        m = parse_manifest(data)
        assert m.fingerprints["1.0.0"]["file1.exe"] == "AABB"

    def test_archived_versions(self):
        data = {
            "latest": "1.0",
            "versions": {
                "1.0": {"manifest_url": "https://cdn/v1.json", "date": "2024-01-01"},
            },
        }
        m = parse_manifest(data)
        assert "1.0" in m.archived_versions
        assert m.archived_versions["1.0"].manifest_url == "https://cdn/v1.json"


# -- DLCDownloadEntry / LanguageDownloadEntry ----------------------------------


class TestDownloadEntries:
    def test_dlc_to_file_entry(self):
        de = DLCDownloadEntry(dlc_id="EP01", url="https://cdn/EP01.zip", size=100, md5="abc")
        fe = de.to_file_entry()
        assert fe.url == "https://cdn/EP01.zip"
        assert fe.size == 100
        assert fe.filename == "EP01.zip"

    def test_language_to_file_entry(self):
        le = LanguageDownloadEntry(
            locale_code="da_DK", url="https://cdn/da_DK.zip", size=50, md5="def"
        )
        fe = le.to_file_entry()
        assert fe.url == "https://cdn/da_DK.zip"
        assert fe.filename == "da_DK.zip"
