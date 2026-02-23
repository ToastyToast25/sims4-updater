"""File utilities — re-exported from the patcher library.

The canonical implementations live in ``patcher.files``.  This module
re-exports them so that existing ``from .files import hash_file`` calls
throughout sims4-updater continue to work without changes.
"""

from __future__ import annotations

from patcher.files import (
    HASH_CHUNK_SIZE,
    copyfileobj,
    delete_empty_dirs,
    get_files_dict,
    get_files_set,
    get_short_path,
    hash_file,
    write_check,
)

__all__ = [
    "HASH_CHUNK_SIZE",
    "copyfileobj",
    "delete_empty_dirs",
    "get_files_dict",
    "get_files_set",
    "get_short_path",
    "hash_file",
    "write_check",
]
