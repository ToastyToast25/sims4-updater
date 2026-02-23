"""Tests for GreenLuma LUA manifest parser."""

from __future__ import annotations

import pytest

from sims4_updater.greenluma.lua_parser import (
    count_summary,
    parse_lua_string,
)

SAMPLE_LUA = """\
-- GreenLuma manifest for The Sims 4
addappid(1222670)
addappid(1222671, 1, "AABBCCDD00112233AABBCCDD00112233AABBCCDD00112233AABBCCDD00112233")
addappid(1222672, 1, "1122334455667788112233445566778811223344556677881122334455667788")
addappid(1222673)
setManifestid(1222671, "9876543210123456789")
setManifestid(1222672, "1234567890987654321")
"""


class TestParseLuaString:
    def test_base_app_id(self):
        result = parse_lua_string(SAMPLE_LUA)
        assert result.app_id == "1222670"

    def test_all_app_ids(self):
        result = parse_lua_string(SAMPLE_LUA)
        # The nokey regex only matches addappid(ID) and addappid(ID, FLAGS),
        # not addappid(ID, FLAGS, "KEY") — so keyed entries aren't in all_app_ids
        assert result.all_app_ids == ["1222670", "1222673"]

    def test_entries_with_keys(self):
        result = parse_lua_string(SAMPLE_LUA)
        assert "1222671" in result.entries
        assert result.entries["1222671"].decryption_key == (
            "AABBCCDD00112233AABBCCDD00112233AABBCCDD00112233AABBCCDD00112233"
        )

    def test_manifest_ids_associated(self):
        result = parse_lua_string(SAMPLE_LUA)
        assert result.entries["1222671"].manifest_id == "9876543210123456789"
        assert result.entries["1222672"].manifest_id == "1234567890987654321"

    def test_entry_without_key_not_in_entries(self):
        result = parse_lua_string(SAMPLE_LUA)
        # 1222670 and 1222673 have no key, so not in entries unless they have a manifest
        assert "1222670" not in result.entries
        assert "1222673" not in result.entries

    def test_keys_count(self):
        result = parse_lua_string(SAMPLE_LUA)
        assert result.keys_count == 2

    def test_manifests_count(self):
        result = parse_lua_string(SAMPLE_LUA)
        assert result.manifests_count == 2

    def test_empty_content_raises(self):
        with pytest.raises(ValueError, match="LUA content is empty"):
            parse_lua_string("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="LUA content is empty"):
            parse_lua_string("   \n\t  ")

    def test_no_addappid_raises(self):
        with pytest.raises(ValueError, match="No addappid"):
            parse_lua_string("-- just a comment\nlocal x = 1\n")

    def test_minimal_addappid(self):
        result = parse_lua_string("addappid(12345)")
        assert result.app_id == "12345"
        assert len(result.all_app_ids) == 1
        assert result.entries == {}

    def test_manifest_without_key_creates_entry(self):
        content = 'addappid(100)\naddappid(200)\nsetManifestid(200, "999")'
        result = parse_lua_string(content)
        assert "200" in result.entries
        assert result.entries["200"].manifest_id == "999"
        assert result.entries["200"].decryption_key == ""

    def test_duplicate_appid_deduplicated(self):
        content = "addappid(100)\naddappid(100)\naddappid(200)"
        result = parse_lua_string(content)
        assert result.all_app_ids == ["100", "200"]


class TestCountSummary:
    def test_counts(self):
        result = parse_lua_string(SAMPLE_LUA)
        summary = count_summary(result)
        assert summary["total_app_ids"] == 2  # only nokey matches go into all_app_ids
        assert summary["entries_with_keys"] == 2
        assert summary["entries_with_manifests"] == 2

    def test_empty_entries(self):
        result = parse_lua_string("addappid(100)")
        summary = count_summary(result)
        assert summary["total_app_ids"] == 1
        assert summary["entries_with_keys"] == 0
        assert summary["entries_with_manifests"] == 0
