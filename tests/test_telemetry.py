"""Tests for TelemetryClient."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, call, patch

import pytest

from sims4_updater.config import Settings
from sims4_updater.core.telemetry import TelemetryClient


class TestTelemetryUID:
    """UID generation and persistence."""

    def test_uid_generated_on_init(self, tmp_path):
        path = tmp_path / "settings.json"
        s = Settings()
        s.save(path)
        s = Settings.load(path)
        assert s.uid == ""

        with (
            patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com"),
            patch("sims4_updater.config.SETTINGS_PATH", path),
        ):
            client = TelemetryClient(s)
        assert len(client.uid) == 32  # uuid4 hex
        # Persisted to disk
        reloaded = Settings.load(path)
        assert reloaded.uid == client.uid

    def test_uid_stable_across_instances(self, tmp_path):
        path = tmp_path / "settings.json"
        s = Settings()
        s.save(path)
        s = Settings.load(path)

        with (
            patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com"),
            patch("sims4_updater.config.SETTINGS_PATH", path),
        ):
            c1 = TelemetryClient(s)
            uid1 = c1.uid

            s2 = Settings.load(path)
            c2 = TelemetryClient(s2)
        assert c2.uid == uid1

    def test_existing_uid_preserved(self, tmp_path):
        path = tmp_path / "settings.json"
        s = Settings(uid="abc123def456")
        s.save(path)
        s = Settings.load(path)

        with patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com"):
            client = TelemetryClient(s)
        assert client.uid == "abc123def456"


class TestHeartbeat:
    """Heartbeat POST behavior."""

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_heartbeat_sends_post(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.heartbeat(game_version="1.121.372", game_detected=True, dlc_count=5)

        mock_post.assert_called_once()
        url = mock_post.call_args.args[0]
        assert url == "https://example.com/stats/heartbeat"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["uid"] == client.uid
        assert payload["game_version"] == "1.121.372"
        assert payload["game_detected"] is True
        assert payload["dlc_count"] == 5
        assert "app_version" in payload
        assert "os_version" in payload
        assert "last_seen" in payload

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_heartbeat_omits_none_fields(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.heartbeat(game_detected=False)

        payload = mock_post.call_args.kwargs["json"]
        assert "game_version" not in payload
        assert "crack_format" not in payload
        assert "dlc_count" not in payload
        assert "locale" not in payload


class TestTrackEvent:
    """Event tracking POST behavior."""

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_track_event_sends_post(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.track_event("dlc_downloaded", {"dlc_id": "EP01"})

        mock_post.assert_called_once()
        url = mock_post.call_args.args[0]
        assert url == "https://example.com/stats/event"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["uid"] == client.uid
        assert payload["event_type"] == "dlc_downloaded"
        assert payload["metadata"]["dlc_id"] == "EP01"

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_track_event_without_metadata(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.track_event("app_launch")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["event_type"] == "app_launch"
        assert "metadata" not in payload


class TestDisabledTelemetry:
    """Telemetry respects the enabled flag."""

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_disabled_sends_nothing(self, mock_post):
        s = Settings(telemetry_enabled=False, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.heartbeat(game_detected=False)
        client.track_event("app_launch")

        mock_post.assert_not_called()

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "")
    def test_empty_url_sends_nothing(self, mock_post):
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.heartbeat(game_detected=False)
        client.track_event("app_launch")

        mock_post.assert_not_called()


class TestErrorHandling:
    """Network and unexpected errors are silently caught."""

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_network_error_silently_ignored(self, mock_post):
        import requests as req

        mock_post.side_effect = req.ConnectionError("no network")
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        # Should not raise
        client.heartbeat(game_detected=False)
        client.track_event("app_launch")

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_server_error_silently_ignored(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        # Should not raise
        client.heartbeat(game_detected=False)
        client.track_event("app_launch")

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_timeout_silently_ignored(self, mock_post):
        import requests as req

        mock_post.side_effect = req.Timeout("timed out")
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        # Should not raise
        client.heartbeat(game_detected=False)


class TestSettingsDefaults:
    """Settings telemetry fields have correct defaults."""

    def test_telemetry_defaults(self):
        s = Settings()
        assert s.uid == ""
        assert s.telemetry_enabled is True

    def test_load_old_settings_without_telemetry_fields(self, tmp_path):
        path = tmp_path / "settings.json"
        data = {"game_path": r"C:\Test", "theme": "dark"}
        path.write_text(json.dumps(data), encoding="utf-8")
        s = Settings.load(path)
        assert s.uid == ""
        assert s.telemetry_enabled is True

    def test_telemetry_fields_persisted(self, tmp_path):
        path = tmp_path / "settings.json"
        s = Settings(uid="my_uid_12345678", telemetry_enabled=False)
        s.save(path)

        reloaded = Settings.load(path)
        assert reloaded.uid == "my_uid_12345678"
        assert reloaded.telemetry_enabled is False


class TestPeriodicHeartbeat:
    """Periodic heartbeat thread behavior."""

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_periodic_heartbeat_fires(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)
        client.set_game_info(game_version="1.0", game_detected=True)

        client.start_periodic_heartbeat(interval=0.1)
        time.sleep(0.35)
        client.stop_periodic_heartbeat()

        # Should have fired at least 2 heartbeats (at 0.1s, 0.2s, maybe 0.3s)
        heartbeat_calls = [
            c for c in mock_post.call_args_list
            if "/heartbeat" in c.args[0]
        ]
        assert len(heartbeat_calls) >= 2

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_periodic_heartbeat_stops(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.start_periodic_heartbeat(interval=0.05)
        time.sleep(0.15)
        client.stop_periodic_heartbeat()
        count_after_stop = mock_post.call_count
        time.sleep(0.15)
        # No more calls after stop
        assert mock_post.call_count == count_after_stop

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_periodic_heartbeat_disabled_noop(self, mock_post):
        s = Settings(telemetry_enabled=False, uid="test_uid_1234567890")
        client = TelemetryClient(s)
        client.start_periodic_heartbeat(interval=0.05)
        time.sleep(0.15)
        client.stop_periodic_heartbeat()
        mock_post.assert_not_called()


class TestSessionEnd:
    """Session lifecycle tracking."""

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_session_end_sends_duration(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        time.sleep(0.1)
        client.session_end()

        # Should have sent a session_end event
        event_calls = [
            c for c in mock_post.call_args_list
            if "/event" in c.args[0]
        ]
        assert len(event_calls) == 1
        payload = event_calls[0].kwargs["json"]
        assert payload["event_type"] == "session_end"
        assert "session_id" in payload["metadata"]
        assert payload["metadata"]["duration_seconds"] >= 0

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_session_end_stops_periodic(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.start_periodic_heartbeat(interval=0.05)
        time.sleep(0.1)
        client.session_end()
        count_after = mock_post.call_count
        time.sleep(0.15)
        assert mock_post.call_count == count_after


class TestGameInfoCache:
    """Game info caching for periodic heartbeats."""

    @patch("sims4_updater.core.telemetry.requests.post")
    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_game_info_cached_for_heartbeat(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        client = TelemetryClient(s)

        client.set_game_info(
            game_version="1.121.372",
            crack_format="anadius_codex",
            dlc_count=15,
            game_detected=True,
            locale="en_US",
        )

        # Heartbeat without args should use cached info
        client.heartbeat(**client._game_info)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["game_version"] == "1.121.372"
        assert payload["crack_format"] == "anadius_codex"
        assert payload["dlc_count"] == 15
        assert payload["game_detected"] is True
        assert payload["locale"] == "en_US"

    @patch("sims4_updater.core.telemetry.TELEMETRY_URL", "https://example.com/stats")
    def test_launch_time_tracked(self):
        s = Settings(telemetry_enabled=True, uid="test_uid_1234567890")
        before = time.monotonic()
        client = TelemetryClient(s)
        after = time.monotonic()
        assert before <= client._launch_time <= after
