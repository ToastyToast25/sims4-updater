"""Improved zipfile module — re-exported from the patcher library.

The canonical implementation lives in ``patcher.myzipfile``.  This module
re-exports it so that existing ``from .core import myzipfile`` calls
throughout sims4-updater continue to work.
"""

from patcher.myzipfile import *  # noqa: F401, F403
