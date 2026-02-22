"""
GreenLuma contribution scanner — extract depot keys and manifest files
from a user's Steam installation for DLCs that the CDN doesn't cover yet.

When a user legitimately owns DLCs through Steam, their machine has:
  - Decryption keys in config.vdf
  - Binary .manifest files in depotcache/

This module extracts that data and submits it to the contribution API
so it can be reviewed, approved, and distributed to other users.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field

import requests

from .. import VERSION
from ..constants import CONTRIBUTE_URL
from . import config_vdf, manifest_cache
from .orchestrator import DLCReadiness
from .steam import SteamInfo

log = logging.getLogger(__name__)

# Use the same base URL but different path for GL contributions
GL_CONTRIBUTE_PATH = "/contribute/greenluma"


@dataclass
class DepotContribution:
    """A single depot's GreenLuma data ready for submission."""

    depot_id: str  # Steam depot/app ID (e.g. "3199780")
    dlc_id: str  # Catalog DLC ID (e.g. "EP19")
    dlc_name: str  # Human-readable name
    decryption_key: str  # 64-char hex from config.vdf
    manifest_id: str  # Extracted from depotcache filename
    manifest_b64: str  # Base64-encoded .manifest binary file


@dataclass
class ScanResult:
    """Result of scanning for contributable GreenLuma data."""

    contributions: list[DepotContribution] = field(default_factory=list)
    skipped_no_key: list[str] = field(default_factory=list)
    skipped_no_manifest: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.contributions)


def scan_gl_contributions(
    steam_info: SteamInfo,
    readiness: list[DLCReadiness],
    progress=None,
) -> ScanResult:
    """Find incomplete DLCs where this user has the key + manifest.

    Scans config.vdf for decryption keys and depotcache for .manifest files
    for any DLCs that are not yet "ready" in the GreenLuma readiness check.

    Args:
        steam_info: SteamInfo with paths to config.vdf and depotcache.
        readiness: List of DLCReadiness from orchestrator.check_readiness().
        progress: Optional callback(message: str).

    Returns:
        ScanResult with contributable depots and skip reasons.
    """
    result = ScanResult()

    # Only look at incomplete DLCs
    incomplete = [r for r in readiness if not r.ready]
    if not incomplete:
        return result

    if progress:
        progress(f"Scanning {len(incomplete)} incomplete DLCs...")

    # Read current depot keys and manifest state
    vdf_state = config_vdf.read_depot_keys(steam_info.config_vdf_path)
    mc_state = manifest_cache.read_depotcache(steam_info.depotcache_dir)

    for r in incomplete:
        depot_id = str(r.steam_app_id)

        # Check for decryption key
        key = vdf_state.keys.get(depot_id)
        if not key:
            result.skipped_no_key.append(r.dlc_id)
            continue

        # Check for manifest file
        manifest_filename = mc_state.files.get(depot_id)
        if not manifest_filename:
            result.skipped_no_manifest.append(r.dlc_id)
            continue

        # Extract manifest_id from filename: "{depot_id}_{manifest_id}.manifest"
        manifest_id = _extract_manifest_id(manifest_filename, depot_id)
        if not manifest_id:
            result.skipped_no_manifest.append(r.dlc_id)
            continue

        # Read and base64 encode the .manifest binary file
        manifest_path = steam_info.depotcache_dir / manifest_filename
        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest_b64 = base64.b64encode(manifest_bytes).decode("ascii")
        except OSError as e:
            log.warning("Cannot read manifest file %s: %s", manifest_path, e)
            result.skipped_no_manifest.append(r.dlc_id)
            continue

        if progress:
            progress(f"Found: {r.dlc_id} ({r.name}) — key + manifest")

        result.contributions.append(
            DepotContribution(
                depot_id=depot_id,
                dlc_id=r.dlc_id,
                dlc_name=r.name,
                decryption_key=key,
                manifest_id=manifest_id,
                manifest_b64=manifest_b64,
            )
        )

    if progress:
        progress(
            f"Scan complete: {result.count} contributable, "
            f"{len(result.skipped_no_key)} missing key, "
            f"{len(result.skipped_no_manifest)} missing manifest"
        )

    return result


def submit_gl_contribution(
    contributions: list[DepotContribution],
    url: str = "",
    timeout: int = 60,
) -> dict:
    """Submit GreenLuma contributions to the API.

    Args:
        contributions: List of DepotContribution to submit.
        url: Override the API base URL.
        timeout: HTTP timeout in seconds.

    Returns:
        API response dict with 'status' and 'message' keys.
    """
    if not contributions:
        return {"status": "error", "message": "No contributions to submit."}

    # Derive the GL contribute URL from the base contribute URL
    base_url = url or CONTRIBUTE_URL
    if not base_url:
        return {"status": "error", "message": "Contribution URL not configured."}

    # Replace /contribute with /contribute/greenluma
    if base_url.endswith("/contribute"):
        endpoint = base_url + "/greenluma"
    else:
        endpoint = base_url.rstrip("/") + GL_CONTRIBUTE_PATH

    payload = {
        "entries": [
            {
                "depot_id": c.depot_id,
                "dlc_id": c.dlc_id,
                "dlc_name": c.dlc_name,
                "key": c.decryption_key,
                "manifest_id": c.manifest_id,
                "manifest_b64": c.manifest_b64,
            }
            for c in contributions
        ],
        "app_version": VERSION,
    }

    resp = requests.post(
        endpoint,
        json=payload,
        timeout=timeout,
        headers={"Content-Type": "application/json"},
    )

    if resp.status_code == 429:
        return {"status": "rate_limited", "message": "Too many submissions. Try again later."}

    if resp.status_code != 200:
        return {"status": "error", "message": f"Server error ({resp.status_code})"}

    return resp.json()


def _extract_manifest_id(filename: str, depot_id: str) -> str:
    """Extract manifest_id from a depotcache filename.

    Filename format: "{depot_id}_{manifest_id}.manifest"
    """
    prefix = depot_id + "_"
    suffix = ".manifest"
    if filename.startswith(prefix) and filename.endswith(suffix):
        return filename[len(prefix) : -len(suffix)]
    return ""
