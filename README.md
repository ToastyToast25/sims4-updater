# Sims 4 Updater

> Standalone Windows tool for updating, managing DLCs, and maintaining The Sims 4 installations.

[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-see%20LICENSE-lightgrey)](LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/ToastyToast25/sims4-updater?label=download&logo=github)](https://github.com/ToastyToast25/sims4-updater/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/ToastyToast25/sims4-updater/build.yml?branch=master&logo=github-actions&logoColor=white)](https://github.com/ToastyToast25/sims4-updater/actions)

---

## Quick Links

| Link | Description |
| --- | --- |
| [Download Latest Release](../../releases/latest) | Get the latest `Sims4Updater.exe` (portable, no install needed) |
| [Documentation](Documentation/) | Full technical reference for all subsystems |
| [Report a Bug](../../issues/new) | Open a GitHub issue |
| [Contributing](CONTRIBUTING.md) | How to contribute to development |

---

## Features

### One-Click Game Updates

Binary delta patching powered by [anadius's patcher engine](https://github.com/anadius) and xdelta3. The updater detects your installed version by hashing sentinel files against a database of 135+ known versions, then uses BFS pathfinding to compute the shortest chain of patch steps from your version to the latest. Downloads support HTTP Range resume and per-file MD5 verification.

### DLC Management

Toggle 109 DLCs across 5 auto-detected crack config formats (RldOrigin, Codex, Rune, Anadius Simple, Anadius Codex-like). Auto-toggle mode scans the game directory and enables/disables DLCs based on which folders are present. Config changes are mirrored to `Bin_LE/` automatically. The catalog includes localized DLC names in 18 languages.

### CDN DLC Downloads

Download any DLC directly from [cdn.hyperabyss.com](https://cdn.hyperabyss.com) (Cloudflare Worker proxying a seedbox). Downloads run in parallel background threads with resume support and MD5 integrity verification. Progress is streamed live to the GUI.

### GreenLuma 2025 Integration

Full management of [GreenLuma 2025](https://cs.rin.ru/forum/viewtopic.php?f=29&t=103825) for Steam DLC unlocking:

- Install/uninstall GreenLuma from a `.7z` archive (normal or stealth mode) with tracked file manifests for clean removal
- Parse `.lua` manifest files to populate `AppList`, inject depot decryption keys into `config.vdf`, and copy `.manifest` files to `depotcache`
- Verify configuration by cross-referencing keys, manifests, and AppList against your LUA file
- Fix AppList (remove duplicates, add missing entries)
- Launch Steam through `DLLInjector.exe` with automatic Steam-restart handling
- Per-DLC readiness indicators (key present, manifest cached, AppList entry) shown in the DLC tab
- **Crowd-sourced key contribution**: users who own DLCs through Steam can contribute their decryption keys and manifest files to help other users
- **CDN key distribution**: automatically download and apply decryption keys, manifest files, and AppList entries from the CDN for DLCs that other users have contributed

### DLC Packer

Pack installed DLC folders into distributable ZIP archives with an auto-generated hosting manifest. Import DLC archives from other users. Available both in the GUI and as the `pack-dlc` CLI command.

### EA DLC Unlocker

One-click install/uninstall of the EA DLC Unlocker with live status detection and automatic admin elevation.

### Language Changer

Switch between 18 game languages. Updates the Windows registry (`HKLM\SOFTWARE\Maxis\The Sims 4\Locale`, both 32-bit and 64-bit views), `RldOrigin.ini`, and the anadius crack config simultaneously. Optionally downloads language files from Steam depots via DepotDownloader.

### Mod Manager

Manage game modifications directly from the GUI.

### Diagnostics

Automated system health checks: VC Redistributable presence, .NET Framework status, Windows Defender Controlled Folder Access, game directory permissions, path issues (semicolons, non-ASCII), and antivirus quarantine detection. File validator scans DLC folders for missing or corrupt files against known-good checksums.

### Version Detection

Hash-based identification using 3 sentinel files (`TS4_x64.exe`, `Default.ini`, `delta/EP01/version.ini`) matched against a bundled database of 135+ versions. Detection returns a confidence level (Definitive / Probable / Unknown). Auto-detection checks the Windows registry and common Steam/EA install paths.

### Self-Updating Hash Database

The version database stays current through 4 complementary sources:

| Source | When | Scope |
| --- | --- | --- |
| Bundled database | Always loaded | 135+ versions shipped in the exe |
| Manifest fingerprints | On update check | Hashes included in your manifest JSON |
| Self-learning | After each successful patch | Sentinel files hashed and saved locally |
| Crowd-sourced | On update check | Validated hashes from `fingerprints_url` endpoint |

### Self-Updater

Checks the GitHub Releases API on startup and offers one-click self-update. Downloads the new exe, validates it, and hot-swaps while the app is running (hidden console, restore on failure).

### Modern Dark-Mode GUI

CustomTkinter dark-mode UI with slide animations, hex-interpolated color transitions, ease-out-cubic easing, and toast notifications. Sidebar navigation with 11 named tabs.

### Full CLI Support

Every major operation is available headlessly for scripting and automation.

---

## Screenshots

Screenshots coming soon.

---

## Installation

### Portable Executable (Recommended)

Download `Sims4Updater.exe` from [Releases](../../releases/latest). No installation, no dependencies — just run it.

**Requirements:**

- Windows 10 or Windows 11 (64-bit)
- An existing installation of The Sims 4

### From Source

```bash
git clone https://github.com/ToastyToast25/sims4-updater.git
cd sims4-updater

# Install with dev extras
pip install -e ".[dev]"

# Run the GUI
PYTHONPATH=src python -m sims4_updater
```

The patcher engine lives in a sibling directory that must be checked out separately:

```bash
git clone https://github.com/ToastyToast25/patcher.git ../patcher
```

---

## Usage

### GUI Mode

Double-click `Sims4Updater.exe` or run with no arguments. The sidebar provides 11 tabs:

| Tab | Description |
| --- | --- |
| **Home** | Game directory, installed version, latest version, DLC summary, and the main Update Now button. Shows a "patch coming soon" banner when EA has released a new version ahead of the available patches. |
| **DLCs** | Scrollable catalog of all 109 DLCs grouped by type. Per-DLC enable/disable toggles, GreenLuma readiness indicators (key / manifest / AppList), Steam pricing, and one-click CDN download. |
| **DLC Downloader** | Download individual DLC archives from the CDN with live progress bars, parallel threads, resume, and MD5 verification. |
| **DLC Packer** | Pack installed DLC folders into distributable ZIP archives. Import ZIP archives from others. |
| **DLC Unlocker** | Install or uninstall the EA DLC Unlocker. Status detection with admin elevation when required. |
| **GreenLuma** | Install/uninstall GreenLuma 2025, apply LUA manifests, verify configuration, fix AppList, apply CDN keys, contribute keys, and launch Steam via DLLInjector. |
| **Language** | Select from 18 languages. Optionally download language files from Steam depots. |
| **Mods** | Manage game modifications. |
| **Diagnostics** | System health checks and DLC file validator. |
| **Settings** | Game path, manifest URL, GreenLuma paths, Steam username, download concurrency, speed limit, theme, and language. |
| **Progress** | Live download/patch progress bars, scrollable log output, and cancel button during updates. |

### CLI Mode

```text
Sims4Updater.exe <command> [options]
```

| Command | Description |
| --- | --- |
| `status [game_dir]` | Show game directory, installed version, language, crack config format, and DLC summary |
| `detect <game_dir>` | Detect the installed version by hashing the 3 sentinel files |
| `check [game_dir]` | Check for available updates; shows patch steps and total download size |
| `manifest <url\|file>` | Inspect a manifest — list all patches, versions, and file sizes |
| `dlc <game_dir>` | Show all DLC states (enabled/disabled, installed/missing) grouped by type |
| `dlc-auto <game_dir>` | Auto-enable installed DLCs and disable missing ones |
| `pack-dlc <game_dir> <ids...> [-o dir]` | Pack one or more DLCs into ZIP archives with a generated hosting manifest |
| `learn <game_dir> <version>` | Hash sentinel files and save them to the local version database |
| `language` | Show current language and all 18 available languages |
| `language <code> [--game-dir DIR]` | Set game language (registry + crack config files) |

#### CLI Examples

```bash
# Auto-detect game and show full status
Sims4Updater.exe status

# Detect version of a specific install
Sims4Updater.exe detect "D:\Games\The Sims 4"

# Check for updates against a custom manifest
Sims4Updater.exe check --manifest-url https://cdn.hyperabyss.com/manifest.json

# Inspect a manifest to see all available patches
Sims4Updater.exe manifest https://cdn.hyperabyss.com/manifest.json

# Show DLC states for a game directory
Sims4Updater.exe dlc "D:\Games\The Sims 4"

# Auto-toggle DLCs after manual patching
Sims4Updater.exe dlc-auto "D:\Games\The Sims 4"

# Pack specific DLCs into ZIP archives
Sims4Updater.exe pack-dlc "D:\Games\The Sims 4" EP01 GP05 SP12 -o ./output

# Pack all installed DLCs
Sims4Updater.exe pack-dlc "D:\Games\The Sims 4" all -o ./output

# Teach the updater your current version's hashes
Sims4Updater.exe learn "D:\Games\The Sims 4" 1.121.372.1020

# Show languages and set to French
Sims4Updater.exe language
Sims4Updater.exe language fr_FR --game-dir "D:\Games\The Sims 4"
```

---

## Hosting Patches

The updater is **backend-agnostic** — it only needs a single manifest URL. Patch files can be hosted anywhere: a CDN, object storage bucket, web server, seedbox, or local network share. The CDN at `cdn.hyperabyss.com` uses a Cloudflare Worker proxying a Whatbox/RapidSeedbox seedbox, but the architecture is fully replaceable by updating the manifest URLs.

### Manifest Format

Host a JSON file at any stable URL. Configure this URL in the updater's Settings tab or via `--manifest-url`.

```json
{
  "latest": "1.121.372.1020",
  "game_latest": "1.122.100.1020",
  "game_latest_date": "2026-02-15",

  "patches": [
    {
      "from": "1.119.109.1020",
      "to": "1.120.250.1020",
      "files": [
        {
          "url": "https://cdn.hyperabyss.com/patches/ts4_1.119_to_1.120.zip",
          "size": 524288000,
          "md5": "ABC123DEF456..."
        }
      ],
      "crack": {
        "url": "https://cdn.hyperabyss.com/cracks/crack_1.120.rar",
        "size": 1048576,
        "md5": "MNO345PQR678..."
      }
    },
    {
      "from": "1.120.250.1020",
      "to": "1.121.372.1020",
      "files": [
        {
          "url": "https://cdn.hyperabyss.com/patches/ts4_1.120_to_1.121.zip",
          "size": 412000000,
          "md5": "STU901VWX234..."
        }
      ]
    }
  ],

  "new_dlcs": [
    {"id": "EP15", "name": "New Expansion Pack"}
  ],

  "fingerprints": {
    "1.121.372.1020": {
      "Game/Bin/TS4_x64.exe": "1E45D4A27DC56134689A306FA92EF115",
      "Game/Bin/Default.ini": "3000759841368CC356E2996B98F33610",
      "delta/EP01/version.ini": "43BF3EAABEBCC513615F5F581567DFC9"
    }
  },

  "fingerprints_url": "https://api.hyperabyss.com/fingerprints.json",
  "report_url": "https://api.hyperabyss.com/report"
}
```

#### Field Reference

| Field | Required | Description |
| --- | --- | --- |
| `latest` | Yes | Newest version with patches available |
| `game_latest` | No | Actual latest EA release (shown when ahead of `latest`) |
| `game_latest_date` | No | Release date of `game_latest` (displayed in GUI) |
| `patches` | Yes | Array of patch entries |
| `patches[].from` | Yes | Source version |
| `patches[].to` | Yes | Target version |
| `patches[].files` | Yes | Downloadable patch archives (multi-part supported) |
| `patches[].files[].url` | Yes | Direct download URL |
| `patches[].files[].size` | Yes | File size in bytes (for progress bars) |
| `patches[].files[].md5` | Yes | MD5 checksum for integrity verification |
| `patches[].crack` | No | Optional crack archive for this version step |
| `new_dlcs` | No | DLCs announced but not yet patchable (shown as "pending" in GUI) |
| `fingerprints` | No | Version hashes for auto-detection |
| `fingerprints_url` | No | URL to a crowd-sourced fingerprints JSON |
| `report_url` | No | URL where clients POST learned hashes |
| `contribute_url` | No | URL for DLC/GreenLuma contribution submissions |
| `greenluma` | No | Dict of depot_id → {key, manifest_id, manifest_url} for GreenLuma CDN keys |

#### Multi-Step Updates

The updater uses BFS pathfinding to find the shortest chain of patches from the user's installed version to `latest`. If a direct patch does not exist, it chains intermediate steps automatically. Among equal-length paths it picks the one with the smallest total download size.

#### Patch-Pending Awareness

When `game_latest` is ahead of `latest`, the GUI shows a "patch coming soon" banner and disables the update button. Users are told that a new EA version exists without being able to attempt a doomed update. Once you create the patch and update `latest` in the manifest, the button becomes available on the next manifest fetch.

### Creating Patches

Patches are created using the patcher tool in the sibling `../patcher/` directory, which generates xdelta3 binary delta files. You need a clean copy of both the old and new game versions.

**Step-by-step:**

1. Obtain clean copies of the old and new game versions.

2. Run the patcher tool to create the delta:

   ```bash
   cd ../patcher
   python patcher.py create --old "D:\TS4_1.119" --new "D:\TS4_1.120" --output ts4_1.119_to_1.120.zip
   ```

3. Hash the sentinel files of the new version:

   ```bash
   Sims4Updater.exe learn "D:\TS4_1.120" 1.120.250.1020
   ```

   This outputs the MD5 hashes for `TS4_x64.exe`, `Default.ini`, and `delta/EP01/version.ini`. Copy them into the manifest's `fingerprints` section.

4. Get the patch archive checksum:

   ```bash
   certutil -hashfile ts4_1.119_to_1.120.zip MD5
   ```

5. Upload the patch file to your hosting provider.

6. Add the patch entry to the manifest and update `latest`.

**When a new game update is released:**

1. Set `game_latest` in the manifest immediately — users see "patch coming soon" right away.
2. Create the patch archive from old version to new version.
3. Upload to your host.
4. Add the patch entry, update `latest`, and users will see "Update Now" on their next check.

**When new DLC is released:**

1. Add the DLC to `new_dlcs` — it appears as "pending" in the DLC catalog immediately.
2. Once the patch is ready, move the DLC out of `new_dlcs` and into the normal patch flow.
3. Add the DLC to `data/dlc_catalog.json` and rebuild the exe for localized names.

### CDN Infrastructure (cdn.hyperabyss.com)

The live CDN uses a Cloudflare Worker that proxies requests to a RapidSeedbox seedbox (Whatbox Swift NL). Users only see `cdn.hyperabyss.com`; the seedbox URL is never exposed.

```text
User app  ->  cdn.hyperabyss.com/dlc/EP01.zip  ->  Cloudflare Worker  ->  Seedbox  ->  file streamed back
```

The Worker reads a KV namespace (`CDN_ROUTES`) that maps clean paths (e.g., `dlc/EP01.zip`) to seedbox secure links. Adding a new file to the CDN is a three-step operation: upload to seedbox, generate a secure link, add a KV entry. Setup details and the complete Worker source are in the [`cloudflare-worker/`](cloudflare-worker/) directory.

**URL structure:**

```text
cdn.hyperabyss.com/
├── manifest.json
├── patches/
│   └── 1.120.250_to_1.121.372.zip
├── dlc/
│   ├── EP01.zip
│   └── GP01.zip
└── language/
    └── de_DE.zip
```

**Cost breakdown:**

| Service | Cost |
| --- | --- |
| Cloudflare Worker | Free (100k req/day) |
| Cloudflare KV | Free (100k reads/day, 1k writes/day) |
| RapidSeedbox Swift | $8/mo |
| **Total** | **$8/mo** |

### Crowd-Sourced Hash Reporting

Set up two optional API endpoints to automate version fingerprint distribution across all users:

1. **`report_url`** — Receives `POST {"version": "...", "hashes": {...}}` after each successful patch or `learn` command. A Cloudflare Worker with KV auto-validates by requiring 3+ matching reports from distinct IPs.

2. **`fingerprints_url`** — Serves the validated fingerprint database. The updater fetches this on every manifest check and merges new hashes into the local learned database.

Example `fingerprints_url` response:

```json
{
  "versions": {
    "1.121.372.1020": {
      "Game/Bin/TS4_x64.exe": "1E45D4A27DC56134689A306FA92EF115",
      "Game/Bin/Default.ini": "3000759841368CC356E2996B98F33610",
      "delta/EP01/version.ini": "43BF3EAABEBCC513615F5F581567DFC9"
    }
  }
}
```

A complete Cloudflare Worker implementation for the fingerprint API (with IP deduplication and majority-vote validation) can be adapted for deployment at any Cloudflare Workers account from the source in `cloudflare-worker/api-worker.js`.

### Version Fingerprints

When creating a patch, hash the 3 sentinel files and include them in the manifest `fingerprints` block. This enables every user to auto-detect the new version immediately — even before they have applied the patch themselves — because the hashes are fetched from the manifest on every update check.

```bash
Sims4Updater.exe learn "D:\Games\The Sims 4" 1.121.372.1020
# Outputs MD5s for the 3 sentinel files — paste into manifest fingerprints
```

---

## Building from Source

### Prerequisites

- Python 3.12+ (CI uses 3.12; development uses 3.14)
- The `patcher/` sibling directory checked out (see above)

### Setup

```bash
pip install -e ".[dev]"
```

This installs runtime dependencies (`customtkinter`, `requests`, `pywin32`) plus dev extras (`pytest`, `pytest-cov`, `ruff`, `pyinstaller`).

### Build

```bash
pyinstaller --clean --noconfirm Sims4Updater.spec
```

Output: `dist/Sims4Updater.exe` — a single-file portable executable bundling:

- CustomTkinter GUI assets and fonts
- xdelta3 binaries (x64 and x86) from `../patcher/tools/`
- unrar executable
- `data/version_hashes.json` — 135+ version fingerprints
- `data/dlc_catalog.json` — 109 DLC entries with 18-language names
- `mods/` — bundled mod resources

A convenience batch file is also available:

```bat
build.bat
```

### Lint and Tests

```bash
# Lint (ruff, py312 target, 100-char lines)
ruff check src/
ruff format src/

# Tests
pytest tests/ -v --tb=short
```

### CI/CD

GitHub Actions workflow (`.github/workflows/build.yml`):

- **Trigger**: push to `master` (build + test), or any `v*` tag (build + release)
- **Build environment**: `windows-latest`, Python 3.12
- **Patcher dependency**: checked out from `ToastyToast25/patcher` as a sibling directory
- **Release**: tagged pushes create a GitHub Release automatically via `softprops/action-gh-release` with generated release notes

---

## Project Structure

```text
sims4-updater/
├── src/
│   ├── sims4_updater/
│   │   ├── __init__.py              # VERSION string ("2.2.0")
│   │   ├── __main__.py              # CLI argparse entry point + GUI launcher
│   │   ├── constants.py             # SENTINEL_FILES, registry paths, get_data_dir(), get_tools_dir()
│   │   ├── config.py                # Settings dataclass, get_app_dir() -> %LOCALAPPDATA%\ToastyToast25\
│   │   ├── updater.py               # Sims4Updater(BasePatcher) — main engine, patcher sys.path injection
│   │   ├── core/
│   │   │   ├── exceptions.py        # UpdaterError hierarchy
│   │   │   ├── version_detect.py    # VersionDetector, VersionDatabase, DetectionResult, Confidence
│   │   │   ├── learned_hashes.py    # LearnedHashDB — local writable version fingerprint store
│   │   │   ├── self_update.py       # GitHub Releases self-update pipeline
│   │   │   ├── unlocker.py          # EA DLC Unlocker install/uninstall/status
│   │   │   ├── rate_limiter.py      # Download rate limiting (token bucket)
│   │   │   ├── files.py             # hash_file() (MD5), write_check(), get_short_path()
│   │   │   ├── myzipfile.py         # ZIP with LZMA metadata support
│   │   │   ├── cache.py             # JSON cache with atomic writes
│   │   │   ├── subprocess_.py       # Subprocess with Ctrl+C handling
│   │   │   ├── diagnostics.py       # System health checks (VC Redist, .NET, AV, permissions)
│   │   │   ├── validator.py         # Game file validator — missing/corrupt/extra file scanner
│   │   │   ├── contribute.py        # DLC contribution scanner — submit unknown DLC metadata to API
│   │   │   └── utils.py             # Size parsing utilities
│   │   ├── patch/
│   │   │   ├── manifest.py          # Manifest, PatchEntry, FileEntry, DLCDownloadEntry, GreenLumaEntry, parse_manifest()
│   │   │   ├── planner.py           # UpdatePlan, plan_update() — BFS shortest-path planner
│   │   │   ├── downloader.py        # HTTP download with resume + MD5 verification + progress callbacks
│   │   │   └── client.py            # PatchClient — fetch manifest, check update, download orchestration
│   │   ├── dlc/
│   │   │   ├── catalog.py           # DLCCatalog, DLCInfo, DLCStatus — 109 DLCs, 18 languages
│   │   │   ├── formats.py           # 5 DLCConfigAdapter implementations + detect_format()
│   │   │   ├── manager.py           # DLCManager — unified toggle facade over all crack formats
│   │   │   ├── downloader.py        # DLCDownloader — download/extract/register pipeline
│   │   │   ├── packer.py            # DLCPacker — ZIP creation + manifest generation
│   │   │   └── steam.py             # SteamPriceCache, fetch_prices_batch()
│   │   ├── greenluma/
│   │   │   ├── steam.py             # Steam path detection, process checks, SteamInfo
│   │   │   ├── installer.py         # GreenLuma install/uninstall/launch, install manifest tracking
│   │   │   ├── applist.py           # AppList (numbered .txt files) read/write/fix/backup
│   │   │   ├── config_vdf.py        # Steam config.vdf parsing and depot key management
│   │   │   ├── lua_parser.py        # LUA manifest file parser
│   │   │   ├── manifest_cache.py    # depotcache .manifest file management
│   │   │   ├── orchestrator.py      # High-level GL operations (readiness, apply, verify, CDN keys)
│   │   │   └── contribute.py        # GL contribution scanner — extract + submit depot keys/manifests
│   │   ├── language/
│   │   │   ├── changer.py           # LANGUAGES dict, registry + RldOrigin.ini language setter
│   │   │   ├── downloader.py        # Steam depot-based language file downloader
│   │   │   ├── packer.py            # Language file packing
│   │   │   └── steam.py             # Steam language depot configuration
│   │   ├── mods/
│   │   │   └── manager.py           # Mod management
│   │   └── gui/
│   │       ├── app.py               # App(ctk.CTk) — window, sidebar, run_async(), show_toast(), _enqueue_gui()
│   │       ├── theme.py             # COLORS dict, fonts, sizing, animation timing constants
│   │       ├── components.py        # InfoCard, StatusBadge, ToastNotification
│   │       ├── animations.py        # Animator, lerp_color(), ease_out_cubic()
│   │       └── frames/
│   │           ├── home_frame.py        # Version display, update button, self-update banner
│   │           ├── dlc_frame.py         # DLC catalog, filters, GL readiness indicators
│   │           ├── downloader_frame.py  # DLC download interface with live progress
│   │           ├── packer_frame.py      # Pack/import DLC archives
│   │           ├── unlocker_frame.py    # EA DLC Unlocker install/uninstall
│   │           ├── greenluma_frame.py   # GreenLuma install/apply LUA/verify/launch
│   │           ├── language_frame.py    # Language selection and Steam depot downloads
│   │           ├── mods_frame.py        # Mod management
│   │           ├── diagnostics_frame.py # System checks and file validator
│   │           ├── settings_frame.py    # Settings (2-card layout: Game & Updates / GreenLuma)
│   │           └── progress_frame.py    # Live progress bars, log, cancel button
│   └── patch_maker/                 # Patch creation CLI tool (registered as patch-maker entry point)
├── data/
│   ├── version_hashes.json          # Bundled sentinel-file hash database (135+ versions)
│   └── dlc_catalog.json             # All 109 DLCs with localized names, pack types, Steam App IDs
├── cloudflare-worker/               # Cloudflare Worker source + deployment scripts for cdn.hyperabyss.com
│   ├── worker.js                    # CDN proxy worker (KV route lookup -> seedbox fetch)
│   ├── api-worker.js                # Fingerprint API worker (report + validate hashes)
│   ├── wrangler.toml                # Wrangler deployment config
│   ├── cdn_upload.py                # Upload patch files and update KV routes
│   ├── cdn_pack_upload.py           # Upload packed DLC ZIPs to CDN
│   └── SETUP.md                     # Step-by-step CDN infrastructure setup guide
├── mods/                            # Bundled mod resources
├── tools/                           # Runtime tools: xdelta3, unrar, EA DLC Unlocker DLL
├── Sims4Updater.spec                # PyInstaller build config (active)
├── pyproject.toml                   # Hatchling build backend, ruff config, pytest config
├── requirements.txt                 # Runtime dependencies
├── requirements-dev.txt             # Dev/build dependencies
└── .github/workflows/build.yml      # CI/CD pipeline
```

---

## Crack Config Formats

The DLC manager auto-detects which crack format is in use by scanning the game directory (checked in priority order, first match wins):

| Format | Config File | Toggle Method | Config Mirror |
| --- | --- | --- | --- |
| AnadiusCodex | `Game/Bin/anadius.cfg` (with `Config2` group) | Group string swap (CODEX-style) | `Bin_LE/` if present |
| AnadiusSimple | `Game/Bin/anadius.cfg` (without `Config2`) | `//` comment prefix | `Bin_LE/` if present |
| Rune | `Game/Bin/rune.ini` | `[CODE_]` suffix on section names = disabled | `Bin_LE/` if present |
| Codex | `Game/Bin/codex.cfg` | Group string swap (CODEX-style) | `Bin_LE/` if present |
| RldOrigin | `Game/Bin/RldOrigin.ini` | `;` comment prefix | `Bin_LE/` if present |

All paths are also searched under `Game-cracked/Bin/`.

---

## Data and Settings Paths

| Path | Content |
| --- | --- |
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\settings.json` | User preferences (game path, manifest URL, language, theme, GreenLuma paths) |
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\learned_hashes.json` | Self-learned version fingerprints (takes priority over bundled DB) |
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\downloads\` | Patch download cache (resumable) |
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\packed_dlcs\` | DLC Packer output directory |
| `%APPDATA%\ToastyToast25\EA DLC Unlocker\` | EA DLC Unlocker entitlements.ini |

Settings auto-migrate from the old `anadius` directory on first run.

---

## Documentation

Full technical reference for all subsystems:

| Document | Scope |
| --- | --- |
| [User Guide](Documentation/User_Guide.md) | End-user reference — every tab, all CLI commands, troubleshooting, FAQ |
| [Architecture and Developer Guide](Documentation/Architecture_and_Developer_Guide.md) | 3-layer architecture, module map, threading model, GUI patterns, how-to guides for adding features |
| [Update and Patching System](Documentation/Update_and_Patching_System.md) | Version detection internals, manifest format, BFS planning algorithm, download pipeline, hash learning |
| [DLC Management System](Documentation/DLC_Management_System.md) | DLC catalog design, all 5 crack config formats, download pipeline, EA Unlocker, Steam pricing, GL readiness |
| [DLC Packer and Distribution](Documentation/DLC_Packer_and_Distribution.md) | Packer class internals, ZIP format specification, manifest generation, import flow, distribution workflow |
| [GreenLuma Integration](Documentation/GreenLuma_Integration.md) | Steam detection, AppList management, config.vdf depot keys, LUA manifest parsing, depotcache, orchestrator |
| [CDN Infrastructure](Documentation/CDN_Infrastructure.md) | Cloudflare Worker proxy, KV routing, seedbox integration, upload tools, deployment guide |

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting pull requests, reporting bugs, and adding new features.

Key development conventions:

- `from __future__ import annotations` in all non-trivial modules
- `TYPE_CHECKING` guards for circular import avoidance
- All GUI colors as hex (`#RRGGBB`) via `theme.COLORS["key"]` — CustomTkinter does not support `rgba()`
- Never update widgets from a background thread — always use `app._enqueue_gui()` or `on_done`/`on_error` callbacks
- Line length: 100 characters (`ruff` enforced)
- Linting: `ruff check src/` must pass before opening a PR

---

## Disclaimer

**THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.** By using this software, you acknowledge and agree to the following:

1. **No liability.** The author(s) and contributor(s) of this software shall not be held liable for any damages, losses, data corruption, account bans, legal consequences, or any other negative outcomes arising from the use, misuse, or inability to use this software. This includes, but is not limited to, damage to game installations, loss of save data, violation of terms of service, or any other direct or indirect consequences.

2. **Use at your own risk.** This software interacts with game files, the Windows registry, and network resources. You are solely responsible for any changes made to your system. Always maintain backups of your game files and save data before using this tool.

3. **No affiliation.** This project is not affiliated with, endorsed by, or associated with Electronic Arts Inc., Maxis, Valve Corporation, or any other company. "The Sims" is a registered trademark of Electronic Arts Inc. All other trademarks are the property of their respective owners.

4. **Terms of service.** Using this software may violate the terms of service of The Sims 4, EA, Steam, or other platforms. You are solely responsible for understanding and complying with all applicable terms of service and laws in your jurisdiction.

5. **No guarantee of functionality.** This software is provided for educational and personal use purposes. There is no guarantee that it will work with any specific version of the game, and it may break at any time due to game updates or other changes.

6. **Distribution.** If you redistribute this software or derivative works, you do so at your own risk and responsibility. The original author(s) bear no responsibility for how redistributed copies are used.

**By downloading, installing, or using this software, you accept full responsibility for your actions and agree that the author(s) cannot be held liable for any consequences.**

---

## License

This project is provided for educational purposes. See [LICENSE](LICENSE) for details.
