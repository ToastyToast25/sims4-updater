"""Tests for core file utilities."""

from __future__ import annotations

import io

from sims4_updater.core.files import copyfileobj, hash_file, write_check


class TestHashFile:
    def test_known_content(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        # MD5 of "hello world" = 5eb63bbbe01eeed093cb22bb8f5acdc3
        result = hash_file(str(f))
        assert result == "5EB63BBBE01EEED093CB22BB8F5ACDC3"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        # MD5 of empty = d41d8cd98f00b204e9800998ecf8427e
        result = hash_file(str(f))
        assert result == "D41D8CD98F00B204E9800998ECF8427E"

    def test_returns_uppercase(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"test")
        result = hash_file(str(f))
        assert result == result.upper()

    def test_progress_callback(self, tmp_path):
        f = tmp_path / "test.bin"
        data = b"x" * 200
        f.write_bytes(data)
        calls = []
        hash_file(str(f), chunk_size=100, progress=calls.append)
        # Should get: 0, 100, 200
        assert calls[0] == 0
        assert calls[-1] == 200

    def test_small_chunk_size(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"abc")
        result = hash_file(str(f), chunk_size=1)
        # Same hash regardless of chunk size
        assert result == hash_file(str(f), chunk_size=65536)


class TestCopyFileObj:
    def test_copies_data(self):
        src = io.BytesIO(b"hello world")
        dst = io.BytesIO()
        progress_calls = []
        copyfileobj(src, dst, progress=progress_calls.append)
        assert dst.getvalue() == b"hello world"

    def test_progress_starts_at_zero(self):
        src = io.BytesIO(b"test")
        dst = io.BytesIO()
        calls = []
        copyfileobj(src, dst, progress=calls.append)
        assert calls[0] == 0

    def test_progress_ends_at_total(self):
        data = b"x" * 500
        src = io.BytesIO(data)
        dst = io.BytesIO()
        calls = []
        copyfileobj(src, dst, progress=calls.append, length=100)
        assert calls[-1] == 500

    def test_empty_source(self):
        src = io.BytesIO(b"")
        dst = io.BytesIO()
        calls = []
        copyfileobj(src, dst, progress=calls.append)
        assert dst.getvalue() == b""
        assert calls == [0]


class TestWriteCheck:
    def test_writable_dir(self, tmp_path):
        # Should not raise
        write_check(str(tmp_path))

    def test_nonexistent_deep_path_succeeds(self, tmp_path):
        # write_check creates parent dirs
        new_dir = tmp_path / "a" / "b" / "c"
        write_check(str(new_dir))
        assert new_dir.is_dir()
