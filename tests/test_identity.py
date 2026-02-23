"""Tests for core.identity — shared identity headers."""

from __future__ import annotations

import pytest

from sims4_updater.core import identity


@pytest.fixture(autouse=True)
def _reset():
    """Clear headers between tests."""
    identity._headers.clear()
    yield
    identity._headers.clear()


class TestIdentity:
    def test_configure_and_get_headers(self):
        """Round-trip: configure values, get them back."""
        identity.configure("abc123", "uid456")
        h = identity.get_headers()
        assert h["X-Machine-Id"] == "abc123"
        assert h["X-UID"] == "uid456"

    def test_empty_uid_omitted(self):
        """X-UID header should not be present when uid is empty."""
        identity.configure("abc123", "")
        h = identity.get_headers()
        assert "X-Machine-Id" in h
        assert "X-UID" not in h

    def test_empty_machine_id_omitted(self):
        """X-Machine-Id should not be present when machine_id is empty."""
        identity.configure("", "uid456")
        h = identity.get_headers()
        assert "X-Machine-Id" not in h
        assert "X-UID" in h

    def test_get_headers_returns_copy(self):
        """get_headers() should return a new dict each time (not the internal one)."""
        identity.configure("mid", "uid")
        h1 = identity.get_headers()
        h2 = identity.get_headers()
        assert h1 == h2
        assert h1 is not h2

    def test_reconfigure_clears_previous(self):
        """Calling configure() again should replace old values."""
        identity.configure("old_mid", "old_uid")
        identity.configure("new_mid", "")
        h = identity.get_headers()
        assert h["X-Machine-Id"] == "new_mid"
        assert "X-UID" not in h
