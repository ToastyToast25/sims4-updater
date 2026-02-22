"""
CDN Pack & Upload -- Package DLCs from game installation and upload to CDN.

Features:
  - Parallel uploads (--workers N, default 4) for maximum throughput
  - Each worker: pack ZIP -> upload SFTP -> register KV -> delete ZIP
  - Resume support via local state file (survives crashes/reboots)
  - Retry with exponential backoff on connection failures
  - Graceful Ctrl+C: finishes active uploads, saves progress
  - Throttled progress output (updates every 2 seconds, not every chunk)

Usage:
    python cdn_pack_upload.py                      # Upload all DLCs, 4 parallel
    python cdn_pack_upload.py --workers 6          # 6 parallel uploads
    python cdn_pack_upload.py --only EP01 EP02     # Only specific DLCs
    python cdn_pack_upload.py --skip-upload        # Just package, don't upload
    python cdn_pack_upload.py --manifest-only      # Only generate manifest from KV
    python cdn_pack_upload.py --fresh              # Ignore local state, re-check KV
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import hashlib
import json
import os
import signal
import sys
import threading
import time
import zipfile
from pathlib import Path

import paramiko
import requests

# ── Config ────────────────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / "cdn_config.json"
STATE_FILE = Path(__file__).parent / "upload_state.json"
SEEDBOX_BASE_DIR = "files/sims4"
CDN_DOMAIN = "https://cdn.hyperabyss.com"
GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\The Sims 4")
OUTPUT_DIR = Path(__file__).parent / "packed_temp"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

MAX_RETRIES = 5
RETRY_BASE_DELAY = 5  # seconds
PROGRESS_INTERVAL = 2.0  # seconds between progress line updates
DEFAULT_WORKERS = "auto"
SPEEDTEST_SIZE_MB = 5  # Upload this many MB to measure single-connection speed
SPEEDTEST_REMOTE_FILE = f"{SEEDBOX_BASE_DIR}/.speedtest_tmp"
TARGET_BANDWIDTH_RATIO = 0.85  # Use 85% of detected bandwidth


# ── Graceful shutdown ─────────────────────────────────────────────

_shutdown_requested = False


def _signal_handler(sig, frame):
    global _shutdown_requested
    if _shutdown_requested:
        print("\n\n  Force quit. Progress saved to upload_state.json.")
        sys.exit(1)
    _shutdown_requested = True
    print("\n\n  Ctrl+C detected — finishing active uploads then stopping...")
    print("  Press Ctrl+C again to force quit.\n")


signal.signal(signal.SIGINT, _signal_handler)


# ── Thread-safe state persistence ────────────────────────────────

_state_lock = threading.Lock()


def load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"completed": {}, "failed": []}


def save_state(state: dict) -> None:
    with _state_lock:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def mark_completed(state: dict, dlc_id: str, entry: dict) -> None:
    with _state_lock:
        state.setdefault("completed", {})[dlc_id] = entry
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── Thread-safe print ────────────────────────────────────────────

_print_lock = threading.Lock()


def tprint(*args, **kwargs):
    """Thread-safe print."""
    with _print_lock:
        print(*args, **kwargs)


# ── Config loader ────────────────────────────────────────────────


def load_config() -> dict:
    if not CONFIG_FILE.is_file():
        print(f"ERROR: Config file not found: {CONFIG_FILE}")
        print("Copy cdn_config.example.json to cdn_config.json and fill in credentials.")
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


# ── DLC catalog ───────────────────────────────────────────────────


def load_dlc_catalog() -> dict:
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


def scan_installed_dlcs(game_dir: Path) -> list[str]:
    dlcs = []
    for d in sorted(game_dir.iterdir()):
        if d.is_dir() and len(d.name) >= 3:
            prefix = d.name[:2]
            suffix = d.name[2:]
            if prefix in ("EP", "GP", "SP", "FP") and suffix.isdigit():
                dlcs.append(d.name)
    return dlcs


# ── File utilities ────────────────────────────────────────────────


def fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.2f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def fmt_time(seconds: float) -> str:
    if seconds >= 3600:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"
    if seconds >= 60:
        return f"{seconds / 60:.1f}m"
    return f"{seconds:.0f}s"


def get_folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


# ── SFTP with retry ──────────────────────────────────────────────


def _connect_sftp(config: dict):
    """Connect to Whatbox SFTP with large window for max throughput."""
    transport = paramiko.Transport((config["whatbox_host"], config.get("whatbox_port", 22)))
    transport.default_window_size = paramiko.common.MAX_WINDOW_SIZE
    transport.connect(username=config["whatbox_user"], password=config["whatbox_pass"])
    sftp = paramiko.SFTPClient.from_transport(transport)
    return transport, sftp


def run_speedtest(config: dict) -> tuple[float, int]:
    """Upload a test payload to measure single-connection SFTP speed.

    Returns (speed_bytes_per_sec, recommended_workers).
    """
    test_size = SPEEDTEST_SIZE_MB * 1_048_576
    test_data = os.urandom(test_size)

    # Write temp file
    tmp_path = Path(__file__).parent / ".speedtest_tmp"
    tmp_path.write_bytes(test_data)

    try:
        transport, sftp = _connect_sftp(config)
        try:
            # Ensure remote dir exists
            parts = SPEEDTEST_REMOTE_FILE.split("/")
            current = ""
            for part in parts[:-1]:
                current = f"{current}/{part}" if current else part
                try:
                    sftp.stat(current)
                except FileNotFoundError:
                    with contextlib.suppress(OSError):
                        sftp.mkdir(current)

            # Upload and time it
            start = time.monotonic()
            sftp.put(str(tmp_path), SPEEDTEST_REMOTE_FILE)
            elapsed = time.monotonic() - start

            # Clean up remote file
            with contextlib.suppress(OSError):
                sftp.remove(SPEEDTEST_REMOTE_FILE)

            single_speed = test_size / elapsed if elapsed > 0 else 0

            # Estimate total bandwidth by assuming we can scale linearly
            # Use 85% of line speed to avoid congestion
            # We can't know line speed from one connection, but we know per-connection speed
            # Optimal workers = line_speed / single_speed
            # Since we can't measure line speed directly, ask the user OR
            # use a heuristic: try 2 connections briefly to see if they scale
            return single_speed, _calculate_workers(single_speed)

        finally:
            sftp.close()
            transport.close()
    except Exception as e:
        print(f"  Speedtest failed: {e}")
        print(f"  Falling back to {4} workers")
        return 0, 4
    finally:
        tmp_path.unlink(missing_ok=True)


def run_dual_speedtest(config: dict) -> tuple[float, float, int]:
    """Run 1-connection then 2-connection speedtest to detect bandwidth ceiling.

    Returns (single_speed, dual_speed, recommended_workers).
    """
    test_size = SPEEDTEST_SIZE_MB * 1_048_576
    tmp_path = Path(__file__).parent / ".speedtest_tmp"
    tmp_path.write_bytes(os.urandom(test_size))
    remote1 = f"{SEEDBOX_BASE_DIR}/.speedtest_1"
    remote2 = f"{SEEDBOX_BASE_DIR}/.speedtest_2"

    def _ensure_dirs(sftp):
        parts = SEEDBOX_BASE_DIR.split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            try:
                sftp.stat(current)
            except FileNotFoundError:
                with contextlib.suppress(OSError):
                    sftp.mkdir(current)

    try:
        # ── Single connection test ──
        print("  [1/2] Testing single connection speed...")
        t1, s1 = _connect_sftp(config)
        try:
            _ensure_dirs(s1)
            start = time.monotonic()
            s1.put(str(tmp_path), remote1)
            single_elapsed = time.monotonic() - start
            single_speed = test_size / single_elapsed
            print(f"        Single: {fmt_size(int(single_speed))}/s")
            with contextlib.suppress(OSError):
                s1.remove(remote1)
        finally:
            s1.close()
            t1.close()

        # ── Dual connection test ──
        print("  [2/2] Testing dual connection speed...")
        t1, s1 = _connect_sftp(config)
        t2, s2 = _connect_sftp(config)
        try:
            barrier = threading.Barrier(2)
            results = [0.0, 0.0]

            def _upload(sftp, remote, idx):
                barrier.wait()
                s = time.monotonic()
                sftp.put(str(tmp_path), remote)
                results[idx] = time.monotonic() - s

            th1 = threading.Thread(target=_upload, args=(s1, remote1, 0))
            th2 = threading.Thread(target=_upload, args=(s2, remote2, 1))
            th1.start()
            th2.start()
            th1.join()
            th2.join()

            # Combined throughput = 2 * test_size / max(elapsed)
            max_elapsed = max(results[0], results[1])
            dual_speed = (2 * test_size) / max_elapsed if max_elapsed > 0 else 0
            print(f"        Dual:   {fmt_size(int(dual_speed))}/s")

            # Clean up
            for sftp, remote in [(s1, remote1), (s2, remote2)]:
                with contextlib.suppress(OSError):
                    sftp.remove(remote)
        finally:
            s1.close()
            t1.close()
            s2.close()
            t2.close()

        # ── Calculate optimal workers ──
        # If dual ~= 2x single, bandwidth scales linearly (not capped yet)
        # Estimate ceiling: extrapolate from scaling ratio
        if single_speed > 0:
            scaling_ratio = dual_speed / single_speed
            if scaling_ratio >= 1.8:
                # Near-linear scaling — bandwidth not saturated with 2 connections
                # Estimate: keep adding workers until we'd hit ~85% of line speed
                # Heuristic: line speed ≈ dual_speed * (2 / scaling_ratio) * some headroom
                # Simpler: workers = ceil(dual_speed / single_speed) + 2
                estimated_line = dual_speed * 1.5  # conservative estimate
                workers = max(2, int(estimated_line / single_speed * TARGET_BANDWIDTH_RATIO))
            elif scaling_ratio >= 1.3:
                # Some scaling but hitting limits — bandwidth partially saturated
                workers = max(2, int(dual_speed / single_speed * TARGET_BANDWIDTH_RATIO) + 1)
            else:
                # No scaling — single connection already saturates
                workers = 2
        else:
            workers = 4

        workers = min(workers, 10)  # cap at 10
        print(f"        Scaling ratio: {dual_speed / single_speed:.2f}x")
        print(f"        Recommended workers: {workers}")

        return single_speed, dual_speed, workers

    except Exception as e:
        print(f"  Speedtest failed: {e}")
        print("  Falling back to 4 workers")
        return 0, 0, 4
    finally:
        tmp_path.unlink(missing_ok=True)


def _calculate_workers(single_speed: float) -> int:
    """Fallback worker calc from single-speed only (when dual test isn't used)."""
    # Assume typical home upload: 5-50 Mbps
    # If single conn gets 1 MB/s, and user has ~10 MB/s, need ~8 workers
    # Without knowing line speed, use a reasonable default based on single speed
    if single_speed < 512 * 1024:  # < 512 KB/s — slow connection
        return 2
    if single_speed < 2 * 1_048_576:  # < 2 MB/s — likely bandwidth limited per conn
        return 6
    return 4  # fast single connection, fewer workers needed


def upload_sftp_with_retry(
    config: dict,
    local_path: Path,
    remote_path: str,
    dlc_id: str = "",
    max_retries: int = MAX_RETRIES,
) -> None:
    """Upload a file via SFTP with retry on failure and throttled progress."""
    last_progress_time = [0.0]
    upload_start = [0.0]
    tag = f"[{dlc_id}] " if dlc_id else ""

    def progress_cb(sent, total):
        now = time.monotonic()
        if sent < total and (now - last_progress_time[0]) < PROGRESS_INTERVAL:
            return
        last_progress_time[0] = now

        pct = (sent / total) * 100 if total > 0 else 0
        bar_len = 25
        filled = int(bar_len * sent // total) if total > 0 else 0
        bar = "#" * filled + "-" * (bar_len - filled)

        elapsed = now - upload_start[0]
        if elapsed > 0 and sent > 0:
            speed = sent / elapsed
            remaining = (total - sent) / speed if speed > 0 else 0
            speed_str = f"{fmt_size(int(speed))}/s"
            eta_str = f"ETA {fmt_time(remaining)}"
        else:
            speed_str = "..."
            eta_str = ""

        tprint(
            f"\r  {tag}[{bar}] {pct:.1f}%  {fmt_size(sent)}/{fmt_size(total)}  "
            f"{speed_str}  {eta_str}   ",
            end="",
            flush=True,
        )

    for attempt in range(1, max_retries + 1):
        try:
            transport, sftp = _connect_sftp(config)
            try:
                # Ensure remote directories exist
                parts = remote_path.split("/")
                current = ""
                for part in parts[:-1]:
                    current = f"{current}/{part}" if current else part
                    try:
                        sftp.stat(current)
                    except FileNotFoundError:
                        with contextlib.suppress(OSError):
                            sftp.mkdir(current)

                last_progress_time[0] = 0.0
                upload_start[0] = time.monotonic()
                sftp.put(str(local_path), remote_path, callback=progress_cb)
                tprint()  # newline after progress bar
                return  # success
            finally:
                sftp.close()
                transport.close()

        except (OSError, paramiko.SSHException, EOFError) as e:
            tprint()  # newline after any partial progress
            if attempt == max_retries:
                raise ConnectionError(f"Upload failed after {max_retries} attempts: {e}") from e

            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            tprint(f"  {tag}Connection error: {e}")
            tprint(f"  {tag}Retry {attempt}/{max_retries} in {delay}s...")
            time.sleep(delay)

            if _shutdown_requested:
                raise KeyboardInterrupt("Shutdown requested during retry wait") from None


# ── Cloudflare KV with retry ─────────────────────────────────────


def _kv_headers(config: dict) -> dict:
    return {"Authorization": f"Bearer {config['cloudflare_api_token']}"}


def _kv_url(config: dict, key: str = "") -> str:
    account_id = config["cloudflare_account_id"]
    namespace_id = config["cloudflare_kv_namespace_id"]
    base = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        f"/storage/kv/namespaces/{namespace_id}"
    )
    return f"{base}/values/{key}" if key else base


def kv_exists(config: dict, key: str) -> bool:
    for attempt in range(3):
        try:
            resp = requests.get(
                _kv_url(config, key),
                headers=_kv_headers(config),
                timeout=15,
            )
            return resp.status_code == 200
        except requests.RequestException:
            if attempt == 2:
                return False
            time.sleep(2)
    return False


def add_kv_entry(config: dict, key: str, value: str) -> None:
    for attempt in range(3):
        try:
            resp = requests.put(
                _kv_url(config, key),
                headers={**_kv_headers(config), "Content-Type": "text/plain"},
                data=value,
                timeout=30,
            )
            if resp.status_code == 200 and resp.json().get("success"):
                return
            raise RuntimeError(f"KV write failed: {resp.status_code} {resp.text}")
        except requests.RequestException as e:
            if attempt == 2:
                raise ConnectionError(f"KV unreachable after 3 attempts: {e}") from e
            time.sleep(2)


def list_kv_entries(config: dict) -> list[str]:
    url = _kv_url(config) + "/keys"
    all_keys = []
    cursor = None
    while True:
        params = {}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            url,
            headers=_kv_headers(config),
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"ERROR listing KV: {resp.status_code}: {resp.text}")
            break
        data = resp.json()
        all_keys.extend(e.get("name", "") for e in data.get("result", []))
        cursor = data.get("result_info", {}).get("cursor")
        if not cursor:
            break
    return all_keys


# ── Pack ──────────────────────────────────────────────────────────


def pack_dlc(game_dir: Path, dlc_id: str, output_dir: Path) -> Path:
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


# ── Process single DLC (runs in worker thread) ───────────────────


def process_dlc(
    game_dir: Path,
    dlc_id: str,
    catalog: dict,
    config: dict,
    output_dir: Path,
    state: dict,
    skip_upload: bool = False,
) -> dict | None:
    """Pack, upload, and clean up a single DLC. Returns manifest entry or None."""
    cdn_path = f"dlc/{dlc_id}.zip"
    remote_path = f"{SEEDBOX_BASE_DIR}/{cdn_path}"
    dlc_name = get_dlc_name(catalog, dlc_id)
    tag = f"[{dlc_id}]"

    # Check local state first (fast, no network)
    if dlc_id in state.get("completed", {}):
        return state["completed"][dlc_id]

    dlc_dir = game_dir / dlc_id
    if not dlc_dir.is_dir():
        tprint(f"  {tag} Folder not found, skipping")
        return None

    # Check KV (network, but fast)
    if kv_exists(config, cdn_path):
        tprint(f"  {tag} Already on CDN, skipping")
        entry = {
            "url": f"{CDN_DOMAIN}/{cdn_path}",
            "size": 0,
            "md5": "",
            "filename": f"{dlc_id}.zip",
        }
        mark_completed(state, dlc_id, entry)
        return entry

    if _shutdown_requested:
        return None

    # Step 1: Pack
    folder_size = get_folder_size(dlc_dir)
    tprint(f"  {tag} Packing {dlc_name} ({fmt_size(folder_size)})...")
    zip_path = pack_dlc(game_dir, dlc_id, output_dir)
    zip_size = zip_path.stat().st_size
    zip_md5 = md5_file(zip_path)
    tprint(f"  {tag} Packed: {fmt_size(zip_size)}  MD5: {zip_md5}")

    if _shutdown_requested:
        tprint(f"  {tag} Shutdown requested, keeping ZIP for resume")
        return None

    if skip_upload:
        zip_path.unlink(missing_ok=True)
        return {
            "url": f"{CDN_DOMAIN}/{cdn_path}",
            "size": zip_size,
            "md5": zip_md5,
            "filename": f"{dlc_id}.zip",
        }

    # Step 2: Upload via SFTP
    tprint(f"  {tag} Uploading {fmt_size(zip_size)}...")
    try:
        upload_sftp_with_retry(config, zip_path, remote_path, dlc_id=dlc_id)
    except (ConnectionError, KeyboardInterrupt) as e:
        tprint(f"  {tag} UPLOAD FAILED: {e}")
        return None

    if _shutdown_requested:
        zip_path.unlink(missing_ok=True)
        return None

    # Step 3: Register in KV
    try:
        add_kv_entry(config, cdn_path, remote_path)
        tprint(f"  {tag} Registered in CDN")
    except (ConnectionError, RuntimeError) as e:
        tprint(f"  {tag} KV registration failed: {e}")
        zip_path.unlink(missing_ok=True)
        return None

    # Step 4: Clean up local ZIP
    zip_path.unlink(missing_ok=True)

    entry = {
        "url": f"{CDN_DOMAIN}/{cdn_path}",
        "size": zip_size,
        "md5": zip_md5,
        "filename": f"{dlc_id}.zip",
        "name": dlc_name,
    }
    mark_completed(state, dlc_id, entry)
    tprint(f"  {tag} DONE ({fmt_size(zip_size)})")
    return entry


# ── Manifest ──────────────────────────────────────────────────────


def generate_manifest(
    dlc_downloads: dict,
    output_path: Path,
    version: str = "",
    language_downloads: dict | None = None,
    patches: list | None = None,
    versions: dict | None = None,
    dlc_catalog: list | None = None,
    preserve_from: Path | None = None,
) -> None:
    # Preserve metadata fields from existing manifest if provided
    preserved = {}
    _PRESERVE_KEYS = [
        "entitlements_url", "self_update_url", "contribute_url",
        "fingerprints", "fingerprints_url", "report_url",
        "game_latest", "game_latest_date", "new_dlcs",
        "greenluma",
    ]
    if preserve_from and preserve_from.is_file():
        try:
            with open(preserve_from, encoding="utf-8") as f:
                old = json.load(f)
            for key in _PRESERVE_KEYS:
                if key in old and old[key]:
                    preserved[key] = old[key]
        except (OSError, json.JSONDecodeError):
            pass

    manifest = {
        "latest": version,
        **preserved,
        "dlc_downloads": dlc_downloads,
    }
    if versions:
        manifest["versions"] = versions
    if language_downloads:
        manifest["language_downloads"] = language_downloads
    if patches:
        manifest["patches"] = patches
    if dlc_catalog:
        manifest["dlc_catalog"] = dlc_catalog
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest written to: {output_path}")
    print(f"  DLC entries: {len(dlc_downloads)}")
    if language_downloads:
        print(f"  Language entries: {len(language_downloads)}")
    if dlc_catalog:
        print(f"  Catalog entries: {len(dlc_catalog)}")
    if preserved:
        print(f"  Preserved fields: {', '.join(preserved.keys())}")
    if version:
        print(f"  Version: {version}")


def build_manifest_from_results(results: dict) -> dict:
    downloads = {}
    for dlc_id, entry in sorted(results.items()):
        downloads[dlc_id] = {
            "url": entry["url"],
            "size": entry["size"],
            "md5": entry["md5"],
            "filename": entry["filename"],
        }
    return downloads


# ── Main ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Pack & upload DLCs to CDN (parallel)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--workers",
        default=DEFAULT_WORKERS,
        help="Parallel upload workers (default: auto via speedtest)",
    )
    parser.add_argument("--only", nargs="+", help="Only process these DLC IDs")
    parser.add_argument("--skip-upload", action="store_true", help="Pack only, don't upload")
    parser.add_argument("--manifest-only", action="store_true", help="Generate manifest from KV")
    parser.add_argument("--fresh", action="store_true", help="Ignore local state file")
    parser.add_argument("--game-dir", type=Path, default=GAME_DIR, help="Game directory")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Temp dir for ZIPs")
    parser.add_argument("--version", default="", help="Game version for manifest 'latest' field")
    parser.add_argument(
        "--merge-languages",
        type=Path,
        default=None,
        help="Path to language_downloads.json to merge into manifest",
    )
    parser.add_argument(
        "--archive-version",
        default="",
        help="Archive current CDN content as this version before uploading",
    )
    args = parser.parse_args()

    config = load_config()
    catalog = load_dlc_catalog()

    # Archive current CDN content before uploading new DLCs
    if args.archive_version:
        from cdn_archive import cmd_create

        print(f"  Archiving current CDN content as version {args.archive_version}...")
        print()
        cmd_create(config, args.archive_version)
        print()

    # Fetch existing versions index from live manifest (preserves archive history)
    existing_versions = None
    try:
        resp = requests.get(f"{CDN_DOMAIN}/manifest.json", timeout=15)
        if resp.status_code == 200:
            live = resp.json()
            if live.get("versions"):
                existing_versions = live["versions"]
    except Exception:
        pass  # non-critical, new manifest just won't have versions

    # Determine worker count
    num_workers = None if args.workers == "auto" else max(1, min(int(args.workers), 10))

    print("=" * 60)
    print("  Sims 4 DLC CDN Uploader")
    print("  Press Ctrl+C to gracefully stop")
    print("=" * 60)
    print()

    # Run speedtest if workers=auto and we're actually uploading
    if num_workers is None and not args.skip_upload and not args.manifest_only:
        print("Running upload speedtest...")
        single, dual, recommended = run_dual_speedtest(config)
        num_workers = recommended
        print(
            f"\n  Using {num_workers} workers "
            f"(single: {fmt_size(int(single))}/s, "
            f"dual: {fmt_size(int(dual))}/s)\n"
        )
    elif num_workers is None:
        num_workers = 4

    print(f"  Workers: {num_workers} parallel uploads")
    print()

    # Manifest-only mode
    if args.manifest_only:
        print("Generating manifest from existing CDN entries...")
        keys = list_kv_entries(config)
        dlc_keys = [k for k in keys if k.startswith("dlc/") and k.endswith(".zip")]
        print(f"Found {len(dlc_keys)} DLC entries on CDN")

        # Load state file for MD5s from previous uploads
        prev_state = load_state()
        prev_completed = prev_state.get("completed", {})

        downloads = {}
        for key in sorted(dlc_keys):
            dlc_id = key.replace("dlc/", "").replace(".zip", "")
            dlc_name = get_dlc_name(catalog, dlc_id)

            # Try to get real size via HEAD request
            url = f"{CDN_DOMAIN}/{key}"
            size = 0
            try:
                resp = requests.head(url, timeout=15, allow_redirects=True)
                if resp.status_code == 200:
                    size = int(resp.headers.get("Content-Length", 0))
            except requests.RequestException:
                pass

            # Try to get MD5 from state file
            md5 = prev_completed.get(dlc_id, {}).get("md5", "")

            downloads[dlc_id] = {
                "url": url,
                "size": size,
                "md5": md5,
                "filename": f"{dlc_id}.zip",
            }
            size_str = fmt_size(size) if size > 0 else "??"
            md5_str = md5[:8] + "..." if md5 else "no MD5"
            print(f"  {dlc_id}: {dlc_name} ({size_str}, {md5_str})")

        # Load language downloads if provided
        language_downloads = None
        if args.merge_languages and args.merge_languages.is_file():
            language_downloads = json.loads(args.merge_languages.read_text(encoding="utf-8"))
            print(f"  Merging {len(language_downloads)} language entries")

        manifest_path = Path(__file__).parent / "manifest.json"
        generate_manifest(
            downloads,
            manifest_path,
            version=args.version,
            language_downloads=language_downloads,
            versions=existing_versions,
        )
        return

    # Load state
    state = {"completed": {}, "failed": []} if args.fresh else load_state()
    if state.get("completed"):
        print(f"Resuming: {len(state['completed'])} DLCs already completed")

    # Scan installed DLCs
    if not args.game_dir.is_dir():
        print(f"ERROR: Game directory not found: {args.game_dir}")
        sys.exit(1)

    installed = scan_installed_dlcs(args.game_dir)
    print(f"Found {len(installed)} DLCs installed")

    if args.only:
        target_dlcs = [d for d in args.only if d in installed]
        skipped = [d for d in args.only if d not in installed]
        if skipped:
            print(f"Warning: Not installed: {', '.join(skipped)}")
    else:
        target_dlcs = installed

    # Filter out already-completed DLCs
    pending_dlcs = [d for d in target_dlcs if d not in state.get("completed", {})]
    already_done = len(target_dlcs) - len(pending_dlcs)

    print(f"Total: {len(target_dlcs)}  |  Done: {already_done}  |  Remaining: {len(pending_dlcs)}")
    print()

    # Load language downloads if provided
    language_downloads = None
    if args.merge_languages and args.merge_languages.is_file():
        language_downloads = json.loads(args.merge_languages.read_text(encoding="utf-8"))
        print(f"Merging {len(language_downloads)} language entries into manifest")

    if not pending_dlcs:
        print("All DLCs already uploaded! Use --fresh to re-upload.")
        results = state.get("completed", {})
        if results:
            downloads = build_manifest_from_results(results)
            manifest_path = Path(__file__).parent / "manifest.json"
            generate_manifest(
                downloads,
                manifest_path,
                version=args.version,
                language_downloads=language_downloads,
                versions=existing_versions,
            )
        return

    # Run parallel uploads
    results = dict(state.get("completed", {}))
    failed = []
    uploaded_count = 0
    uploaded_bytes = 0
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as pool:
        future_to_dlc = {}
        for dlc_id in pending_dlcs:
            if _shutdown_requested:
                break
            future = pool.submit(
                process_dlc,
                args.game_dir,
                dlc_id,
                catalog,
                config,
                args.output_dir,
                state,
                args.skip_upload,
            )
            future_to_dlc[future] = dlc_id

        for future in concurrent.futures.as_completed(future_to_dlc):
            dlc_id = future_to_dlc[future]
            try:
                entry = future.result()
                if entry:
                    results[dlc_id] = entry
                    if entry.get("size", 0) > 0:
                        uploaded_count += 1
                        uploaded_bytes += entry["size"]
            except Exception as e:
                tprint(f"  [{dlc_id}] FAILED: {e}")
                failed.append((dlc_id, str(e)))

            # Progress summary
            done_total = len(results)
            elapsed = time.time() - start_time
            if uploaded_count > 0:
                remaining_count = len(pending_dlcs) - uploaded_count - len(failed)
                if remaining_count > 0:
                    avg = elapsed / (uploaded_count + len(failed))
                    eta = avg * remaining_count
                    tprint(
                        f"\n  >>> Progress: {done_total}/{len(target_dlcs)} total  |  "
                        f"{uploaded_count} uploaded this run  |  "
                        f"{fmt_time(elapsed)} elapsed  |  ~{fmt_time(eta)} remaining\n"
                    )

    # Summary
    total_time = time.time() - start_time
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Total on CDN: {len(results)} DLCs")
    print(f"  Uploaded this run: {uploaded_count} ({fmt_size(uploaded_bytes)})")
    if already_done:
        print(f"  Already on CDN: {already_done}")
    if failed:
        print(f"  Failed: {len(failed)}")
        for dlc_id, err in failed:
            print(f"    {dlc_id}: {err}")
    print(f"  Time: {fmt_time(total_time)}")
    if uploaded_count > 0 and total_time > 0:
        speed = uploaded_bytes / total_time
        print(f"  Average speed: {fmt_size(int(speed))}/s")
    if _shutdown_requested:
        print("\n  Stopped early. Run again to continue where you left off.")

    # Generate manifest from ALL completed (including previous runs)
    if results:
        print()
        downloads = build_manifest_from_results(results)
        manifest_path = Path(__file__).parent / "manifest.json"
        generate_manifest(
            downloads,
            manifest_path,
            version=args.version,
            language_downloads=language_downloads,
            versions=existing_versions,
        )

        if not args.skip_upload and not _shutdown_requested:
            print("\n  Uploading manifest to CDN...")
            try:
                remote_manifest = f"{SEEDBOX_BASE_DIR}/manifest.json"
                upload_sftp_with_retry(config, manifest_path, remote_manifest)
                add_kv_entry(config, "manifest.json", f"{SEEDBOX_BASE_DIR}/manifest.json")
                print("  Manifest uploaded and registered!")
            except Exception as e:
                print(f"  ERROR uploading manifest: {e}")
                print(f"  Local manifest saved at: {manifest_path}")

    # Clean up temp dir
    if args.output_dir.is_dir():
        with contextlib.suppress(OSError):
            args.output_dir.rmdir()

    print(f"\n  State saved to: {STATE_FILE}")
    print("  Done!")


if __name__ == "__main__":
    main()
