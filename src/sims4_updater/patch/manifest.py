"""
Manifest parsing and validation.

The manifest is a JSON file hosted at a known URL that describes
available patches and their download locations. This decouples the
updater from any specific hosting — patches can live anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.exceptions import ManifestError


@dataclass
class FileEntry:
    """A single downloadable file (patch archive or crack)."""

    url: str
    size: int
    md5: str
    filename: str = ""  # derived from URL if not specified

    def __post_init__(self):
        if not self.filename:
            self.filename = self.url.rsplit("/", 1)[-1].split("?")[0]


@dataclass
class PatchEntry:
    """A single version-to-version patch with downloadable files."""

    version_from: str
    version_to: str
    files: list[FileEntry] = field(default_factory=list)
    crack: FileEntry | None = None

    @property
    def total_size(self) -> int:
        total = sum(f.size for f in self.files)
        if self.crack:
            total += self.crack.size
        return total


@dataclass
class Manifest:
    """Parsed manifest describing all available patches."""

    latest: str
    patches: list[PatchEntry] = field(default_factory=list)
    manifest_url: str = ""

    def get_patch(self, version_from: str, version_to: str) -> PatchEntry | None:
        for p in self.patches:
            if p.version_from == version_from and p.version_to == version_to:
                return p
        return None

    @property
    def all_versions(self) -> set[str]:
        versions = {self.latest}
        for p in self.patches:
            versions.add(p.version_from)
            versions.add(p.version_to)
        return versions


def parse_manifest(data: dict, source_url: str = "") -> Manifest:
    """Parse a manifest dict into a Manifest object.

    Raises ManifestError on invalid data.
    """
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON object.")

    latest = data.get("latest")
    if not latest or not isinstance(latest, str):
        raise ManifestError("Manifest missing 'latest' version string.")

    patches_raw = data.get("patches", [])
    if not isinstance(patches_raw, list):
        raise ManifestError("Manifest 'patches' must be a list.")

    patches = []
    for i, entry in enumerate(patches_raw):
        try:
            patches.append(_parse_patch_entry(entry))
        except (KeyError, TypeError, ValueError) as e:
            raise ManifestError(f"Invalid patch entry at index {i}: {e}") from e

    return Manifest(latest=latest, patches=patches, manifest_url=source_url)


def _parse_patch_entry(entry: dict) -> PatchEntry:
    """Parse a single patch entry from manifest data."""
    version_from = entry["from"]
    version_to = entry["to"]

    files = []
    for f in entry.get("files", []):
        files.append(FileEntry(
            url=f["url"],
            size=int(f.get("size", 0)),
            md5=f.get("md5", ""),
            filename=f.get("filename", ""),
        ))

    crack = None
    crack_data = entry.get("crack")
    if crack_data and isinstance(crack_data, dict):
        crack = FileEntry(
            url=crack_data["url"],
            size=int(crack_data.get("size", 0)),
            md5=crack_data.get("md5", ""),
            filename=crack_data.get("filename", ""),
        )

    return PatchEntry(
        version_from=version_from,
        version_to=version_to,
        files=files,
        crack=crack,
    )
