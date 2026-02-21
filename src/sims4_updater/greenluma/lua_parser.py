"""
LUA manifest parser for GreenLuma/SteamTools.

Parses LUA files that declare Steam app IDs, decryption keys, and manifest IDs
using addappid() and setManifestid() calls. These files drive GreenLuma's DLC
unlock and depot download functionality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex patterns for LUA call extraction
# ---------------------------------------------------------------------------

# addappid with decryption key: addappid(ID, FLAGS, "HEX_KEY")
_RE_ADDAPPID_KEY = re.compile(
    r'addappid\(\s*(\d+)\s*,\s*\d+\s*,\s*"([0-9a-fA-F]+)"\s*\)'
)

# addappid without key: addappid(ID) or addappid(ID, FLAGS)
_RE_ADDAPPID_NOKEY = re.compile(
    r'addappid\(\s*(\d+)\s*(?:,\s*\d+\s*)?\)'
)

# setManifestid: setManifestid(DEPOT_ID, "MANIFEST_ID")
_RE_MANIFEST = re.compile(
    r'setManifestid\(\s*(\d+)\s*,\s*"(\d+)"\s*\)'
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DepotEntry:
    """A single depot with optional decryption key and manifest ID."""

    depot_id: str
    decryption_key: str = ""   # 64-char hex string, empty if none
    manifest_id: str = ""      # large numeric string, empty if none


@dataclass
class LuaManifest:
    """Parsed representation of a GreenLuma LUA manifest file."""

    app_id: str                                          # first addappid (base game)
    entries: dict[str, DepotEntry] = field(default_factory=dict)  # depot_id -> DepotEntry
    all_app_ids: list[str] = field(default_factory=list)          # all IDs in order

    @property
    def keys_count(self) -> int:
        """Number of entries that have a decryption key."""
        return sum(1 for e in self.entries.values() if e.decryption_key)

    @property
    def manifests_count(self) -> int:
        """Number of entries that have a manifest ID."""
        return sum(1 for e in self.entries.values() if e.manifest_id)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_lua_string(content: str) -> LuaManifest:
    """Parse LUA manifest content from a string.

    Args:
        content: Raw LUA file content.

    Returns:
        Structured LuaManifest with all extracted entries.

    Raises:
        ValueError: If the content is empty or contains no addappid calls.
    """
    if not content or not content.strip():
        raise ValueError("LUA content is empty")

    # Collect all app IDs in declaration order (with and without keys)
    all_app_ids: list[str] = []
    seen_ids: set[str] = set()

    for match in _RE_ADDAPPID_NOKEY.finditer(content):
        app_id = match.group(1)
        if app_id not in seen_ids:
            all_app_ids.append(app_id)
            seen_ids.add(app_id)

    if not all_app_ids:
        raise ValueError("No addappid() calls found in LUA content")

    base_app_id = all_app_ids[0]

    # Build entries for depots that have decryption keys
    entries: dict[str, DepotEntry] = {}
    for match in _RE_ADDAPPID_KEY.finditer(content):
        depot_id = match.group(1)
        key = match.group(2)
        entries[depot_id] = DepotEntry(depot_id=depot_id, decryption_key=key)

    # Associate manifest IDs with existing entries (or create new ones)
    for match in _RE_MANIFEST.finditer(content):
        depot_id = match.group(1)
        manifest_id = match.group(2)
        if depot_id in entries:
            entries[depot_id].manifest_id = manifest_id
        else:
            entries[depot_id] = DepotEntry(
                depot_id=depot_id, manifest_id=manifest_id
            )

    return LuaManifest(
        app_id=base_app_id,
        entries=entries,
        all_app_ids=all_app_ids,
    )


def parse_lua_file(path: Path) -> LuaManifest:
    """Parse a GreenLuma LUA manifest file from disk.

    Args:
        path: Path to the .lua file.

    Returns:
        Structured LuaManifest with all extracted entries.

    Raises:
        ValueError: If the file is empty, unreadable, or contains no valid calls.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read LUA file: {exc}") from exc

    return parse_lua_string(content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def count_summary(manifest: LuaManifest) -> dict[str, int]:
    """Return a summary of counts from a parsed manifest.

    Returns:
        Dict with keys ``total_app_ids``, ``entries_with_keys``,
        ``entries_with_manifests``.
    """
    return {
        "total_app_ids": len(manifest.all_app_ids),
        "entries_with_keys": manifest.keys_count,
        "entries_with_manifests": manifest.manifests_count,
    }
