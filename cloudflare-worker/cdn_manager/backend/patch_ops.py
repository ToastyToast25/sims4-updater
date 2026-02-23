"""Patch operations — version registry and PatchMaker integration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Event

from .connection import CDN_DOMAIN, SEEDBOX_BASE_DIR, ConnectionManager
from .dlc_ops import fmt_size, md5_file


def load_version_hashes() -> dict:
    """Load the version fingerprint database.

    Returns {version_string: {relative_path: md5_hash}}.
    Looks in data/version_hashes.json relative to the project root.
    """
    # In source mode: sims4-updater/data/version_hashes.json
    project_root = Path(__file__).resolve().parents[3]
    hashes_path = project_root / "data" / "version_hashes.json"

    if not hashes_path.is_file() and getattr(sys, "frozen", False):
        hashes_path = Path(sys.executable).parent / "data" / "version_hashes.json"

    if not hashes_path.is_file():
        return {}

    try:
        data = json.loads(hashes_path.read_text(encoding="utf-8"))
        return data.get("versions", {})
    except (json.JSONDecodeError, OSError):
        return {}


def detect_version_fingerprint(game_dir: str) -> tuple[str | None, float]:
    """Detect game version by hashing sentinel files and matching against database.

    Returns (version_string, confidence) where confidence is 0.0-1.0.
    Returns (None, 0.0) if no match found.
    """
    versions_db = load_version_hashes()
    if not versions_db:
        return None, 0.0

    # Load sentinel file list from the DB structure
    dir_path = Path(game_dir)
    if not dir_path.is_dir():
        return None, 0.0

    # Hash all sentinel files that exist
    sentinel_hashes: dict[str, str] = {}
    all_sentinels: set[str] = set()
    for _ver, file_hashes in versions_db.items():
        for rel_path in file_hashes:
            all_sentinels.add(rel_path)

    for rel_path in all_sentinels:
        full_path = dir_path / rel_path.replace("/", "\\")
        if full_path.is_file():
            sentinel_hashes[rel_path] = md5_file(full_path)

    if not sentinel_hashes:
        return None, 0.0

    # Match against known versions
    best_match: str | None = None
    best_score = 0.0

    for version, file_hashes in versions_db.items():
        if not file_hashes:
            continue
        matches = 0
        total = len(file_hashes)
        for rel_path, expected_md5 in file_hashes.items():
            actual = sentinel_hashes.get(rel_path)
            if actual and actual == expected_md5:
                matches += 1

        score = matches / total if total > 0 else 0.0
        if score > best_score:
            best_score = score
            best_match = version

    if best_score >= 0.5:
        return best_match, best_score

    return None, 0.0


def parse_version_from_default_ini(game_dir: str) -> str | None:
    """Fallback: parse version from Game/Bin/Default.ini.

    Looks for a line like 'gameversion = 1.121.372.1020'.
    Returns the version string or None.
    """
    dir_path = Path(game_dir)
    for candidate in [
        dir_path / "Game" / "Bin" / "Default.ini",
        dir_path / "Game-cracked" / "Bin" / "Default.ini",
    ]:
        if candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line.lower().startswith("gameversion"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            ver = parts[1].strip()
                            # Validate format: digits and dots (e.g. 1.121.372.1020)
                            if ver and all(c.isdigit() or c == "." for c in ver):
                                return ver
            except OSError:
                continue
    return None


def get_patcher_dir(config_patcher_dir: str) -> Path | None:
    """Resolve the patcher directory. Returns None if not found."""
    if config_patcher_dir:
        p = Path(config_patcher_dir)
        if p.is_dir():
            return p

    # Default: ../patcher relative to sims4-updater repo root
    repo_root = Path(__file__).resolve().parents[3]
    default = repo_root.parent / "patcher"
    if default.is_dir():
        return default

    return None


def inject_patcher_path(patcher_dir: Path) -> None:
    """Add patcher directory to sys.path for PatchMaker imports."""
    patcher_str = str(patcher_dir)
    if patcher_str not in sys.path:
        sys.path.insert(0, patcher_str)


def load_version_registry(config_path: Path) -> list[dict]:
    """Load the version registry from the config file.

    Each entry: {version, directory, verified, file_count, date_added}.
    """
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data.get("version_registry", [])
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_version_registry(config_path: Path, registry: list[dict]) -> None:
    """Save the version registry to the config file."""
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}
    data["version_registry"] = registry
    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def register_version(
    directory: str,
    version: str,
    registry: list[dict],
) -> dict:
    """Register a game directory as a version.

    Returns the new registry entry. Includes fingerprint verification if possible.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    # Count files
    file_count = sum(1 for f in dir_path.rglob("*") if f.is_file())

    # Fingerprint verification
    detected_version, confidence = detect_version_fingerprint(directory)
    verified = False
    if detected_version and detected_version == version and confidence >= 0.5:
        verified = True

    from datetime import datetime

    entry = {
        "version": version,
        "directory": str(dir_path),
        "verified": verified,
        "fingerprint_match": detected_version,
        "fingerprint_confidence": confidence,
        "file_count": file_count,
        "date_added": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    # Remove existing entry for same version
    registry[:] = [e for e in registry if e["version"] != version]
    registry.append(entry)
    return entry


def create_patch(
    from_dir: str,
    to_dir: str,
    from_version: str,
    to_version: str,
    patcher_dir: Path,
    output_dir: Path,
    *,
    cancel_event: Event | None = None,
    log_cb=None,
    progress_cb=None,
) -> Path | None:
    """Create a delta patch between two game directories.

    Returns path to the created patch ZIP, or None on failure/cancel.
    """

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    inject_patcher_path(patcher_dir)

    try:
        from patcher.patch_maker import PatchMaker
    except ImportError as e:
        log(f"PatchMaker import failed: {e}", "error")
        log("Ensure ../patcher/ directory exists with patcher/patch_maker.py", "warning")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{from_version}_to_{to_version}.zip"

    log(f"Creating patch: {from_version} -> {to_version}")
    log(f"From: {from_dir}")
    log(f"To: {to_dir}")

    # Resolve xdelta3 tool path
    tools_dir = patcher_dir / "tools"
    xdelta_path = tools_dir / "xdelta3-x64.exe"
    if not xdelta_path.is_file():
        xdelta_path = tools_dir / "xdelta3.exe"

    if not xdelta_path.is_file():
        log(f"xdelta3 not found in {tools_dir}", "error")
        return None

    try:
        maker = PatchMaker(
            old_dir=from_dir,
            new_dir=to_dir,
            xdelta_path=str(xdelta_path),
        )

        def _progress_wrapper(stage: str, current: int, total: int):
            if log_cb:
                log_cb(f"[{stage}] {current}/{total}", "debug")
            if progress_cb:
                progress_cb(current, total)
            if cancel_event and cancel_event.is_set():
                raise KeyboardInterrupt("Cancelled")

        result = maker.make_patch(
            output_path=str(output_path),
            progress_callback=_progress_wrapper,
        )

        if result and output_path.is_file():
            size = output_path.stat().st_size
            log(f"Patch created: {fmt_size(size)}", "success")
            return output_path
        else:
            log("Patch creation returned no result", "error")
            return None

    except KeyboardInterrupt:
        log("Patch creation cancelled", "warning")
        output_path.unlink(missing_ok=True)
        return None
    except Exception as e:
        log(f"Patch creation failed: {e}", "error")
        output_path.unlink(missing_ok=True)
        return None


def upload_patch(
    conn: ConnectionManager,
    patch_path: Path,
    from_version: str,
    to_version: str,
    *,
    log_cb=None,
    progress_cb=None,
) -> dict | None:
    """Upload a patch to CDN and return a manifest entry."""

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    cdn_path = f"patches/{from_version}_to_{to_version}.zip"
    remote_path = f"{SEEDBOX_BASE_DIR}/{cdn_path}"

    patch_size = patch_path.stat().st_size
    patch_md5 = md5_file(patch_path)

    log(f"Uploading patch ({fmt_size(patch_size)})...")

    try:
        conn.upload_sftp(patch_path, remote_path, progress_cb=progress_cb)
        conn.kv_put(cdn_path, remote_path)
        log("Patch uploaded and registered", "success")
    except Exception as e:
        log(f"Upload failed: {e}", "error")
        return None

    return {
        "from_version": from_version,
        "to_version": to_version,
        "url": f"{CDN_DOMAIN}/{cdn_path}",
        "size": patch_size,
        "md5": patch_md5,
    }
