"""Manifest operations — fetch, audit, fix, diff, upload."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .connection import ConnectionManager
from .dlc_ops import fmt_size


def fetch_manifest(conn: ConnectionManager) -> dict[str, Any]:
    """Fetch the live manifest from CDN."""
    return conn.fetch_manifest()


def audit_dlc_entries(
    dlc_downloads: dict[str, Any],
    *,
    workers: int = 10,
    progress_cb=None,
) -> list[tuple[str, str, int, int, int]]:
    """HEAD-request every DLC URL in parallel.

    Returns list of (dlc_id, issue, manifest_size, real_size, status_code).
    issue is "ok", "size_zero", "size_mismatch", or "unreachable".
    """
    results = []
    if not dlc_downloads:
        return results

    total = len(dlc_downloads)

    def _check(dlc_id: str, entry: dict) -> tuple[str, str, int, int, int]:
        url = entry.get("url", "")
        manifest_size = entry.get("size", 0)
        if not url:
            return (dlc_id, "unreachable", manifest_size, 0, 0)
        status, real_size = ConnectionManager.head_check(url)
        if status != 200:
            return (dlc_id, "unreachable", manifest_size, 0, status)
        if manifest_size == 0 and real_size > 0:
            return (dlc_id, "size_zero", manifest_size, real_size, 200)
        if manifest_size != real_size and real_size > 0:
            return (dlc_id, "size_mismatch", manifest_size, real_size, 200)
        return (dlc_id, "ok", manifest_size, real_size, 200)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_check, dlc_id, entry): dlc_id for dlc_id, entry in dlc_downloads.items()
        }
        for done_count, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if progress_cb:
                progress_cb(done_count, total)

    results.sort(key=lambda r: r[0])
    return results


def audit_language_entries(
    lang_downloads: dict[str, Any],
    *,
    workers: int = 10,
    progress_cb=None,
) -> list[tuple[str, str, int, int, int]]:
    """HEAD-request every language URL in parallel. Same format as DLC audit."""
    results = []
    if not lang_downloads:
        return results

    total = len(lang_downloads)

    def _check(locale: str, entry: dict) -> tuple[str, str, int, int, int]:
        url = entry.get("url", "")
        manifest_size = entry.get("size", 0)
        if not url:
            return (locale, "unreachable", manifest_size, 0, 0)
        status, real_size = ConnectionManager.head_check(url)
        if status != 200:
            return (locale, "unreachable", manifest_size, 0, status)
        if manifest_size == 0 and real_size > 0:
            return (locale, "size_zero", manifest_size, real_size, 200)
        if manifest_size != real_size and real_size > 0:
            return (locale, "size_mismatch", manifest_size, real_size, 200)
        return (locale, "ok", manifest_size, real_size, 200)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_check, locale, entry): locale for locale, entry in lang_downloads.items()
        }
        for done_count, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if progress_cb:
                progress_cb(done_count, total)

    results.sort(key=lambda r: r[0])
    return results


def fix_sizes(
    downloads: dict[str, Any],
    audit_results: list[tuple[str, str, int, int, int]],
) -> list[tuple[str, str, int, int]]:
    """Fix entries with wrong/zero sizes. Returns list of (id, issue, old, new)."""
    fixes = []
    for entry_id, issue, manifest_size, real_size, _ in audit_results:
        if issue in ("size_zero", "size_mismatch") and real_size > 0 and entry_id in downloads:
            downloads[entry_id]["size"] = real_size
            fixes.append((entry_id, issue, manifest_size, real_size))
    return fixes


def diff_manifests(original: dict, modified: dict) -> list[str]:
    """Generate a human-readable diff between two manifest dicts."""
    changes = []

    # Top-level scalar fields
    for key in ("latest", "game_latest", "game_latest_date"):
        old_val = original.get(key, "")
        new_val = modified.get(key, "")
        if old_val != new_val:
            changes.append(f'{key}: "{old_val}" -> "{new_val}"')

    # DLC changes
    old_dlcs = set(original.get("dlc_downloads", {}).keys())
    new_dlcs = set(modified.get("dlc_downloads", {}).keys())
    added = new_dlcs - old_dlcs
    removed = old_dlcs - new_dlcs
    if added:
        changes.append(f"DLC added: {', '.join(sorted(added))}")
    if removed:
        changes.append(f"DLC removed: {', '.join(sorted(removed))}")

    # Size changes in DLCs
    for dlc_id in old_dlcs & new_dlcs:
        old_size = original["dlc_downloads"][dlc_id].get("size", 0)
        new_size = modified["dlc_downloads"][dlc_id].get("size", 0)
        if old_size != new_size:
            changes.append(f"DLC {dlc_id} size: {fmt_size(old_size)} -> {fmt_size(new_size)}")

    # Language changes
    old_langs = set(original.get("language_downloads", {}).keys())
    new_langs = set(modified.get("language_downloads", {}).keys())
    l_added = new_langs - old_langs
    l_removed = old_langs - new_langs
    if l_added:
        changes.append(f"Languages added: {', '.join(sorted(l_added))}")
    if l_removed:
        changes.append(f"Languages removed: {', '.join(sorted(l_removed))}")

    # Patch changes
    old_patches = len(original.get("patches", []))
    new_patches = len(modified.get("patches", []))
    if old_patches != new_patches:
        changes.append(f"Patches: {old_patches} -> {new_patches}")

    if not changes:
        changes.append("No changes detected")

    return changes


def save_manifest_local(manifest: dict, output_path: Path) -> None:
    """Write manifest to a local JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def upload_manifest(conn: ConnectionManager, manifest_path: Path) -> None:
    """Upload manifest.json to CDN."""
    conn.publish_manifest(manifest_path)


def backup_manifest(conn: ConnectionManager, backup_dir: Path) -> Path | None:
    """Fetch the live manifest and save a timestamped backup locally.

    Returns the backup path, or None if fetch failed.
    """
    from datetime import datetime

    try:
        manifest = conn.fetch_manifest()
    except Exception:
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"manifest_backup_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return backup_path


def merge_dlc_entries_and_publish(
    conn: ConnectionManager,
    new_entries: dict[str, dict],
    *,
    log_cb=None,
) -> bool:
    """Fetch live manifest, merge DLC entries, and re-publish.

    new_entries: {dlc_id: {url, size, md5, filename}}
    Returns True on success.
    """

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    if not new_entries:
        return True

    try:
        manifest = conn.fetch_manifest()
    except Exception as e:
        log(f"Failed to fetch manifest for update: {e}", "error")
        return False

    downloads = manifest.setdefault("dlc_downloads", {})
    added = 0
    updated = 0
    for dlc_id, entry in new_entries.items():
        # Only merge entries with real data (skip size=0 "already on CDN" stubs)
        if entry.get("size", 0) > 0:
            if dlc_id in downloads:
                updated += 1
            else:
                added += 1
            downloads[dlc_id] = entry

    if added == 0 and updated == 0:
        log("No new DLC entries to add to manifest")
        return True

    log(f"Updating manifest: {added} new, {updated} updated DLC entries...")
    return _publish_manifest_dict(conn, manifest, log)


def merge_language_entries_and_publish(
    conn: ConnectionManager,
    new_entries: dict[str, dict],
    *,
    log_cb=None,
) -> bool:
    """Fetch live manifest, merge language entries, and re-publish.

    new_entries: {locale: {url, size, md5, filename}}
    Returns True on success.
    """

    def log(msg, level="info"):
        if log_cb:
            log_cb(msg, level)

    if not new_entries:
        return True

    try:
        manifest = conn.fetch_manifest()
    except Exception as e:
        log(f"Failed to fetch manifest for update: {e}", "error")
        return False

    downloads = manifest.setdefault("language_downloads", {})
    added = 0
    updated = 0
    for locale, entry in new_entries.items():
        if entry.get("size", 0) > 0:
            if locale in downloads:
                updated += 1
            else:
                added += 1
            downloads[locale] = entry

    if added == 0 and updated == 0:
        log("No new language entries to add to manifest")
        return True

    log(f"Updating manifest: {added} new, {updated} updated language entries...")
    return _publish_manifest_dict(conn, manifest, log)


def _publish_manifest_dict(conn: ConnectionManager, manifest: dict, log) -> bool:
    """Write manifest dict to temp file and publish to CDN."""
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(manifest, tmp, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp.name)
        try:
            conn.publish_manifest(tmp_path)
            log("Manifest updated on CDN", "success")
            return True
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as e:
        log(f"Manifest publish failed: {e}", "error")
        return False


def detect_orphans(
    manifest: dict,
    kv_keys: list[str],
) -> tuple[list[str], list[str]]:
    """Cross-reference manifest entries vs KV keys.

    Returns (in_kv_not_manifest, in_manifest_not_kv).
    """
    # Build expected KV keys from manifest
    expected_keys: set[str] = set()
    for dlc_id in manifest.get("dlc_downloads", {}):
        expected_keys.add(f"dlc/{dlc_id}.zip")
    for locale in manifest.get("language_downloads", {}):
        expected_keys.add(f"language/{locale}.zip")
    for patch in manifest.get("patches", []):
        from_v = patch.get("from_version", "")
        to_v = patch.get("to_version", "")
        if from_v and to_v:
            expected_keys.add(f"patches/{from_v}_to_{to_v}.zip")
    # manifest.json itself is always expected
    expected_keys.add("manifest.json")

    # Content keys only (skip metadata-like keys)
    content_keys = {
        k
        for k in kv_keys
        if k.startswith(("dlc/", "language/", "patches/", "archives/")) or k == "manifest.json"
    }

    in_kv_not_manifest = sorted(content_keys - expected_keys)
    in_manifest_not_kv = sorted(expected_keys - content_keys)

    return in_kv_not_manifest, in_manifest_not_kv
