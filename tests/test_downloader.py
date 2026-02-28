"""Tests for patch.downloader — download, resume, MD5 verify, cancel, ban check."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sims4_updater.core.exceptions import (
    AccessRequiredError,
    BannedError,
    DownloadError,
    IntegrityError,
)
from sims4_updater.patch.downloader import (
    Downloader,
    DownloadResult,
    _check_ban_response,
    _compute_md5,
    _verify_md5,
)
from sims4_updater.patch.manifest import FileEntry

# ── Helpers ──────────────────────────────────────────────────────


def _make_entry(
    url="https://cdn.example.com/file.zip",
    size=1000,
    md5="",
    filename="file.zip",
) -> FileEntry:
    return FileEntry(url=url, size=size, md5=md5, filename=filename)


def _file_md5(path: Path) -> str:
    m = hashlib.md5()
    with open(path, "rb") as f:
        m.update(f.read())
    return m.hexdigest().upper()


# ── MD5 helpers ──────────────────────────────────────────────────


class TestComputeMd5:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty"
        p.write_bytes(b"")
        assert _compute_md5(p) == hashlib.md5(b"").hexdigest().upper()

    def test_known_content(self, tmp_path):
        p = tmp_path / "hello"
        p.write_bytes(b"hello world")
        expected = hashlib.md5(b"hello world").hexdigest().upper()
        assert _compute_md5(p) == expected


class TestVerifyMd5:
    def test_match(self, tmp_path):
        p = tmp_path / "data"
        p.write_bytes(b"test data")
        md5 = hashlib.md5(b"test data").hexdigest()
        assert _verify_md5(p, md5) is True

    def test_mismatch(self, tmp_path):
        p = tmp_path / "data"
        p.write_bytes(b"actual data")
        assert _verify_md5(p, "0" * 32) is False

    def test_case_insensitive(self, tmp_path):
        p = tmp_path / "data"
        p.write_bytes(b"data")
        md5 = hashlib.md5(b"data").hexdigest().upper()
        assert _verify_md5(p, md5.lower()) is True


# ── Ban response check ───────────────────────────────────────────


class TestCheckBanResponse:
    def test_200_passes(self):
        resp = MagicMock()
        resp.status_code = 200
        _check_ban_response(resp)  # should not raise

    def test_403_banned(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {
            "error": "banned",
            "reason": "Abuse",
            "ban_type": "machine",
            "expires_at": "2026-04-01T00:00:00Z",
        }
        with pytest.raises(BannedError) as exc_info:
            _check_ban_response(resp)
        assert exc_info.value.reason == "Abuse"
        assert exc_info.value.ban_type == "machine"

    def test_403_access_required(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {
            "error": "access_required",
            "cdn_name": "Private CDN",
            "request_url": "/access/request",
        }
        with pytest.raises(AccessRequiredError) as exc_info:
            _check_ban_response(resp)
        assert exc_info.value.cdn_name == "Private CDN"

    def test_403_unknown_json(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {"error": "unknown_error"}
        _check_ban_response(resp)  # should not raise

    def test_403_invalid_json(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.json.side_effect = ValueError("no json")
        _check_ban_response(resp)  # should not raise

    def test_401_banned(self):
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {
            "error": "banned",
            "reason": "Expired",
        }
        with pytest.raises(BannedError):
            _check_ban_response(resp)


# ── Downloader ───────────────────────────────────────────────────


class TestDownloader:
    @pytest.fixture()
    def dl(self, tmp_path):
        """Create a Downloader with a mocked session."""
        d = Downloader(tmp_path / "downloads")
        # Inject mock session directly — `session` is a @property,
        # so we set the private `_session` to avoid lazy creation.
        mock_session = MagicMock()
        d._session = mock_session
        return d

    def _mock_response(self, content: bytes, status=200, headers=None):
        resp = MagicMock()
        resp.status_code = status
        resp.headers = headers or {"Content-Length": str(len(content))}
        resp.iter_content.return_value = [content]
        resp.close = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError("not json")
        return resp

    def test_basic_download(self, dl):
        content = b"file content here"
        md5 = hashlib.md5(content).hexdigest()
        entry = _make_entry(md5=md5, size=len(content))

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        result = dl.download_file(entry)

        assert isinstance(result, DownloadResult)
        assert result.path.exists()
        assert result.path.read_bytes() == content
        assert result.verified is True

    def test_md5_mismatch_raises(self, dl):
        content = b"file content"
        entry = _make_entry(md5="0" * 32, size=len(content))

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        with pytest.raises(IntegrityError, match="MD5 mismatch"):
            dl.download_file(entry)

    def test_no_md5_still_downloads(self, dl):
        content = b"no hash file"
        entry = _make_entry(md5="", size=len(content))

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        result = dl.download_file(entry)

        assert result.verified is False
        assert result.path.exists()

    def test_skip_download_when_already_verified(self, dl):
        """If final file exists and MD5 matches, skip download."""
        content = b"already downloaded"
        md5 = hashlib.md5(content).hexdigest()
        entry = _make_entry(md5=md5, size=len(content))

        # Pre-create the file
        final = dl.download_dir / "file.zip"
        final.write_bytes(content)

        result = dl.download_file(entry)

        # Session.get should NOT be called (skipped)
        dl._session.get.assert_not_called()
        assert result.verified is True
        assert result.bytes_downloaded == 0

    def test_cancel_before_download(self, dl):
        dl.cancel()
        entry = _make_entry()
        with pytest.raises(DownloadError, match="cancelled"):
            dl.download_file(entry)

    def test_cancel_during_download(self, dl):
        """Cancel event during chunk iteration."""
        entry = _make_entry(size=100)
        cancel = dl._cancel

        def _cancel_on_first_chunk(_):
            cancel.set()
            return iter([b"first chunk"])

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Length": "100"}
        resp.iter_content = _cancel_on_first_chunk
        resp.close = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError()

        dl._session.get.return_value = resp

        with pytest.raises(DownloadError, match="cancelled"):
            dl.download_file(entry)

    def test_path_traversal_sanitized(self, dl):
        """Path traversal in filename is sanitized — '../etc/passwd' → 'passwd'."""
        content = b"sanitized file"
        md5 = hashlib.md5(content).hexdigest()
        entry = _make_entry(filename="../../../etc/passwd", md5=md5, size=len(content))

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        result = dl.download_file(entry)

        # Path should be sanitized to just the filename component
        assert result.path.name == "passwd"
        assert result.path.exists()
        # Must be inside the download_dir
        assert result.path.resolve().is_relative_to(dl.download_dir.resolve())

    def test_empty_filename_derived_from_url(self, dl):
        """Empty filename is derived from URL by FileEntry.__post_init__."""
        content = b"derived name"
        md5 = hashlib.md5(content).hexdigest()
        entry = _make_entry(
            url="https://cdn.example.com/archive.zip",
            filename="",
            md5=md5,
            size=len(content),
        )

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        result = dl.download_file(entry)

        # FileEntry derives filename from URL
        assert result.path.name == "archive.zip"
        assert result.path.exists()

    def test_dot_filename_becomes_download(self, dl):
        """'.' filename is replaced with 'download' by FileEntry.__post_init__."""
        content = b"dot name"
        md5 = hashlib.md5(content).hexdigest()
        entry = _make_entry(filename=".", md5=md5, size=len(content))

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        result = dl.download_file(entry)

        assert result.path.name == "download"
        assert result.path.exists()

    def test_progress_callback(self, dl):
        content = b"x" * 1000
        md5 = hashlib.md5(content).hexdigest()
        entry = _make_entry(md5=md5, size=len(content))

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        progress_calls = []

        def track_progress(downloaded, total, filename):
            progress_calls.append((downloaded, total, filename))

        dl.download_file(entry, progress=track_progress)

        assert len(progress_calls) > 0
        # Last progress should be total == downloaded
        last = progress_calls[-1]
        assert last[0] == last[1]

    def test_subdir(self, dl):
        content = b"subdir file"
        md5 = hashlib.md5(content).hexdigest()
        entry = _make_entry(md5=md5, size=len(content))

        resp = self._mock_response(content)
        dl._session.get.return_value = resp

        result = dl.download_file(entry, subdir="patches")

        assert "patches" in str(result.path)
        assert result.path.exists()

    def test_context_manager(self, tmp_path):
        with Downloader(tmp_path / "dl") as dl:
            assert dl.download_dir.exists()

    def test_download_files_sequential(self, dl):
        """download_files should handle multiple entries."""
        entries = []
        for i in range(3):
            content = f"file_{i}".encode()
            md5 = hashlib.md5(content).hexdigest()
            entries.append(
                _make_entry(
                    url=f"https://cdn.example.com/file_{i}.zip",
                    md5=md5,
                    size=len(content),
                    filename=f"file_{i}.zip",
                )
            )

        call_count = 0

        def mock_get(url, **kwargs):
            nonlocal call_count
            content = f"file_{call_count}".encode()
            call_count += 1
            resp = self._mock_response(content)
            return resp

        dl._session.get.side_effect = mock_get

        results = dl.download_files(entries)

        assert len(results) == 3
        for r in results:
            assert r.path.exists()

    def test_banned_response_raises(self, dl):
        entry = _make_entry()

        resp = MagicMock()
        resp.status_code = 403
        resp.headers = {}
        resp.json.return_value = {
            "error": "banned",
            "reason": "Abuse",
            "ban_type": "ip",
        }
        resp.close = MagicMock()
        resp.raise_for_status = MagicMock()

        dl._session.get.return_value = resp

        with pytest.raises(BannedError):
            dl.download_file(entry)


# ── Resume support ───────────────────────────────────────────────


class TestResume:
    def test_resume_sends_range_header(self, tmp_path):
        dl = Downloader(tmp_path / "downloads")
        mock_session = MagicMock()
        dl._session = mock_session
        entry = _make_entry(size=100)

        # Create a partial file
        partial = dl.download_dir / "file.zip.partial"
        partial.write_bytes(b"x" * 50)

        resp = MagicMock()
        resp.status_code = 206
        resp.headers = {
            "Content-Range": "bytes 50-99/100",
            "Content-Length": "50",
        }
        resp.iter_content.return_value = [b"y" * 50]
        resp.close = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError()

        mock_session.get.return_value = resp

        result = dl.download_file(entry)

        # Should have sent Range header
        call_kwargs = mock_session.get.call_args
        assert "Range" in call_kwargs[1].get("headers", {})
        assert call_kwargs[1]["headers"]["Range"] == "bytes=50-"
        assert result.resumed is True
