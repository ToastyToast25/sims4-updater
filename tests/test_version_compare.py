"""Tests for _version_less_than and UpdateInfo.is_downgrade."""

from __future__ import annotations

from sims4_updater.patch.client import UpdateInfo, _version_less_than


class TestVersionLessThan:
    def test_older_version(self):
        assert _version_less_than("1.0.0", "2.0.0") is True

    def test_newer_version(self):
        assert _version_less_than("2.0.0", "1.0.0") is False

    def test_equal_versions(self):
        assert _version_less_than("1.0.0", "1.0.0") is False

    def test_four_part_versions(self):
        assert _version_less_than("1.121.370.1010", "1.121.372.1020") is True
        assert _version_less_than("1.121.372.1020", "1.121.370.1010") is False

    def test_minor_difference(self):
        assert _version_less_than("1.0.0.0", "1.0.1.0") is True

    def test_invalid_version_returns_false(self):
        assert _version_less_than("abc", "1.0.0") is False
        assert _version_less_than("1.0.0", "abc") is False

    def test_none_returns_false(self):
        assert _version_less_than(None, "1.0.0") is False
        assert _version_less_than("1.0.0", None) is False

    def test_empty_string_returns_false(self):
        assert _version_less_than("", "1.0.0") is False


class TestUpdateInfoIsDowngrade:
    def test_defaults_to_false(self):
        info = UpdateInfo(
            current_version="1.0.0",
            latest_version="2.0.0",
            update_available=True,
        )
        assert info.is_downgrade is False

    def test_can_be_set_true(self):
        info = UpdateInfo(
            current_version="2.0.0",
            latest_version="1.0.0",
            update_available=True,
            is_downgrade=True,
        )
        assert info.is_downgrade is True
