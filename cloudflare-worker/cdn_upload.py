"""
CDN Upload Tool -- upload files to Whatbox and register them on Cloudflare KV.

Commands:
    python cdn_upload.py publish-patch <from_ver> <to_ver> <local_file>
    python cdn_upload.py publish-dlc <dlc_id> <local_file>
    python cdn_upload.py publish-language <locale> <game_version> <local_file>
    python cdn_upload.py publish-manifest <local_file>
    python cdn_upload.py upload <local_file> <cdn_path>       # Manual upload
    python cdn_upload.py batch <local_dir> <cdn_prefix>       # Upload a whole folder
    python cdn_upload.py list                                  # List all CDN entries
    python cdn_upload.py delete <cdn_path>                     # Remove a CDN entry
    python cdn_upload.py verify <cdn_path>                     # Check if accessible

Examples:
    python cdn_upload.py publish-patch 1.121.372 1.122.100 ./patch.zip
    python cdn_upload.py publish-dlc EP01 ./EP01.zip
    python cdn_upload.py publish-dlc GP05 ./GP05.zip
    python cdn_upload.py publish-language de_DE 1.122.100 ./de_DE.zip
    python cdn_upload.py publish-manifest ./manifest.json
    python cdn_upload.py batch ./packed_dlcs dlc

CDN URL Structure:
    cdn.hyperabyss.com/manifest.json
    cdn.hyperabyss.com/patches/<from>_to_<to>.zip
    cdn.hyperabyss.com/dlc/<DLC_ID>.zip
    cdn.hyperabyss.com/language/<game_version>/<locale>.zip

Setup:
    pip install paramiko requests
    Create cdn_config.json next to this script (see cdn_config.example.json)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("ERROR: paramiko not installed. Run: pip install paramiko")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)


CONFIG_FILE = Path(__file__).parent / "cdn_config.json"
SEEDBOX_BASE_DIR = "files/sims4"
CDN_DOMAIN = "https://cdn.hyperabyss.com"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_FILE.is_file():
        print(f"ERROR: Config file not found: {CONFIG_FILE}")
        print("Copy cdn_config.example.json to cdn_config.json and fill in your credentials.")
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# SFTP helpers
# ---------------------------------------------------------------------------

def _connect_sftp(config: dict) -> tuple:
    """Connect to Whatbox SFTP. Returns (transport, sftp)."""
    host = config["whatbox_host"]
    user = config["whatbox_user"]
    password = config["whatbox_pass"]
    port = config.get("whatbox_port", 22)

    transport = paramiko.Transport((host, port))
    transport.connect(username=user, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)
    return transport, sftp


def file_exists_sftp(config: dict, remote_path: str) -> bool:
    """Check if a file already exists on the seedbox."""
    transport, sftp = _connect_sftp(config)
    try:
        sftp.stat(remote_path)
        return True
    except FileNotFoundError:
        return False
    finally:
        sftp.close()
        transport.close()


def upload_sftp(config: dict, local_path: Path, remote_path: str) -> None:
    """Upload a file to Whatbox via SFTP."""
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
                print(f"  Creating directory: {current}")
                sftp.mkdir(current)

        # Upload with progress
        file_size = local_path.stat().st_size

        def progress(sent, total):
            pct = (sent / total) * 100 if total > 0 else 0
            bar_len = 30
            filled = int(bar_len * sent // total) if total > 0 else 0
            bar = "#" * filled + "-" * (bar_len - filled)
            print(
                f"\r  Uploading: [{bar}] {pct:.1f}% ({sent:,}/{total:,} bytes)",
                end="",
                flush=True,
            )

        print(f"  File size: {file_size:,} bytes")
        sftp.put(str(local_path), remote_path, callback=progress)
        print()  # newline after progress bar
    finally:
        sftp.close()
        transport.close()


# ---------------------------------------------------------------------------
# Cloudflare KV helpers
# ---------------------------------------------------------------------------

def _kv_url(config: dict, key: str = "") -> str:
    account_id = config["cloudflare_account_id"]
    namespace_id = config["cloudflare_kv_namespace_id"]
    base = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        f"/storage/kv/namespaces/{namespace_id}"
    )
    if key:
        return f"{base}/values/{key}"
    return base


def _kv_headers(config: dict) -> dict:
    return {"Authorization": f"Bearer {config['cloudflare_api_token']}"}


def kv_exists(config: dict, key: str) -> bool:
    """Check if a KV entry already exists."""
    url = _kv_url(config, key)
    resp = requests.get(url, headers=_kv_headers(config), timeout=15)
    return resp.status_code == 200


def add_kv_entry(config: dict, key: str, value: str) -> None:
    """Add a key-value entry to Cloudflare KV."""
    url = _kv_url(config, key)
    resp = requests.put(
        url,
        headers={**_kv_headers(config), "Content-Type": "text/plain"},
        data=value,
        timeout=30,
    )

    if resp.status_code == 200:
        result = resp.json()
        if result.get("success"):
            print(f"  KV entry added: {key} -> {value}")
            return

    print(f"  ERROR: Failed to add KV entry. Status {resp.status_code}: {resp.text}")
    sys.exit(1)


def delete_kv_entry(config: dict, cdn_path: str) -> None:
    """Delete a KV entry."""
    url = _kv_url(config, cdn_path)
    resp = requests.delete(url, headers=_kv_headers(config), timeout=30)
    if resp.status_code == 200:
        print(f"  Deleted: {cdn_path}")
    else:
        print(f"  ERROR: {resp.status_code}: {resp.text}")


def list_kv_entries(config: dict) -> list[str]:
    """List all KV keys. Returns list of key names."""
    url = _kv_url(config) + "/keys"
    resp = requests.get(url, headers=_kv_headers(config), timeout=30)
    if resp.status_code == 200:
        return [e.get("name", "") for e in resp.json().get("result", [])]
    print(f"ERROR: {resp.status_code}: {resp.text}")
    return []


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_cdn(cdn_path: str) -> bool:
    """Verify the file is accessible via CDN."""
    url = f"{CDN_DOMAIN}/{cdn_path}"
    print(f"  Checking {url} ...")

    for attempt in range(3):
        try:
            resp = requests.head(url, timeout=15, allow_redirects=True)
            if resp.status_code == 200:
                size = resp.headers.get("Content-Length", "unknown")
                print(f"  Live! Status: 200, Size: {size} bytes")
                return True
            if resp.status_code == 404 and attempt < 2:
                print("  Not yet available (KV propagation), retrying in 3s...")
                time.sleep(3)
                continue
            print(f"  WARNING: Status {resp.status_code}")
            return False
        except requests.RequestException as e:
            print(f"  WARNING: {e}")
            if attempt < 2:
                time.sleep(3)
    return False


# ---------------------------------------------------------------------------
# Local file hashing
# ---------------------------------------------------------------------------

def md5_file(path: Path) -> str:
    """Compute MD5 hash of a local file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Core upload logic (with duplicate protection)
# ---------------------------------------------------------------------------

def upload_to_cdn(
    config: dict,
    local_path: Path,
    cdn_path: str,
    *,
    force: bool = False,
    skip_verify: bool = False,
) -> bool:
    """
    Upload a single file to CDN with duplicate protection.

    Returns True if file was uploaded, False if skipped (already exists).
    """
    cdn_path = cdn_path.strip("/")
    seedbox_path = f"{SEEDBOX_BASE_DIR}/{cdn_path}"

    print(f"\n  Local:   {local_path}")
    print(f"  CDN URL: {CDN_DOMAIN}/{cdn_path}")
    print(f"  Seedbox: {seedbox_path}")

    # Check if already exists
    if not force:
        print("  Checking for duplicates...")

        # Check KV first (fast, free API call)
        if kv_exists(config, cdn_path):
            print("  SKIPPED: Already exists on CDN (KV entry found).")
            print(f"  Use --force to overwrite.")
            return False

        # Check seedbox (SFTP stat)
        if file_exists_sftp(config, seedbox_path):
            print("  SKIPPED: File already exists on seedbox.")
            print(f"  Use --force to overwrite.")
            return False

        print("  No duplicates found.")
    else:
        print("  Force mode: skipping duplicate check.")

    # Upload to Whatbox
    print("  Uploading to Whatbox...")
    upload_sftp(config, local_path, seedbox_path)

    # Add KV entry
    print("  Adding Cloudflare KV entry...")
    add_kv_entry(config, cdn_path, seedbox_path)

    # Verify
    if not skip_verify:
        print("  Verifying CDN access...")
        verify_cdn(cdn_path)

    print(f"  Done! -> {CDN_DOMAIN}/{cdn_path}")
    return True


# ---------------------------------------------------------------------------
# Content-type publish commands
# ---------------------------------------------------------------------------

def publish_patch(config: dict, from_ver: str, to_ver: str, local_path: Path, **kw) -> bool:
    """Upload a patch file: patches/<from>_to_<to>.zip"""
    cdn_path = f"patches/{from_ver}_to_{to_ver}.zip"
    print(f"\n[Patch] {from_ver} -> {to_ver}")
    return upload_to_cdn(config, local_path, cdn_path, **kw)


def publish_dlc(config: dict, dlc_id: str, local_path: Path, **kw) -> bool:
    """Upload a DLC archive: dlc/<DLC_ID>.zip"""
    cdn_path = f"dlc/{dlc_id.upper()}.zip"
    print(f"\n[DLC] {dlc_id.upper()}")
    return upload_to_cdn(config, local_path, cdn_path, **kw)


def publish_language(
    config: dict, locale: str, game_version: str, local_path: Path, **kw
) -> bool:
    """Upload a language pack: language/<game_version>/<locale>.zip"""
    cdn_path = f"language/{game_version}/{locale}.zip"
    print(f"\n[Language] {locale} for v{game_version}")
    return upload_to_cdn(config, local_path, cdn_path, **kw)


def publish_manifest(config: dict, local_path: Path, **kw) -> bool:
    """Upload the master manifest: manifest.json (always overwrites)."""
    print("\n[Manifest] manifest.json")
    return upload_to_cdn(config, local_path, "manifest.json", force=True, **kw)


# ---------------------------------------------------------------------------
# Batch upload
# ---------------------------------------------------------------------------

def batch_upload(
    config: dict, local_dir: Path, cdn_prefix: str, **kw
) -> tuple[int, int]:
    """
    Upload all files in a local directory to CDN under a prefix.

    Returns (uploaded_count, skipped_count).
    """
    cdn_prefix = cdn_prefix.strip("/")
    files = sorted(f for f in local_dir.rglob("*") if f.is_file())

    if not files:
        print(f"No files found in {local_dir}")
        return 0, 0

    print(f"\nBatch upload: {len(files)} files from {local_dir}")
    print(f"CDN prefix: {cdn_prefix}/")
    print("-" * 50)

    uploaded = 0
    skipped = 0

    for i, fpath in enumerate(files, 1):
        rel = fpath.relative_to(local_dir).as_posix()
        cdn_path = f"{cdn_prefix}/{rel}"
        print(f"\n[{i}/{len(files)}] {rel}")

        if upload_to_cdn(config, fpath, cdn_path, **kw):
            uploaded += 1
        else:
            skipped += 1

    print(f"\n{'=' * 50}")
    print(f"Batch complete: {uploaded} uploaded, {skipped} skipped")
    return uploaded, skipped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CDN Upload Tool -- Whatbox + Cloudflare KV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Content-type commands (auto-paths, duplicate protection):
  publish-patch     Upload a game patch
  publish-dlc       Upload a DLC archive
  publish-language  Upload a language pack
  publish-manifest  Upload the master manifest (always overwrites)

General commands:
  upload            Upload any file to a custom CDN path
  batch             Upload all files in a directory
  list              List all CDN entries
  delete            Remove a CDN entry
  verify            Check if a CDN path is accessible

Contribution review:
  contributions     List pending user contributions
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # --- publish-patch ---
    pp = sub.add_parser("publish-patch", help="Upload a game patch")
    pp.add_argument("from_ver", help="Source version (e.g. 1.121.372)")
    pp.add_argument("to_ver", help="Target version (e.g. 1.122.100)")
    pp.add_argument("local_file", help="Path to patch zip file")
    pp.add_argument("--force", action="store_true", help="Overwrite if exists")
    pp.add_argument("--skip-verify", action="store_true")

    # --- publish-dlc ---
    pd = sub.add_parser("publish-dlc", help="Upload a DLC archive")
    pd.add_argument("dlc_id", help="DLC ID (e.g. EP01, GP05, SP18)")
    pd.add_argument("local_file", help="Path to DLC zip file")
    pd.add_argument("--force", action="store_true", help="Overwrite if exists")
    pd.add_argument("--skip-verify", action="store_true")

    # --- publish-language ---
    pl = sub.add_parser("publish-language", help="Upload a language pack")
    pl.add_argument("locale", help="Locale code (e.g. de_DE, fr_FR)")
    pl.add_argument("game_version", help="Game version (e.g. 1.122.100)")
    pl.add_argument("local_file", help="Path to language zip file")
    pl.add_argument("--force", action="store_true", help="Overwrite if exists")
    pl.add_argument("--skip-verify", action="store_true")

    # --- publish-manifest ---
    pm = sub.add_parser("publish-manifest", help="Upload master manifest.json")
    pm.add_argument("local_file", help="Path to manifest.json")
    pm.add_argument("--skip-verify", action="store_true")

    # --- upload (manual) ---
    up = sub.add_parser("upload", help="Upload any file to a custom CDN path")
    up.add_argument("local_file", help="Path to local file")
    up.add_argument("cdn_path", help="CDN path (e.g. tools/file.exe)")
    up.add_argument("--force", action="store_true", help="Overwrite if exists")
    up.add_argument("--skip-verify", action="store_true")

    # --- batch ---
    ba = sub.add_parser("batch", help="Upload all files in a directory")
    ba.add_argument("local_dir", help="Local directory to upload")
    ba.add_argument("cdn_prefix", help="CDN prefix (e.g. dlc, patches)")
    ba.add_argument("--force", action="store_true", help="Overwrite if exists")
    ba.add_argument("--skip-verify", action="store_true")

    # --- list ---
    sub.add_parser("list", help="List all CDN entries")

    # --- delete ---
    rm = sub.add_parser("delete", help="Remove a CDN entry")
    rm.add_argument("cdn_path", help="CDN path to remove")

    # --- verify ---
    vf = sub.add_parser("verify", help="Verify a CDN path is accessible")
    vf.add_argument("cdn_path", help="CDN path to verify")

    # --- contributions ---
    ct = sub.add_parser("contributions", help="List pending user contributions")
    ct.add_argument("--all", action="store_true", help="Show all (not just pending)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_config()
    opts = {"force": getattr(args, "force", False), "skip_verify": getattr(args, "skip_verify", False)}

    if args.command == "publish-patch":
        local_path = Path(args.local_file)
        if not local_path.is_file():
            print(f"ERROR: File not found: {local_path}")
            sys.exit(1)
        publish_patch(config, args.from_ver, args.to_ver, local_path, **opts)

    elif args.command == "publish-dlc":
        local_path = Path(args.local_file)
        if not local_path.is_file():
            print(f"ERROR: File not found: {local_path}")
            sys.exit(1)
        publish_dlc(config, args.dlc_id, local_path, **opts)

    elif args.command == "publish-language":
        local_path = Path(args.local_file)
        if not local_path.is_file():
            print(f"ERROR: File not found: {local_path}")
            sys.exit(1)
        publish_language(config, args.locale, args.game_version, local_path, **opts)

    elif args.command == "publish-manifest":
        local_path = Path(args.local_file)
        if not local_path.is_file():
            print(f"ERROR: File not found: {local_path}")
            sys.exit(1)
        publish_manifest(config, local_path, skip_verify=opts["skip_verify"])

    elif args.command == "upload":
        local_path = Path(args.local_file)
        if not local_path.is_file():
            print(f"ERROR: File not found: {local_path}")
            sys.exit(1)
        upload_to_cdn(config, local_path, args.cdn_path, **opts)

    elif args.command == "batch":
        local_dir = Path(args.local_dir)
        if not local_dir.is_dir():
            print(f"ERROR: Directory not found: {local_dir}")
            sys.exit(1)
        batch_upload(config, local_dir, args.cdn_prefix, **opts)

    elif args.command == "list":
        keys = list_kv_entries(config)
        if not keys:
            print("No entries in CDN_ROUTES.")
        else:
            # Group by category
            patches = []
            dlcs = []
            languages = []
            other = []
            for k in keys:
                if k.startswith("patches/"):
                    patches.append(k)
                elif k.startswith("dlc/"):
                    dlcs.append(k)
                elif k.startswith("language/"):
                    languages.append(k)
                else:
                    other.append(k)

            print(f"CDN Routes ({len(keys)} entries):\n")
            if other:
                print("  General:")
                for k in other:
                    print(f"    {CDN_DOMAIN}/{k}")
            if patches:
                print(f"\n  Patches ({len(patches)}):")
                for k in sorted(patches):
                    print(f"    {CDN_DOMAIN}/{k}")
            if dlcs:
                print(f"\n  DLCs ({len(dlcs)}):")
                for k in sorted(dlcs):
                    print(f"    {CDN_DOMAIN}/{k}")
            if languages:
                print(f"\n  Languages ({len(languages)}):")
                for k in sorted(languages):
                    print(f"    {CDN_DOMAIN}/{k}")

    elif args.command == "delete":
        cdn_path = args.cdn_path.strip("/")
        print(f"Deleting CDN entry: {cdn_path}")
        delete_kv_entry(config, cdn_path)

    elif args.command == "verify":
        cdn_path = args.cdn_path.strip("/")
        verify_cdn(cdn_path)

    elif args.command == "contributions":
        list_contributions(config, show_all=args.all)


def list_contributions(config: dict, show_all: bool = False) -> None:
    """Fetch and display contributions from the API."""
    api_url = config.get("contribution_api_url", "https://api.hyperabyss.com")
    admin_pw = config.get("contribution_admin_password", "")

    if not admin_pw:
        print("ERROR: 'contribution_admin_password' not set in cdn_config.json")
        sys.exit(1)

    url = f"{api_url}/admin/list?pw={admin_pw}"
    try:
        resp = requests.get(url, timeout=15)
    except requests.RequestException as e:
        print(f"ERROR: Could not connect to API: {e}")
        sys.exit(1)

    if resp.status_code == 401:
        print("ERROR: Invalid admin password.")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"ERROR: API returned {resp.status_code}")
        sys.exit(1)

    contributions = resp.json()

    if not show_all:
        contributions = [c for c in contributions if c.get("status") == "pending"]

    if not contributions:
        print("No pending contributions." if not show_all else "No contributions found.")
        return

    for c in contributions:
        status = c.get("status", "unknown").upper()
        dlc_id = c.get("dlc_id", "???")
        dlc_name = c.get("dlc_name", "")
        file_count = c.get("file_count", 0)
        total_size = c.get("total_size", 0)
        submitted = c.get("submitted_at", "")[:19]
        size_mb = total_size / 1024 / 1024

        # Status colors (ANSI)
        if status == "PENDING":
            badge = f"\033[33m[{status}]\033[0m"
        elif status == "APPROVED":
            badge = f"\033[32m[{status}]\033[0m"
        elif status == "REJECTED":
            badge = f"\033[31m[{status}]\033[0m"
        else:
            badge = f"[{status}]"

        label = f"{dlc_id} - {dlc_name}" if dlc_name else dlc_id
        print(f"  {badge} {label}")
        print(f"         {file_count} files, {size_mb:.1f} MB | Submitted: {submitted}")

        # Show files for pending
        if c.get("status") == "pending":
            for f in c.get("files", [])[:5]:
                fname = f.get("name", "")
                fmd5 = f.get("md5", "")
                fsize = f.get("size", 0) / 1024 / 1024
                print(f"           {fname} ({fsize:.1f} MB) md5:{fmd5}")
            remaining = len(c.get("files", [])) - 5
            if remaining > 0:
                print(f"           ... and {remaining} more files")

        print()


if __name__ == "__main__":
    main()
