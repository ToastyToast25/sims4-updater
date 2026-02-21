"""
DLC Contribution Scanner -- detects installed DLCs not in the CDN manifest
and submits metadata to the contribution API for review.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from .. import VERSION

log = logging.getLogger(__name__)

# Contribution API endpoint
CONTRIBUTE_URL = "https://api.hyperabyss.com/contribute"


@dataclass
class FileMetadata:
    """Metadata for a single file in a DLC folder."""

    name: str
    size: int
    md5: str


@dataclass
class DLCContribution:
    """A contribution payload for a missing DLC."""

    dlc_id: str
    dlc_name: str
    files: list[FileMetadata] = field(default_factory=list)
    app_version: str = ""

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    def to_dict(self) -> dict:
        return {
            "dlc_id": self.dlc_id,
            "dlc_name": self.dlc_name,
            "files": [asdict(f) for f in self.files],
            "app_version": self.app_version,
        }


def _md5_file(path: Path) -> str:
    """Compute MD5 hash of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_dlc_folder(dlc_dir: Path, progress=None) -> list[FileMetadata]:
    """
    Scan a DLC folder and return metadata for all files.

    Args:
        dlc_dir: Path to the DLC folder (e.g. game_dir/EP01).
        progress: Optional callback(current, total, filename).

    Returns:
        List of FileMetadata for each file in the folder.
    """
    if not dlc_dir.is_dir():
        return []

    files = sorted(f for f in dlc_dir.rglob("*") if f.is_file())
    results = []

    for i, fpath in enumerate(files):
        if progress:
            progress(i, len(files), fpath.name)

        try:
            rel_name = fpath.relative_to(dlc_dir).as_posix()
            size = fpath.stat().st_size
            md5 = _md5_file(fpath)
            results.append(FileMetadata(name=rel_name, size=size, md5=md5))
        except OSError:
            log.warning("Could not read file: %s", fpath)

    if progress:
        progress(len(files), len(files), "")

    return results


def find_missing_dlcs(
    game_dir: Path,
    manifest_dlc_ids: set[str],
    catalog_dlcs: list,
) -> list[tuple[str, str]]:
    """
    Find DLCs installed on disk but not available in the CDN manifest.

    Args:
        game_dir: Path to game installation.
        manifest_dlc_ids: Set of DLC IDs that already have CDN downloads.
        catalog_dlcs: List of DLCInfo from the catalog.

    Returns:
        List of (dlc_id, dlc_name) tuples for missing DLCs.
    """
    missing = []
    for dlc in catalog_dlcs:
        dlc_dir = game_dir / dlc.id
        if not dlc_dir.is_dir():
            continue

        # Must have the main package file to be considered complete
        if not (dlc_dir / "SimulationFullBuild0.package").is_file():
            continue

        # Already in manifest = not missing
        if dlc.id in manifest_dlc_ids:
            continue

        missing.append((dlc.id, dlc.name_en))

    return missing


def submit_contribution(
    contribution: DLCContribution,
    timeout: int = 30,
) -> dict:
    """
    Submit a DLC contribution to the API.

    Args:
        contribution: The contribution payload.
        timeout: Request timeout in seconds.

    Returns:
        API response dict with 'status' and 'message' keys.

    Raises:
        requests.RequestException: On network errors.
    """
    contribution.app_version = VERSION

    resp = requests.post(
        CONTRIBUTE_URL,
        json=contribution.to_dict(),
        timeout=timeout,
        headers={"Content-Type": "application/json"},
    )

    if resp.status_code == 429:
        return {"status": "rate_limited", "message": "Too many submissions. Try again later."}

    if resp.status_code != 200:
        return {"status": "error", "message": f"Server error ({resp.status_code})"}

    return resp.json()


def scan_and_submit(
    game_dir: Path,
    dlc_id: str,
    dlc_name: str,
    progress=None,
) -> dict:
    """
    Scan a single DLC folder and submit its metadata.

    Args:
        game_dir: Path to game installation.
        dlc_id: DLC ID to scan (e.g. "EP01").
        dlc_name: Human-readable DLC name.
        progress: Optional callback(current, total, filename).

    Returns:
        API response dict.
    """
    dlc_dir = game_dir / dlc_id

    if not dlc_dir.is_dir():
        return {"status": "error", "message": f"DLC folder not found: {dlc_dir}"}

    # Scan files
    files = scan_dlc_folder(dlc_dir, progress=progress)

    if not files:
        return {"status": "error", "message": "No files found in DLC folder."}

    # Build and submit
    contribution = DLCContribution(
        dlc_id=dlc_id,
        dlc_name=dlc_name,
        files=files,
    )

    return submit_contribution(contribution)
