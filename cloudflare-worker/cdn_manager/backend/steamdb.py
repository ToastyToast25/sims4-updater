"""SteamDB manifest data — bundled database, clipboard parser, HTTP scraper.

Provides manifest discovery for Steam depots by:
1. Loading a bundled manifest database (scraped from SteamDB)
2. Parsing clipboard data in multiple formats (DepotDownloader, JSON, plain text)
3. Attempting live HTTP scrape from SteamDB (may fail due to Cloudflare)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# JS snippet the user can paste into the SteamDB browser console to extract all manifests
STEAMDB_JS_SNIPPET = (
    "(()=>{const d=[];document.querySelectorAll('table tr').forEach(r=>{"
    "const c=r.querySelectorAll('td');"
    "if(c.length>=3){const l=c[2]?.querySelector('a');"
    "if(l&&/^\\\\d{10,}$/.test(l.textContent.trim())){"
    "d.push({date:c[0].textContent.trim().split(' \\u2013 ')[0],"
    "manifest_id:l.textContent.trim()})}}});"
    "navigator.clipboard.writeText(JSON.stringify(d,null,2));"
    "alert('Copied '+d.length+' manifests!')})()"
)


@dataclass
class SteamDBManifest:
    """A single manifest entry from SteamDB."""

    date: str  # ISO date or human-readable
    manifest_id: str
    depot_id: str = "1222671"
    version: str = ""  # Game version string (e.g. "1.121.372.1020")


def _get_cdn_manager_data_dir() -> Path:
    """Resolve the cdn_manager data directory (frozen or source)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "cdn_manager_data"
    return Path(__file__).resolve().parent.parent / "data"


def load_bundled_manifests() -> list[SteamDBManifest]:
    """Load the bundled SteamDB manifest database.

    Returns list of SteamDBManifest sorted by date (newest first).
    """
    data_file = _get_cdn_manager_data_dir() / "sims4_depot_manifests.json"
    if not data_file.is_file():
        return []

    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
        depot_id = data.get("depot_id", "1222671")
        manifests = []
        for entry in data.get("manifests", []):
            manifests.append(
                SteamDBManifest(
                    date=entry.get("date", ""),
                    manifest_id=entry.get("manifest_id", ""),
                    depot_id=depot_id,
                    version=entry.get("version", ""),
                )
            )
        return manifests
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def parse_clipboard_text(text: str) -> list[SteamDBManifest]:
    """Parse manifest data from clipboard text in multiple formats.

    Supported formats:
    - JSON array: [{"date": "...", "manifest_id": "..."}]
    - DepotDownloader commands: -manifest 1234567890
    - Plain manifest IDs: one per line (16+ digit numbers)
    - Tab-separated: date\\tmanifest_id
    """
    text = text.strip()
    if not text:
        return []

    # Try JSON first
    if text.startswith("["):
        try:
            entries = json.loads(text)
            results = []
            for entry in entries:
                if isinstance(entry, dict) and "manifest_id" in entry:
                    results.append(
                        SteamDBManifest(
                            date=entry.get("date", ""),
                            manifest_id=str(entry["manifest_id"]),
                        )
                    )
            if results:
                return results
        except json.JSONDecodeError:
            pass

    results = []
    seen = set()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # DepotDownloader format: -manifest 1234567890
        m = re.search(r"-manifest\s+(\d{10,})", line)
        if m:
            mid = m.group(1)
            if mid not in seen:
                seen.add(mid)
                results.append(SteamDBManifest(date="", manifest_id=mid))
            continue

        # Steam console format: download_depot 1222670 1222671 1234567890
        m = re.search(r"download_depot\s+\d+\s+\d+\s+(\d{10,})", line)
        if m:
            mid = m.group(1)
            if mid not in seen:
                seen.add(mid)
                results.append(SteamDBManifest(date="", manifest_id=mid))
            continue

        # Tab/comma separated: date, manifest_id (or manifest_id, date)
        parts = re.split(r"[\t,;|]+", line)
        if len(parts) >= 2:
            for part in parts:
                part = part.strip()
                if re.match(r"^\d{16,}$", part):
                    if part not in seen:
                        seen.add(part)
                        # Try to find a date in the other parts
                        date = ""
                        for other in parts:
                            other = other.strip()
                            if other != part and re.search(r"\d{4}", other):
                                date = other
                                break
                        results.append(SteamDBManifest(date=date, manifest_id=part))
                    break
            else:
                # No manifest ID found in parts, try plain number
                if re.match(r"^\d{16,}$", line) and line not in seen:
                    seen.add(line)
                    results.append(SteamDBManifest(date="", manifest_id=line))
            continue

        # Plain manifest ID (16+ digit number on its own line)
        if re.match(r"^\d{16,}$", line) and line not in seen:
            seen.add(line)
            results.append(SteamDBManifest(date="", manifest_id=line))

    return results


def scrape_steamdb_manifests(
    depot_id: str = "1222671",
    timeout: int = 15,
) -> tuple[list[SteamDBManifest], str]:
    """Attempt to scrape manifest data from SteamDB via HTTP.

    Returns (manifests, error_message). If scraping fails (Cloudflare block,
    login required), returns empty list with a helpful error message.

    Note: SteamDB uses Cloudflare protection and JavaScript rendering.
    This will likely fail — it's provided as a best-effort first attempt.
    The clipboard import and bundled database are the reliable fallbacks.
    """
    url = f"https://steamdb.info/depot/{depot_id}/manifests/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return [], (
                "SteamDB blocked the request (Cloudflare protection).\n"
                "Use 'Load Bundled' to load the built-in manifest database,\n"
                "or use 'Open SteamDB' + clipboard import for the latest data."
            )
        return [], f"HTTP error {e.code}: {e.reason}"
    except Exception as e:
        return [], f"Request failed: {e}"

    # Parse HTML — SteamDB renders manifest IDs in table cells
    manifests = []
    seen = set()

    # Look for manifest IDs (16+ digit numbers) near date patterns
    for m in re.finditer(r"(\d{1,2}\s+\w+\s+\d{4})\s*.*?(\d{16,})", html):
        date_str = m.group(1)
        manifest_id = m.group(2)
        if manifest_id not in seen:
            seen.add(manifest_id)
            manifests.append(
                SteamDBManifest(date=date_str, manifest_id=manifest_id, depot_id=depot_id)
            )

    if not manifests:
        return [], (
            "Could not parse manifest data from SteamDB response.\n"
            "The page may require JavaScript rendering or login.\n"
            "Use 'Load Bundled' or the clipboard import instead."
        )

    return manifests, ""
