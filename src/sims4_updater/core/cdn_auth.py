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
        token = self._cdn_auth.get_token()
        if token:
            r.headers["Authorization"] = f"Bearer {token}"
        return r


class CDNAuth:
    """Manages JWT session token for CDN access."""

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

    @property
    def api_url(self) -> str:
        return self._api_url

    def get_token(self) -> str:
        """Return a valid token, refreshing if near expiry (< 60 s left)."""
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token
        with self._lock:
            # Double-check after acquiring lock (another thread may have refreshed)
            if self._token and time.monotonic() < self._expires_at - 60:
                return self._token
            self._refresh()
        return self._token

    def get_auth_adapter(self) -> CDNTokenAuth:
        """Return a ``requests.auth.AuthBase`` adapter for a Session."""
        return CDNTokenAuth(self)

    def request_access(self, reason: str = "") -> dict[str, Any]:
        """Submit an access request for a private CDN.

        Returns the JSON response body on success, or raises on error.
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
        resp.raise_for_status()
        return resp.json()

    # ── internal ───────────────────────────────────────────────

    def _refresh(self) -> None:
        """Request a new JWT from the CDN API."""
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
        except requests.RequestException as exc:
            log.warning("CDN token request network error: %s", exc)
            # Keep existing token if still valid, otherwise clear atomically
            if self._token and time.monotonic() < self._expires_at:
                return
            self._token, self._expires_at = "", 0
            return

        if resp.status_code == 403:
            body: dict[str, Any] = {}
            with contextlib.suppress(Exception):
                body = resp.json()
            if body.get("error") == "access_required":
                raise AccessRequiredError(
                    cdn_name=body.get("cdn_name", ""),
                    request_url=body.get("request_url", ""),
                )
            raise BannedError(
                reason=body.get("reason", ""),
                ban_type=body.get("ban_type", ""),
                expires_at=body.get("expires_at", ""),
            )

        if resp.status_code != 200:
            log.warning("CDN token request returned %d", resp.status_code)
            return

        try:
            data = resp.json()
            self._token = data["token"]
            self._expires_at = time.monotonic() + data.get("expires_in", 3600)
        except Exception as exc:
            log.warning("CDN token parse error: %s", exc)
