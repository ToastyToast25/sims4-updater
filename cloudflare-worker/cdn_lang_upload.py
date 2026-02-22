"""
CDN Language Pack Upload -- Pack & upload Sims 4 language packs to CDN via SFTP + Cloudflare KV.

Scans the game directory for installed Strings_XXX_XX.package files, packs each into a
ZIP archive with Data/Client/ structure, uploads to the seedbox, and registers KV entries
so the CDN worker can serve them.

Usage:
    python cdn_lang_upload.py                          # Upload all languages
    python cdn_lang_upload.py --only de_DE fr_FR       # Only specific locales
    python cdn_lang_upload.py --skip-upload             # Pack only, don't upload
    python cdn_lang_upload.py --game-dir "C:\\..."      # Custom game directory
"""

from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
import time
import zipfile
from pathlib import Path

# Allow imports from the main project
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cdn_pack_upload import (
    add_kv_entry,
    fmt_size,
    fmt_time,
    kv_exists,
    load_config,
    md5_file,
    tprint,
    upload_sftp_with_retry,
)

# ── Constants ────────────────────────────────────────────────────

CDN_DOMAIN = "https://cdn.hyperabyss.com"
SEEDBOX_BASE_DIR = "files/sims4"
GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\The Sims 4")
OUTPUT_DIR = Path(__file__).parent / "lang_packed_temp"
OUTPUT_JSON = Path(__file__).parent / "language_downloads.json"

LANGUAGES: dict[str, str] = {
    "cs_CZ": "\u010ce\u0161tina",
    "da_DK": "Dansk",
    "de_DE": "Deutsch",
    "en_US": "English",
    "es_ES": "Espa\u00f1ol",
    "fr_FR": "Fran\u00e7ais",
    "it_IT": "Italiano",
    "nl_NL": "Nederlands",
    "no_NO": "Norsk",
    "pl_PL": "Polski",
    "pt_BR": "Portugu\u00eas (Brasil)",
    "fi_FI": "Suomi",
    "sv_SE": "Svenska",
    "ru_RU": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "ja_JP": "\u65e5\u672c\u8a9e",
    "zh_TW": "\u7e41\u9ad4\u4e2d\u6587",
    "zh_CN": "\u7b80\u4f53\u4e2d\u6587",
    "ko_KR": "\ud55c\uad6d\uc5b4",
}

LOCALE_TO_STRINGS: dict[str, str] = {
    "cs_CZ": "CZE_CZ",
    "da_DK": "DAN_DK",
    "de_DE": "GER_DE",
    "en_US": "ENG_US",
    "es_ES": "SPA_ES",
    "fr_FR": "FRE_FR",
    "it_IT": "ITA_IT",
    "nl_NL": "DUT_NL",
    "no_NO": "NOR_NO",
    "pl_PL": "POL_PL",
    "pt_BR": "POR_BR",
    "fi_FI": "FIN_FI",
    "sv_SE": "SWE_SE",
    "ru_RU": "RUS_RU",
    "ja_JP": "JPN_JP",
    "zh_TW": "CHT_CN",
    "zh_CN": "CHS_CN",
    "ko_KR": "KOR_KR",
}

# Directories under the game dir that contain Strings_XXX_XX.package files
STRINGS_SEARCH_DIRS = [
    "Data/Client",
    "Delta/Base",
]


# ── Graceful shutdown ─────────────────────────────────────────────

_shutdown_requested = False


def _signal_handler(sig, frame):
    global _shutdown_requested
    if _shutdown_requested:
        print("\n\n  Force quit.")
        sys.exit(1)
    _shutdown_requested = True
    print("\n\n  Ctrl+C detected -- finishing current language then stopping...")
    print("  Press Ctrl+C again to force quit.\n")


signal.signal(signal.SIGINT, _signal_handler)


# ── Scanning ──────────────────────────────────────────────────────


def scan_installed_languages(game_dir: Path) -> dict[str, list[Path]]:
    """Find all installed Strings_XXX_XX.package files for each locale.

    Returns a dict mapping locale code to a list of absolute paths
    for all matching Strings files found in the search directories.
    """
    installed: dict[str, list[Path]] = {}

    for locale_code, strings_suffix in LOCALE_TO_STRINGS.items():
        filename = f"Strings_{strings_suffix}.package"
        found_paths: list[Path] = []

        for search_dir in STRINGS_SEARCH_DIRS:
            candidate = game_dir / search_dir / filename
            if candidate.is_file():
                found_paths.append(candidate)

        if found_paths:
            installed[locale_code] = found_paths

    return installed


# ── Packing ───────────────────────────────────────────────────────


def pack_language(
    game_dir: Path,
    locale_code: str,
    output_dir: Path,
) -> Path:
    """Create a ZIP for a language pack with Data/Client/ internal structure.

    The ZIP is named <locale>.zip and contains the Strings file at
    Data/Client/Strings_XXX_XX.package so it extracts directly into
    the game directory.

    Returns the path to the created ZIP file.
    """
    strings_suffix = LOCALE_TO_STRINGS.get(locale_code)
    if not strings_suffix:
        raise ValueError(f"Unknown locale code: {locale_code}")

    filename = f"Strings_{strings_suffix}.package"
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{locale_code}.zip"

    files_to_pack: list[tuple[str, Path]] = []

    for search_dir in STRINGS_SEARCH_DIRS:
        candidate = game_dir / search_dir / filename
        if candidate.is_file():
            # Use forward-slash archive path for cross-platform compat
            archive_name = f"{search_dir}/{filename}"
            files_to_pack.append((archive_name, candidate))

    if not files_to_pack:
        raise FileNotFoundError(
            f"No Strings file found for {locale_code} "
            f"(expected {filename} in {STRINGS_SEARCH_DIRS})"
        )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for archive_name, abs_path in files_to_pack:
            zf.write(abs_path, archive_name)

    return zip_path


# ── Process single language ───────────────────────────────────────


def process_language(
    game_dir: Path,
    locale_code: str,
    config: dict,
    output_dir: Path,
    skip_upload: bool = False,
) -> dict | None:
    """Pack, upload, and register a single language pack.

    Returns a manifest entry dict on success, or None on failure.
    """
    cdn_path = f"language/{locale_code}.zip"
    remote_path = f"{SEEDBOX_BASE_DIR}/{cdn_path}"
    lang_name = LANGUAGES.get(locale_code, locale_code)
    tag = f"[{locale_code}]"

    # Check if already on CDN (skip re-upload)
    if not skip_upload and kv_exists(config, cdn_path):
        tprint(f"  {tag} Already on CDN ({lang_name}), skipping")
        return {
            "url": f"{CDN_DOMAIN}/{cdn_path}",
            "size": 0,
            "md5": "",
            "filename": f"{locale_code}.zip",
        }

    if _shutdown_requested:
        return None

    # Step 1: Pack
    tprint(f"  {tag} Packing {lang_name}...")
    try:
        zip_path = pack_language(game_dir, locale_code, output_dir)
    except FileNotFoundError as e:
        tprint(f"  {tag} SKIP: {e}")
        return None

    zip_size = zip_path.stat().st_size
    zip_md5 = md5_file(zip_path)
    tprint(f"  {tag} Packed: {fmt_size(zip_size)}  MD5: {zip_md5}")

    if _shutdown_requested:
        tprint(f"  {tag} Shutdown requested, keeping ZIP")
        return None

    if skip_upload:
        entry = {
            "url": f"{CDN_DOMAIN}/{cdn_path}",
            "size": zip_size,
            "md5": zip_md5,
            "filename": f"{locale_code}.zip",
        }
        zip_path.unlink(missing_ok=True)
        return entry

    # Step 2: Upload via SFTP
    tprint(f"  {tag} Uploading {fmt_size(zip_size)}...")
    try:
        upload_sftp_with_retry(
            config,
            zip_path,
            remote_path,
            dlc_id=locale_code,
        )
    except (ConnectionError, KeyboardInterrupt) as e:
        tprint(f"  {tag} UPLOAD FAILED: {e}")
        zip_path.unlink(missing_ok=True)
        return None

    if _shutdown_requested:
        zip_path.unlink(missing_ok=True)
        return None

    # Step 3: Register in Cloudflare KV
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
        "filename": f"{locale_code}.zip",
    }
    tprint(f"  {tag} DONE ({lang_name}, {fmt_size(zip_size)})")
    return entry


# ── Main ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pack & upload Sims 4 language packs to CDN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="LOCALE",
        help="Only process these locale codes (e.g. de_DE fr_FR)",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Pack only, don't upload to CDN",
    )
    parser.add_argument(
        "--game-dir",
        type=Path,
        default=GAME_DIR,
        help="Game installation directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Temp directory for packed ZIPs",
    )
    args = parser.parse_args()

    config = load_config()

    print("=" * 60)
    print("  Sims 4 Language Pack CDN Uploader")
    print("  Press Ctrl+C to gracefully stop")
    print("=" * 60)
    print()

    # Validate game directory
    if not args.game_dir.is_dir():
        print(f"ERROR: Game directory not found: {args.game_dir}")
        sys.exit(1)

    # Scan for installed languages
    installed = scan_installed_languages(args.game_dir)
    print(f"Found {len(installed)} languages installed:")
    for locale_code in sorted(installed):
        lang_name = LANGUAGES.get(locale_code, locale_code)
        file_count = len(installed[locale_code])
        total_size = sum(p.stat().st_size for p in installed[locale_code])
        print(
            f"  {locale_code}: {lang_name} "
            f"({file_count} file{'s' if file_count > 1 else ''}, "
            f"{fmt_size(total_size)})"
        )
    print()

    # Determine target locales
    if args.only:
        target_locales = []
        for loc in args.only:
            if loc not in LOCALE_TO_STRINGS:
                print(f"Warning: Unknown locale code '{loc}', skipping")
            elif loc not in installed:
                print(f"Warning: {loc} not installed in game dir, skipping")
            else:
                target_locales.append(loc)
        if not target_locales:
            print("ERROR: No valid locales to process.")
            sys.exit(1)
    else:
        target_locales = sorted(installed.keys())

    print(f"Processing {len(target_locales)} language(s)...")
    print()

    # Process each language sequentially
    results: dict[str, dict] = {}
    uploaded_count = 0
    skipped_count = 0
    failed_count = 0
    uploaded_bytes = 0
    start_time = time.time()

    for locale_code in target_locales:
        if _shutdown_requested:
            print("\n  Stopping due to shutdown request...")
            break

        entry = process_language(
            args.game_dir,
            locale_code,
            config,
            args.output_dir,
            skip_upload=args.skip_upload,
        )

        if entry is None:
            failed_count += 1
        elif entry.get("size", 0) == 0 and entry.get("md5", "") == "":
            # Already on CDN (skipped)
            results[locale_code] = entry
            skipped_count += 1
        else:
            results[locale_code] = entry
            uploaded_count += 1
            uploaded_bytes += entry.get("size", 0)

    total_time = time.time() - start_time

    # Write language_downloads.json
    if results:
        downloads: dict[str, dict] = {}
        for locale_code in sorted(results):
            entry = results[locale_code]
            downloads[locale_code] = {
                "url": entry["url"],
                "size": entry["size"],
                "md5": entry["md5"],
                "filename": entry["filename"],
            }

        OUTPUT_JSON.write_text(
            json.dumps(downloads, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  Output written to: {OUTPUT_JSON}")

    # Summary
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Total processed: {len(results)} languages")
    print(f"  Uploaded:  {uploaded_count} ({fmt_size(uploaded_bytes)})")
    print(f"  Skipped:   {skipped_count} (already on CDN)")
    print(f"  Failed:    {failed_count}")
    print(f"  Time:      {fmt_time(total_time)}")
    if uploaded_count > 0 and total_time > 0:
        speed = uploaded_bytes / total_time
        print(f"  Avg speed: {fmt_size(int(speed))}/s")
    if _shutdown_requested:
        print("\n  Stopped early. Run again to upload remaining.")
    print()

    # Clean up temp dir
    if args.output_dir.is_dir():
        with contextlib.suppress(OSError):
            args.output_dir.rmdir()

    print("  Done!")


if __name__ == "__main__":
    main()
