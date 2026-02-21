"""
Sims 4 Updater - main entry point.

Usage:
    python -m sims4_updater                         # Launch GUI
    python -m sims4_updater detect <game_dir>       # Detect version
    python -m sims4_updater check [game_dir]        # Check for updates
    python -m sims4_updater dlc <game_dir>          # Show DLC states
    python -m sims4_updater dlc-auto <game_dir>     # Auto-toggle DLCs
    python -m sims4_updater pack-dlc <game_dir> ... # Pack DLC zip archives
    python -m sims4_updater language                 # Show current language
    python -m sims4_updater language <code> [dir]    # Set language
    python -m sims4_updater manifest <url|file>     # Inspect a manifest
    python -m sims4_updater learn <game_dir> <ver>  # Learn version hashes
"""

import argparse
import io
import os
import sys


def _fix_console_encoding():
    """Ensure stdout/stderr can handle Unicode on Windows."""
    if os.name == "nt" and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )


_fix_console_encoding()


def detect_version(game_dir):
    """CLI version detection."""
    from sims4_updater.core.version_detect import VersionDetector

    detector = VersionDetector()

    def progress(name, current, total):
        if name == "done":
            print()
        else:
            print(f"  Hashing {name}... ({current + 1}/{total})")

    print(f"Scanning: {game_dir}")
    print()

    if not detector.validate_game_dir(game_dir):
        print("ERROR: Not a valid Sims 4 installation directory.")
        print("Expected to find: Game/Bin/TS4_x64.exe and Data/Client/")
        sys.exit(1)

    result = detector.detect(game_dir, progress=progress)

    if result.version:
        print(f"Detected version: {result.version}")
        print(f"Confidence: {result.confidence.value}")
        if len(result.matched_versions) > 1:
            print(f"Possible matches: {', '.join(result.matched_versions)}")
    else:
        print("Could not detect version.")
        print("Hashes found:")
        for sentinel, md5 in result.local_hashes.items():
            print(f"  {sentinel}: {md5}")

    print()
    print(f"Sentinel files hashed: {len(result.local_hashes)}")


def show_dlc_states(game_dir):
    """Show DLC states for a game directory."""
    from pathlib import Path
    from sims4_updater.dlc.manager import DLCManager
    from sims4_updater.dlc.formats import detect_format
    from sims4_updater.language.changer import get_current_language

    game_dir = Path(game_dir)
    manager = DLCManager()
    adapter = detect_format(game_dir)
    locale = get_current_language()

    if adapter:
        print(f"Crack config format: {adapter.get_format_name()}")
        config_path = adapter.get_config_path(game_dir)
        print(f"Config file: {config_path}")
    else:
        print("No crack config found.")

    print()
    states = manager.get_dlc_states(game_dir, locale)

    # Group by type
    type_order = ["expansion", "game_pack", "stuff_pack", "kit", "free_pack", "other"]
    type_labels = {
        "expansion": "Expansion Packs",
        "game_pack": "Game Packs",
        "stuff_pack": "Stuff Packs",
        "kit": "Kits",
        "free_pack": "Free Packs",
        "other": "Other",
    }

    for pack_type in type_order:
        type_states = [s for s in states if s.dlc.pack_type == pack_type]
        if not type_states:
            continue

        print(f"--- {type_labels.get(pack_type, pack_type)} ---")
        for state in type_states:
            dlc = state.dlc
            name = dlc.get_name(locale)

            status_parts = []
            if state.enabled is True:
                status_parts.append("ENABLED")
            elif state.enabled is False:
                status_parts.append("DISABLED")
            else:
                status_parts.append("N/A")

            if state.installed:
                status_parts.append("installed")
            else:
                status_parts.append("MISSING")

            status = ", ".join(status_parts)
            print(f"  [{dlc.id}] {name} ({status})")
        print()

    total = len(states)
    installed = sum(1 for s in states if s.installed)
    enabled = sum(1 for s in states if s.enabled is True)
    print(f"Total: {total} DLCs | Installed: {installed} | Enabled: {enabled}")


def auto_toggle_dlcs(game_dir):
    """Auto-enable installed DLCs, disable missing ones."""
    from sims4_updater.dlc.manager import DLCManager

    manager = DLCManager()
    print(f"Auto-toggling DLCs for: {game_dir}")
    print()

    changes = manager.auto_toggle(game_dir)

    if not changes:
        print("No changes needed. All DLCs are correctly configured.")
    else:
        for dlc_id, new_state in sorted(changes.items()):
            action = "ENABLED" if new_state else "DISABLED"
            print(f"  {dlc_id}: {action}")
        print(f"\n{len(changes)} DLC(s) changed.")


def check_for_updates(args):
    """Check for available updates."""
    from sims4_updater.core.version_detect import VersionDetector
    from sims4_updater.patch.client import PatchClient, format_size
    from sims4_updater.core.exceptions import ManifestError, NoUpdatePathError

    detector = VersionDetector()

    # Resolve game directory
    game_dir = getattr(args, "game_dir", None)
    if not game_dir:
        game_dir = detector.find_game_dir()
        if not game_dir:
            print("ERROR: Could not auto-detect game directory.")
            print("Provide a game directory: sims4-updater check <game_dir>")
            sys.exit(1)
        print(f"Auto-detected: {game_dir}")

    if not detector.validate_game_dir(game_dir):
        print("ERROR: Not a valid Sims 4 installation directory.")
        sys.exit(1)

    # Detect version
    print("Detecting installed version...")
    result = detector.detect(game_dir)

    if not result.version:
        print("ERROR: Could not detect installed version.")
        sys.exit(1)

    print(f"Installed: {result.version}")

    # Resolve manifest URL
    manifest_url = getattr(args, "manifest_url", None)
    if not manifest_url:
        from sims4_updater.constants import MANIFEST_URL
        manifest_url = MANIFEST_URL

    if not manifest_url:
        print()
        print("No manifest URL configured.")
        print("Use --manifest-url <url> or set it in Settings.")
        sys.exit(1)

    # Check for updates
    print(f"Checking manifest...")
    try:
        client = PatchClient(manifest_url=manifest_url)
        info = client.check_update(result.version)
    except ManifestError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except NoUpdatePathError as e:
        print(f"\n{e}")
        sys.exit(1)

    print(f"Latest:    {info.latest_version}")
    print()

    if not info.update_available:
        print("You are up to date!")
    else:
        print(f"Update available!")
        print(f"  Steps: {info.step_count}")
        print(f"  Download size: {format_size(info.total_download_size)}")
        print()
        for step in info.plan.steps:
            p = step.patch
            size = format_size(p.total_size)
            print(f"  {step.step_number}. {p.version_from} -> {p.version_to} ({size})")

    client.close()


def inspect_manifest(args):
    """Inspect a manifest file or URL."""
    from sims4_updater.patch.client import PatchClient, format_size
    from sims4_updater.core.exceptions import ManifestError

    source = args.source

    try:
        client = PatchClient(manifest_url="")

        if source.startswith("http://") or source.startswith("https://"):
            client.manifest_url = source
            manifest = client.fetch_manifest()
        else:
            manifest = client.load_manifest_from_file(source)
    except ManifestError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Source: {manifest.manifest_url}")
    print(f"Latest version: {manifest.latest}")
    print(f"Patches: {len(manifest.patches)}")
    print(f"Versions referenced: {len(manifest.all_versions)}")
    print()

    if manifest.patches:
        print("Available patches:")
        for p in manifest.patches:
            size = format_size(p.total_size)
            files = len(p.files)
            crack = " + crack" if p.crack else ""
            print(f"  {p.version_from} -> {p.version_to}  ({files} file(s){crack}, {size})")

    client.close()


def show_status(args):
    """Show overall status: game dir, version, DLC summary."""
    from sims4_updater.core.version_detect import VersionDetector
    from sims4_updater.dlc.manager import DLCManager
    from sims4_updater.dlc.formats import detect_format
    from sims4_updater.language.changer import get_current_language
    from sims4_updater.config import Settings
    from pathlib import Path

    settings = Settings.load()
    detector = VersionDetector()

    # Resolve game directory
    game_dir = getattr(args, "game_dir", None) or settings.game_path
    if not game_dir:
        game_dir = detector.find_game_dir()

    print("=== Sims 4 Updater Status ===")
    print()

    if not game_dir:
        print("Game directory: NOT FOUND")
        print("  Provide a path: sims4-updater status <game_dir>")
        return

    print(f"Game directory: {game_dir}")

    if not detector.validate_game_dir(game_dir):
        print("  WARNING: Directory does not look like a valid Sims 4 install.")
        return

    # Version
    result = detector.detect(game_dir)
    if result.version:
        print(f"Installed version: {result.version} ({result.confidence.value})")
    else:
        print("Installed version: UNKNOWN")

    # Language
    language = get_current_language()
    from sims4_updater.language.changer import LANGUAGES
    lang_name = LANGUAGES.get(language, language)
    print(f"Language: {lang_name} ({language})")

    # Crack config
    game_path = Path(game_dir)
    adapter = detect_format(game_path)
    if adapter:
        print(f"Crack config: {adapter.get_format_name()}")
    else:
        print("Crack config: None detected")

    # DLC summary
    manager = DLCManager()
    states = manager.get_dlc_states(game_path)
    total = len(states)
    installed = sum(1 for s in states if s.installed)
    enabled = sum(1 for s in states if s.enabled is True)
    print(f"DLCs: {installed}/{total} installed, {enabled} enabled")

    # Settings
    print()
    if settings.manifest_url:
        print(f"Manifest URL: {settings.manifest_url}")
    else:
        print("Manifest URL: Not configured")

    if settings.last_known_version:
        print(f"Last known version: {settings.last_known_version}")


def learn_hashes(args):
    """Learn version hashes from a known game installation."""
    from pathlib import Path
    from sims4_updater.core.version_detect import VersionDetector
    from sims4_updater.core.learned_hashes import LearnedHashDB
    from sims4_updater.core.files import hash_file
    from sims4_updater import constants

    game_dir = Path(args.game_dir)
    version = args.version
    detector = VersionDetector()

    if not detector.validate_game_dir(game_dir):
        print("ERROR: Not a valid Sims 4 installation directory.")
        sys.exit(1)

    print(f"Game directory: {game_dir}")
    print(f"Version: {version}")
    print()

    # Hash sentinel files
    hashes = {}
    for sentinel in constants.SENTINEL_FILES:
        file_path = game_dir / sentinel.replace("/", os.sep)
        if file_path.is_file():
            md5 = hash_file(str(file_path))
            hashes[sentinel] = md5
            print(f"  {sentinel}: {md5}")
        else:
            print(f"  {sentinel}: MISSING")

    if not hashes:
        print("\nERROR: No sentinel files found.")
        sys.exit(1)

    # Check if this conflicts with an existing version
    db = detector.db
    existing = db.versions.get(version)
    if existing and existing != hashes:
        print(f"\nWARNING: Bundled DB already has different hashes for {version}.")
        print("Your local hashes will take priority for future detection.")

    # Save to learned DB
    learned = LearnedHashDB()
    learned.add_version(version, hashes)
    learned.save()

    print(f"\nSaved {len(hashes)} hash(es) for version {version}.")
    print(f"Database: {learned.path}")
    print(f"Total learned versions: {learned.version_count}")


def show_language(args):
    """Show or set language."""
    from sims4_updater.language.changer import get_current_language, set_language, LANGUAGES

    if args.code:
        result = set_language(args.code, game_dir=args.game_dir)
        if result.success:
            print(f"Language set to: {LANGUAGES.get(args.code, args.code)} ({args.code})")
            if result.anadius_updated:
                print(f"  Updated {len(result.anadius_updated)} anadius config(s)")
            if result.registry_ok:
                print(f"  Registry updated")
            if result.rld_updated:
                print(f"  Updated {len(result.rld_updated)} RldOrigin config(s)")
        else:
            print(f"Failed to update any config. Try running as administrator.")
    else:
        current = get_current_language(game_dir=args.game_dir)
        print(f"Current language: {LANGUAGES.get(current, current)} ({current})")
        print()
        print("Available languages:")
        for code, name in LANGUAGES.items():
            marker = " <--" if code == current else ""
            print(f"  {code}: {name}{marker}")


def pack_dlc(args):
    """Create standard zip archives for individual DLCs."""
    import json
    from pathlib import Path
    from sims4_updater.dlc.catalog import DLCCatalog
    from sims4_updater.dlc.packer import DLCPacker

    game_dir = Path(args.game_dir)
    output_dir = Path(args.output or ".")
    dlc_ids = args.dlc_ids

    if not game_dir.is_dir():
        print(f"ERROR: Game directory not found: {game_dir}")
        sys.exit(1)

    catalog = DLCCatalog()
    packer = DLCPacker(catalog)

    # Resolve DLC IDs
    if dlc_ids == ["all"]:
        targets = []
        for dlc in catalog.all_dlcs():
            if (game_dir / dlc.id).is_dir():
                targets.append(dlc)
        if not targets:
            print("No installed DLCs found.")
            sys.exit(1)
        print(f"Packing all {len(targets)} installed DLC(s)...")
    else:
        targets = []
        for dlc_id in dlc_ids:
            dlc = catalog.get_by_id(dlc_id.upper())
            if not dlc:
                print(f"WARNING: Unknown DLC ID: {dlc_id}")
                continue
            if not (game_dir / dlc.id).is_dir():
                print(f"WARNING: {dlc.id} not installed (no folder at {game_dir / dlc.id})")
                continue
            targets.append(dlc)

        if not targets:
            print("No valid DLCs to pack.")
            sys.exit(1)

    def progress(idx, total, dlc_id, msg):
        if dlc_id:
            print(f"\n[{idx + 1}/{total}] {msg}")

    results = packer.pack_multiple(game_dir, targets, output_dir, progress_cb=progress)

    for r in results:
        size_mb = r.size / (1024 * 1024)
        print(f"  {r.dlc_id}: {r.file_count} files, {size_mb:.1f} MB, MD5: {r.md5}")

    # Generate manifest
    if results:
        manifest_path = packer.generate_manifest(results, output_dir)
        print(f"\n{'=' * 60}")
        print(f"Manifest written to: {manifest_path}")
        print(f"{'=' * 60}")
        with open(manifest_path, encoding="utf-8") as f:
            print(f.read())
        print("Replace <UPLOAD_URL> with the actual hosting URL.")


def main():
    parser = argparse.ArgumentParser(
        prog="sims4-updater",
        description="The Sims 4 Updater",
    )
    subparsers = parser.add_subparsers(dest="command")

    # detect
    detect_parser = subparsers.add_parser("detect", help="Detect installed Sims 4 version")
    detect_parser.add_argument("game_dir", help="Path to The Sims 4 installation directory")

    # check
    check_parser = subparsers.add_parser("check", help="Check for updates")
    check_parser.add_argument("game_dir", nargs="?", help="Path to The Sims 4 installation directory")
    check_parser.add_argument("--manifest-url", help="Manifest URL to check against")

    # status
    status_parser = subparsers.add_parser("status", help="Show game status overview")
    status_parser.add_argument("game_dir", nargs="?", help="Path to The Sims 4 installation directory")

    # manifest
    manifest_parser = subparsers.add_parser("manifest", help="Inspect a manifest file or URL")
    manifest_parser.add_argument("source", help="Manifest URL or local file path")

    # dlc
    dlc_parser = subparsers.add_parser("dlc", help="Show DLC states")
    dlc_parser.add_argument("game_dir", help="Path to The Sims 4 installation directory")

    # dlc-auto
    dlc_auto_parser = subparsers.add_parser("dlc-auto", help="Auto-toggle DLCs")
    dlc_auto_parser.add_argument("game_dir", help="Path to The Sims 4 installation directory")

    # pack-dlc
    pack_parser = subparsers.add_parser(
        "pack-dlc", help="Create standard zip archives for DLCs",
    )
    pack_parser.add_argument("game_dir", help="Path to The Sims 4 installation directory")
    pack_parser.add_argument(
        "dlc_ids", nargs="+",
        help="DLC IDs to pack (e.g. EP01 GP01) or 'all' for all installed",
    )
    pack_parser.add_argument(
        "-o", "--output", default=".",
        help="Output directory for zip files (default: current dir)",
    )

    # learn
    learn_parser = subparsers.add_parser("learn", help="Learn version hashes from game directory")
    learn_parser.add_argument("game_dir", help="Path to The Sims 4 installation directory")
    learn_parser.add_argument("version", help="Version string (e.g. 1.120.123.1020)")

    # language
    lang_parser = subparsers.add_parser("language", help="Show or set language")
    lang_parser.add_argument("code", nargs="?", help="Language code (e.g. en_US)")
    lang_parser.add_argument("--game-dir", help="Game directory for RldOrigin.ini update")

    args = parser.parse_args()

    if args.command == "detect":
        detect_version(args.game_dir)
    elif args.command == "check":
        check_for_updates(args)
    elif args.command == "status":
        show_status(args)
    elif args.command == "manifest":
        inspect_manifest(args)
    elif args.command == "dlc":
        show_dlc_states(args.game_dir)
    elif args.command == "dlc-auto":
        auto_toggle_dlcs(args.game_dir)
    elif args.command == "pack-dlc":
        pack_dlc(args)
    elif args.command == "learn":
        learn_hashes(args)
    elif args.command == "language":
        show_language(args)
    elif args.command is None:
        # No command — launch the GUI
        try:
            from sims4_updater.gui.app import launch
            launch()
        except ImportError:
            print("Sims 4 Updater v2.0.0")
            print("GUI requires customtkinter: pip install customtkinter")
            print()
            print("Commands:")
            print('  status [game_dir]         Show game status overview')
            print('  detect <game_dir>         Detect installed version')
            print('  check [game_dir]          Check for updates')
            print('  manifest <url|file>       Inspect a patch manifest')
            print('  dlc <game_dir>            Show DLC states')
            print('  dlc-auto <game_dir>       Auto-toggle DLCs')
            print('  pack-dlc <dir> <ids...>   Pack DLC zip archives')
            print('  learn <game_dir> <ver>    Learn version hashes')
            print('  language [code]           Show or set language')
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
