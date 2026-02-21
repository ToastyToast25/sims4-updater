"""
Steam depotcache manifest file management for GreenLuma integration.

Manages binary .manifest files stored in Steam's ``depotcache/`` directory.
Files follow the naming convention ``{depot_id}_{manifest_id}.manifest``.
This module does not parse the binary content -- it copies and tracks files
by name only.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ManifestState:
    """Snapshot of all .manifest files present in a depotcache directory."""

    files: dict[str, str] = field(default_factory=dict)
    """depot_id -> full filename (e.g. ``"1222671"`` -> ``"1222671_7...manifest"``)."""

    depot_ids: set[str] = field(default_factory=set)
    """Set of all depot IDs present."""

    total_count: int = 0
    """Total number of .manifest files found."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_manifest_filename(depot_id: str, manifest_id: str) -> str:
    """Return the canonical manifest filename for a depot/manifest pair.

    Args:
        depot_id: Steam depot ID (numeric string).
        manifest_id: Steam manifest ID (large numeric string).

    Returns:
        Filename in the form ``{depot_id}_{manifest_id}.manifest``.
    """
    return f"{depot_id}_{manifest_id}.manifest"


def _parse_depot_id(filename: str) -> str | None:
    """Extract the depot ID from a manifest filename.

    Returns ``None`` if the filename does not contain an underscore
    (i.e. it does not follow the expected naming convention).
    """
    underscore_pos = filename.find("_")
    if underscore_pos <= 0:
        return None
    return filename[:underscore_pos]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def read_depotcache(depotcache_dir: Path) -> ManifestState:
    """Scan a depotcache directory and return a structured manifest state.

    Args:
        depotcache_dir: Path to Steam's ``depotcache/`` directory.

    Returns:
        A :class:`ManifestState` describing all ``.manifest`` files found.
        If the directory does not exist or is empty, an empty state is returned.
    """
    state = ManifestState()

    if not depotcache_dir.is_dir():
        logger.debug("Depotcache directory does not exist: %s", depotcache_dir)
        return state

    try:
        entries = list(depotcache_dir.iterdir())
    except OSError as exc:
        logger.warning("Cannot read depotcache directory: %s", exc)
        return state

    for entry in entries:
        if not entry.is_file() or entry.suffix.lower() != ".manifest":
            continue

        filename = entry.name
        depot_id = _parse_depot_id(filename)
        if depot_id is None:
            logger.debug("Skipping manifest with no underscore in name: %s", filename)
            continue

        state.files[depot_id] = filename
        state.depot_ids.add(depot_id)
        state.total_count += 1

    logger.debug(
        "Read depotcache: %d manifest files, %d unique depots",
        state.total_count,
        len(state.depot_ids),
    )
    return state


# ---------------------------------------------------------------------------
# Copying
# ---------------------------------------------------------------------------


def copy_manifests(
    source_dir: Path,
    depotcache_dir: Path,
    overwrite: bool = False,
) -> tuple[int, int]:
    """Copy all .manifest files from *source_dir* into *depotcache_dir*.

    Args:
        source_dir: Directory containing .manifest files to copy.
        depotcache_dir: Target Steam depotcache directory.
        overwrite: If ``False``, skip files whose depot ID already exists
            in *depotcache_dir*. If ``True``, overwrite existing files.

    Returns:
        Tuple of ``(copied_count, skipped_count)``.
    """
    if not source_dir.is_dir():
        logger.warning("Source directory does not exist: %s", source_dir)
        return 0, 0

    depotcache_dir.mkdir(parents=True, exist_ok=True)

    # Pre-scan destination so we know which depot IDs are already present
    existing = read_depotcache(depotcache_dir) if not overwrite else ManifestState()

    copied = 0
    skipped = 0

    try:
        source_files = list(source_dir.iterdir())
    except OSError as exc:
        logger.warning("Cannot read source directory: %s", exc)
        return 0, 0

    for entry in source_files:
        if not entry.is_file() or entry.suffix.lower() != ".manifest":
            continue

        depot_id = _parse_depot_id(entry.name)
        if depot_id is None:
            continue

        if not overwrite and depot_id in existing.depot_ids:
            logger.debug("Skipping existing depot %s: %s", depot_id, entry.name)
            skipped += 1
            continue

        dest_path = depotcache_dir / entry.name
        try:
            shutil.copy2(entry, dest_path)
            copied += 1
            logger.debug("Copied manifest: %s", entry.name)
        except OSError as exc:
            logger.warning("Failed to copy %s: %s", entry.name, exc)
            skipped += 1

    logger.info("Manifest copy complete: %d copied, %d skipped", copied, skipped)
    return copied, skipped


def copy_matching_manifests(
    source_dir: Path,
    depotcache_dir: Path,
    depot_ids: set[str],
    overwrite: bool = False,
) -> tuple[int, int]:
    """Copy .manifest files from *source_dir* that match the given depot IDs.

    Like :func:`copy_manifests` but only copies files whose depot ID is
    in the *depot_ids* set.

    Args:
        source_dir: Directory containing .manifest files to copy.
        depotcache_dir: Target Steam depotcache directory.
        depot_ids: Set of depot IDs to include. Files with depot IDs not
            in this set are ignored entirely.
        overwrite: If ``False``, skip files whose depot ID already exists
            in *depotcache_dir*. If ``True``, overwrite existing files.

    Returns:
        Tuple of ``(copied_count, skipped_count)``.
    """
    if not source_dir.is_dir():
        logger.warning("Source directory does not exist: %s", source_dir)
        return 0, 0

    if not depot_ids:
        logger.debug("Empty depot_ids set — nothing to copy")
        return 0, 0

    depotcache_dir.mkdir(parents=True, exist_ok=True)

    existing = read_depotcache(depotcache_dir) if not overwrite else ManifestState()

    copied = 0
    skipped = 0

    try:
        source_files = list(source_dir.iterdir())
    except OSError as exc:
        logger.warning("Cannot read source directory: %s", exc)
        return 0, 0

    for entry in source_files:
        if not entry.is_file() or entry.suffix.lower() != ".manifest":
            continue

        depot_id = _parse_depot_id(entry.name)
        if depot_id is None:
            continue

        if depot_id not in depot_ids:
            continue

        if not overwrite and depot_id in existing.depot_ids:
            logger.debug("Skipping existing depot %s: %s", depot_id, entry.name)
            skipped += 1
            continue

        dest_path = depotcache_dir / entry.name
        try:
            shutil.copy2(entry, dest_path)
            copied += 1
            logger.debug("Copied manifest: %s", entry.name)
        except OSError as exc:
            logger.warning("Failed to copy %s: %s", entry.name, exc)
            skipped += 1

    logger.info(
        "Matching manifest copy complete: %d copied, %d skipped", copied, skipped
    )
    return copied, skipped


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def find_missing_manifests(
    depotcache_dir: Path,
    expected_depots: dict[str, str],
) -> list[str]:
    """Find depot IDs that are expected but have no matching manifest file.

    Args:
        depotcache_dir: Path to Steam's ``depotcache/`` directory.
        expected_depots: Mapping of ``depot_id`` -> ``manifest_id`` (from
            :class:`~sims4_updater.greenluma.lua_parser.LuaManifest` entries).

    Returns:
        List of depot IDs that appear in *expected_depots* with a non-empty
        manifest_id but have no corresponding file in *depotcache_dir*.
    """
    if not expected_depots:
        return []

    current = read_depotcache(depotcache_dir)
    missing: list[str] = []

    for depot_id, manifest_id in expected_depots.items():
        if not manifest_id:
            continue

        expected_filename = get_manifest_filename(depot_id, manifest_id)
        actual_filename = current.files.get(depot_id)

        if actual_filename != expected_filename:
            missing.append(depot_id)

    if missing:
        logger.debug(
            "Found %d missing manifests out of %d expected",
            len(missing),
            len(expected_depots),
        )

    return missing
