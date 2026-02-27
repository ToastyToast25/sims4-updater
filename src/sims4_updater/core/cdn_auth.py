"""
CDN session token lifecycle — request, cache, auto-refresh, inject.

The CDN Worker requires a JWT to serve downloads.  This module handles
the token exchange and transparently refreshes expired tokens via a
``requests.auth.AuthBase`` adapter attached to the download session.

Token flow:
  1. Client POSTs ``{api_url}/auth/token`` with machine_id/uid
  2. Server validates (not banned, approved for private CDNs) → returns JWT
  3. JWT is 1-hour TTL, auto-refreshed per-request via ``CDNTokenAuth``
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Any

import requests
from requests.auth import AuthBase

from . import identity
from .exceptions import AccessRequiredError, BannedError

log = logging.getLogger(__name__)

_TIMEOUT = 10


class CDNTokenAuth(AuthBase):
    """Per-request auth adapter — auto-refreshes the JWT before each request."""

    def __init__(self, cdn_auth: CDNAuth) -> None:
        self._cdn_auth = cdn_auth

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        try:
            token = self._cdn_auth.get_token()
        except RuntimeError:
            token = ""
        if token:
            r.headers["Authorization"] = f"Bearer {token}"
        return r


class CDNAuth:
    """Manages JWT session token for CDN access."""

    _MIN_RETRY_INTERVAL = 5  # seconds between refresh attempts

    def __init__(
        self,
        api_url: str,
        machine_id: str,
        uid: str,
        app_version: str,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._machine_id = machine_id
        self._uid = uid
        self._app_version = app_version
        self._token: str = ""
        self._expires_at: float = 0
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()  # serialises network refresh calls
        self._denied: BannedError | AccessRequiredError | None = None
        self._last_refresh_attempt: float = 0

    @property
    def api_url(self) -> str:
        return self._api_url

    def _check_denied(self) -> None:
        """Raise a *copy* of the denied error if still active (call under _lock)."""
        if self._denied is None:
            return
        if isinstance(self._denied, BannedError) and self._denied.expires_at:
            import datetime

            try:
                exp = datetime.datetime.fromisoformat(
                    self._denied.expires_at.replace("Z", "+00:00")
                )
                if datetime.datetime.now(datetime.UTC) >= exp:
                    self._denied = None  # ban expired, allow retry
                    return
            except (ValueError, TypeError):
                pass
        # Raise a fresh copy so each thread gets its own traceback
        denied = self._denied
        if isinstance(denied, BannedError):
            raise BannedError(
                reason=denied.reason,
                ban_type=denied.ban_type,
                expires_at=denied.expires_at,
            )
        if isinstance(denied, AccessRequiredError):
            raise AccessRequiredError(
                cdn_name=denied.cdn_name,
                request_url=denied.request_url,
            )
        raise denied  # pragma: no cover

    def get_token(self) -> str:
        """Return a valid token, refreshing if near expiry (< 60 s left)."""
        # Fast path: token still valid (no lock needed)
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token
        with self._lock:
            self._check_denied()
            # Double-check after acquiring lock (another thread may have refreshed)
            if self._token and time.monotonic() < self._expires_at - 60:
                return self._token
        # Only one thread refreshes at a time; others wait then re-check
        with self._refresh_lock:
            # Triple-check: another thread may have refreshed while we waited
            if self._token and time.monotonic() < self._expires_at - 60:
                return self._token
            self._refresh()
        if not self._token:
            raise RuntimeError("Token refresh failed — no valid token available.")
        return self._token

    def get_auth_adapter(self) -> CDNTokenAuth:
        """Return a ``requests.auth.AuthBase`` adapter for a Session."""
        return CDNTokenAuth(self)

    def request_access(self, reason: str = "") -> dict[str, Any]:
        """Submit an access request for a private CDN.

        Returns the JSON response body on success, or raises on error.
        Raises BannedError if the server responds with a ban.
        """
        resp = requests.post(
            f"{self._api_url}/access/request",
            json={
                "machine_id": self._machine_id,
                "uid": self._uid,
                "app_version": self._app_version,
                "reason": reason,
            },
            headers=identity.get_headers(),
            timeout=_TIMEOUT,
        )
        # Check for ban response before generic raise_for_status
        if resp.status_code == 403:
            body: dict[str, Any] = {}
            with contextlib.suppress(Exception):
                body = resp.json()
            if body.get("error") == "banned":
                raise BannedError(
                    reason=body.get("reason", ""),
                    ban_type=body.get("ban_type", ""),
                    expires_at=body.get("expires_at", ""),
                )
        resp.raise_for_status()
        return resp.json()

    # ── internal ───────────────────────────────────────────────

    def _refresh(self) -> None:
        """Request a new JWT from the CDN API (with cooldown and single retry).

        Must be called under ``_refresh_lock`` to serialise concurrent callers.
        Shared state writes are protected by ``_lock``.
        """
        now = time.monotonic()
        if now - self._last_refresh_attempt < self._MIN_RETRY_INTERVAL:
            # Still in cooldown — keep existing token if valid, else silently skip
            if self._token and now < self._expires_at:
                return
            return
        self._last_refresh_attempt = now

        resp = None
        for attempt in range(2):
            try:
                resp = requests.post(
                    f"{self._api_url}/auth/token",
                    json={
                        "machine_id": self._machine_id,
                        "uid": self._uid,
                        "app_version": self._app_version,
                    },
                    headers=identity.get_headers(),
                    timeout=_TIMEOUT,
                )
                # Retry on 5xx server errors
                if resp.status_code >= 500 and attempt == 0:
                    log.warning("CDN token request returned %d, retrying", resp.status_code)
                    time.sleep(1)
                    continue
                break
            except requests.RequestException as exc:
                if attempt == 0:
                    time.sleep(1)
                    continue
                log.warning("CDN token request network error: %s", exc)
                with self._lock:
                    if self._token and time.monotonic() < self._expires_at:
                        return
                    self._token, self._expires_at = "", 0
                return

        if resp is None:
            return

        if resp.status_code == 403:
            body: dict[str, Any] = {}
            with contextlib.suppress(Exception):
                body = resp.json()
            with self._lock:
                self._token, self._expires_at = "", 0
                if body.get("error") == "access_required":
                    self._denied = AccessRequiredError(
                        cdn_name=body.get("cdn_name", ""),
                        request_url=body.get("request_url", ""),
                    )
                    denied = self._denied
                else:
                    self._denied = BannedError(
                        reason=body.get("reason", ""),
                        ban_type=body.get("ban_type", ""),
                        expires_at=body.get("expires_at", ""),
                    )
                    denied = self._denied
            raise denied

        if resp.status_code != 200:
            log.warning("CDN token request returned %d", resp.status_code)
            return

        try:
            data = resp.json()
            token = data.get("token", "")
            if not token or not isinstance(token, str):
                log.warning("CDN token response missing valid 'token' field")
                return
            with self._lock:
                self._token = token
                self._expires_at = time.monotonic() + data.get("expires_in", 3600)
        except Exception as exc:
            log.warning("CDN token parse error: %s", exc)
