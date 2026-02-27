import errno
import json
import os
from pathlib import Path

from .exceptions import NotEnoughSpaceError, UpdaterError

__all__ = ["load", "save"]


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return None
    except (OSError, PermissionError):
        raise UpdaterError(
            f"Can't read \"{path}\". Make sure your anti-virus doesn't block this program."
        ) from None


def save(path, obj):
    try:
        serialized = json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return

    path = str(path)
    path_tmp = f"{path}_tmp"
    try:
        with open(path_tmp, "w", encoding="utf-8") as f:
            f.write(serialized)
        os.replace(path_tmp, path)
    except (OSError, PermissionError) as e:
        if e.errno == errno.ENOSPC:
            raise NotEnoughSpaceError(
                f"You don't have enough space on {Path(path).anchor} drive!"
            ) from e
        raise UpdaterError(
            f'Can\'t save "{path}". Make sure your '
            "anti-virus doesn't block this program. "
            "If this file exists - move it somewhere else and then copy "
            "it back. If it doesn't exist - do the same with the folder "
            "this file was supposed to be in."
        ) from e
