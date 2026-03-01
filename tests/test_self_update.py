"""Tests for core.self_update — self-update check, download, and apply."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from sims4_updater.core.self_update import (
    AppUpdateInfo,
    SelfUpdateError,
    _version_newer,
    check_for_app_update,
    download_app_update,
)

# ── Version comparison ──────────────────────────────────────────


class TestVersionNewer:
    def test_newer(self):
        assert _version_newer("2.1.0", "2.0.0") is True

    def test_same(self):
        assert _version_newer("2.0.0", "2.0.0") is False

    def test_older(self):
        assert _version_newer("1.9.0", "2.0.0") is False

    def test_minor_bump(self):
        assert _version_newer("2.1.0", "2.0.9") is True

    def test_patch_bump(self):
        assert _version_newer("2.0.1", "2.0.0") is True

    def test_invalid_falls_back(self):
        assert _version_newer("abc", "def") is True  # not equal


# ── check_for_app_update ────────────────────────────────────────


class TestCheckForAppUpdate:
    def _make_release(self, tag="v2.1.0", exe_url=None, sha_content=None):
        """Build a fake GitHub API response."""
        assets = []
        if exe_url is not None:
            assets.append(
                {
                    "name": "Sims4Updater.exe",
                    "browser_download_url": exe_url,
                    "size": 15_000_000,
                }
            )
        if sha_content is not None:
            assets.append(
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://github.com/releases/SHA256SUMS.txt",
                    "size": 200,
                }
            )
        return {"tag_name": tag, "assets": assets, "body": "Release notes"}

    def test_basic_check(self):
        release = self._make_release(exe_url="https://github.com/releases/Sims4Updater.exe")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = release

        with patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp):
            info = check_for_app_update()

        assert info.latest_version == "2.1.0"
        assert info.download_url == "https://github.com/releases/Sims4Updater.exe"
        assert info.download_size == 15_000_000

    def test_sha256_parsed_from_release(self):
        """SHA256SUMS.txt asset should be fetched and parsed."""
        sha_content = (
            "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
            "  Sims4Updater.exe\n"
            "1111111111111111111111111111111111111111111111111111111111111111"
            "  CDNManager.exe\n"
        )
        release = self._make_release(
            exe_url="https://github.com/releases/Sims4Updater.exe",
            sha_content=sha_content,
        )
        mock_api = MagicMock()
        mock_api.status_code = 200
        mock_api.json.return_value = release

        mock_sha = MagicMock()
        mock_sha.status_code = 200
        mock_sha.text = sha_content

        def _get(url, **kwargs):
            if "SHA256SUMS" in url:
                return mock_sha
            return mock_api

        with patch("sims4_updater.core.self_update.requests.get", side_effect=_get):
            info = check_for_app_update()

        assert info.sha256_expected == (
            "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        )

    def test_sha256_missing_asset(self):
        """If no SHA256SUMS.txt, sha256_expected should be empty."""
        release = self._make_release(exe_url="https://github.com/releases/Sims4Updater.exe")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = release

        with patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp):
            info = check_for_app_update()

        assert info.sha256_expected == ""

    def test_404_no_releases(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp):
            info = check_for_app_update()

        assert info.update_available is False

    def test_invalid_version_format(self):
        release = {"tag_name": "v2.0.0-beta; rm -rf /", "assets": [], "body": ""}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = release

        with (
            patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp),
            pytest.raises(SelfUpdateError, match="Invalid version format"),
        ):
            check_for_app_update()

    def test_rejects_non_github_download_url(self):
        """Download URLs not on github.com should be ignored."""
        release = self._make_release(exe_url="https://evil.com/Sims4Updater.exe")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = release

        with patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp):
            info = check_for_app_update()

        assert info.download_url == ""


# ── download_app_update with SHA-256 ────────────────────────────


class TestDownloadAppUpdate:
    def _make_info(self, sha256="", url="https://github.com/releases/dl/Sims4Updater.exe"):
        return AppUpdateInfo(
            current_version="2.0.0",
            latest_version="2.1.0",
            update_available=True,
            download_url=url,
            download_size=10_000_000,
            sha256_expected=sha256,
        )

    def test_sha256_verification_pass(self, tmp_path):
        """Download with correct SHA-256 should succeed."""
        fake_exe = b"MZ" + b"\x00" * 10_000_000
        expected_hash = hashlib.sha256(fake_exe).hexdigest().lower()
        info = self._make_info(sha256=expected_hash)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": str(len(fake_exe))}
        mock_resp.iter_content.return_value = [fake_exe]
        mock_resp.close = MagicMock()

        with (
            patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp),
            patch("sims4_updater.core.self_update.get_app_dir", return_value=tmp_path),
        ):
            result = download_app_update(info)

        assert result.exists()
        assert result.stat().st_size == len(fake_exe)

    def test_sha256_verification_fail(self, tmp_path):
        """Download with wrong SHA-256 should raise and delete the file."""
        fake_exe = b"MZ" + b"\x00" * 10_000_000
        info = self._make_info(sha256="0" * 64)  # Wrong hash

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": str(len(fake_exe))}
        mock_resp.iter_content.return_value = [fake_exe]
        mock_resp.close = MagicMock()

        with (
            patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp),
            patch("sims4_updater.core.self_update.get_app_dir", return_value=tmp_path),
            pytest.raises(SelfUpdateError, match="SHA-256 verification failed"),
        ):
            download_app_update(info)

        # File should be cleaned up
        dl_path = tmp_path / "updates" / "Sims4Updater_v2.1.0.exe"
        assert not dl_path.exists()

    def test_no_sha256_skips_verification(self, tmp_path):
        """Download without SHA-256 should still succeed (size-only check)."""
        fake_exe = b"MZ" + b"\x00" * 10_000_000
        info = self._make_info(sha256="")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": str(len(fake_exe))}
        mock_resp.iter_content.return_value = [fake_exe]
        mock_resp.close = MagicMock()

        with (
            patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp),
            patch("sims4_updater.core.self_update.get_app_dir", return_value=tmp_path),
        ):
            result = download_app_update(info)

        assert result.exists()

    def test_too_small_rejected(self, tmp_path):
        """Files under 5MB should be rejected."""
        fake_exe = b"MZ" + b"\x00" * 1000
        info = self._make_info()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": str(len(fake_exe))}
        mock_resp.iter_content.return_value = [fake_exe]
        mock_resp.close = MagicMock()

        with (
            patch("sims4_updater.core.self_update.requests.get", return_value=mock_resp),
            patch("sims4_updater.core.self_update.get_app_dir", return_value=tmp_path),
            pytest.raises(SelfUpdateError, match="too small"),
        ):
            download_app_update(info)

    def test_no_download_url_rejected(self):
        info = self._make_info(url="")
        with pytest.raises(SelfUpdateError, match="No download URL"):
            download_app_update(info)

    def test_non_https_rejected(self):
        info = self._make_info(url="http://github.com/releases/dl/Sims4Updater.exe")
        with pytest.raises(SelfUpdateError, match="HTTPS"):
            download_app_update(info)


# ── _bat_escape and path validation ─────────────────────────────


class TestBatEscape:
    """Test the batch escaping logic used in apply_app_update."""

    def _bat_escape(self, s: str) -> str:
        """Mirror the _bat_escape inner function."""
        return s.replace('"', "").replace("^", "^^").replace("%", "%%").replace("!", "^!")

    def test_percent(self):
        assert self._bat_escape("C:\\100%done") == "C:\\100%%done"

    def test_caret(self):
        assert self._bat_escape("file^name") == "file^^name"

    def test_exclamation(self):
        assert self._bat_escape("hello!world") == "hello^!world"

    def test_double_quote_stripped(self):
        assert self._bat_escape('file"name') == "filename"

    def test_combined(self):
        result = self._bat_escape('path^with%special!"chars')
        assert result == "path^^with%%special^!chars"

    def test_normal_path_unchanged(self):
        normal = r"C:\Users\Admin\AppData\Local\ToastyToast25"
        assert self._bat_escape(normal) == normal

    def test_parentheses_path(self):
        """Paths like C:\\Program Files (x86) should pass through."""
        path = r"C:\Program Files (x86)\Steam"
        assert self._bat_escape(path) == path


class TestPathValidation:
    """Test the _SAFE_PATH_RE pattern used in apply_app_update."""

    def setup_method(self):
        from sims4_updater.core.self_update import _SAFE_PATH_RE

        self._re = _SAFE_PATH_RE

    def test_normal_windows_path(self):
        assert self._re.match(r"C:\Users\Admin\AppData\Local\app\update.exe")

    def test_path_with_spaces(self):
        assert self._re.match(r"C:\Program Files (x86)\Steam\steamapps")

    def test_rejects_single_quote(self):
        """Single quotes could escape PowerShell quoting."""
        assert self._re.match("C:\\Users\\Admin's Folder") is None

    def test_rejects_semicolon(self):
        assert self._re.match("C:\\path;evil") is None

    def test_rejects_ampersand(self):
        assert self._re.match("C:\\path&evil") is None

    def test_rejects_pipe(self):
        assert self._re.match("C:\\path|evil") is None

    def test_rejects_backtick(self):
        assert self._re.match("C:\\path`evil") is None

    def test_rejects_dollar(self):
        assert self._re.match("C:\\path$evil") is None
