"""
Anonymous telemetry — heartbeat and event tracking via Cloudflare Worker → Supabase.

All methods are fire-and-forget: they catch all exceptions internally
and never raise.  The module respects the ``telemetry_enabled`` setting.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import platform
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

import requests

from .. import VERSION
from ..constants import TELEMETRY_URL

if TYPE_CHECKING:
    from ..config import Settings

log = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds — short to avoid stalling the app


class TelemetryClient:
    """Fire-and-forget telemetry via Cloudflare Worker → Supabase."""

    def __init__(self, settings: Settings, base_url: str = "") -> None:
        self._settings = settings
        self._base_url = base_url or TELEMETRY_URL
        self._session_id = uuid.uuid4().hex
        self._os_version = self._get_os_version()
        self._launch_time = time.monotonic()
        self._game_info: dict[str, Any] = {}
        self._heartbeat_stop: threading.Event | None = None
        self._disabled = False  # set True on 403 to stop further requests
        self._ensure_uid()

    # ── UID management ────────────────────────────────────────

    def _ensure_uid(self) -> None:
        """Generate a stable UUID4 if the user doesn't have one yet."""
        if not self._settings.uid:
            self._settings.uid = uuid.uuid4().hex
            self._settings.save()

    @property
    def uid(self) -> str:
        return self._settings.uid

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_base_url(self, url: str) -> None:
        """Update the telemetry endpoint URL (e.g. from CDN manifest config)."""
        if url:
            self._base_url = url

    # ── Game info cache ───────────────────────────────────────

    def set_game_info(
        self,
        *,
        game_version: str | None = None,
        crack_format: str | None = None,
        dlc_count: int | None = None,
        game_detected: bool = False,
        locale: str | None = None,
    ) -> None:
        """Cache game info for use in periodic heartbeats."""
        self._game_info = {
            "game_version": game_version,
            "crack_format": crack_format,
            "dlc_count": dlc_count,
            "game_detected": game_detected,
            "locale": locale,
        }

    # ── Public API ────────────────────────────────────────────

    def heartbeat(
        self,
        *,
        game_version: str | None = None,
        crack_format: str | None = None,
        dlc_count: int | None = None,
        game_detected: bool = False,
        locale: str | None = None,
    ) -> None:
        """Upsert user record with current system info."""
        if not self._is_enabled():
            return

        data: dict[str, Any] = {
            "uid": self.uid,
            "session_id": self._session_id,
            "app_version": VERSION,
            "os_version": self._os_version,
            "game_detected": game_detected,
            "last_seen": datetime.datetime.now(datetime.UTC).isoformat(),
        }
        if game_version is not None:
            data["game_version"] = game_version
        if crack_format is not None:
            data["crack_format"] = crack_format
        if dlc_count is not None:
            data["dlc_count"] = dlc_count
        if locale is not None:
            data["locale"] = locale

        self._post("/heartbeat", data)

    def track_event(
        self,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append an event to the events log."""
        if not self._is_enabled():
            return

        data: dict[str, Any] = {
            "uid": self.uid,
            "event_type": event_type,
        }
        if metadata:
            data["metadata"] = metadata

        self._post("/event", data)

    # ── Periodic heartbeat ────────────────────────────────────

    def start_periodic_heartbeat(self, interval: int = 300) -> None:
        """Start a daemon thread that sends heartbeats every *interval* seconds."""
        if not self._is_enabled():
            return
        if self._heartbeat_stop is not None:
            return  # Already running

        self._heartbeat_stop = threading.Event()
        stop = self._heartbeat_stop

        def _loop():
            while not stop.wait(interval):
                with contextlib.suppress(Exception):
                    self.heartbeat(**self._game_info)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def stop_periodic_heartbeat(self) -> None:
        """Signal the periodic heartbeat thread to stop."""
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
            self._heartbeat_stop = None

    # ── Session lifecycle ─────────────────────────────────────

    def session_end(self) -> None:
        """Send session_end event with duration, then stop periodic heartbeat."""
        self.stop_periodic_heartbeat()
        duration = int(time.monotonic() - self._launch_time)
        self.track_event(
            "session_end",
            {
                "session_id": self._session_id,
                "duration_seconds": duration,
            },
        )

    # ── Internal ──────────────────────────────────────────────

    def _is_enabled(self) -> bool:
        """Check if telemetry is enabled and configured."""
        if self._disabled:
            return False
        return bool(self._settings.telemetry_enabled and self._base_url)

    def _post(self, endpoint: str, data: dict) -> None:
        """POST to the stats API in a background thread. Never blocks the caller."""
        threading.Thread(target=self._do_post, args=(endpoint, data), daemon=True).start()

    def _do_post(self, endpoint: str, data: dict) -> None:
        """Actual HTTP POST. Runs on a daemon thread — never raises."""
        from . import identity

        try:
            url = f"{self._base_url}{endpoint}"
            headers = {"Content-Type": "application/json"}
            headers.update(identity.get_headers())
            resp = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=_TIMEOUT,
            )
            if resp.status_code == 403:
                log.debug("Telemetry got 403 — disabling for this session")
                self._disabled = True
                return
            if resp.status_code not in (200, 201):
                log.debug("Telemetry %s failed: %s", endpoint, resp.status_code)
        except requests.RequestException as exc:
            log.debug("Telemetry network error (%s): %s", endpoint, exc)
        except Exception as exc:
            log.debug("Telemetry unexpected error (%s): %s", endpoint, exc)

    @staticmethod
    def _get_os_version() -> str:
        """Get a human-readable OS version string."""
        try:
            return f"{platform.system()} {platform.version()}"
        except Exception:
            return "Unknown"
