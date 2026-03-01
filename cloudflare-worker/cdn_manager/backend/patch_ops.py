"""Patch operations — version registry and PatchMaker integration."""

from __future__ import annotations

import json
import os
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

    # Walk up from this file looking for a sibling "patcher/" directory.
    # Works in both source mode and frozen (PyInstaller) mode.
    current = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = current.parent / "patcher"
        if candidate.is_dir():
            return candidate
        current = current.parent

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

    # Resolve xdelta3 tool path — PatchMaker calls bare "xdelta3" so we
    # need an exe named exactly "xdelta3.exe" on PATH.
    tools_dir = patcher_dir / "tools"
    xdelta_canonical = tools_dir / "xdelta3.exe"

    # If only xdelta3-x64.exe exists, copy it to xdelta3.exe so PatchMaker finds it
    if not xdelta_canonical.is_file():
        for candidate in ("xdelta3-x64.exe", "xdelta3-x86.exe"):
            src = tools_dir / candidate
            if src.is_file():
                import shutil

                shutil.copy2(src, xdelta_canonical)
                log(f"Copied {candidate} -> xdelta3.exe", "debug")
                break

    if not xdelta_canonical.is_file():
        log(f"xdelta3 not found in {tools_dir}", "error")
        return None

    # Put tools dir on PATH so PatchMaker can find xdelta3
    tools_str = str(tools_dir)
    env_path = os.environ.get("PATH", "")
    if tools_str not in env_path:
        os.environ["PATH"] = tools_str + os.pathsep + env_path

    try:

        def _callback(callback_type: str, *args):
            if cancel_event and cancel_event.is_set():
                raise KeyboardInterrupt("Cancelled")
            if callback_type == "xdelta":
                log(f"  xdelta: {args[0]}", "debug")
            elif callback_type == "hashing":
                log(f"  hashing: {Path(args[0]).name}", "debug")

        maker = PatchMaker(game_name="The Sims 4", callback=_callback)

        result = maker.make_patch(
            output_path=str(output_path),
            version_from=from_version,
            version_to=to_version,
            folder_from=from_dir,
            folder_to=to_dir,
            extension=".xdelta",
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
    patch_md5 = md5_file(patch_path).lower()

    # Skip upload if already on seedbox with matching size + hash
    try:
        remote_size = conn.file_size_sftp(remote_path)
        if remote_size == patch_size:
            log(f"Patch exists on seedbox ({fmt_size(patch_size)}), verifying hash...")
            remote_md5 = conn.md5_remote_sftp(remote_path)
            if remote_md5 == patch_md5:
                log("Hash verified, skipping upload", "success")
            else:
                log(
                    f"Hash mismatch (remote={remote_md5}, local={patch_md5}), re-uploading...",
                    "warning",
                )
                conn.upload_sftp(patch_path, remote_path, progress_cb=progress_cb)
                log("Patch re-uploaded", "success")
        else:
            if remote_size > 0:
                log(
                    f"Remote size mismatch ({fmt_size(remote_size)} vs"
                    f" {fmt_size(patch_size)}), re-uploading...",
                    "warning",
                )
            log(f"Uploading patch ({fmt_size(patch_size)})...")
            conn.upload_sftp(patch_path, remote_path, progress_cb=progress_cb)
            log("Patch uploaded", "success")
    except Exception as e:
        log(f"Upload failed: {e}", "error")
        return None

    # Verify upload integrity
    remote_md5_check = conn.md5_remote_sftp(remote_path)
    if remote_md5_check and remote_md5_check != patch_md5:
        log(
            f"Post-upload hash mismatch ({remote_md5_check} vs {patch_md5}), upload corrupt!",
            "error",
        )
        return None

    return {
        "from": from_version,
        "to": to_version,
        "url": f"{CDN_DOMAIN}/{cdn_path}",
        "size": patch_size,
        "md5": patch_md5,
        "kv_route": {"key": cdn_path, "value": remote_path},
    }
