"""
Event Rewards Unlocker — unlock Sims 4 live-event rewards via accountDataDB.package patching.

The game stores event progress in an accountDataDB.package file (DBPF 2.1 format) in the
user's Documents/Electronic Arts/The Sims 4/ folder.  This module patches a pre-built
template that has all event rewards marked as claimed, replacing placeholder instance IDs
with the user's actual EA account IDs extracted from UserSetting.ini.

Approach (identical to the anadius web tool):
  1. Read UserSetting.ini to discover EA account IDs
  2. Load a bundled template accountDataDB.package containing all known event rewards
  3. Patch the DBPF index entries — replace placeholder instance IDs with real ones
  4. Write the result to the user's Sims 4 data folder
"""

from __future__ import annotations

import os
import re
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..constants import get_data_dir

if TYPE_CHECKING:
    from collections.abc import Callable

# ── Template constants ───────────────────────────────────────────────

# Template filename (bundled in data/)
_TEMPLATE_FILENAME = "accountDataDB_009.package"

# Max account slots in the template
MAX_ACCOUNT_SLOTS = 10

# Each account occupies 4 index entries (DataKey, Blob, Header, Entry).
# Each index entry is 28 bytes.  The instance ID is an 8-byte field at
# offset +4 within each entry (after the 4-byte type field).
#
# Index layout in accountDataDB_009.package:
#   Index starts at byte 45186
#   Flags (4 bytes) + constant group (4 bytes) = 8 bytes header
#   First entry at 45194
#   Instance ID at entry_start + 4
#
# Pre-computed offsets for each account slot (4 offsets per slot).
_INSTANCE_OFFSETS: list[list[int]] = [
    [45198, 45226, 45254, 45282],
    [45310, 45338, 45366, 45394],
    [45422, 45450, 45478, 45506],
    [45534, 45562, 45590, 45618],
    [45646, 45674, 45702, 45730],
    [45758, 45786, 45814, 45842],
    [45870, 45898, 45926, 45954],
    [45982, 46010, 46038, 46066],
    [46094, 46122, 46150, 46178],
    [46206, 46234, 46262, 46290],
]


# ── Known events ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class EventInfo:
    """Metadata for a known Sims 4 live event."""

    name: str
    date: str
    status: str  # "live", "ended", "base_game"
    note: str = ""


KNOWN_EVENTS: list[EventInfo] = [
    EventInfo(
        "Lost Legacies Event",
        "February 2026",
        "live",
        "Use the tool to claim rewards and tie them to your EA account!",
    ),
    EventInfo(
        "Deck the Palms Login Event",
        "December 2025",
        "ended",
    ),
    EventInfo(
        "Forever Friends Event",
        "September 2025",
        "ended",
    ),
    EventInfo(
        "Nature's Calling Event",
        "June 2025",
        "ended",
    ),
    EventInfo(
        "Blast From The Past Event",
        "February 2025",
        "ended",
    ),
    EventInfo(
        "Cozy Celebrations Event",
        "December 2024",
        "ended",
    ),
    EventInfo(
        "Reaper's Rewards Event",
        "September 2024",
        "ended",
    ),
    EventInfo(
        "Happy at Home Login Event",
        "June 2024",
        "base_game",
        "Rewards added to base game in update 1.109.207",
    ),
]


# ── Sims 4 user data directory ───────────────────────────────────────

# Localized folder names for "The Sims 4" under Documents/Electronic Arts/
_SIMS4_FOLDER_NAMES = [
    "The Sims 4",
    "Die Sims 4",
    "Les Sims 4",
    "Los Sims 4",
    "De Sims 4",
    "The Sims 4 Edição Legacy",
]


def find_sims4_user_dir() -> Path | None:
    """Find the Documents/Electronic Arts/The Sims 4 user data directory."""
    ea_dir = Path(os.path.expanduser("~")) / "Documents" / "Electronic Arts"
    if not ea_dir.is_dir():
        return None
    for name in _SIMS4_FOLDER_NAMES:
        candidate = ea_dir / name
        if candidate.is_dir():
            return candidate
    return None


def find_user_setting_ini(sims4_dir: Path | None = None) -> Path | None:
    """Locate the UserSetting.ini file."""
    if sims4_dir is None:
        sims4_dir = find_sims4_user_dir()
    if sims4_dir is None:
        return None
    ini_path = sims4_dir / "UserSetting.ini"
    return ini_path if ini_path.is_file() else None


# ── INI parsing ──────────────────────────────────────────────────────


def parse_account_ids(ini_path: Path) -> list[int]:
    """Extract EA account IDs from a UserSetting.ini file.

    Account IDs appear as numeric prefixes in the [uiaccountsettings] section,
    e.g.  ``1002602570288#playersessions#uint = 15``
    The prefix before the first ``#`` is the account ID.
    """
    text = ini_path.read_text(encoding="utf-8", errors="replace")

    # Simple INI parser — configparser lowercases keys and can choke on
    # the Sims 4 format, so we parse manually (matching the anadius approach).
    sections: dict[str, dict[str, str]] = {}
    current_section = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\[(.*?)\]$", line)
        if m:
            current_section = m.group(1).lower()
            sections.setdefault(current_section, {})
            continue
        m = re.match(r"^(.*?)\s*=\s*(.*?)\s*$", line)
        if m and current_section:
            sections[current_section][m.group(1)] = m.group(2)

    account_settings = sections.get("uiaccountsettings", {})
    if not account_settings:
        return []

    ids: dict[int, None] = {}
    for key in account_settings:
        prefix = key.split("#")[0]
        try:
            ids[int(prefix)] = None
        except ValueError:
            continue

    return list(ids)


# ── DBPF instance ID encoding ────────────────────────────────────────


def _encode_instance_id(account_id: int) -> bytes:
    """Encode an EA account ID as 8 bytes for the DBPF index.

    The DBPF index stores 64-bit instance IDs as [InstanceHi_LE][InstanceLo_LE].
    To write a numeric ID correctly, we split it into high/low 32-bit halves
    and write each as little-endian uint32.  This is equivalent to the
    ``dont_ask_me`` transform in the anadius JavaScript tool.
    """
    hi = (account_id >> 32) & 0xFFFFFFFF
    lo = account_id & 0xFFFFFFFF
    return struct.pack("<II", hi, lo)


# ── Package generation ───────────────────────────────────────────────


class EventUnlockerError(Exception):
    """Raised when event unlocking fails."""


def get_template_path() -> Path:
    """Return the path to the bundled template package."""
    return get_data_dir() / _TEMPLATE_FILENAME


def generate_package(
    account_ids: list[int],
    *,
    template_path: Path | None = None,
) -> bytearray:
    """Generate a patched accountDataDB.package for the given account IDs.

    Returns the raw bytes of the patched package.
    """
    if not account_ids:
        raise EventUnlockerError("No account IDs provided.")
    if len(account_ids) > MAX_ACCOUNT_SLOTS:
        raise EventUnlockerError(
            f"Too many accounts ({len(account_ids)}). "
            f"Maximum supported: {MAX_ACCOUNT_SLOTS}. "
            "Delete or rename UserSetting.ini, run the game once, "
            "then try again with the new file."
        )

    if template_path is None:
        template_path = get_template_path()
    if not template_path.is_file():
        raise EventUnlockerError(
            f"Template not found: {template_path}\n"
            "The event unlocker template is missing from the installation."
        )

    data = bytearray(template_path.read_bytes())

    for slot_idx, account_id in enumerate(account_ids):
        encoded = _encode_instance_id(account_id)
        for offset in _INSTANCE_OFFSETS[slot_idx]:
            data[offset : offset + 8] = encoded

    return data


@dataclass
class UnlockResult:
    """Result of an event unlock operation."""

    output_path: Path
    account_ids: list[int]
    backup_path: Path | None


def unlock_events(
    ini_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    backup: bool = True,
    progress: Callable[[str], None] | None = None,
) -> UnlockResult:
    """Full event unlock pipeline: parse INI -> patch template -> write output.

    Args:
        ini_path: Path to UserSetting.ini. Auto-detected if None.
        output_dir: Directory to write accountDataDB.package. Defaults to the
                    same directory as UserSetting.ini.
        backup: Whether to back up existing accountDataDB.package.
        progress: Optional callback for status messages.

    Returns:
        UnlockResult with output path, account IDs, and optional backup path.
    """

    def _log(msg: str) -> None:
        if progress:
            progress(msg)

    # 1. Find UserSetting.ini
    if ini_path is None:
        _log("Searching for UserSetting.ini...")
        ini_path = find_user_setting_ini()
        if ini_path is None:
            raise EventUnlockerError(
                "Could not find UserSetting.ini.\n"
                "Make sure the game has been run at least once.\n"
                "Expected location: Documents/Electronic Arts/The Sims 4/UserSetting.ini"
            )
    elif not ini_path.is_file():
        raise EventUnlockerError(f"UserSetting.ini not found: {ini_path}")

    _log(f"Found: {ini_path}")

    # 2. Parse account IDs
    _log("Parsing account IDs...")
    account_ids = parse_account_ids(ini_path)
    if not account_ids:
        raise EventUnlockerError(
            "No account IDs found in UserSetting.ini.\n"
            "Make sure the game has been run at least once and you've logged in."
        )
    _log(f"Found {len(account_ids)} account(s): {', '.join(str(a) for a in account_ids)}")

    # 3. Generate patched package
    _log("Generating event rewards package...")
    patched = generate_package(account_ids)

    # 4. Determine output directory
    if output_dir is None:
        output_dir = ini_path.parent
    output_path = output_dir / "accountDataDB.package"

    # 5. Backup existing file
    backup_path = None
    if backup and output_path.is_file():
        backup_path = output_path.with_suffix(".package.bak")
        _log(f"Backing up existing file to {backup_path.name}...")
        shutil.copy2(output_path, backup_path)

    # 6. Write patched package
    _log("Writing accountDataDB.package...")
    output_path.write_bytes(patched)
    _log(f"Done! Event rewards unlocked for {len(account_ids)} account(s).")

    return UnlockResult(
        output_path=output_path,
        account_ids=account_ids,
        backup_path=backup_path,
    )
