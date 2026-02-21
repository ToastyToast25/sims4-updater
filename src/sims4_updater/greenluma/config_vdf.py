"""
Manage decryption keys in Steam's config.vdf file.

Reads, inserts, and updates depot decryption keys within the VDF-formatted
``config.vdf`` that Steam uses to store per-depot crypto material.  All
mutations are guarded by a Steam-process check and automatic backups.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class VdfKeyState:
    """Snapshot of decryption keys found in a config.vdf file."""

    keys: dict[str, str]  # depot_id -> hex_key
    total_keys: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_braces(content: str) -> bool:
    """Return ``True`` if all curly braces in *content* are balanced."""
    depth = 0
    for ch in content:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _find_depots_section(content: str) -> tuple[int, int]:
    """Locate the ``"depots"`` block within *content*.

    Returns the character positions ``(start, end)`` where *start* is the
    index of the opening brace of the ``"depots"`` block and *end* is the
    index of the matching closing brace (inclusive).

    Raises:
        ValueError: If no ``"depots"`` section can be found or if the
            braces are unbalanced.
    """
    pattern = re.compile(r'"depots"\s*\{')
    match = pattern.search(content)
    if match is None:
        raise ValueError("No \"depots\" section found in config.vdf")

    open_brace = match.end() - 1
    depth = 1
    pos = open_brace + 1

    while pos < len(content) and depth > 0:
        if content[pos] == "{":
            depth += 1
        elif content[pos] == "}":
            depth -= 1
        pos += 1

    if depth != 0:
        raise ValueError("Unbalanced braces in depots section")

    close_brace = pos - 1
    return open_brace, close_brace


def _detect_depot_indent(content: str, depots_start: int, depots_end: int) -> str:
    """Detect the indentation used for depot entries inside the depots block.

    Falls back to five tabs if no existing entries are found.
    """
    section = content[depots_start:depots_end]
    indent_match = re.search(r'\n(\t+)"\d+"', section)
    if indent_match:
        return indent_match.group(1)
    return "\t\t\t\t\t"


def _extract_depot_blocks(content: str) -> dict[str, tuple[str, int, int]]:
    """Extract all top-level depot blocks from the ``"depots"`` section.

    Handles nested sub-blocks (e.g. ``EncryptedManifests``) correctly by
    tracking brace depth instead of using a regex with ``[^}]*``.

    Returns:
        A dict mapping ``depot_id`` -> ``(block_text, start_pos, end_pos)``
        where start/end are absolute positions in *content*.
    """
    try:
        depots_start, depots_end = _find_depots_section(content)
    except ValueError:
        return {}

    depots_body = content[depots_start + 1 : depots_end]
    body_offset = depots_start + 1

    depot_header = re.compile(r'"(\d+)"\s*\{')
    result: dict[str, tuple[str, int, int]] = {}
    search_start = 0

    while True:
        m = depot_header.search(depots_body, search_start)
        if not m:
            break

        depot_id = m.group(1)
        open_pos = m.end() - 1  # position of '{'
        depth = 1
        pos = open_pos + 1

        while pos < len(depots_body) and depth > 0:
            if depots_body[pos] == "{":
                depth += 1
            elif depots_body[pos] == "}":
                depth -= 1
            pos += 1

        if depth != 0:
            search_start = m.end()
            continue

        close_pos = pos  # one past the closing brace
        block_text = depots_body[m.start() : close_pos]
        abs_start = body_offset + m.start()
        abs_end = body_offset + close_pos

        result[depot_id] = (block_text, abs_start, abs_end)
        search_start = close_pos

    return result


def _extract_key_from_block(block_text: str) -> str | None:
    """Extract the DecryptionKey hex value from a depot block string."""
    m = re.search(r'"DecryptionKey"\s+"([0-9a-fA-F]+)"', block_text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_depot_keys(config_vdf_path: Path) -> VdfKeyState:
    """Read all depot decryption keys from *config_vdf_path*.

    Uses brace-depth-aware parsing to correctly handle depot blocks
    that contain nested sub-blocks (e.g. ``EncryptedManifests``).

    Args:
        config_vdf_path: Path to Steam's ``config.vdf``.

    Returns:
        A :class:`VdfKeyState` with all depot ID to hex-key mappings.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be read.
        ValueError: If the file content is empty.
    """
    path = Path(config_vdf_path)
    content = path.read_text(encoding="utf-8")

    if not content.strip():
        raise ValueError(f"config.vdf is empty: {path}")

    keys: dict[str, str] = {}
    for depot_id, (block_text, _, _) in _extract_depot_blocks(content).items():
        hex_key = _extract_key_from_block(block_text)
        if hex_key:
            keys[depot_id] = hex_key

    logger.debug("Read %d depot decryption keys from %s", len(keys), path)
    return VdfKeyState(keys=keys, total_keys=len(keys))


def add_depot_keys(
    config_vdf_path: Path,
    new_keys: dict[str, str],
    auto_backup: bool = True,
) -> tuple[int, int]:
    """Insert or update depot decryption keys in *config_vdf_path*.

    For each entry in *new_keys*:

    * If the depot already exists with the **same** key -- skip.
    * If the depot already exists with a **different** key -- update in-place.
    * If the depot does **not** exist -- insert a new block before the
      closing brace of the ``"depots"`` section.

    Args:
        config_vdf_path: Path to Steam's ``config.vdf``.
        new_keys: Mapping of depot ID to 64-character hex key.
        auto_backup: Whether to create a backup before modifying. Set to
            ``False`` if the caller already created one.

    Returns:
        A tuple ``(added_count, updated_count)``.

    Raises:
        RuntimeError: If Steam is currently running.
        FileNotFoundError: If the file does not exist.
        ValueError: If the file has unbalanced braces before or after editing.
    """
    from .steam import is_steam_running

    if is_steam_running():
        raise RuntimeError(
            "Cannot modify config.vdf while Steam is running. "
            "Please close Steam and try again."
        )

    path = Path(config_vdf_path)
    content = path.read_text(encoding="utf-8")

    if not _validate_braces(content):
        raise ValueError(
            f"config.vdf has unbalanced braces before modification: {path}"
        )

    if auto_backup:
        backup_config_vdf(path)

    # Parse existing depot blocks (brace-depth-aware)
    existing_blocks = _extract_depot_blocks(content)
    existing_keys: dict[str, str] = {}
    for depot_id, (block_text, _, _) in existing_blocks.items():
        hex_key = _extract_key_from_block(block_text)
        if hex_key:
            existing_keys[depot_id] = hex_key

    added_count = 0
    updated_count = 0
    to_insert: dict[str, str] = {}

    for depot_id, hex_key in new_keys.items():
        if depot_id in existing_keys:
            if existing_keys[depot_id].lower() == hex_key.lower():
                logger.debug("Depot %s already has the correct key, skipping", depot_id)
                continue
            else:
                logger.info("Updating decryption key for depot %s", depot_id)
                block_text, abs_start, abs_end = existing_blocks[depot_id]
                old_key = existing_keys[depot_id]
                new_block = block_text.replace(f'"{old_key}"', f'"{hex_key}"', 1)
                content = content[:abs_start] + new_block + content[abs_end:]
                updated_count += 1
                # Re-parse since positions shifted
                existing_blocks = _extract_depot_blocks(content)
        else:
            to_insert[depot_id] = hex_key

    # Insert new depot blocks
    if to_insert:
        depots_start, depots_end = _find_depots_section(content)
        indent = _detect_depot_indent(content, depots_start, depots_end)
        inner_indent = indent + "\t"

        blocks: list[str] = []
        for depot_id, hex_key in to_insert.items():
            block = (
                f'{indent}"{depot_id}"\n'
                f"{indent}{{\n"
                f'{inner_indent}"DecryptionKey"\t\t"{hex_key}"\n'
                f"{indent}}}"
            )
            blocks.append(block)
            added_count += 1

        insert_text = "\n" + "\n".join(blocks) + "\n"
        content = content[:depots_end] + insert_text + content[depots_end:]

    # Validate braces after modification
    if not _validate_braces(content):
        raise ValueError(
            "config.vdf would have unbalanced braces after modification. "
            "Aborting write -- backup is safe."
        )

    path.write_text(content, encoding="utf-8")
    logger.info(
        "config.vdf updated: %d keys added, %d keys updated",
        added_count,
        updated_count,
    )

    return added_count, updated_count


def backup_config_vdf(config_vdf_path: Path) -> Path:
    """Create a timestamped backup of *config_vdf_path*.

    The backup is placed alongside the original file with the name
    ``config.vdf.backup_YYYYMMDD_HHMMSS``.

    Args:
        config_vdf_path: Path to Steam's ``config.vdf``.

    Returns:
        The path to the newly created backup file.

    Raises:
        FileNotFoundError: If the source file does not exist.
        PermissionError: If the file cannot be copied.
    """
    path = Path(config_vdf_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.parent / f"config.vdf.backup_{timestamp}"

    shutil.copy2(path, backup_path)
    logger.info("Backed up config.vdf to %s", backup_path)
    return backup_path


def verify_keys(
    config_vdf_path: Path,
    expected: dict[str, str],
) -> dict:
    """Compare expected depot keys against the contents of *config_vdf_path*.

    Performs case-insensitive hex comparison.

    Args:
        config_vdf_path: Path to Steam's ``config.vdf``.
        expected: Mapping of depot ID to expected hex key.

    Returns:
        A dict with keys ``"matching"`` (int), ``"mismatched"`` (list of
        depot IDs whose keys differ), and ``"missing"`` (list of depot IDs
        not found in the file).
    """
    state = read_depot_keys(config_vdf_path)

    matching = 0
    mismatched: list[str] = []
    missing: list[str] = []

    for depot_id, expected_key in expected.items():
        if depot_id not in state.keys:
            missing.append(depot_id)
        elif state.keys[depot_id].lower() == expected_key.lower():
            matching += 1
        else:
            mismatched.append(depot_id)

    return {
        "matching": matching,
        "mismatched": mismatched,
        "missing": missing,
    }
