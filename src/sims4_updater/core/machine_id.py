"""
Deterministic machine fingerprint for CDN access control.

Generates a stable ID from Windows MachineGuid. This ID is sent on ALL
requests to our CDN/API regardless of telemetry settings — it is NOT
telemetry, it is mandatory infrastructure for abuse prevention.
"""

from __future__ import annotations

import hashlib
import logging
import platform

log = logging.getLogger(__name__)

_SALT = "sims4updater-v1:"
_FALLBACK = "unknown"
_cached: str | None = None


def get_machine_id() -> str:
    """Return a deterministic 32-char hex machine fingerprint.

    On Windows: SHA256(salt + MachineGuid), truncated to 32 chars.
    Falls back to ``"unknown"`` if the registry read fails.
    """
    global _cached
    if _cached is not None:
        return _cached

    guid = _read_machine_guid()
    if not guid:
        _cached = _FALLBACK
        return _cached

    _cached = hashlib.sha256((_SALT + guid).encode()).hexdigest()[:32]
    return _cached


def _read_machine_guid() -> str:
    """Read MachineGuid from the Windows registry."""
    if platform.system() != "Windows":
        return ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception as exc:
        log.debug("Could not read MachineGuid: %s", exc)
        return ""
