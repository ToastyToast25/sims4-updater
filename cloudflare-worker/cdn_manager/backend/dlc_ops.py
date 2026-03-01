"""DLC operations — scan, pack, upload pipeline for the GUI."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from .connection import CDN_DOMAIN, SEEDBOX_BASE_DIR, ConnectionManager

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # sims4-updater/
STATE_FILE = Path(__file__).resolve().parent.parent.parent / "upload_state.json"


# -- Upload state persistence -----------------------------------------------


def load_upload_state() -> dict:
    """Load the upload state file. Returns empty dict if missing/corrupt."""
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_upload_state(state: dict) -> None:
    """Write the upload state file."""
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def start_upload_session(dlc_ids: list[str]) -> dict:
    """Create a new upload session in the state file."""
    state = {
        "session": {
            "started": datetime.now(UTC).isoformat(),
            "dlc_ids": dlc_ids,
            "completed": {},
            "finished": False,
        },
    }
    save_upload_state(state)
    return state


def record_dlc_complete(dlc_id: str, entry: dict) -> None:
    """Record a successfully uploaded DLC in the state file."""
    state = load_upload_state()
    session = state.get("session", {})
    completed = session.get("completed", {})
    completed[dlc_id] = {
        **entry,
        "ts": datetime.now(UTC).isoformat(),
    }
    session["completed"] = completed
    state["session"] = session
    save_upload_state(state)


def finish_upload_session() -> None:
    """Mark the current upload session as complete."""
    state = load_upload_state()
    if "session" in state:
        state["session"]["finished"] = True
        save_upload_state(state)


def get_pending_resume() -> list[str] | None:
    """Check if there's an incomplete session. Returns remaining DLC IDs or None."""
    state = load_upload_state()
    session = state.get("session", {})
    if session.get("finished", True):
        return None
    dlc_ids = session.get("dlc_ids", [])
    completed = set(session.get("completed", {}).keys())
    remaining = [d for d in dlc_ids if d not in completed]
    return remaining if remaining else None


def load_dlc_catalog() -> dict:
    """Load the DLC catalog. Returns {dlc_id: dlc_info}."""
    catalog_path = PROJECT_ROOT / "data" / "dlc_catalog.json"
    if catalog_path.is_file():
        with open(catalog_path, encoding="utf-8") as f:
            data = json.load(f)
        dlcs = data.get("dlcs", data) if isinstance(data, dict) else data
        return {d["id"]: d for d in dlcs}
    return {}


def get_dlc_name(catalog: dict, dlc_id: str) -> str:
    if dlc_id in catalog:
        names = catalog[dlc_id].get("names", {})
        return names.get("en_us", names.get("en_US", dlc_id))
    return dlc_id


def get_dlc_type(catalog: dict, dlc_id: str) -> str:
    if dlc_id in catalog:
        return catalog[dlc_id].get("pack_type", "unknown")
    prefix = dlc_id[:2] if len(dlc_id) >= 2 else ""
    type_map = {"EP": "expansion", "GP": "game_pack", "SP": "stuff_pack", "FP": "free_pack"}
    return type_map.get(prefix, "unknown")


def scan_installed_dlcs(game_dir: Path) -> list[str]:
    """Scan game directory for installed DLC folders."""
    dlcs = []
    if not game_dir.is_dir():
        return dlcs
    for d in sorted(game_dir.iterdir()):
        if d.is_dir() and len(d.name) >= 3:
            prefix = d.name[:2]
            suffix = d.name[2:]
            if prefix in ("EP", "GP", "SP", "FP") and suffix.isdigit():
                dlcs.append(d.name)
    return dlcs


def scan_version_dlcs(version_dir: Path) -> list[str]:
    """Scan version_dir/Delta/ for DLC folders (EP01, GP01, SP01...).

    Returns sorted list of DLC IDs found in the Delta directory.
    """
    delta_dir = version_dir / "Delta"
    if not delta_dir.is_dir():
        return []
    return sorted(
        d.name
        for d in delta_dir.iterdir()
        if d.is_dir()
        and len(d.name) >= 3
        and d.name[:2] in ("EP", "GP", "SP", "FP")
        and d.name[2:].isdigit()
    )


def build_dlc_version_map(
    versions: list[str],
    download_base_dir: Path,
) -> dict[str, str]:
    """Build {dlc_id: min_version} from downloaded versions.

    Versions must be sorted oldest-to-newest (numeric, not string).
    Returns a dict mapping each DLC ID to the earliest version where it appears.
    """
    min_versions: dict[str, str] = {}
    for version in versions:
        version_dir = download_base_dir / version
        if not version_dir.is_dir():
            continue
        for dlc_id in scan_version_dlcs(version_dir):
            if dlc_id not in min_versions:
                min_versions[dlc_id] = version
    return min_versions


def get_folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


def fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.2f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def pack_dlc(game_dir: Path, dlc_id: str, output_dir: Path) -> Path:
    """Pack a DLC folder into a ZIP archive. Returns path to ZIP."""
    dlc_dir = game_dir / dlc_id
    if not dlc_dir.is_dir():
        raise FileNotFoundError(f"DLC folder not found: {dlc_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{dlc_id}.zip"

    files = []
    for path in dlc_dir.rglob("*"):
        if path.is_file():
            files.append((path.relative_to(game_dir), path))

    installer_dir = game_dir / "__Installer" / "DLC" / dlc_id
    if installer_dir.is_dir():
        for path in installer_dir.rglob("*"):
            if path.is_file():
                files.append((path.relative_to(game_dir), path))

    if not files:
        raise FileNotFoundError(f"{dlc_id} has no files to pack")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, abs_path in sorted(files):
            zf.write(abs_path, str(rel_path).replace("\\", "/"))

    return zip_path


def check_cdn_status(conn: ConnectionManager, dlc_ids: list[str]) -> dict[str, str]:
    """Check CDN status for a list of DLCs.

    Returns {dlc_id: status} where status is "uploaded", "missing", or "error".
    """
    statuses = {}
    for dlc_id in dlc_ids:
        cdn_path = f"dlc/{dlc_id}.zip"
        try:
            if conn.kv_exists(cdn_path):
                statuses[dlc_id] = "uploaded"
            else:
                statuses[dlc_id] = "missing"
        except Exception:
            statuses[dlc_id] = "error"
    return statuses


def process_single_dlc(
    game_dir: Path,
    dlc_id: str,
    conn: ConnectionManager,
    output_dir: Path,
    *,
    force: bool = False,
    cancel_event: Event | None = None,
    log_cb=None,
    progress_cb=None,
) -> dict | None:
    """Pack, upload, and register a single DLC.

    Returns a manifest entry dict on success, or None on failure/cancel.
    log_cb(message, level) for status updates.
    progress_cb(sent, total) for upload progress.
    """
    cdn_path = f"dlc/{dlc_id}.zip"
    remote_path = f"{SEEDBOX_BASE_DIR}/{cdn_path}"
    tag = f"[{dlc_id}]"

    def log(msg, level="info"):
        if log_cb:
            log_cb(f"{tag} {msg}", level)

    # Check if already on CDN
    if not force and conn.kv_exists(cdn_path):
        log("Already on CDN, skipping")
        return {
            "url": f"{CDN_DOMAIN}/{cdn_path}",
            "size": 0,
            "md5": "",
            "filename": f"{dlc_id}.zip",
        }

    if cancel_event and cancel_event.is_set():
        return None

    dlc_dir = game_dir / dlc_id
    if not dlc_dir.is_dir():
        log("Folder not found, skipping", "warning")
        return None

    # Pack
    folder_size = get_folder_size(dlc_dir)
    log(f"Packing ({fmt_size(folder_size)})...")
    zip_path = pack_dlc(game_dir, dlc_id, output_dir)
    zip_size = zip_path.stat().st_size
    zip_md5 = md5_file(zip_path)
    log(f"Packed: {fmt_size(zip_size)}, MD5: {zip_md5}")

    if cancel_event and cancel_event.is_set():
        zip_path.unlink(missing_ok=True)
        return None

    # Upload
    log(f"Uploading {fmt_size(zip_size)}...")
    try:
        conn.upload_sftp(zip_path, remote_path, progress_cb=progress_cb)
    except Exception as e:
        log(f"Upload failed: {e}", "error")
        zip_path.unlink(missing_ok=True)
        return None

    if cancel_event and cancel_event.is_set():
        zip_path.unlink(missing_ok=True)
        return None

    # Register KV
    try:
        conn.kv_put(cdn_path, remote_path)
        log("Registered in CDN")
    except Exception as e:
        log(f"KV registration failed: {e}", "error")
        zip_path.unlink(missing_ok=True)
        return None

    # Clean up
    zip_path.unlink(missing_ok=True)

    entry = {
        "url": f"{CDN_DOMAIN}/{cdn_path}",
        "size": zip_size,
        "md5": zip_md5,
        "filename": f"{dlc_id}.zip",
    }
    log(f"Done ({fmt_size(zip_size)})", "success")
    return entry
