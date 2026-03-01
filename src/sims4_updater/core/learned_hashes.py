"""
Local learned hash database.

Stores version fingerprints learned from:
  - Successful patches (self-learning)
  - Manifest fingerprints (merged on fetch)
  - Crowd-sourced reports (fetched from API)
  - Manual CLI 'learn' command

Persisted at %LocalAppData%/ToastyToast25/sims4_updater/learned_hashes.json
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from ..config import get_app_dir

logger = logging.getLogger(__name__)


def _default_path() -> Path:
    return get_app_dir() / "learned_hashes.json"


class LearnedHashDB:
    """Writable local database of version fingerprints."""

    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()
        self.sentinel_files: list[str] = []
        self.versions: dict[str, dict[str, str]] = {}
        self._dirty = False
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if not self.path.is_file():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Root must be a JSON object")
            self.sentinel_files = data.get("sentinel_files", [])
            self.versions = data.get("versions", {})
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Corrupt learned hash DB at %s: %s — starting fresh", self.path, e)
            # Back up corrupt file so user data isn't lost
            backup = self.path.with_suffix(".json.corrupt")
            try:
                os.replace(self.path, backup)
                logger.info("Backed up corrupt DB to %s", backup)
            except OSError:
                pass
        except OSError as e:
            logger.warning("Could not read learned hash DB: %s", e)

    def save(self):
        """Write the database to disk (atomic)."""
        with self._lock:
            if not self._dirty and self.path.is_file():
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "sentinel_files": list(self.sentinel_files),
                "versions": {v: dict(h) for v, h in self.versions.items()},
                "updated": int(time.time()),
            }
            self._dirty = False
        tmp = self.path.with_suffix(".json_tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def add_version(self, version: str, hashes: dict[str, str]):
        """Add or update a version's fingerprint.

        Args:
            version: Version string (e.g. "1.120.xxx.1020").
            hashes: Dict of {sentinel_path: md5_hash}.
        """
        if not version or not hashes:
            return

        with self._lock:
            for sentinel in hashes:
                if sentinel not in self.sentinel_files:
                    self.sentinel_files.append(sentinel)

            existing = self.versions.get(version, {})
            if existing == hashes:
                return  # no change

            self.versions[version] = hashes
            self._dirty = True

    _MD5_RE = __import__("re").compile(r"^[0-9a-fA-F]{32}$")
    _MAX_VERSIONS = 5000  # sanity cap on total version count
    _MAX_SENTINELS_PER_VERSION = 50

    def merge(self, other_versions: dict[str, dict[str, str]]):
        """Merge another set of version fingerprints into this DB.

        Existing entries are updated (new hashes override old ones per sentinel).
        Malformed entries (bad types, invalid MD5 hex, excessive counts) are skipped.
        """
        if not isinstance(other_versions, dict):
            logger.warning(
                "Ignoring fingerprints: expected dict, got %s",
                type(other_versions).__name__,
            )
            return

        with self._lock:
            for version, hashes in other_versions.items():
                if not isinstance(version, str) or not isinstance(hashes, dict):
                    continue
                if not hashes or len(hashes) > self._MAX_SENTINELS_PER_VERSION:
                    continue
                if len(self.versions) >= self._MAX_VERSIONS and version not in self.versions:
                    logger.debug("Skipping version %s — DB at capacity", version)
                    continue

                # Validate each hash is a 32-char hex MD5
                clean: dict[str, str] = {}
                for sentinel, md5 in hashes.items():
                    if (
                        isinstance(sentinel, str)
                        and isinstance(md5, str)
                        and self._MD5_RE.match(md5)
                    ):
                        clean[sentinel] = md5

                if not clean:
                    continue

                existing = self.versions.get(version, {})
                merged = {**existing, **clean}
                if merged != existing:
                    self.versions[version] = merged
                    self._dirty = True
                    for sentinel in clean:
                        if sentinel not in self.sentinel_files:
                            self.sentinel_files.append(sentinel)

    def has_version(self, version: str) -> bool:
        return version in self.versions

    @property
    def version_count(self) -> int:
        return len(self.versions)
