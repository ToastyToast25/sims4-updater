"""Archive operations — create, list, verify, delete, promote versioned snapshots."""

from __future__ import annotations

import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from .connection import CDN_DOMAIN, SEEDBOX_BASE_DIR, ConnectionManager

# Strict pattern for version strings — prevents command injection in SSH commands
_VERSION_RE = re.compile(r"^[\d]+(?:\.[\d]+)*$")


def list_archives(conn: ConnectionManager) -> dict[str, dict]:
    """Fetch archived versions from the live manifest.

    Returns {version: {date, manifest_url, dlc_count, language_count}}.
    """
    manifest = conn.fetch_manifest()
    return manifest.get("versions", {})


def create_archive(
    conn: ConnectionManager,
    version: str,
    *,
    log_cb=None,
) -> bool:
    """Archive current CDN content as a versioned snapshot.

    Uses SSH hardlinks on seedbox (zero extra disk), generates archived
    manifest with rewritten URLs, registers KV entries, and updates
    the main manifest's versions dict.
    """

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    if not _VERSION_RE.match(version):
        log(f"Invalid version string: {version!r}", "error")
        return False

    log(f"Creating archive for version {version}...")

    # Fetch current manifest
    log("Fetching manifest from CDN...")
    manifest = conn.fetch_manifest()
    dlc_downloads = manifest.get("dlc_downloads", {})
    lang_downloads = manifest.get("language_downloads", {})
    log(f"Found {len(dlc_downloads)} DLCs, {len(lang_downloads)} languages")

    if not dlc_downloads and not lang_downloads:
        log("Manifest has no DLC or language entries to archive", "error")
        return False

    # SSH to seedbox
    log("Connecting to seedbox via SSH...")
    ssh = conn.connect_ssh()

    try:
        archive_base = f"{SEEDBOX_BASE_DIR}/archives/{version}"

        # Create directories
        _, stderr, rc = _ssh_exec(ssh, f"mkdir -p ~/{archive_base}/dlc ~/{archive_base}/language")
        if rc != 0:
            log(f"mkdir failed: {stderr.strip()}", "error")
            return False

        # Hardlink DLCs (use $HOME instead of ~ to avoid tilde-in-quotes issue)
        if dlc_downloads:
            log(f"Hardlinking {len(dlc_downloads)} DLC archives...")
            ln_cmds = []
            for dlc_id in sorted(dlc_downloads):
                src = f"$HOME/{SEEDBOX_BASE_DIR}/dlc/{dlc_id}.zip"
                dst = f"$HOME/{archive_base}/dlc/{dlc_id}.zip"
                ln_cmds.append(f'ln "{src}" "{dst}" 2>/dev/null')
            _ssh_exec(ssh, " ; ".join(ln_cmds))

            out, _, _ = _ssh_exec(ssh, f"ls -1 ~/{archive_base}/dlc/ 2>/dev/null")
            dlc_count = len([f for f in out.strip().split("\n") if f.endswith(".zip")])
            log(f"Linked {dlc_count}/{len(dlc_downloads)} DLC files")

        # Hardlink languages
        if lang_downloads:
            log(f"Hardlinking {len(lang_downloads)} language packs...")
            ln_cmds = []
            for locale in sorted(lang_downloads):
                src = f"$HOME/{SEEDBOX_BASE_DIR}/language/{locale}.zip"
                dst = f"$HOME/{archive_base}/language/{locale}.zip"
                ln_cmds.append(f'ln "{src}" "{dst}" 2>/dev/null')
            _ssh_exec(ssh, " ; ".join(ln_cmds))

            out, _, _ = _ssh_exec(ssh, f"ls -1 ~/{archive_base}/language/ 2>/dev/null")
            lang_count = len([f for f in out.strip().split("\n") if f.endswith(".zip")])
            log(f"Linked {lang_count}/{len(lang_downloads)} language files")

        # Generate archived manifest
        log("Generating archived manifest...")
        archived_manifest: dict[str, Any] = {"latest": version}

        if dlc_downloads:
            archived_manifest["dlc_downloads"] = {
                dlc_id: {**entry, "url": f"{CDN_DOMAIN}/archives/{version}/dlc/{dlc_id}.zip"}
                for dlc_id, entry in dlc_downloads.items()
            }
        if lang_downloads:
            archived_manifest["language_downloads"] = {
                locale: {**entry, "url": f"{CDN_DOMAIN}/archives/{version}/language/{locale}.zip"}
                for locale, entry in lang_downloads.items()
            }

        # Upload archived manifest via SFTP
        sftp = ssh.open_sftp()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                json.dump(archived_manifest, tmp, indent=2)
                tmp_path = Path(tmp.name)
            sftp.put(str(tmp_path), f"{archive_base}/manifest.json")
            tmp_path.unlink(missing_ok=True)
        finally:
            sftp.close()

        # Register KV entries
        log("Registering Cloudflare KV entries...")
        kv_count = 0

        conn.kv_put(
            f"archives/{version}/manifest.json",
            f"{SEEDBOX_BASE_DIR}/archives/{version}/manifest.json",
        )
        kv_count += 1

        for dlc_id in sorted(dlc_downloads):
            kv_key = f"archives/{version}/dlc/{dlc_id}.zip"
            if not conn.kv_exists(kv_key):
                conn.kv_put(kv_key, f"{SEEDBOX_BASE_DIR}/archives/{version}/dlc/{dlc_id}.zip")
            kv_count += 1

        for locale in sorted(lang_downloads):
            kv_key = f"archives/{version}/language/{locale}.zip"
            if not conn.kv_exists(kv_key):
                conn.kv_put(kv_key, f"{SEEDBOX_BASE_DIR}/archives/{version}/language/{locale}.zip")
            kv_count += 1

        log(f"Registered {kv_count} KV entries")

        # Update main manifest versions
        log("Updating main manifest...")
        manifest["versions"] = manifest.get("versions", {})
        manifest["versions"][version] = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "manifest_url": f"{CDN_DOMAIN}/archives/{version}/manifest.json",
            "dlc_count": len(dlc_downloads),
            "language_count": len(lang_downloads),
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(manifest, tmp, indent=2)
            tmp_path = Path(tmp.name)
        try:
            conn.publish_manifest(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        log(f"Archive {version} created successfully!", "success")
        return True

    finally:
        ssh.close()


def verify_archive(
    conn: ConnectionManager,
    version: str,
    *,
    workers: int = 10,
    log_cb=None,
    progress_cb=None,
) -> tuple[int, int, list[tuple[str, str, int]]]:
    """HEAD-check all URLs in an archived manifest.

    Returns (ok_count, broken_count, broken_list).
    broken_list items: (category_id, url, status_code).
    """

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    archive_url = f"{CDN_DOMAIN}/archives/{version}/manifest.json"
    log("Fetching archived manifest...")

    import urllib.request

    req = urllib.request.Request(archive_url, headers={"User-Agent": "CDNManager/1.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    archived = json.loads(resp.read().decode("utf-8"))

    urls_to_check: list[tuple[str, str]] = []
    urls_to_check.append(("manifest", archive_url))

    for dlc_id, entry in sorted(archived.get("dlc_downloads", {}).items()):
        url = entry.get("url", "")
        if url:
            urls_to_check.append((f"dlc:{dlc_id}", url))

    for locale, entry in sorted(archived.get("language_downloads", {}).items()):
        url = entry.get("url", "")
        if url:
            urls_to_check.append((f"lang:{locale}", url))

    total = len(urls_to_check)
    log(f"Checking {total} URLs...")

    ok_count = 0
    broken: list[tuple[str, str, int]] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(ConnectionManager.head_check, url): (label, url)
            for label, url in urls_to_check
        }
        for done_count, future in enumerate(as_completed(futures), 1):
            label, url = futures[future]
            status, size = future.result()
            if status == 200:
                ok_count += 1
            else:
                broken.append((label, url, status))
            if progress_cb:
                progress_cb(done_count, total)

    return ok_count, len(broken), broken


def delete_archive(
    conn: ConnectionManager,
    version: str,
    *,
    log_cb=None,
) -> bool:
    """Remove archive from seedbox, KV, and main manifest."""

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    if not _VERSION_RE.match(version):
        log(f"Invalid version string: {version!r}", "error")
        return False

    log(f"Deleting archive {version}...")

    # SSH to remove files
    log("Connecting to seedbox via SSH...")
    ssh = conn.connect_ssh()
    try:
        archive_path = f"~/{SEEDBOX_BASE_DIR}/archives/{version}"
        _, stderr, rc = _ssh_exec(ssh, f"rm -rf {archive_path}")
        if rc != 0:
            log(f"rm -rf warning: {stderr.strip()}", "warning")
        else:
            log("Removed from seedbox", "success")
    finally:
        ssh.close()

    # Delete KV entries
    log("Listing KV entries...")
    all_keys = conn.kv_list()
    prefix = f"archives/{version}/"
    matching = [k for k in all_keys if k.startswith(prefix)]

    if matching:
        log(f"Deleting {len(matching)} KV entries...")
        deleted = sum(1 for k in matching if conn.kv_delete(k))
        log(f"Deleted {deleted}/{len(matching)} KV entries")

    # Update main manifest
    log("Updating main manifest...")
    manifest = conn.fetch_manifest()
    versions = manifest.get("versions", {})
    if version in versions:
        del versions[version]
        manifest["versions"] = versions

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(manifest, tmp, indent=2)
            tmp_path = Path(tmp.name)
        try:
            conn.publish_manifest(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        log(f"Removed {version} from main manifest")

    log(f"Archive {version} deleted", "success")
    return True


def promote_archive(
    conn: ConnectionManager,
    version: str,
    *,
    log_cb=None,
) -> bool:
    """Rollback: copy archived files back to main CDN paths."""

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    if not _VERSION_RE.match(version):
        log(f"Invalid version string: {version!r}", "error")
        return False

    log(f"Promoting archive {version} to main...")

    # Fetch archived manifest
    import urllib.request

    archive_url = f"{CDN_DOMAIN}/archives/{version}/manifest.json"
    req = urllib.request.Request(archive_url, headers={"User-Agent": "CDNManager/1.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    archived = json.loads(resp.read().decode("utf-8"))

    dlc_downloads = archived.get("dlc_downloads", {})
    lang_downloads = archived.get("language_downloads", {})
    log(f"Found {len(dlc_downloads)} DLCs, {len(lang_downloads)} languages")

    # SSH copy files
    log("Connecting to seedbox via SSH...")
    ssh = conn.connect_ssh()
    try:
        archive_base = f"{SEEDBOX_BASE_DIR}/archives/{version}"

        if dlc_downloads:
            log(f"Copying {len(dlc_downloads)} DLC files to main directory...")
            _, stderr, rc = _ssh_exec(
                ssh,
                f"cp ~/{archive_base}/dlc/*.zip ~/{SEEDBOX_BASE_DIR}/dlc/",
            )
            if rc != 0:
                log(f"cp warning: {stderr.strip()}", "warning")

        if lang_downloads:
            log(f"Copying {len(lang_downloads)} language files to main directory...")
            _, stderr, rc = _ssh_exec(
                ssh,
                f"cp ~/{archive_base}/language/*.zip ~/{SEEDBOX_BASE_DIR}/language/",
            )
            if rc != 0:
                log(f"cp warning: {stderr.strip()}", "warning")
    finally:
        ssh.close()

    # Update KV entries
    log("Updating KV entries to main paths...")
    kv_count = 0

    for dlc_id in sorted(dlc_downloads):
        conn.kv_put(f"dlc/{dlc_id}.zip", f"{SEEDBOX_BASE_DIR}/dlc/{dlc_id}.zip")
        kv_count += 1

    for locale in sorted(lang_downloads):
        conn.kv_put(f"language/{locale}.zip", f"{SEEDBOX_BASE_DIR}/language/{locale}.zip")
        kv_count += 1

    log(f"Updated {kv_count} KV entries")

    # Rebuild main manifest
    log("Rebuilding main manifest...")
    manifest = conn.fetch_manifest()
    manifest["latest"] = version

    if dlc_downloads:
        manifest["dlc_downloads"] = {
            dlc_id: {**entry, "url": f"{CDN_DOMAIN}/dlc/{dlc_id}.zip"}
            for dlc_id, entry in dlc_downloads.items()
        }
    if lang_downloads:
        manifest["language_downloads"] = {
            locale: {**entry, "url": f"{CDN_DOMAIN}/language/{locale}.zip"}
            for locale, entry in lang_downloads.items()
        }

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(manifest, tmp, indent=2)
        tmp_path = Path(tmp.name)
    try:
        conn.publish_manifest(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    log(f"Promotion complete — CDN now serves {version}", "success")
    return True


def _ssh_exec(client, command: str) -> tuple[str, str, int]:
    """Execute SSH command, return (stdout, stderr, exit_status)."""
    stdin, stdout, stderr = client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode(), exit_status
