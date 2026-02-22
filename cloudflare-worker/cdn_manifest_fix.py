"""
CDN Manifest Fix -- Audit, repair, and rebuild the CDN manifest.

Fetches the live manifest from CDN, validates every DLC entry via parallel
HEAD requests, fixes entries with size=0 or missing MD5, sets the latest
version, optionally merges language downloads, and writes a corrected
manifest.json.

Usage:
    python cdn_manifest_fix.py --version 1.121.372.1020
    python cdn_manifest_fix.py --version 1.121.372.1020 --merge-languages language_downloads.json
    python cdn_manifest_fix.py --version 1.121.372.1020 \
        --merge-languages language_downloads.json --upload
    python cdn_manifest_fix.py --audit-only
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from cdn_pack_upload import fmt_size, load_config
from cdn_upload import publish_manifest

# ── Constants ────────────────────────────────────────────────────

CDN_DOMAIN = "https://cdn.hyperabyss.com"
MANIFEST_URL = f"{CDN_DOMAIN}/manifest.json"
SEEDBOX_BASE_DIR = "files/sims4"
SCRIPT_DIR = Path(__file__).parent
HEAD_WORKERS = 10
HEAD_TIMEOUT = 20

# ANSI color helpers
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


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


# ── Fetch manifest ───────────────────────────────────────────────


def fetch_manifest(url: str) -> dict[str, Any]:
    """GET the manifest from CDN and return parsed JSON."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"{_err('ERROR')}: Failed to fetch manifest from {url}")
        print(f"  {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"{_err('ERROR')}: Manifest is not valid JSON")
        print(f"  {e}")
        sys.exit(1)


# ── Audit DLC entries ────────────────────────────────────────────


def _head_dlc_entry(
    dlc_id: str,
    entry: dict[str, Any],
) -> tuple[str, str, int, int, int]:
    """HEAD-request a single DLC URL.

    Returns (dlc_id, issue, manifest_size, real_size, status_code).
    Issue is one of: "ok", "size_zero", "size_mismatch", "unreachable".
    """
    url = entry.get("url", "")
    manifest_size = entry.get("size", 0)

    if not url:
        return (dlc_id, "unreachable", manifest_size, 0, 0)

    try:
        resp = requests.head(
            url,
            timeout=HEAD_TIMEOUT,
            allow_redirects=True,
        )
    except requests.RequestException:
        return (dlc_id, "unreachable", manifest_size, 0, 0)

    if resp.status_code != 200:
        return (dlc_id, "unreachable", manifest_size, 0, resp.status_code)

    real_size = int(resp.headers.get("Content-Length", 0))

    if manifest_size == 0 and real_size > 0:
        return (dlc_id, "size_zero", manifest_size, real_size, 200)

    if manifest_size != real_size and real_size > 0:
        return (dlc_id, "size_mismatch", manifest_size, real_size, 200)

    return (dlc_id, "ok", manifest_size, real_size, 200)


def audit_dlc_entries(
    dlc_downloads: dict[str, Any],
) -> list[tuple[str, str, int, int, int]]:
    """HEAD-request every DLC URL in parallel, return audit results.

    Each result is (dlc_id, issue, manifest_size, real_size, status_code).
    """
    results: list[tuple[str, str, int, int, int]] = []

    if not dlc_downloads:
        return results

    total = len(dlc_downloads)
    print(f"  Auditing {total} DLC entries ({HEAD_WORKERS} workers)...")

    with ThreadPoolExecutor(max_workers=HEAD_WORKERS) as pool:
        futures = {
            pool.submit(_head_dlc_entry, dlc_id, entry): dlc_id
            for dlc_id, entry in dlc_downloads.items()
        }
        for done_count, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            # Throttled progress every 20 entries
            if done_count % 20 == 0 or done_count == total:
                print(
                    f"\r  Checked {done_count}/{total}...",
                    end="",
                    flush=True,
                )
        print()  # newline after progress

    # Sort by DLC ID for stable output
    results.sort(key=lambda r: r[0])
    return results


# ── Fix DLC entries ──────────────────────────────────────────────


def fix_dlc_entries(
    dlc_downloads: dict[str, Any],
    audit_results: list[tuple[str, str, int, int, int]],
) -> list[tuple[str, str, int, int]]:
    """Patch entries with correct sizes from audit. Returns list of fixes.

    Each fix is (dlc_id, issue, old_value, new_value).
    """
    fixes: list[tuple[str, str, int, int]] = []

    for dlc_id, issue, manifest_size, real_size, _status in audit_results:
        if issue in ("size_zero", "size_mismatch") and real_size > 0 and dlc_id in dlc_downloads:
            dlc_downloads[dlc_id]["size"] = real_size
            fixes.append((dlc_id, issue, manifest_size, real_size))

    return fixes


# ── Merge language downloads ─────────────────────────────────────


def merge_languages(
    manifest: dict[str, Any],
    lang_path: Path,
) -> int:
    """Load language_downloads.json and merge into manifest.

    Returns the number of language entries merged.
    """
    if not lang_path.is_file():
        print(f"{_err('ERROR')}: Language file not found: {lang_path}")
        sys.exit(1)

    try:
        lang_data = json.loads(lang_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"{_err('ERROR')}: Failed to read language file: {e}")
        sys.exit(1)

    manifest["language_downloads"] = lang_data
    return len(lang_data)


# ── Audit report ─────────────────────────────────────────────────


def print_audit_report(
    audit_results: list[tuple[str, str, int, int, int]],
    fixes: list[tuple[str, str, int, int]],
    manifest: dict[str, Any],
    old_version: str,
    new_version: str,
    lang_merged: int,
    output_path: Path | None,
) -> None:
    """Pretty-print the full audit report to console."""
    dlc_downloads = manifest.get("dlc_downloads", {})

    print()
    print(f"{_bold('=== CDN MANIFEST AUDIT ===')}")
    print()

    # Version
    if old_version != new_version:
        print(f'  Version: "{old_version}" -> "{new_version}" ({_ok("FIXED")})')
    elif new_version:
        print(f'  Version: "{new_version}" ({_ok("OK")})')
    else:
        print(f'  Version: "" ({_warn("EMPTY")})')
    print()

    # DLC Downloads
    total_entries = len(dlc_downloads)
    ok_entries = [r for r in audit_results if r[1] == "ok"]
    fixed_entries = [f for f in fixes]
    no_md5 = [dlc_id for dlc_id, entry in dlc_downloads.items() if not entry.get("md5")]
    unreachable = [r for r in audit_results if r[1] == "unreachable"]

    # Compute total size of OK entries
    ok_total_bytes = sum(
        dlc_downloads.get(r[0], {}).get("size", 0) for r in audit_results if r[1] == "ok"
    )
    print(f"  DLC Downloads ({total_entries} entries):")
    print(f"    {_ok('OK')}:     {len(ok_entries)} entries ({fmt_size(ok_total_bytes)} total)")

    if fixed_entries:
        print(f"    {_warn('FIXED')}:  {len(fixed_entries)} entries")
        for dlc_id, issue, old_val, new_val in fixed_entries:
            label = "size 0" if issue == "size_zero" else "size mismatch"
            print(f"      {dlc_id}: {label} {old_val} -> {new_val} ({fmt_size(new_val)})")

    if no_md5:
        print(f"    {_warn('NO MD5')}: {len(no_md5)} entries")
        for dlc_id in no_md5[:10]:
            print(f"      {dlc_id}: no MD5 hash (file exists but hash unknown)")
        if len(no_md5) > 10:
            print(f"      ... and {len(no_md5) - 10} more")

    if unreachable:
        print(f"    {_err('UNREACHABLE')}: {len(unreachable)} entries")
        for dlc_id, _, _, _, status in unreachable:
            status_str = f"HTTP {status}" if status else "connection failed"
            print(f"      {dlc_id}: {status_str}")

    print()

    # Language Downloads
    lang_downloads = manifest.get("language_downloads")
    if lang_merged > 0:
        print(
            f"  Language Downloads: "
            f"{_warn('MISSING')} -> merged {lang_merged} entries "
            f"from language file"
        )
    elif lang_downloads:
        print(f"  Language Downloads: {_ok('OK')} ({len(lang_downloads)} entries)")
    else:
        print(f"  Language Downloads: {_warn('MISSING')}")
    print()

    # Patches
    patches = manifest.get("patches")
    if patches:
        print(f"  Patches: {_ok('OK')} ({len(patches)} entries)")
    else:
        print(f"  Patches: {_info('NONE')} (skipped)")
    print()

    # Output
    if output_path:
        print(f"  Output: {output_path.name} (corrected)")
    else:
        print(f"  Output: {_info('none')} (audit-only mode)")

    print()

    # Summary line
    total_issues = len(fixed_entries) + len(unreachable)
    if total_issues == 0 and not no_md5:
        print(f"  {_ok('All entries OK!')}")
    else:
        parts = []
        if fixed_entries:
            parts.append(f"{len(fixed_entries)} fixed")
        if unreachable:
            parts.append(f"{len(unreachable)} unreachable")
        if no_md5:
            parts.append(f"{len(no_md5)} missing MD5")
        print(f"  Issues: {', '.join(parts)}")

    print()


# ── Main ─────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit, repair, and rebuild the CDN manifest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cdn_manifest_fix.py --version 1.121.372.1020
  python cdn_manifest_fix.py --version 1.121.372.1020 --merge-languages language_downloads.json
  python cdn_manifest_fix.py --version 1.121.372.1020 \
      --merge-languages language_downloads.json --upload
  python cdn_manifest_fix.py --audit-only
        """,
    )
    parser.add_argument(
        "--version",
        default="",
        help="Set the 'latest' version in the manifest",
    )
    parser.add_argument(
        "--merge-languages",
        type=Path,
        default=None,
        help="Path to language_downloads.json to merge into manifest",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the fixed manifest to CDN via SFTP + KV",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Just report issues, don't write any files",
    )
    parser.add_argument(
        "--manifest-url",
        default=MANIFEST_URL,
        help=f"Manifest URL to fetch (default: {MANIFEST_URL})",
    )
    args = parser.parse_args()

    # Validate arguments
    if not args.audit_only and not args.version:
        parser.error("--version is required unless using --audit-only")

    if args.upload and args.audit_only:
        parser.error("--upload and --audit-only are mutually exclusive")

    print()
    print(f"{_bold('=== CDN Manifest Fix ===')}")
    print()

    # Step 1: Fetch current manifest
    print(f"  Fetching manifest from {args.manifest_url}...")
    manifest = fetch_manifest(args.manifest_url)
    old_version = manifest.get("latest", "")
    dlc_downloads = manifest.get("dlc_downloads", {})

    print(f'  Current version: "{old_version}"')
    print(f"  DLC entries: {len(dlc_downloads)}")
    lang_section = manifest.get("language_downloads")
    if lang_section:
        print(f"  Language entries: {len(lang_section)}")
    else:
        print(f"  Language entries: {_warn('none')}")
    patches_section = manifest.get("patches")
    if patches_section:
        print(f"  Patch entries: {len(patches_section)}")
    else:
        print(f"  Patch entries: {_info('none')}")
    print()

    # Step 2: Audit all DLC entries via HEAD requests
    audit_results = audit_dlc_entries(dlc_downloads)

    # Step 3: Fix entries with bad sizes
    fixes = fix_dlc_entries(dlc_downloads, audit_results)

    # Step 4: Set the latest version
    new_version = args.version if args.version else old_version
    manifest["latest"] = new_version

    # Step 5: Merge language downloads if requested
    lang_merged = 0
    if args.merge_languages:
        lang_merged = merge_languages(manifest, args.merge_languages)

    # Step 6: Print the full audit report
    output_path = None if args.audit_only else SCRIPT_DIR / "manifest.json"
    print_audit_report(
        audit_results,
        fixes,
        manifest,
        old_version,
        new_version,
        lang_merged,
        output_path,
    )

    # Step 7: Write corrected manifest (unless audit-only)
    if args.audit_only:
        print(f"  {_info('Audit-only mode -- no files written.')}")
        print()
        return

    output_path = SCRIPT_DIR / "manifest.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Wrote corrected manifest to: {output_path}")

    # Step 8: Upload if requested
    if args.upload:
        print()
        print(f"  {_bold('Uploading manifest to CDN...')}")
        config = load_config()
        try:
            publish_manifest(config, output_path)
            print(f"  {_ok('Manifest uploaded successfully!')}")
        except Exception as e:
            print(f"  {_err('Upload failed')}: {e}")
            print(f"  Local file saved at: {output_path}")
            sys.exit(1)

    print()
    print(f"  {_ok('Done!')}")
    print()


if __name__ == "__main__":
    main()
