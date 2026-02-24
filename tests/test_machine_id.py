"""Tests for core.machine_id — deterministic machine fingerprint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset cached value between tests."""
    import sims4_updater.core.machine_id as mid
    mid._cached = None
    yield
    mid._cached = None


class TestGetMachineId:
    def test_returns_32_hex_chars(self):
        """Machine ID should be a 32-char hex string."""
        with patch(
            "sims4_updater.core.machine_id._read_machine_guid",
            return_value="test-guid-12345",
        ):
            from sims4_updater.core.machine_id import get_machine_id

            mid = get_machine_id()
            assert len(mid) == 32
            assert all(c in "0123456789abcdef" for c in mid)

    def test_deterministic(self):
        """Same GUID should produce the same machine ID."""
        with patch(
            "sims4_updater.core.machine_id._read_machine_guid",
            return_value="my-stable-guid",
        ):
            from sims4_updater.core.machine_id import get_machine_id

            id1 = get_machine_id()

        # Reset cache and re-derive
        import sims4_updater.core.machine_id as mod
        mod._cached = None

        with patch(
            "sims4_updater.core.machine_id._read_machine_guid",
            return_value="my-stable-guid",
        ):
            id2 = get_machine_id()

        assert id1 == id2

    def test_cached_after_first_call(self):
        """Registry should only be read once — subsequent calls use cache."""
        mock_read = MagicMock(return_value="cached-guid")
        with patch(
            "sims4_updater.core.machine_id._read_machine_guid",
            mock_read,
        ):
            from sims4_updater.core.machine_id import get_machine_id

            id1 = get_machine_id()
            id2 = get_machine_id()

        assert id1 == id2
        mock_read.assert_called_once()

    def test_registry_failure_returns_valid_fallback(self):
        """If the registry read fails, fallback to a persistent random ID (still 32 hex)."""
        with (
            patch(
                "sims4_updater.core.machine_id._read_machine_guid",
                return_value="",
            ),
            patch(
                "sims4_updater.core.machine_id._get_or_create_fallback_id",
                return_value="abcdef1234567890abcdef1234567890",
            ),
        ):
            from sims4_updater.core.machine_id import get_machine_id

            mid = get_machine_id()
            assert len(mid) == 32
            assert all(c in "0123456789abcdef" for c in mid)
            assert mid != "unknown"

    def test_different_guids_produce_different_ids(self):
        """Different GUIDs should produce different machine IDs."""
        import sims4_updater.core.machine_id as mod

        with patch(
            "sims4_updater.core.machine_id._read_machine_guid",
            return_value="guid-aaa",
        ):
            id_a = mod.get_machine_id()

        mod._cached = None

        with patch(
            "sims4_updater.core.machine_id._read_machine_guid",
            return_value="guid-bbb",
        ):
            id_b = mod.get_machine_id()

        assert id_a != id_b
