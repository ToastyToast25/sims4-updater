"""Tests for config.vdf parsing and depot key management."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sims4_updater.greenluma.config_vdf import (
    _extract_depot_blocks,
    _extract_key_from_block,
    _find_depots_section,
    _validate_braces,
    add_depot_keys,
    read_depot_keys,
    verify_keys,
)

# A realistic minimal config.vdf snippet
SAMPLE_VDF = """\
"InstallConfigStore"
{
\t"Software"
\t{
\t\t"Valve"
\t\t{
\t\t\t"Steam"
\t\t\t{
\t\t\t\t"depots"
\t\t\t\t{
\t\t\t\t\t"1222671"
\t\t\t\t\t{
\t\t\t\t\t\t"DecryptionKey"\t\t"AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011"
\t\t\t\t\t}
\t\t\t\t\t"1222672"
\t\t\t\t\t{
\t\t\t\t\t\t"DecryptionKey"\t\t"CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233"
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t}
}
"""

# VDF with nested EncryptedManifests block
NESTED_VDF = """\
"InstallConfigStore"
{
\t"Software"
\t{
\t\t"depots"
\t\t{
\t\t\t"12345"
\t\t\t{
\t\t\t\t"DecryptionKey"\t\t"AA11BB22CC33DD44AA11BB22CC33DD44AA11BB22CC33DD44AA11BB22CC33DD44"
\t\t\t\t"EncryptedManifests"
\t\t\t\t{
\t\t\t\t\t"0"
\t\t\t\t\t{
\t\t\t\t\t\t"encrypted_gid_2"\t\t"someval"
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t}
}
"""


class TestValidateBraces:
    def test_balanced(self):
        assert _validate_braces('{"a": {"b": 1}}') is True

    def test_empty(self):
        assert _validate_braces("") is True

    def test_no_braces(self):
        assert _validate_braces("hello world") is True

    def test_unbalanced_open(self):
        assert _validate_braces("{unclosed") is False

    def test_unbalanced_close(self):
        assert _validate_braces("}extra") is False

    def test_complex_balanced(self):
        assert _validate_braces(SAMPLE_VDF) is True


class TestFindDepotsSection:
    def test_finds_section(self):
        start, end = _find_depots_section(SAMPLE_VDF)
        assert SAMPLE_VDF[start] == "{"
        assert SAMPLE_VDF[end] == "}"
        section = SAMPLE_VDF[start : end + 1]
        assert "1222671" in section
        assert "1222672" in section

    def test_no_depots_raises(self):
        with pytest.raises(ValueError, match='No "depots" section'):
            _find_depots_section('{"some_other_key": {}}')

    def test_unbalanced_raises(self):
        with pytest.raises(ValueError, match="Unbalanced braces"):
            _find_depots_section('"depots" { unclosed')


class TestExtractDepotBlocks:
    def test_extracts_two_depots(self):
        blocks = _extract_depot_blocks(SAMPLE_VDF)
        assert "1222671" in blocks
        assert "1222672" in blocks

    def test_block_text_contains_key(self):
        blocks = _extract_depot_blocks(SAMPLE_VDF)
        block_text, _, _ = blocks["1222671"]
        assert "AABB0011" in block_text

    def test_nested_blocks(self):
        blocks = _extract_depot_blocks(NESTED_VDF)
        assert "12345" in blocks
        block_text, _, _ = blocks["12345"]
        assert "EncryptedManifests" in block_text
        assert "DecryptionKey" in block_text

    def test_no_depots_section(self):
        blocks = _extract_depot_blocks('{"no_depots": {}}')
        assert blocks == {}


class TestExtractKeyFromBlock:
    def test_extracts_key(self):
        block = '"12345"\n{\n\t"DecryptionKey"\t\t"AABB1122"\n}'
        assert _extract_key_from_block(block) == "AABB1122"

    def test_no_key(self):
        block = '"12345"\n{\n\t"SomeOther"\t\t"value"\n}'
        assert _extract_key_from_block(block) is None

    def test_empty_block(self):
        assert _extract_key_from_block("") is None


class TestReadDepotKeys:
    def test_reads_keys(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")
        state = read_depot_keys(vdf_file)
        assert state.total_keys == 2
        assert "1222671" in state.keys
        assert state.keys["1222671"].startswith("AABB0011")

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_depot_keys(tmp_path / "missing.vdf")

    def test_empty_file(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="config.vdf is empty"):
            read_depot_keys(vdf_file)

    def test_nested_vdf(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(NESTED_VDF, encoding="utf-8")
        state = read_depot_keys(vdf_file)
        assert state.total_keys == 1
        assert "12345" in state.keys


class TestAddDepotKeys:
    def test_inserts_new_key(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")

        with patch("sims4_updater.greenluma.steam.is_steam_running", return_value=False):
            added, updated = add_depot_keys(vdf_file, {"9999": "FF" * 32}, auto_backup=False)

        assert added == 1
        assert updated == 0
        state = read_depot_keys(vdf_file)
        assert "9999" in state.keys
        assert state.keys["9999"] == "FF" * 32

    def test_skips_existing_same_key(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")
        existing_key = "AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011"

        with patch("sims4_updater.greenluma.steam.is_steam_running", return_value=False):
            added, updated = add_depot_keys(vdf_file, {"1222671": existing_key}, auto_backup=False)

        assert added == 0
        assert updated == 0

    def test_updates_different_key(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")

        with patch("sims4_updater.greenluma.steam.is_steam_running", return_value=False):
            added, updated = add_depot_keys(vdf_file, {"1222671": "11" * 32}, auto_backup=False)

        assert added == 0
        assert updated == 1
        state = read_depot_keys(vdf_file)
        assert state.keys["1222671"] == "11" * 32

    def test_raises_when_steam_running(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")

        with (
            patch("sims4_updater.greenluma.steam.is_steam_running", return_value=True),
            pytest.raises(RuntimeError, match="Steam is running"),
        ):
            add_depot_keys(vdf_file, {"9999": "FF" * 32})


class TestVerifyKeys:
    def test_all_matching(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")
        result = verify_keys(
            vdf_file,
            {
                "1222671": "AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011AABB0011",
                "1222672": "CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233CCDD2233",
            },
        )
        assert result["matching"] == 2
        assert result["mismatched"] == []
        assert result["missing"] == []

    def test_missing_key(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")
        result = verify_keys(vdf_file, {"9999": "FF" * 32})
        assert result["missing"] == ["9999"]

    def test_case_insensitive_match(self, tmp_path):
        vdf_file = tmp_path / "config.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")
        result = verify_keys(
            vdf_file,
            {"1222671": "aabb0011aabb0011aabb0011aabb0011aabb0011aabb0011aabb0011aabb0011"},
        )
        assert result["matching"] == 1
