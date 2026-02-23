"""Tests for GreenLuma AppList read/write/modify."""

from __future__ import annotations

from pathlib import Path

import pytest

from sims4_updater.greenluma.applist import (
    APPLIST_LIMIT,
    AppListState,
    _is_applist_file,
    add_ids,
    ordered_ids_from_state,
    read_applist,
    remove_ids,
    write_applist,
)


class TestIsApplistFile:
    def test_valid(self):
        assert _is_applist_file(Path("0.txt")) is True
        assert _is_applist_file(Path("99.txt")) is True
        assert _is_applist_file(Path("123.txt")) is True

    def test_invalid_suffix(self):
        assert _is_applist_file(Path("0.csv")) is False
        assert _is_applist_file(Path("0.ini")) is False

    def test_non_numeric_stem(self):
        assert _is_applist_file(Path("readme.txt")) is False
        assert _is_applist_file(Path("abc.txt")) is False
        assert _is_applist_file(Path("0a.txt")) is False


class TestOrderedIdsFromState:
    def test_sorted_by_numeric_index(self):
        state = AppListState(
            entries={"2.txt": "333", "0.txt": "111", "1.txt": "222"},
            unique_ids={"111", "222", "333"},
            count=3,
            duplicates=[],
        )
        assert ordered_ids_from_state(state) == ["111", "222", "333"]

    def test_deduplicates(self):
        state = AppListState(
            entries={"0.txt": "111", "1.txt": "111", "2.txt": "222"},
            unique_ids={"111", "222"},
            count=3,
            duplicates=[("1.txt", "111")],
        )
        result = ordered_ids_from_state(state)
        assert result == ["111", "222"]

    def test_empty(self):
        state = AppListState(entries={}, unique_ids=set(), count=0, duplicates=[])
        assert ordered_ids_from_state(state) == []


class TestReadApplist:
    def test_reads_files(self, tmp_path):
        (tmp_path / "0.txt").write_text("1222670", encoding="utf-8")
        (tmp_path / "1.txt").write_text("1222671", encoding="utf-8")
        state = read_applist(tmp_path)
        assert state.count == 2
        assert "1222670" in state.unique_ids
        assert "1222671" in state.unique_ids
        assert state.duplicates == []

    def test_detects_duplicates(self, tmp_path):
        (tmp_path / "0.txt").write_text("1111", encoding="utf-8")
        (tmp_path / "1.txt").write_text("1111", encoding="utf-8")
        (tmp_path / "2.txt").write_text("2222", encoding="utf-8")
        state = read_applist(tmp_path)
        assert state.count == 3
        assert len(state.duplicates) == 1
        assert state.duplicates[0] == ("1.txt", "1111")

    def test_skips_non_numeric_content(self, tmp_path):
        (tmp_path / "0.txt").write_text("valid123", encoding="utf-8")
        (tmp_path / "1.txt").write_text("1222670", encoding="utf-8")
        state = read_applist(tmp_path)
        # "valid123" is not purely numeric, should be skipped
        assert state.count == 1

    def test_skips_empty_files(self, tmp_path):
        (tmp_path / "0.txt").write_text("", encoding="utf-8")
        (tmp_path / "1.txt").write_text("1222670", encoding="utf-8")
        state = read_applist(tmp_path)
        assert state.count == 1

    def test_nonexistent_dir(self, tmp_path):
        state = read_applist(tmp_path / "nonexistent")
        assert state.count == 0
        assert state.entries == {}

    def test_ignores_non_applist_files(self, tmp_path):
        (tmp_path / "0.txt").write_text("1111", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("2222", encoding="utf-8")
        (tmp_path / "config.ini").write_text("3333", encoding="utf-8")
        state = read_applist(tmp_path)
        assert state.count == 1


class TestWriteApplist:
    def test_writes_sequential(self, tmp_path):
        count = write_applist(tmp_path, ["1111", "2222", "3333"])
        assert count == 3
        assert (tmp_path / "0.txt").read_text(encoding="utf-8") == "1111"
        assert (tmp_path / "1.txt").read_text(encoding="utf-8") == "2222"
        assert (tmp_path / "2.txt").read_text(encoding="utf-8") == "3333"

    def test_deduplicates(self, tmp_path):
        count = write_applist(tmp_path, ["1111", "2222", "1111", "3333"])
        assert count == 3
        # Only 3 files, not 4
        assert not (tmp_path / "3.txt").exists()

    def test_clears_existing(self, tmp_path):
        # Pre-populate with old data
        (tmp_path / "0.txt").write_text("old_id", encoding="utf-8")
        (tmp_path / "1.txt").write_text("old_id2", encoding="utf-8")
        write_applist(tmp_path, ["new_id"])
        assert (tmp_path / "0.txt").read_text(encoding="utf-8") == "new_id"
        assert not (tmp_path / "1.txt").exists()

    def test_exceeds_limit_raises(self, tmp_path):
        ids = [str(i) for i in range(APPLIST_LIMIT + 1)]
        with pytest.raises(ValueError, match="exceeding the GreenLuma limit"):
            write_applist(tmp_path, ids)

    def test_creates_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "AppList"
        write_applist(new_dir, ["1111"])
        assert new_dir.is_dir()
        assert (new_dir / "0.txt").exists()


class TestAddIds:
    def test_adds_new_ids(self, tmp_path):
        (tmp_path / "0.txt").write_text("1111", encoding="utf-8")
        added = add_ids(tmp_path, ["2222", "3333"])
        assert added == 2
        state = read_applist(tmp_path)
        assert state.count == 3

    def test_skips_existing(self, tmp_path):
        (tmp_path / "0.txt").write_text("1111", encoding="utf-8")
        added = add_ids(tmp_path, ["1111", "2222"])
        assert added == 1  # only 2222 was new

    def test_exceeds_limit_raises(self, tmp_path):
        write_applist(tmp_path, [str(i) for i in range(APPLIST_LIMIT)])
        with pytest.raises(ValueError, match="exceeding the GreenLuma limit"):
            add_ids(tmp_path, ["999999"])


class TestRemoveIds:
    def test_removes_ids(self, tmp_path):
        write_applist(tmp_path, ["1111", "2222", "3333"])
        removed = remove_ids(tmp_path, {"2222"})
        assert removed == 1
        state = read_applist(tmp_path)
        assert state.count == 2
        assert "2222" not in state.unique_ids

    def test_remove_nonexistent(self, tmp_path):
        write_applist(tmp_path, ["1111"])
        removed = remove_ids(tmp_path, {"9999"})
        assert removed == 0

    def test_renumbers_after_removal(self, tmp_path):
        write_applist(tmp_path, ["1111", "2222", "3333"])
        remove_ids(tmp_path, {"2222"})
        # After removal, files are rewritten sequentially
        assert (tmp_path / "0.txt").read_text(encoding="utf-8") == "1111"
        assert (tmp_path / "1.txt").read_text(encoding="utf-8") == "3333"
        assert not (tmp_path / "2.txt").exists()
