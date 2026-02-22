"""
CDN Archive Manager -- Archive, list, verify, delete, and promote DLC/language snapshots.

Creates versioned snapshots of all DLC and language pack files on the Whatbox seedbox
using hardlinks (no additional disk usage), then registers archived manifests on the CDN
via Cloudflare KV. Supports rollback by promoting an archived version back to main.

Usage:
    python cdn_archive.py create 1.121.372.1020      # Archive current files as this version
    python cdn_archive.py list                        # Show all archived versions
    python cdn_archive.py verify 1.121.372.1020       # HEAD-request all URLs in archived manifest
    python cdn_archive.py delete 1.121.372.1020       # Remove archive from seedbox + KV + manifest
    python cdn_archive.py delete 1.121.372.1020 --yes # Skip confirmation prompt
    python cdn_archive.py promote 1.121.372.1020      # Rollback: copy archived files to main paths

Setup:
    pip install paramiko requests
    Create cdn_config.json next to this script (see cdn_config.example.json)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import paramiko
import requests
from cdn_pack_upload import (
    CDN_DOMAIN,
    SEEDBOX_BASE_DIR,
    add_kv_entry,
    fmt_size,
    kv_exists,
    list_kv_entries,
    load_config,
)
from cdn_upload import publish_manifest

# ── ANSI Colors ──────────────────────────────────────────────────

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

MANIFEST_URL = f"{CDN_DOMAIN}/manifest.json"
HEAD_WORKERS = 10
HEAD_TIMEOUT = 20
SCRIPT_DIR = Path(__file__).parent


def _ok(text: str) -> str:
    return f"{_GREEN}{text}{_RESET}"


def _warn(text: str) -> str:
    return f"{_YELLOW}{text}{_RESET}"


def _err(text: str) -> str:
    return f"{_RED}{text}{_RESET}"


def _info(text: str) -> str:
    return f"{_CYAN}{text}{_RESET}"


def _bold(text: str) -> str:
    return f"{_BOLD}{text}{_RESET}"


# ── SSH Helper ───────────────────────────────────────────────────


def _connect_ssh(config: dict) -> paramiko.SSHClient:
    """Open an SSH connection to the Whatbox seedbox.

    Returns a connected paramiko.SSHClient with AutoAddPolicy set.
    The caller is responsible for closing the client when done.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=config["whatbox_host"],
        port=config.get("whatbox_port", 22),
        username=config["whatbox_user"],
        password=config["whatbox_pass"],
    )
    return client


def _ssh_exec(client: paramiko.SSHClient, command: str) -> tuple[str, str, int]:
    """Execute a command over SSH and return (stdout, stderr, exit_status)."""
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode(), exit_status


# ── Manifest Fetch ───────────────────────────────────────────────


def _fetch_manifest(url: str = MANIFEST_URL) -> dict:
    """Fetch and parse the JSON manifest from the CDN."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  {_err('ERROR')}: Failed to fetch manifest from {url}")
        print(f"  {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"  {_err('ERROR')}: Manifest is not valid JSON")
        print(f"  {e}")
        sys.exit(1)


# ── HEAD Verification ────────────────────────────────────────────


def _head_check(url: str) -> tuple[str, int, int]:
    """HEAD-request a single URL.

    Returns (url, status_code, content_length). On connection failure
    status_code is 0 and content_length is 0.
    """
    try:
        resp = requests.head(url, timeout=HEAD_TIMEOUT, allow_redirects=True)
        size = int(resp.headers.get("Content-Length", 0))
        return url, resp.status_code, size
    except requests.RequestException:
        return url, 0, 0


# ── Create Archive ───────────────────────────────────────────────


def cmd_create(config: dict, version: str) -> None:
    """Archive the current DLC and language files as a versioned snapshot.

    Creates hardlinks on the seedbox (zero extra disk space), generates an
    archived manifest with rewritten URLs, registers all files in Cloudflare KV,
    and updates the main manifest's ``versions`` dict.
    """
    print()
    print(f"{_bold('=== Create Archive ===')}  version: {_info(version)}")
    print()

    # Step 1: Connect via SSH
    print("  Connecting to seedbox via SSH...")
    ssh = _connect_ssh(config)

    try:
        # Step 2: Fetch current manifest from CDN
        print(f"  Fetching manifest from {MANIFEST_URL}...")
        manifest = _fetch_manifest()

        dlc_downloads = manifest.get("dlc_downloads", {})
        lang_downloads = manifest.get("language_downloads", {})
        print(f"  DLC entries:      {len(dlc_downloads)}")
        print(f"  Language entries:  {len(lang_downloads)}")
        print()

        if not dlc_downloads and not lang_downloads:
            print(f"  {_err('ERROR')}: Manifest has no DLC or language entries to archive.")
            return

        # Step 3: Create archive directories on seedbox
        archive_base = f"{SEEDBOX_BASE_DIR}/archives/{version}"
        print(f"  Creating archive directories at ~/{archive_base}/...")

        _, stderr, rc = _ssh_exec(
            ssh,
            f"mkdir -p ~/{archive_base}/dlc ~/{archive_base}/language",
        )
        if rc != 0:
            print(f"  {_err('ERROR')}: mkdir failed: {stderr.strip()}")
            return

        # Step 4: Create hardlinks for DLC ZIPs
        dlc_count = 0
        dlc_total_size = 0

        if dlc_downloads:
            print(f"  Hardlinking {len(dlc_downloads)} DLC archives...")

            # Build a single ln command for all DLC files at once
            ln_cmds = []
            for dlc_id in sorted(dlc_downloads):
                src = f"~/{SEEDBOX_BASE_DIR}/dlc/{dlc_id}.zip"
                dst = f"~/{archive_base}/dlc/{dlc_id}.zip"
                ln_cmds.append(f'ln "{src}" "{dst}" 2>/dev/null')

            batch_cmd = " ; ".join(ln_cmds)
            _ssh_exec(ssh, batch_cmd)

            # Verify how many succeeded by listing the archive dir
            out, _, _ = _ssh_exec(ssh, f"ls -1 ~/{archive_base}/dlc/ 2>/dev/null")
            linked_files = [f for f in out.strip().split("\n") if f.endswith(".zip")]
            dlc_count = len(linked_files)

            # Get total size of the archive dir
            out, _, _ = _ssh_exec(ssh, f"du -sb ~/{archive_base}/dlc/ 2>/dev/null")
            if out.strip():
                with contextlib.suppress(ValueError, IndexError):
                    dlc_total_size = int(out.strip().split()[0])

            print(f"    Linked: {dlc_count}/{len(dlc_downloads)} DLC files")

        # Step 5: Create hardlinks for language ZIPs
        lang_count = 0
        lang_total_size = 0

        if lang_downloads:
            print(f"  Hardlinking {len(lang_downloads)} language packs...")

            ln_cmds = []
            for locale in sorted(lang_downloads):
                src = f"~/{SEEDBOX_BASE_DIR}/language/{locale}.zip"
                dst = f"~/{archive_base}/language/{locale}.zip"
                ln_cmds.append(f'ln "{src}" "{dst}" 2>/dev/null')

            batch_cmd = " ; ".join(ln_cmds)
            _ssh_exec(ssh, batch_cmd)

            out, _, _ = _ssh_exec(ssh, f"ls -1 ~/{archive_base}/language/ 2>/dev/null")
            linked_files = [f for f in out.strip().split("\n") if f.endswith(".zip")]
            lang_count = len(linked_files)

            out, _, _ = _ssh_exec(ssh, f"du -sb ~/{archive_base}/language/ 2>/dev/null")
            if out.strip():
                with contextlib.suppress(ValueError, IndexError):
                    lang_total_size = int(out.strip().split()[0])

            print(f"    Linked: {lang_count}/{len(lang_downloads)} language files")

        print()

        # Step 6: Generate archived manifest with rewritten URLs
        print("  Generating archived manifest...")

        archived_manifest = {
            "latest": version,
        }

        # Rewrite DLC download URLs to archive paths
        if dlc_downloads:
            archived_dlcs = {}
            for dlc_id, entry in dlc_downloads.items():
                archived_dlcs[dlc_id] = {
                    **entry,
                    "url": f"{CDN_DOMAIN}/archives/{version}/dlc/{dlc_id}.zip",
                }
            archived_manifest["dlc_downloads"] = archived_dlcs

        # Rewrite language download URLs to archive paths
        if lang_downloads:
            archived_langs = {}
            for locale, entry in lang_downloads.items():
                archived_langs[locale] = {
                    **entry,
                    "url": (f"{CDN_DOMAIN}/archives/{version}/language/{locale}.zip"),
                }
            archived_manifest["language_downloads"] = archived_langs

        # Step 7: Upload archived manifest to seedbox via SFTP
        print(f"  Uploading archived manifest to ~/{archive_base}/manifest.json...")

        sftp = ssh.open_sftp()
        try:
            manifest_json = json.dumps(archived_manifest, indent=2)
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(manifest_json)
                tmp_path = Path(tmp.name)

            remote_manifest = f"{archive_base}/manifest.json"
            sftp.put(str(tmp_path), remote_manifest)
            tmp_path.unlink(missing_ok=True)
        finally:
            sftp.close()

        # Step 8: Register KV entries for all archived files
        print("  Registering Cloudflare KV entries...")

        kv_count = 0

        # Archived manifest
        kv_key = f"archives/{version}/manifest.json"
        kv_value = f"{SEEDBOX_BASE_DIR}/archives/{version}/manifest.json"
        add_kv_entry(config, kv_key, kv_value)
        kv_count += 1

        # DLC entries
        for dlc_id in sorted(dlc_downloads):
            kv_key = f"archives/{version}/dlc/{dlc_id}.zip"
            kv_value = f"{SEEDBOX_BASE_DIR}/archives/{version}/dlc/{dlc_id}.zip"
            if not kv_exists(config, kv_key):
                add_kv_entry(config, kv_key, kv_value)
            kv_count += 1

        # Language entries
        for locale in sorted(lang_downloads):
            kv_key = f"archives/{version}/language/{locale}.zip"
            kv_value = f"{SEEDBOX_BASE_DIR}/archives/{version}/language/{locale}.zip"
            if not kv_exists(config, kv_key):
                add_kv_entry(config, kv_key, kv_value)
            kv_count += 1

        print(f"    Registered {kv_count} KV entries")
        print()

        # Step 9: Update main manifest's versions dict
        print("  Updating main manifest versions...")

        manifest["versions"] = manifest.get("versions", {})
        manifest["versions"][version] = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "manifest_url": f"{CDN_DOMAIN}/archives/{version}/manifest.json",
            "dlc_count": len(dlc_downloads),
            "language_count": len(lang_downloads),
        }

        # Step 10: Write updated main manifest to temp file and upload
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
            dir=str(SCRIPT_DIR),
        ) as tmp:
            json.dump(manifest, tmp, indent=2)
            tmp_manifest_path = Path(tmp.name)

        print("  Uploading updated main manifest to CDN...")
        try:
            publish_manifest(config, tmp_manifest_path)
        finally:
            tmp_manifest_path.unlink(missing_ok=True)

        # Step 11: Print summary
        total_size = dlc_total_size + lang_total_size
        print()
        print(f"{_bold('=== Archive Created ===')}")
        print()
        print(f"  Version:    {_info(version)}")
        print(f"  DLCs:       {dlc_count} files ({fmt_size(dlc_total_size)})")
        print(f"  Languages:  {lang_count} files ({fmt_size(lang_total_size)})")
        print(f"  Total:      {fmt_size(total_size)} (hardlinked, no extra disk)")
        print(f"  KV entries: {kv_count}")
        print(f"  Manifest:   {CDN_DOMAIN}/archives/{version}/manifest.json")
        print()

    finally:
        ssh.close()


# ── List Archives ────────────────────────────────────────────────


def cmd_list(config: dict) -> None:
    """Display a table of all archived versions from the main manifest."""
    print()
    print(f"{_bold('=== Archived Versions ===')}")
    print()

    manifest = _fetch_manifest()
    versions = manifest.get("versions", {})

    if not versions:
        print(f"  {_warn('No archived versions found.')}")
        print()
        print("  Create one with:  python cdn_archive.py create <version>")
        print()
        return

    # Determine column widths for alignment
    ver_width = max(len(v) for v in versions)
    ver_width = max(ver_width, 7)  # minimum "VERSION" header

    # Header
    print(f"  {'VERSION':<{ver_width}}  {'DATE':<12}  {'DLCs':>5}  {'Langs':>5}  MANIFEST URL")
    print(f"  {'-' * ver_width}  {'-' * 12}  {'-' * 5}  {'-' * 5}  {'-' * 50}")

    # Rows sorted by date descending, then version
    sorted_versions = sorted(
        versions.items(),
        key=lambda kv: (kv[1].get("date", ""), kv[0]),
        reverse=True,
    )

    for ver, info in sorted_versions:
        date = info.get("date", "unknown")
        dlc_count = info.get("dlc_count", 0)
        lang_count = info.get("language_count", 0)
        manifest_url = info.get("manifest_url", "")
        print(f"  {ver:<{ver_width}}  {date:<12}  {dlc_count:>5}  {lang_count:>5}  {manifest_url}")

    print()
    print(f"  Total: {len(versions)} archived version(s)")
    print()


# ── Verify Archive ───────────────────────────────────────────────


def cmd_verify(config: dict, version: str) -> None:
    """HEAD-request every URL in an archived manifest and report status."""
    print()
    print(f"{_bold('=== Verify Archive ===')}  version: {_info(version)}")
    print()

    archive_manifest_url = f"{CDN_DOMAIN}/archives/{version}/manifest.json"
    print(f"  Fetching archived manifest from {archive_manifest_url}...")

    archived = _fetch_manifest(archive_manifest_url)

    dlc_downloads = archived.get("dlc_downloads", {})
    lang_downloads = archived.get("language_downloads", {})

    # Collect all URLs to check
    urls_to_check: list[tuple[str, str, str]] = []  # (category, id, url)

    urls_to_check.append(("manifest", version, archive_manifest_url))

    for dlc_id, entry in sorted(dlc_downloads.items()):
        url = entry.get("url", "")
        if url:
            urls_to_check.append(("dlc", dlc_id, url))

    for locale, entry in sorted(lang_downloads.items()):
        url = entry.get("url", "")
        if url:
            urls_to_check.append(("language", locale, url))

    total = len(urls_to_check)
    print(f"  Checking {total} URLs ({HEAD_WORKERS} workers)...")
    print()

    ok_count = 0
    broken: list[tuple[str, str, str, int]] = []  # (category, id, url, status)

    with ThreadPoolExecutor(max_workers=HEAD_WORKERS) as pool:
        future_to_info = {}
        for category, entry_id, url in urls_to_check:
            future = pool.submit(_head_check, url)
            future_to_info[future] = (category, entry_id, url)

        for _done_count, future in enumerate(as_completed(future_to_info), 1):
            category, entry_id, url = future_to_info[future]
            _, status, size = future.result()

            if status == 200:
                ok_count += 1
                size_str = fmt_size(size) if size > 0 else "??"
                tag = f"[{category}:{entry_id}]"
                print(
                    f"\r  {_ok('OK')}  {tag:<30} {size_str:>10}",
                    end="",
                    flush=True,
                )
            else:
                status_str = f"HTTP {status}" if status else "unreachable"
                broken.append((category, entry_id, url, status))
                tag = f"[{category}:{entry_id}]"
                print(
                    f"\r  {_err('FAIL')}  {tag:<30} {status_str}",
                    end="",
                    flush=True,
                )

            # Print each on its own line
            print()

    # Summary
    print()
    print(f"{_bold('=== Verification Summary ===')}")
    print()
    print(f"  Total:   {total}")
    print(f"  OK:      {_ok(str(ok_count))}")
    print(f"  Broken:  {_err(str(len(broken)))}")

    if broken:
        print()
        print(f"  {_err('Broken entries:')}")
        for category, entry_id, url, status in broken:
            status_str = f"HTTP {status}" if status else "unreachable"
            print(f"    [{category}:{entry_id}] {status_str}")
            print(f"      {url}")

    print()


# ── Delete Archive ───────────────────────────────────────────────


def cmd_delete(config: dict, version: str, skip_confirm: bool = False) -> None:
    """Remove an archived version from seedbox, KV, and main manifest."""
    print()
    print(f"{_bold('=== Delete Archive ===')}  version: {_info(version)}")
    print()

    # Confirm with user
    if not skip_confirm:
        print(f"  {_warn('WARNING')}: This will permanently delete archive '{version}' from:")
        print(f"    - Seedbox: ~/{SEEDBOX_BASE_DIR}/archives/{version}/")
        print(f"    - Cloudflare KV: all archives/{version}/* entries")
        print(f"    - Main manifest: versions['{version}']")
        print()
        answer = input("  Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print(f"\n  {_info('Cancelled.')}")
            print()
            return

    print()

    # Step 1: SSH to seedbox and remove the archive directory
    print("  Connecting to seedbox via SSH...")
    ssh = _connect_ssh(config)

    try:
        archive_path = f"~/{SEEDBOX_BASE_DIR}/archives/{version}"
        print(f"  Removing {archive_path}...")

        _, stderr, rc = _ssh_exec(ssh, f"rm -rf {archive_path}")
        if rc != 0:
            print(f"  {_warn('WARNING')}: rm -rf returned exit {rc}: {stderr.strip()}")
        else:
            print(f"    {_ok('Removed from seedbox')}")
    finally:
        ssh.close()

    # Step 2: List and delete all matching KV entries
    print("  Listing Cloudflare KV entries...")
    all_keys = list_kv_entries(config)
    prefix = f"archives/{version}/"
    matching_keys = [k for k in all_keys if k.startswith(prefix)]

    if matching_keys:
        print(f"  Deleting {len(matching_keys)} KV entries matching '{prefix}'...")

        kv_url_base = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{config['cloudflare_account_id']}/storage/kv/namespaces/"
            f"{config['cloudflare_kv_namespace_id']}/values"
        )
        headers = {"Authorization": f"Bearer {config['cloudflare_api_token']}"}

        deleted_count = 0
        for key in matching_keys:
            try:
                resp = requests.delete(
                    f"{kv_url_base}/{key}",
                    headers=headers,
                    timeout=30,
                )
                if resp.status_code == 200:
                    deleted_count += 1
                else:
                    print(
                        f"    {_warn('WARN')}: Failed to delete KV '{key}': HTTP {resp.status_code}"
                    )
            except requests.RequestException as e:
                print(f"    {_warn('WARN')}: Failed to delete KV '{key}': {e}")

        print(f"    {_ok('Deleted')} {deleted_count}/{len(matching_keys)} KV entries")
    else:
        print(f"    No KV entries found for '{prefix}'")

    # Step 3: Remove version from main manifest and re-upload
    print("  Updating main manifest...")
    manifest = _fetch_manifest()
    versions = manifest.get("versions", {})

    if version in versions:
        del versions[version]
        manifest["versions"] = versions

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
            dir=str(SCRIPT_DIR),
        ) as tmp:
            json.dump(manifest, tmp, indent=2)
            tmp_path = Path(tmp.name)

        try:
            publish_manifest(config, tmp_path)
            print(f"    {_ok('Removed')} version '{version}' from main manifest")
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        print(f"    Version '{version}' was not in main manifest (already gone)")

    # Summary
    print()
    print(f"  {_ok('Archive deleted:')} {version}")
    print()


# ── Promote Archive (Rollback) ───────────────────────────────────


def cmd_promote(config: dict, version: str) -> None:
    """Rollback: copy archived files back to main DLC and language paths.

    Copies files from the archive directory to the main ``dlc/`` and
    ``language/`` directories on the seedbox, updates KV entries to point
    to the main paths, and rebuilds the main manifest with the promoted
    version.
    """
    print()
    print(f"{_bold('=== Promote Archive ===')}  version: {_info(version)}")
    print()

    # Step 1: Fetch archived manifest
    archive_manifest_url = f"{CDN_DOMAIN}/archives/{version}/manifest.json"
    print(f"  Fetching archived manifest from {archive_manifest_url}...")

    archived = _fetch_manifest(archive_manifest_url)

    dlc_downloads = archived.get("dlc_downloads", {})
    lang_downloads = archived.get("language_downloads", {})
    print(f"  DLC entries:      {len(dlc_downloads)}")
    print(f"  Language entries:  {len(lang_downloads)}")
    print()

    # Step 2: SSH to seedbox and copy files back to main paths
    print("  Connecting to seedbox via SSH...")
    ssh = _connect_ssh(config)

    try:
        archive_base = f"{SEEDBOX_BASE_DIR}/archives/{version}"

        # Copy DLC files
        if dlc_downloads:
            print(f"  Copying {len(dlc_downloads)} DLC files to main directory...")
            cmd = f"cp ~/{archive_base}/dlc/*.zip ~/{SEEDBOX_BASE_DIR}/dlc/"
            _, stderr, rc = _ssh_exec(ssh, cmd)
            if rc != 0:
                print(f"    {_warn('WARNING')}: cp returned exit {rc}: {stderr.strip()}")
            else:
                print(f"    {_ok('Copied DLC files')}")

        # Copy language files
        if lang_downloads:
            print(f"  Copying {len(lang_downloads)} language files to main directory...")
            cmd = f"cp ~/{archive_base}/language/*.zip ~/{SEEDBOX_BASE_DIR}/language/"
            _, stderr, rc = _ssh_exec(ssh, cmd)
            if rc != 0:
                print(f"    {_warn('WARNING')}: cp returned exit {rc}: {stderr.strip()}")
            else:
                print(f"    {_ok('Copied language files')}")

    finally:
        ssh.close()

    print()

    # Step 3: Update KV entries for all promoted files to point to main paths
    print("  Updating Cloudflare KV entries to main paths...")

    kv_count = 0

    for dlc_id in sorted(dlc_downloads):
        kv_key = f"dlc/{dlc_id}.zip"
        kv_value = f"{SEEDBOX_BASE_DIR}/dlc/{dlc_id}.zip"
        add_kv_entry(config, kv_key, kv_value)
        kv_count += 1

    for locale in sorted(lang_downloads):
        kv_key = f"language/{locale}.zip"
        kv_value = f"{SEEDBOX_BASE_DIR}/language/{locale}.zip"
        add_kv_entry(config, kv_key, kv_value)
        kv_count += 1

    print(f"    Updated {kv_count} KV entries")
    print()

    # Step 4: Rebuild and upload main manifest
    print("  Rebuilding main manifest...")

    manifest = _fetch_manifest()

    # Set latest version
    manifest["latest"] = version

    # Rebuild DLC download URLs back to main paths
    if dlc_downloads:
        main_dlcs = {}
        for dlc_id, entry in dlc_downloads.items():
            main_dlcs[dlc_id] = {
                **entry,
                "url": f"{CDN_DOMAIN}/dlc/{dlc_id}.zip",
            }
        manifest["dlc_downloads"] = main_dlcs

    # Rebuild language download URLs back to main paths
    if lang_downloads:
        main_langs = {}
        for locale, entry in lang_downloads.items():
            main_langs[locale] = {
                **entry,
                "url": f"{CDN_DOMAIN}/language/{locale}.zip",
            }
        manifest["language_downloads"] = main_langs

    # Step 5: Upload updated main manifest
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
        dir=str(SCRIPT_DIR),
    ) as tmp:
        json.dump(manifest, tmp, indent=2)
        tmp_path = Path(tmp.name)

    print("  Uploading updated main manifest to CDN...")
    try:
        publish_manifest(config, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Summary
    print()
    print(f"{_bold('=== Promotion Complete ===')}")
    print()
    print(f"  Version:    {_info(version)}")
    print(f"  DLCs:       {len(dlc_downloads)} restored to main CDN paths")
    print(f"  Languages:  {len(lang_downloads)} restored to main CDN paths")
    print(f"  KV updated: {kv_count} entries")
    print(f"  Manifest:   latest = '{version}'")
    print()
    print(f"  {_ok('Rollback complete.')} Main CDN now serves version {_info(version)}.")
    print()


# ── CLI ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "CDN Archive Manager -- versioned snapshots of DLC and language "
            "packs on Whatbox seedbox with Cloudflare KV routing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  create   Archive current DLC/language files as a versioned snapshot
  list     Show all archived versions with metadata
  verify   HEAD-request all URLs in an archived manifest
  delete   Remove an archive from seedbox, KV, and manifest
  promote  Rollback: copy archived files back to main CDN paths

examples:
  python cdn_archive.py create 1.121.372.1020
  python cdn_archive.py list
  python cdn_archive.py verify 1.121.372.1020
  python cdn_archive.py delete 1.121.372.1020 --yes
  python cdn_archive.py promote 1.121.372.1020
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser(
        "create",
        help="Archive current DLC/language files as a versioned snapshot",
    )
    p_create.add_argument(
        "version",
        help="Version string for the archive (e.g. 1.121.372.1020)",
    )

    # list
    sub.add_parser("list", help="Show all archived versions")

    # verify
    p_verify = sub.add_parser(
        "verify",
        help="HEAD-request all URLs in an archived manifest",
    )
    p_verify.add_argument(
        "version",
        help="Version string of the archive to verify",
    )

    # delete
    p_delete = sub.add_parser(
        "delete",
        help="Remove archive from seedbox, KV, and manifest",
    )
    p_delete.add_argument(
        "version",
        help="Version string of the archive to delete",
    )
    p_delete.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    # promote
    p_promote = sub.add_parser(
        "promote",
        help="Rollback: copy archived files back to main CDN paths",
    )
    p_promote.add_argument(
        "version",
        help="Version string of the archive to promote (rollback to)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_config()

    if args.command == "create":
        cmd_create(config, args.version)

    elif args.command == "list":
        cmd_list(config)

    elif args.command == "verify":
        cmd_verify(config, args.version)

    elif args.command == "delete":
        cmd_delete(config, args.version, skip_confirm=args.yes)

    elif args.command == "promote":
        cmd_promote(config, args.version)


if __name__ == "__main__":
    main()
