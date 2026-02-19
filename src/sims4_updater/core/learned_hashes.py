"""
Local learned hash database.

Stores version fingerprints learned from:
  - Successful patches (self-learning)
  - Manifest fingerprints (merged on fetch)
  - Crowd-sourced reports (fetched from API)
  - Manual CLI 'learn' command

Persisted at %LocalAppData%/anadius/sims4_updater/learned_hashes.json
"""

import json
import os
import time
from pathlib import Path


def _default_path() -> Path:
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        return Path(local) / "anadius" / "sims4_updater" / "learned_hashes.json"
    return Path.home() / ".config" / "sims4_updater" / "learned_hashes.json"


class LearnedHashDB:
    """Writable local database of version fingerprints."""

    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()
        self.sentinel_files: list[str] = []
        self.versions: dict[str, dict[str, str]] = {}
        self._dirty = False
        self._load()

    def _load(self):
        if not self.path.is_file():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.sentinel_files = data.get("sentinel_files", [])
            self.versions = data.get("versions", {})
        except (json.JSONDecodeError, OSError):
            pass

    def save(self):
        """Write the database to disk (atomic)."""
        if not self._dirty and self.path.is_file():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "sentinel_files": self.sentinel_files,
            "versions": self.versions,
            "updated": int(time.time()),
        }
        tmp = self.path.with_suffix(".json_tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)
        self._dirty = False

    def add_version(self, version: str, hashes: dict[str, str]):
        """Add or update a version's fingerprint.

        Args:
            version: Version string (e.g. "1.120.xxx.1020").
            hashes: Dict of {sentinel_path: md5_hash}.
        """
        if not version or not hashes:
            return

        # Update sentinel list if needed
        for sentinel in hashes:
            if sentinel not in self.sentinel_files:
                self.sentinel_files.append(sentinel)

        existing = self.versions.get(version, {})
        if existing == hashes:
            return  # no change

        self.versions[version] = hashes
        self._dirty = True

    def merge(self, other_versions: dict[str, dict[str, str]]):
        """Merge another set of version fingerprints into this DB.

        Existing entries are updated (new hashes override old ones per sentinel).
        """
        for version, hashes in other_versions.items():
            if not hashes:
                continue
            existing = self.versions.get(version, {})
            merged = {**existing, **hashes}
            if merged != existing:
                self.versions[version] = merged
                self._dirty = True
                for sentinel in hashes:
                    if sentinel not in self.sentinel_files:
                        self.sentinel_files.append(sentinel)

    def has_version(self, version: str) -> bool:
        return version in self.versions

    @property
    def version_count(self) -> int:
        return len(self.versions)
