"""
Shared identity headers for all CDN/API requests.

Call ``configure()`` once at startup after settings are loaded.
All HTTP code paths call ``get_headers()`` to include identity headers.
"""

from __future__ import annotations

_headers: dict[str, str] = {}


def configure(machine_id: str, uid: str) -> None:
    """Set identity values. Call once at app startup."""
    _headers.clear()
    if machine_id:
        _headers["X-Machine-Id"] = machine_id
    if uid:
        _headers["X-UID"] = uid


def get_headers() -> dict[str, str]:
    """Return a copy of the identity headers dict."""
    return dict(_headers)
