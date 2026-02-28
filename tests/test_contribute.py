"""Tests for core.contribute — DLC contribution scanner and submission."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

from sims4_updater.core.contribute import (
    DLCContribution,
    FileMetadata,
    _md5_file,
    find_missing_dlcs,
    scan_and_submit,
    scan_dlc_folder,
    submit_contribution,
)

# ── FileMetadata / DLCContribution ────────────────────────────────


class TestFileMetadata:
    def test_fields(self):
        fm = FileMetadata(name="test.package", size=1024, md5="abc123")
        assert fm.name == "test.package"
        assert fm.size == 1024
        assert fm.md5 == "abc123"


class TestDLCContribution:
    def test_total_size_empty(self):
        c = DLCContribution(dlc_id="EP01", dlc_name="Get to Work")
        assert c.total_size == 0

    def test_total_size(self):
        c = DLCContribution(
            dlc_id="EP01",
            dlc_name="Get to Work",
            files=[
                FileMetadata(name="a.pkg", size=100, md5="a"),
                FileMetadata(name="b.pkg", size=200, md5="b"),
            ],
        )
        assert c.total_size == 300

    def test_to_dict(self):
        c = DLCContribution(
            dlc_id="GP05",
            dlc_name="Parenthood",
            files=[FileMetadata(name="f.pkg", size=50, md5="abc")],
            app_version="2.10.0",
        )
        d = c.to_dict()
        assert d["dlc_id"] == "GP05"
        assert d["dlc_name"] == "Parenthood"
        assert d["app_version"] == "2.10.0"
        assert len(d["files"]) == 1
        assert d["files"][0]["name"] == "f.pkg"


# ── _md5_file ─────────────────────────────────────────────────────


class TestMd5File:
    def test_known_content(self, tmp_path):
        p = tmp_path / "data.bin"
        p.write_bytes(b"hello world")
        expected = hashlib.md5(b"hello world").hexdigest()
        assert _md5_file(p) == expected

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty"
        p.write_bytes(b"")
        assert _md5_file(p) == hashlib.md5(b"").hexdigest()


# ── scan_dlc_folder ───────────────────────────────────────────────


class TestScanDlcFolder:
    def test_nonexistent_dir(self, tmp_path):
        result = scan_dlc_folder(tmp_path / "nope")
        assert result == []

    def test_empty_dir(self, tmp_path):
        dlc = tmp_path / "EP01"
        dlc.mkdir()
        result = scan_dlc_folder(dlc)
        assert result == []

    def test_scans_files(self, tmp_path):
        dlc = tmp_path / "EP01"
        dlc.mkdir()
        (dlc / "a.package").write_bytes(b"aaa")
        (dlc / "b.package").write_bytes(b"bbb")

        result = scan_dlc_folder(dlc)

        assert len(result) == 2
        names = {f.name for f in result}
        assert "a.package" in names
        assert "b.package" in names

    def test_scans_nested_files(self, tmp_path):
        dlc = tmp_path / "EP01"
        sub = dlc / "Strings"
        sub.mkdir(parents=True)
        (sub / "en.stbl").write_bytes(b"string data")

        result = scan_dlc_folder(dlc)

        assert len(result) == 1
        assert result[0].name == "Strings/en.stbl"  # posix relative

    def test_md5_correct(self, tmp_path):
        dlc = tmp_path / "EP01"
        dlc.mkdir()
        content = b"test content"
        (dlc / "file.pkg").write_bytes(content)

        result = scan_dlc_folder(dlc)

        expected = hashlib.md5(content).hexdigest()
        assert result[0].md5 == expected

    def test_size_correct(self, tmp_path):
        dlc = tmp_path / "EP01"
        dlc.mkdir()
        content = b"x" * 42
        (dlc / "file.pkg").write_bytes(content)

        result = scan_dlc_folder(dlc)

        assert result[0].size == 42

    def test_progress_callback(self, tmp_path):
        dlc = tmp_path / "EP01"
        dlc.mkdir()
        (dlc / "a.pkg").write_bytes(b"a")
        (dlc / "b.pkg").write_bytes(b"b")

        calls = []

        def progress(current, total, name):
            calls.append((current, total, name))

        scan_dlc_folder(dlc, progress=progress)

        # 2 file progress calls + 1 final call
        assert len(calls) == 3
        assert calls[-1] == (2, 2, "")


# ── find_missing_dlcs ─────────────────────────────────────────────


class TestFindMissingDlcs:
    def _make_dlc_info(self, dlc_id, name="Test DLC"):
        mock = MagicMock()
        mock.id = dlc_id
        mock.name_en = name
        return mock

    def test_no_dlcs_installed(self, tmp_path):
        catalog = [self._make_dlc_info("EP01")]
        result = find_missing_dlcs(tmp_path, manifest_dlc_ids=set(), catalog_dlcs=catalog)
        assert result == []

    def test_dlc_in_manifest_not_missing(self, tmp_path):
        dlc_dir = tmp_path / "EP01"
        dlc_dir.mkdir()
        (dlc_dir / "SimulationFullBuild0.package").write_bytes(b"data")

        catalog = [self._make_dlc_info("EP01")]
        result = find_missing_dlcs(tmp_path, manifest_dlc_ids={"EP01"}, catalog_dlcs=catalog)
        assert result == []

    def test_dlc_missing_from_manifest(self, tmp_path):
        dlc_dir = tmp_path / "EP01"
        dlc_dir.mkdir()
        (dlc_dir / "SimulationFullBuild0.package").write_bytes(b"data")

        catalog = [self._make_dlc_info("EP01", "Get to Work")]
        result = find_missing_dlcs(tmp_path, manifest_dlc_ids=set(), catalog_dlcs=catalog)
        assert result == [("EP01", "Get to Work")]

    def test_dlc_without_main_package_skipped(self, tmp_path):
        dlc_dir = tmp_path / "EP01"
        dlc_dir.mkdir()
        (dlc_dir / "other.txt").write_bytes(b"not a package")

        catalog = [self._make_dlc_info("EP01")]
        result = find_missing_dlcs(tmp_path, manifest_dlc_ids=set(), catalog_dlcs=catalog)
        assert result == []


# ── submit_contribution ───────────────────────────────────────────


class TestSubmitContribution:
    def test_no_url_configured(self):
        c = DLCContribution(dlc_id="EP01", dlc_name="Test")
        with patch("sims4_updater.core.contribute.CONTRIBUTE_URL", ""):
            result = submit_contribution(c)
        assert result["status"] == "error"
        assert "not configured" in result["message"]

    def test_non_https_rejected(self):
        c = DLCContribution(dlc_id="EP01", dlc_name="Test")
        result = submit_contribution(c, url="http://insecure.com/contribute")
        assert result["status"] == "error"
        assert "HTTPS" in result["message"]

    def test_url_from_manifest(self):
        c = DLCContribution(dlc_id="EP01", dlc_name="Test")
        manifest = MagicMock()
        manifest.contribute_url = "https://api.example.com/contribute"

        with (
            patch("sims4_updater.core.contribute.requests.post") as mock_post,
            patch("sims4_updater.core.identity.get_headers", return_value={}),
        ):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"status": "ok"}
            mock_post.return_value = mock_resp

            result = submit_contribution(c, manifest=manifest)

        assert result["status"] == "ok"
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url == "https://api.example.com/contribute"

    def test_rate_limited(self):
        c = DLCContribution(dlc_id="EP01", dlc_name="Test")

        with (
            patch("sims4_updater.core.contribute.requests.post") as mock_post,
            patch("sims4_updater.core.identity.get_headers", return_value={}),
        ):
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_post.return_value = mock_resp

            result = submit_contribution(c, url="https://api.example.com/contribute")

        assert result["status"] == "rate_limited"

    def test_server_error(self):
        c = DLCContribution(dlc_id="EP01", dlc_name="Test")

        with (
            patch("sims4_updater.core.contribute.requests.post") as mock_post,
            patch("sims4_updater.core.identity.get_headers", return_value={}),
        ):
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_post.return_value = mock_resp

            result = submit_contribution(c, url="https://api.example.com/contribute")

        assert result["status"] == "error"
        assert "500" in result["message"]


# ── scan_and_submit ───────────────────────────────────────────────


class TestScanAndSubmit:
    def test_missing_dir(self, tmp_path):
        result = scan_and_submit(tmp_path, "EP01", "Get to Work")
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_empty_dir(self, tmp_path):
        (tmp_path / "EP01").mkdir()
        result = scan_and_submit(tmp_path, "EP01", "Get to Work")
        assert result["status"] == "error"
        assert "No files" in result["message"]

    def test_successful_scan_and_submit(self, tmp_path):
        dlc_dir = tmp_path / "EP01"
        dlc_dir.mkdir()
        (dlc_dir / "file.pkg").write_bytes(b"package data")

        with (
            patch("sims4_updater.core.contribute.submit_contribution") as mock_submit,
        ):
            mock_submit.return_value = {"status": "ok"}
            result = scan_and_submit(
                tmp_path,
                "EP01",
                "Get to Work",
                url="https://api.example.com/contribute",
            )

        assert result["status"] == "ok"
        mock_submit.assert_called_once()
        contribution = mock_submit.call_args[0][0]
        assert contribution.dlc_id == "EP01"
        assert len(contribution.files) == 1
