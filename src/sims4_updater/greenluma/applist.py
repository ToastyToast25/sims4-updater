"""GreenLuma AppList manager — read, write, backup, and modify numbered .txt files."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

APPLIST_LIMIT = 130

__all__ = [
    "APPLIST_LIMIT",
    "AppListState",
    "read_applist",
    "write_applist",
    "backup_applist",
    "add_ids",
    "remove_ids",
    "ensure_applist_dir",
    "ordered_ids_from_state",
]


@dataclass
class AppListState:
    """Snapshot of the current AppList folder contents."""

    entries: dict[str, str]  # filename -> app_id (e.g. "0.txt" -> "1222670")
    unique_ids: set[str]  # deduplicated set of IDs
    count: int  # total file count
    duplicates: list[tuple[str, str]]  # (filename, duplicate_id)


def _is_applist_file(path: Path) -> bool:
    """Check if a file matches the AppList naming pattern (digits-only stem, .txt suffix)."""
    return path.suffix.lower() == ".txt" and path.stem.isdigit()


def read_applist(applist_dir: Path) -> AppListState:
    """Read all numbered .txt files from an AppList directory.

    Parses each file's content as a Steam App/Depot ID, tracks duplicates,
    and returns a structured state object.

    Args:
        applist_dir: Path to the AppList folder.

    Returns:
        AppListState with entries, unique IDs, count, and duplicates.
    """
    entries: dict[str, str] = {}
    unique_ids: set[str] = set()
    duplicates: list[tuple[str, str]] = []

    if not applist_dir.is_dir():
        return AppListState(
            entries=entries, unique_ids=unique_ids, count=0, duplicates=duplicates
        )

    # Collect and sort by numeric index so iteration order is deterministic
    txt_files = sorted(
        (f for f in applist_dir.iterdir() if f.is_file() and _is_applist_file(f)),
        key=lambda p: int(p.stem),
    )

    for filepath in txt_files:
        try:
            content = filepath.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            log.warning("Failed to read AppList file: %s", filepath)
            continue

        if not content:
            log.warning("Empty AppList file: %s", filepath.name)
            continue

        # Validate that content looks like a numeric ID
        if not content.isdigit():
            log.warning(
                "Non-numeric content in AppList file %s: %r", filepath.name, content
            )
            continue

        entries[filepath.name] = content

        if content in unique_ids:
            duplicates.append((filepath.name, content))
        else:
            unique_ids.add(content)

    return AppListState(
        entries=entries,
        unique_ids=unique_ids,
        count=len(entries),
        duplicates=duplicates,
    )


def write_applist(applist_dir: Path, app_ids: list[str]) -> int:
    """Write a sequential set of AppList files, replacing any existing ones.

    Deduplicates the input list (preserving first-seen order) and writes
    ``0.txt``, ``1.txt``, ... into *applist_dir*.

    Args:
        applist_dir: Path to the AppList folder (created if missing).
        app_ids: Ordered list of Steam App/Depot IDs to write.

    Returns:
        Number of files written (after deduplication).

    Raises:
        ValueError: If the deduplicated list exceeds APPLIST_LIMIT.
    """
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for app_id in app_ids:
        if app_id not in seen:
            seen.add(app_id)
            unique.append(app_id)

    if len(unique) > APPLIST_LIMIT:
        raise ValueError(
            f"AppList would contain {len(unique)} entries, "
            f"exceeding the GreenLuma limit of {APPLIST_LIMIT}"
        )

    applist_dir.mkdir(parents=True, exist_ok=True)

    # Remove existing numbered .txt files
    for filepath in applist_dir.iterdir():
        if filepath.is_file() and _is_applist_file(filepath):
            try:
                filepath.unlink()
            except OSError:
                log.warning("Failed to delete old AppList file: %s", filepath)

    # Write new sequential files
    for idx, app_id in enumerate(unique):
        target = applist_dir / f"{idx}.txt"
        target.write_text(app_id, encoding="utf-8")

    log.info("Wrote %d AppList entries to %s", len(unique), applist_dir)
    return len(unique)


def backup_applist(applist_dir: Path) -> Path:
    """Create a timestamped backup of all .txt files in the AppList directory.

    The backup folder is created as a sibling of *applist_dir* with the name
    ``AppList_backup_YYYYMMDD_HHMMSS``.

    Args:
        applist_dir: Path to the AppList folder.

    Returns:
        Path to the newly created backup directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = applist_dir.parent / f"AppList_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for filepath in applist_dir.iterdir():
        if filepath.is_file() and _is_applist_file(filepath):
            shutil.copy2(filepath, backup_dir / filepath.name)

    log.info("Backed up AppList to %s", backup_dir)
    return backup_dir


def add_ids(applist_dir: Path, new_ids: list[str]) -> int:
    """Append new IDs to the AppList, skipping any that already exist.

    Reads the current state, merges in *new_ids* (order-preserving dedup),
    and rewrites the directory sequentially.

    Args:
        applist_dir: Path to the AppList folder.
        new_ids: IDs to add.

    Returns:
        Count of IDs that were actually added (not already present).

    Raises:
        ValueError: If the combined list would exceed APPLIST_LIMIT.
    """
    state = read_applist(applist_dir)

    # Build ordered list from current entries (sorted by index)
    current_ordered = ordered_ids_from_state(state)
    existing = set(state.unique_ids)

    added = 0
    for app_id in new_ids:
        if app_id not in existing:
            current_ordered.append(app_id)
            existing.add(app_id)
            added += 1

    if len(current_ordered) > APPLIST_LIMIT:
        raise ValueError(
            f"Adding {added} IDs would result in {len(current_ordered)} entries, "
            f"exceeding the GreenLuma limit of {APPLIST_LIMIT}"
        )

    write_applist(applist_dir, current_ordered)
    return added


def remove_ids(applist_dir: Path, ids_to_remove: set[str]) -> int:
    """Remove IDs from the AppList and rewrite sequentially to close gaps.

    Args:
        applist_dir: Path to the AppList folder.
        ids_to_remove: Set of IDs to remove.

    Returns:
        Count of IDs that were actually removed.
    """
    state = read_applist(applist_dir)
    current_ordered = ordered_ids_from_state(state)

    filtered = [app_id for app_id in current_ordered if app_id not in ids_to_remove]
    removed = len(current_ordered) - len(filtered)

    if removed > 0:
        write_applist(applist_dir, filtered)

    return removed


def ensure_applist_dir(steam_path: Path) -> Path:
    """Ensure the AppList directory exists under the given Steam path.

    Creates ``{steam_path}/AppList/`` if it does not already exist.

    Args:
        steam_path: Root Steam installation path.

    Returns:
        Path to the AppList directory.
    """
    applist_dir = steam_path / "AppList"
    applist_dir.mkdir(parents=True, exist_ok=True)
    return applist_dir


def ordered_ids_from_state(state: AppListState) -> list[str]:
    """Extract an ordered, deduplicated list of IDs from an AppListState.

    Entries are sorted by their numeric filename index. Duplicates are
    dropped (only the first occurrence is kept).
    """
    sorted_items = sorted(
        state.entries.items(),
        key=lambda item: int(item[0].replace(".txt", "")),
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for _filename, app_id in sorted_items:
        if app_id not in seen:
            seen.add(app_id)
            ordered.append(app_id)
    return ordered
