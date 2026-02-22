# Sims 4 Updater — Architecture and Developer Guide

**Version:** 2.1.0
**Author:** ToastyToast25
**Last Updated:** February 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Repository Layout](#2-repository-layout)
3. [Architecture Overview](#3-architecture-overview)
   - 3.1 [Three-Layer Architecture](#31-three-layer-architecture)
   - 3.2 [Package Dependency Map](#32-package-dependency-map)
   - 3.3 [Data Flow at a Glance](#33-data-flow-at-a-glance)
4. [Layer 1: Base Patcher Engine](#4-layer-1-base-patcher-engine)
   - 4.1 [Role and Responsibilities](#41-role-and-responsibilities)
   - 4.2 [Integration via sys.path Injection](#42-integration-via-syspath-injection)
   - 4.3 [CallbackType Enum](#43-callbacktype-enum)
5. [Layer 2: Updater Core](#5-layer-2-updater-core)
   - 5.1 [Sims4Updater Engine](#51-sims4updater-engine)
   - 5.2 [Full Update Pipeline](#52-full-update-pipeline)
   - 5.3 [UpdateState Machine](#53-updatestate-machine)
   - 5.4 [Core: Version Detection](#54-core-version-detection)
   - 5.5 [Core: Learned Hash Database](#55-core-learned-hash-database)
   - 5.6 [Core: File Utilities](#56-core-file-utilities)
   - 5.7 [Core: Self-Update](#57-core-self-update)
   - 5.8 [Core: DLC Unlocker](#58-core-dlc-unlocker)
   - 5.9 [Patch: Manifest](#59-patch-manifest)
   - 5.10 [Patch: Client](#510-patch-client)
   - 5.11 [Patch: Planner](#511-patch-planner)
   - 5.12 [Patch: Downloader](#512-patch-downloader)
   - 5.13 [DLC: Catalog](#513-dlc-catalog)
   - 5.14 [DLC: Manager](#514-dlc-manager)
   - 5.15 [DLC: Formats (Crack Config Adapters)](#515-dlc-formats-crack-config-adapters)
   - 5.16 [DLC: Downloader](#516-dlc-downloader)
   - 5.17 [DLC: Packer](#517-dlc-packer)
   - 5.18 [DLC: Steam Price Service](#518-dlc-steam-price-service)
   - 5.19 [Language Changer](#519-language-changer)
   - 5.20 [GreenLuma Package](#520-greenluma-package)
6. [Layer 3: GUI](#6-layer-3-gui)
   - 6.1 [App Class and Window Structure](#61-app-class-and-window-structure)
   - 6.2 [Threading Model](#62-threading-model)
   - 6.3 [Frame Lifecycle and Navigation](#63-frame-lifecycle-and-navigation)
   - 6.4 [Slide Transition Animation](#64-slide-transition-animation)
   - 6.5 [Theme System](#65-theme-system)
   - 6.6 [Component Library](#66-component-library)
   - 6.7 [Animation Engine](#67-animation-engine)
   - 6.8 [Frame Reference: HomeFrame](#68-frame-reference-homeframe)
   - 6.9 [Frame Reference: DLCFrame](#69-frame-reference-dlcframe)
   - 6.10 [Frame Reference: PackerFrame](#610-frame-reference-packerframe)
   - 6.11 [Frame Reference: UnlockerFrame](#611-frame-reference-unlockerframe)
   - 6.12 [Frame Reference: GreenLumaFrame](#612-frame-reference-greenlumaframe)
   - 6.13 [Frame Reference: SettingsFrame](#613-frame-reference-settingsframe)
   - 6.14 [Frame Reference: ProgressFrame](#614-frame-reference-progressframe)
7. [Configuration and App Data](#7-configuration-and-app-data)
   - 7.1 [App Data Directory](#71-app-data-directory)
   - 7.2 [Settings Dataclass](#72-settings-dataclass)
   - 7.3 [Settings Migration](#73-settings-migration)
   - 7.4 [Bundled Data Paths](#74-bundled-data-paths)
8. [CLI Entry Point](#8-cli-entry-point)
9. [Exception Hierarchy](#9-exception-hierarchy)
10. [Manifest Format Specification](#10-manifest-format-specification)
11. [DLC Catalog and Custom DLCs](#11-dlc-catalog-and-custom-dlcs)
12. [Build System](#12-build-system)
    - 12.1 [PyInstaller Spec](#121-pyinstaller-spec)
    - 12.2 [Runtime Path Resolution](#122-runtime-path-resolution)
    - 12.3 [Excluded Packages](#123-excluded-packages)
13. [Developer Guides](#13-developer-guides)
    - 13.1 [Adding a New GUI Frame](#131-adding-a-new-gui-frame)
    - 13.2 [Adding a New Crack Config Format](#132-adding-a-new-crack-config-format)
    - 13.3 [Adding a New CLI Subcommand](#133-adding-a-new-cli-subcommand)
    - 13.4 [Extending the DLC Catalog](#134-extending-the-dlc-catalog)
    - 13.5 [Working with the Version Hash DB](#135-working-with-the-version-hash-db)
14. [Security Considerations](#14-security-considerations)
15. [Performance Characteristics](#15-performance-characteristics)
16. [Glossary](#16-glossary)

---

## 1. Executive Summary

The Sims 4 Updater is a Windows desktop application that automates game version management for an offline Sims 4 installation. Its primary concerns are:

- **Patch application** — downloading xdelta3 binary diffs and applying them to game files via the inherited Patcher engine.
- **Version detection** — fingerprinting sentinel files with MD5 to identify the installed game version without relying on any in-game version API.
- **DLC management** — reading and writing five different crack configuration formats to enable or disable DLC packs.
- **DLC distribution** — downloading DLC archives, extracting them, and registering them in the crack config.
- **DLC packing** — creating redistribution-ready ZIP archives from installed DLC folders, generating a hosting manifest.
- **CDN DLC downloads** — downloading DLC content packs from a Cloudflare CDN with parallel downloads, HTTP resume, and MD5 integrity verification.
- **GreenLuma integration** — installing, configuring, and managing GreenLuma 2025 for Steam DLC unlocking, including AppList management, config.vdf depot key injection, LUA manifest parsing, and depotcache manifest handling.
- **Language management** — changing game language via registry and config file manipulation, with Steam depot-based language file downloads.
- **Unlocker management** — installing and uninstalling the PandaDLL-based EA DLC Unlocker (`version.dll`) into the EA Desktop client directory.
- **Self-update** — checking GitHub Releases for a newer version of the updater executable and swapping it in place via a batch script.

The application is distributed as a single-file Windows `.exe` produced by PyInstaller. It can also be run from source. A full CLI is available for all major operations when the GUI is not desired.

A Cloudflare Worker-based CDN at `cdn.hyperabyss.com` provides global distribution of DLC content packs and game patches. See [CDN Infrastructure](CDN_Infrastructure.md) for details.

---

## 2. Repository Layout

```
sims4-updater/                         # Project root
  src/
    sims4_updater/
      __init__.py                      # VERSION = "2.1.0"
      __main__.py                      # CLI argparse entry point + launch()
      constants.py                     # App-wide constants; get_data_dir(), get_tools_dir()
      config.py                        # Settings dataclass, get_app_dir(), migration
      updater.py                       # Sims4Updater — main engine (extends BasePatcher)
      core/
        __init__.py
        exceptions.py                  # UpdaterError hierarchy
        files.py                       # hash_file(), write_check(), get_short_path()
        version_detect.py              # VersionDatabase, VersionDetector, DetectionResult
        learned_hashes.py              # LearnedHashDB — writable local hash store
        myzipfile.py                   # Custom ZIP with LZMA metadata (from patcher)
        self_update.py                 # GitHub release check + exe swap pipeline
        unlocker.py                    # EA DLC Unlocker install/uninstall
        subprocess_.py                 # Subprocess wrapper utilities
        utils.py                       # Misc utilities
        cache.py                       # General-purpose caching helpers
        rate_limiter.py                # TokenBucketRateLimiter for download speed control
      patch/
        __init__.py
        manifest.py                    # Manifest, PatchEntry, FileEntry, DLCDownloadEntry
        client.py                      # PatchClient — manifest fetch, update check, download
        planner.py                     # UpdatePlan — BFS graph path planning
        downloader.py                  # Downloader — HTTP resume, MD5, chunked streaming
      dlc/
        __init__.py
        catalog.py                     # DLCCatalog, DLCInfo, DLCStatus
        manager.py                     # DLCManager — unified toggling facade
        formats.py                     # 5 DLCConfigAdapter implementations + detect_format()
        downloader.py                  # DLCDownloader — download/extract/register pipeline
        packer.py                      # DLCPacker — ZIP creation, manifest gen, RAR import
        steam.py                       # SteamPriceCache, fetch_prices_batch()
      gui/
        __init__.py
        app.py                         # App(ctk.CTk) — main window, sidebar, threading
        theme.py                       # COLORS, fonts, sizing, animation timing
        animations.py                  # Animator, easing functions, lerp_color()
        components.py                  # InfoCard, StatusBadge, ToastNotification
        frames/
          __init__.py
          home_frame.py                # Version display, update button, self-update banner
          dlc_frame.py                 # DLC list, filter, per-DLC download
          packer_frame.py              # Pack/import DLC archives
          unlocker_frame.py            # Install/uninstall EA DLC Unlocker
          greenluma_frame.py           # GreenLuma install/uninstall/apply/verify
          downloader_frame.py          # DLC download interface
          language_frame.py            # Language management with Steam depot downloads
          mods_frame.py                # Mod management
          settings_frame.py            # Edit Settings fields
          progress_frame.py            # Live update progress log
      greenluma/
        __init__.py
        steam.py                       # Steam path detection, process checks, SteamInfo
        installer.py                   # GreenLuma install/uninstall/launch, install manifest
        applist.py                     # AppList (numbered .txt files) read/write/backup
        config_vdf.py                  # Steam config.vdf parsing, depot key management
        lua_parser.py                  # LUA manifest file parser (addappid/setManifestid)
        manifest_cache.py              # depotcache .manifest file management
        orchestrator.py                # High-level GL operations (readiness, apply LUA, verify)
      language/
        __init__.py
        changer.py                     # LANGUAGES dict, get/set registry + RldOrigin.ini
        downloader.py                  # Steam depot-based language file downloads
        packer.py                      # Language file packing
        steam.py                       # Steam language depot configuration
      mods/
        __init__.py
        manager.py                     # Mod management
      ea_api/
        __init__.py                    # (stub/reserved for EA OAuth integration)
    patch_maker/
      __init__.py                      # PatchMaker CLI package (separate tool)
  data/
    dlc_catalog.json                   # Bundled DLC definitions (all known Sims 4 DLCs)
    version_hashes.json                # Bundled version fingerprint database
  tools/                               # (resolved from ../patcher/tools/ at build time)
    xdelta3-x64.exe
    xdelta3-x86.exe
    unrar.exe
    unrar-license.txt
    DLC Unlocker for Windows/
      ea_app/version.dll
      entitlements.ini
  sims4.png                            # 1024x1024 app icon (PNG)
  sims4.ico                            # Windows ICO for exe
  sims4_updater.spec                   # PyInstaller build spec
  Sims4Updater.spec                    # Alternate spec (same output name)
  requirements.txt                     # Runtime dependencies
  requirements-dev.txt                 # Dev/test dependencies
  pyproject.toml                       # Project metadata
  build.bat                            # Convenience build script
  tests/                               # Pytest test suite
  Documentation/                       # This file and related docs
```

The `../patcher/` directory (a sibling to `sims4-updater/`) contains the base patching engine. It is not a Python package installed via pip — it is added to `sys.path` at runtime by `updater.py`.

---

## 3. Architecture Overview

### 3.1 Three-Layer Architecture

The system is organized into three distinct layers, each depending only on the layers below it.

```
+------------------------------------------------------------------+
|                        LAYER 3: GUI                              |
|  App (ctk.CTk)  |  Frames  |  Components  |  Animations  |  Theme |
+------------------------------------------------------------------+
           |                         |
           v                         v
+------------------------------------------------------------------+
|                    LAYER 2: UPDATER CORE                         |
|                                                                  |
|   Sims4Updater (engine)                                          |
|   +------------------+   +------------------+   +-------------+ |
|   |   core/          |   |   patch/         |   |   dlc/      | |
|   | version_detect   |   | manifest         |   | catalog     | |
|   | learned_hashes   |   | client           |   | manager     | |
|   | files            |   | planner          |   | formats     | |
|   | self_update      |   | downloader       |   | downloader  | |
|   | unlocker         |   +------------------+   | packer      | |
|   +------------------+                          | steam       | |
|                                                 +-------------+ |
|   +------------------+   +------------------+   +-------------+ |
|   |   greenluma/     |   |   language/      |   |   mods/     | |
|   | steam            |   | changer          |   | manager     | |
|   | installer        |   | downloader       |   +-------------+ |
|   | applist          |   | packer / steam   |                   |
|   | config_vdf       |   +------------------+                   |
|   | lua_parser       |                                          |
|   | manifest_cache   |                                          |
|   | orchestrator     |                                          |
|   +------------------+                                          |
+------------------------------------------------------------------+
           |
           v
+------------------------------------------------------------------+
|                   LAYER 1: BASE PATCHER ENGINE                   |
|   ../patcher/patcher.py   Patcher, PatchMaker, CallbackType      |
|   ../patcher/myzipfile.py  Custom ZIP with LZMA metadata         |
|   ../patcher/files.py      File I/O utilities                    |
|   ../patcher/exceptions.py NoPatchesDLCsFoundError, etc.         |
+------------------------------------------------------------------+
```

### 3.2 Package Dependency Map

```
sims4_updater.__main__
    └── sims4_updater.gui.app (App / launch)
    └── sims4_updater.updater (Sims4Updater)
            ├── patcher.patcher (BasePatcher, CallbackType)      [external]
            ├── sims4_updater.core.version_detect (VersionDetector)
            ├── sims4_updater.core.learned_hashes (LearnedHashDB)
            ├── sims4_updater.patch.client (PatchClient)
            │       ├── sims4_updater.patch.manifest (parse_manifest)
            │       ├── sims4_updater.patch.planner (plan_update)
            │       └── sims4_updater.patch.downloader (Downloader)
            ├── sims4_updater.dlc.manager (DLCManager)
            │       ├── sims4_updater.dlc.catalog (DLCCatalog)
            │       └── sims4_updater.dlc.formats (detect_format, adapters)
            ├── sims4_updater.dlc.downloader (DLCDownloader)
            └── sims4_updater.config (Settings, get_app_dir)
```

### 3.3 Data Flow at a Glance

```
User clicks "Check for Updates"
        |
        v
HomeFrame._on_check_updates()
        |
        v [background thread via run_async()]
Sims4Updater.check_for_updates()
        |
        +---> VersionDetector.detect(game_dir)
        |          hash_file(sentinel_files) --> VersionDatabase.lookup()
        |
        +---> PatchClient.fetch_manifest()
        |          HTTP GET manifest.json --> parse_manifest()
        |
        +---> plan_update(manifest, current_version)
        |          BFS on patch graph --> UpdatePlan
        |
        v [back to GUI thread via _enqueue_gui()]
HomeFrame._on_updates_checked(UpdateInfo)
        |
        v
User clicks "Update Now"
        |
        v [switches frame]
ProgressFrame.start_update(plan)
        |
        v [background thread]
PatchClient.download_update(plan)
        |   [for each step]
        +---> Downloader.download_file(entry)  [HTTP + resume + MD5]
        |
        v
BasePatcher.patch(selected_dlcs)
        |   [xdelta3 binary diffing + file extraction]
        |
        v
Sims4Updater.learn_version(game_dir, target_version)
        |
        v
DLCManager.auto_toggle(game_dir) / import_states()
        |
        v [GUI thread]
ProgressFrame._on_update_done()
        --> show_toast("Update complete!")
```

---

## 4. Layer 1: Base Patcher Engine

### 4.1 Role and Responsibilities

The base patcher, located at `../patcher/` (a sibling directory to the `sims4-updater/` project root), provides the low-level binary patching infrastructure. It is a standalone package maintained separately and is **not** installed via pip.

Key classes from the base patcher used by Sims 4 Updater:

| Class / Symbol | Responsibility |
|---|---|
| `Patcher` | Base class handling ZIP metadata reading, file extraction, xdelta3 application, crack installation |
| `PatchMaker` | Utility for creating patch archives (used by the separate `patch_maker` CLI tool) |
| `CallbackType` | Enum of progress event types: `HEADER`, `INFO`, `PROGRESS`, `WARNING`, `FAILURE`, `FINISHED` |
| `myzipfile` | Custom ZIP reader/writer supporting LZMA-compressed metadata headers |
| `NoPatchesDLCsFoundError` | Raised when no patch/DLC ZIPs are found in the scan directories |

### 4.2 Integration via sys.path Injection

`updater.py` adds the patcher root to `sys.path` at import time, before any `from patcher...` imports run:

```python
# src/sims4_updater/updater.py
_patcher_root = Path(__file__).resolve().parents[3] / "patcher"
if (
    _patcher_root.is_dir()
    and (_patcher_root / "patcher" / "__init__.py").is_file()
    and str(_patcher_root) not in sys.path
):
    sys.path.insert(0, str(_patcher_root))

from patcher.patcher import Patcher as BasePatcher, CallbackType
```

When the application is frozen by PyInstaller, the patcher source is bundled directly via the `pathex` and `hiddenimports` directives in the `.spec` file. The `sys.path` injection code is still executed but the path may not exist — this is harmless because the frozen modules are already importable.

### 4.3 CallbackType Enum

The callback system allows the backend patching logic to report progress to any frontend (GUI or CLI) without tight coupling. The `Sims4Updater.__init__()` accepts a `callback` parameter and passes it down to `BasePatcher`. The GUI passes `self._enqueue_callback`, which routes events through the thread-safe queue.

```
CallbackType.HEADER    --> Section title (e.g. "Downloading patches")
CallbackType.INFO      --> Per-file status (e.g. "extracting EP01/...")
CallbackType.PROGRESS  --> (bytes_done, bytes_total) numeric progress
CallbackType.WARNING   --> Non-fatal issue
CallbackType.FAILURE   --> File-level failure
CallbackType.FINISHED  --> All done
```

---

## 5. Layer 2: Updater Core

### 5.1 Sims4Updater Engine

**File:** `src/sims4_updater/updater.py`

`Sims4Updater` subclasses `BasePatcher` and is the single orchestrator that ties all subsystems together. It is instantiated once at GUI startup and shared via `App.updater`.

```python
class Sims4Updater(BasePatcher):
    VERSION = 1
    NAME = "Sims4Updater"

    def __init__(self, ask_question, callback=None, settings=None):
        super().__init__(ask_question, callback)
        self.settings = settings or Settings.load()
        self._learned_db = LearnedHashDB()
        self._detector = VersionDetector(learned_db=self._learned_db)
        self._dlc_manager = DLCManager()
        self._patch_client: PatchClient | None = None
        self._dlc_downloader: DLCDownloader | None = None
        self._cancel = threading.Event()
        self._state = UpdateState.IDLE
        self._download_dir = get_app_dir() / "downloads"
```

Key design decisions:

- `_patch_client` and `_dlc_downloader` are lazily instantiated properties — they are not created until first used, keeping startup fast.
- A single `threading.Event` (`_cancel`) is shared with all downloaders. Setting it cancels any in-flight HTTP downloads.
- `exiting_extra()` is the shutdown hook called by `BasePatcher.exiting` — it sets the cancel event, closes the patch client, and saves settings.

The updater overrides three `BasePatcher` methods to adapt the base behavior to the download-dir-centric workflow:

| Override | Purpose |
|---|---|
| `load_all_metadata()` | Scans `downloads/` (not CWD) for patch ZIP files |
| `_get_crack_path()` | Looks for crack archives in `downloads/` subdirectories first |
| `do_after_extraction()` | Logs extraction status instead of deleting archives immediately |

### 5.2 Full Update Pipeline

The `Sims4Updater.update()` method orchestrates the complete end-to-end update:

```
Step 1: Find game directory
        └── Check settings.game_path → _detector.find_game_dir()
                └── Registry → default paths

Step 2: Detect installed version
        └── VersionDetector.detect(game_dir)
                └── hash sentinel files → VersionDatabase.lookup()

Step 3: Check for updates
        └── PatchClient.check_update(current_version)
                └── fetch_manifest() → plan_update()

Step 4: Download patches
        └── PatchClient.download_update(plan)
                └── Downloader.download_file() x N [with resume]

Step 5: Apply patches
        └── BasePatcher.load_all_metadata()
        └── BasePatcher.pick_game()
        └── BasePatcher.check_files_quick()
        └── BasePatcher.patch(selected_dlcs)
                └── xdelta3.exe binary diffing

Step 6: Post-patch finalization
        └── learn_version(game_dir, target_version)
        └── DLCManager.import_states() [restore user toggles]
        └── Enable newly added DLCs
        └── detect_version() to confirm new version
        └── settings.save()
```

DLC states are exported before patching (`export_states`) and restored afterwards (`import_states`) to ensure user-configured DLC enables/disables survive the patch cycle. DLCs that are new in the patch (not present in the saved state) are automatically enabled.

### 5.3 UpdateState Machine

```
IDLE
  └─ detect_version() ──────────────────────────> DETECTING
  └─ check_for_updates() ───────────────────────> CHECKING
  └─ download_update() ─────────────────────────> DOWNLOADING
  └─ patch() ───────────────────────────────────> PATCHING
  └─ learn_version() / import_states() ─────────> FINALIZING
  └─ done ──────────────────────────────────────> DONE

  Any exception in update() ───────────────────> ERROR
```

The state is exposed as `updater.state` and can be checked by the GUI for display purposes, though the GUI primarily relies on callbacks and the `on_done`/`on_error` callback pattern.

### 5.4 Core: Version Detection

**File:** `src/sims4_updater/core/version_detect.py`

Version detection works by hashing a small set of "sentinel files" — stable binary files that change predictably between game versions — and comparing those hashes against a database of known version fingerprints.

**Sentinel files** (defined in `constants.py`):
```python
SENTINEL_FILES = [
    "Game/Bin/TS4_x64.exe",
    "Game/Bin/Default.ini",
    "delta/EP01/version.ini",
]
```

**Detection algorithm:**

```
1. For each sentinel file in VersionDatabase.sentinel_files:
       if file exists: compute MD5 --> local_hashes[sentinel] = md5

2. VersionDatabase.lookup(local_hashes):
       For each (version, fingerprint) in DB:
           matched_count = count of sentinels that match
           if all present sentinels match and matched_count > 0:
               add to matches list

3. Sort matches by matched_count descending
4. Assign confidence:
       1 match --> DEFINITIVE
       multiple matches --> PROBABLE

5. Return DetectionResult(version, confidence, local_hashes, matched_versions)
```

**Database priority (lowest to highest):**

```
Bundled data/version_hashes.json
    < LearnedHashDB (local, user-specific)
        < Manifest fingerprints (fetched from server)
            < Crowd-sourced fingerprints (fetched from fingerprints_url)
```

The merge strategy is additive: new hashes for a version complement existing ones; they do not replace the entire entry.

**Game directory validation:**

Before any detection, `VersionDetector.validate_game_dir()` checks that the required marker paths exist:
```python
SIMS4_INSTALL_MARKERS = [
    "Game/Bin/TS4_x64.exe",
    "Data/Client",
]
```

**Auto-detection order:**

1. `settings.game_path` (if set and valid)
2. Windows Registry: `HKLM\SOFTWARE\Maxis\The Sims 4` and `HKLM\SOFTWARE\WOW6432Node\Maxis\The Sims 4` — `Install Dir` value
3. Hard-coded default paths: `C:\Program Files\EA Games\The Sims 4`, etc.

### 5.5 Core: Learned Hash Database

**File:** `src/sims4_updater/core/learned_hashes.py`

`LearnedHashDB` is a writable JSON store that accumulates version fingerprints over time. It lives at:

```
%LOCALAPPDATA%\ToastyToast25\sims4_updater\learned_hashes.json
```

Structure of the JSON file:

```json
{
  "sentinel_files": ["Game/Bin/TS4_x64.exe", "Game/Bin/Default.ini"],
  "versions": {
    "1.120.xxx.1020": {
      "Game/Bin/TS4_x64.exe": "ABCDEF1234...",
      "Game/Bin/Default.ini": "FEDCBA9876..."
    }
  },
  "updated": 1708000000
}
```

Writes are deferred via a `_dirty` flag and use atomic rename (`os.replace(tmp, path)`) to prevent corruption on crash.

Sources that feed `LearnedHashDB`:

| Source | Mechanism |
|---|---|
| Successful patch | `Sims4Updater.learn_version()` called post-patch |
| Manifest `fingerprints` field | `PatchClient.fetch_manifest()` calls `learned_db.merge()` |
| Crowd-sourced `fingerprints_url` | `PatchClient._fetch_crowd_fingerprints()` |
| Manual CLI | `sims4-updater learn <game_dir> <version>` |

### 5.6 Core: File Utilities

**File:** `src/sims4_updater/core/files.py`

Utility functions shared with the base patcher layer:

| Function | Description |
|---|---|
| `hash_file(path, chunk_size, progress)` | MD5 of a file in 64 KB chunks; returns uppercase hex string |
| `write_check(path)` | Verifies write permission by creating and deleting a temp file |
| `get_short_path(long_path)` | Converts a path with non-ASCII characters to Windows 8.3 short name (Windows only, via `win32file`) |
| `get_files_dict(folder_path)` | Recursively builds `{relative_path: stat}` dict for a directory tree |
| `get_files_set(folder_path)` | Set version of `get_files_dict` |
| `copyfileobj(fsrc, fdst, progress)` | Buffered file copy with progress callback |
| `delete_empty_dirs(src_dir)` | Removes empty directories after file extraction |

### 5.7 Core: Self-Update

**File:** `src/sims4_updater/core/self_update.py`

The updater can update itself by checking GitHub Releases and replacing its own executable.

**GitHub constants:**
```python
GITHUB_REPO = "ToastyToast25/sims4-updater"
GITHUB_API = "https://api.github.com/repos/ToastyToast25/sims4-updater/releases/latest"
EXE_ASSET_NAME = "Sims4Updater.exe"
```

**Three-phase self-update flow:**

**Phase 1 — Check (`check_for_app_update`):**
Queries the GitHub API for the latest release tag. Compares it against the running `VERSION` string using integer tuple comparison. Returns `AppUpdateInfo` with `update_available`, `download_url`, and `download_size`.

**Phase 2 — Download (`download_app_update`):**
Streams the new exe to `%LOCALAPPDATA%\ToastyToast25\sims4_updater\updates\Sims4Updater_vX.Y.Z.exe`. Verifies the final file size matches the `Content-Length` header and performs a minimum size sanity check (must be > 5 MB, since PyInstaller exes are typically > 10 MB).

**Phase 3 — Apply (`apply_app_update`):**
The currently running process cannot replace its own exe on Windows while it is open. The solution is a two-script approach:

1. A batch script (`_self_update.bat`) is written to the updates directory. It:
   - Waits for the updater process (by PID) to exit with a 60-second timeout
   - Kills the PyInstaller bootloader parent process
   - Validates the downloaded exe (exists, size, MZ PE header via PowerShell)
   - Renames the current exe to `_old`
   - Moves the new exe into place with up to 30 retries for AV-locked files
   - Pre-scans the exe with PowerShell to trigger Windows Defender caching
   - Relaunches via `explorer.exe` to ensure it starts in the user session
   - Falls back to `start ""` if the primary launch fails
   - On failure, restores the old exe

2. A VBScript wrapper (`_self_update.vbs`) launches the batch with a hidden console window (`CreateObject("Wscript.Shell").Run ..., 0, False`).

`wscript.exe` launches the VBScript, then the Python process calls `os._exit(0)` to terminate without triggering the PyInstaller cleanup dialog.

### 5.8 Core: DLC Unlocker

**File:** `src/sims4_updater/core/unlocker.py`

Installs the PandaDLL (`version.dll`) into the EA Desktop client directory to enable entitlement spoofing. Requires administrator privileges.

**Detection:** Reads `HKLM\SOFTWARE\Electronic Arts\EA Desktop` then `ClientPath` registry value.

**Installation steps:**

1. Check for admin rights (`ctypes.windll.shell32.IsUserAnAdmin()`)
2. Detect EA Desktop client path from registry
3. Force-stop EA Desktop processes (`EADesktop.exe`, `EABackgroundService.exe`, `EALocalHostSvc.exe`)
4. Remove old unlocker files (`version_o.dll`, `winhttp.dll`, `w_*.ini`)
5. Copy `entitlements.ini` to `%APPDATA%\ToastyToast25\EA DLC Unlocker\`
6. Copy `version.dll` to the EA Desktop client directory (retries 3 times on `PermissionError`)
7. If a `StagedEADesktop` directory exists, copy `version.dll` there too
8. Create a Windows Scheduled Task (`copy_dlc_unlocker`) that xcopy's `version.dll` to the staged directory on login
9. Disable background standalone mode by appending `machine.bgsstandaloneenabled=0` to `%PROGRAMDATA%\EA Desktop\machine.ini`

**Uninstallation** reverses these steps: removes `version.dll`, deletes the entitlements config directory, and deletes the scheduled task.

### 5.9 Patch: Manifest

**File:** `src/sims4_updater/patch/manifest.py`

The manifest is a JSON file hosted at a user-configured URL. It describes all available patch steps and downloadable DLC archives. The design deliberately decouples the updater from any specific hosting backend.

**Manifest JSON structure:**

```json
{
  "latest": "1.120.xxx.1020",
  "game_latest": "1.121.yyy.1020",
  "game_latest_date": "2026-01-15",
  "report_url": "https://example.com/api/report-hashes",
  "fingerprints_url": "https://example.com/api/fingerprints",
  "fingerprints": {
    "1.120.xxx.1020": {
      "Game/Bin/TS4_x64.exe": "ABCDEF..."
    }
  },
  "patches": [
    {
      "from": "1.118.xxx.1020",
      "to":   "1.119.xxx.1020",
      "files": [
        { "url": "https://...", "size": 123456789, "md5": "ABCDEF..." }
      ],
      "crack": { "url": "https://...", "size": 1234, "md5": "..." }
    }
  ],
  "new_dlcs": [
    { "id": "EP18", "name": "Businesses & Hobbies", "status": "pending" }
  ],
  "dlc_catalog": [
    {
      "id": "EP18",
      "code": "SIMS4.OFF.SOLP.0x...",
      "type": "expansion",
      "names": { "en_us": "For Rent", "de_de": "Zur Miete" }
    }
  ],
  "dlc_downloads": {
    "EP01": {
      "url": "https://...",
      "size": 987654321,
      "md5": "FEDCBA...",
      "filename": "Sims4_DLC_EP01_World_Adventures.zip"
    }
  }
}
```

**Key fields:**

| Field | Purpose |
|---|---|
| `latest` | The latest patchable version (what `plan_update` targets by default) |
| `game_latest` | The actual EA release version (may be ahead of `latest` if patch not yet made) |
| `patches` | List of `from -> to` patch steps |
| `fingerprints` | Server-provided version hashes to merge into `LearnedHashDB` |
| `fingerprints_url` | URL for crowd-sourced hash contributions |
| `report_url` | POST endpoint for reporting newly-learned hashes |
| `new_dlcs` | Announced but not yet patchable DLCs (for UI notification) |
| `dlc_catalog` | Remote catalog additions merged into `DLCCatalog` |
| `dlc_downloads` | Per-DLC download entries for individual DLC acquisition |

**Dataclass hierarchy:**

```
Manifest
  ├── patches: list[PatchEntry]
  │       ├── version_from, version_to
  │       ├── files: list[FileEntry]
  │       └── crack: FileEntry | None
  ├── fingerprints: dict[version, dict[sentinel, md5]]
  ├── new_dlcs: list[PendingDLC]
  ├── dlc_catalog: list[ManifestDLC]
  └── dlc_downloads: dict[dlc_id, DLCDownloadEntry]
```

`patch_pending` is a computed property: `bool(game_latest and game_latest != latest)`. It signals to the UI that a newer EA release exists but no patch for it is available yet.

### 5.10 Patch: Client

**File:** `src/sims4_updater/patch/client.py`

`PatchClient` is the high-level coordinator for the patch subsystem. It caches the parsed manifest in-memory across calls within the same session.

```python
class PatchClient:
    def __init__(self, manifest_url, download_dir, cancel_event, learned_db, dlc_catalog):
        ...

    def fetch_manifest(self, force=False) -> Manifest: ...
    def check_update(self, current_version, target_version=None) -> UpdateInfo: ...
    def download_update(self, plan, progress, status) -> list[list[DownloadResult]]: ...
    def report_hashes(self, version, hashes, report_url=None): ...
    def get_downloaded_files(self, plan) -> list[Path]: ...
    def close(): ...
```

`check_update()` handles three distinct cases:

1. `current_version == game_latest` — user is at the actual latest EA release; no update available, no patch pending.
2. `current_version == latest` (patchable) — user is at the latest patchable version; `patch_pending` may be True if `game_latest` is newer.
3. Otherwise — compute update path via `plan_update()`.

`download_update()` downloads all files for all steps in the plan sequentially, accumulating a grand total byte count for a unified progress callback across multi-step updates.

`report_hashes()` is fire-and-forget: it spawns a daemon thread to POST learned hashes to the server's `report_url`. The thread completes independently; errors are silently swallowed.

`format_size()` is a module-level utility function that formats byte counts as human-readable strings (`"12.5 MB"`, `"1.02 GB"`, etc.).

### 5.11 Patch: Planner

**File:** `src/sims4_updater/patch/planner.py`

`plan_update()` treats the manifest's patch list as a directed graph and finds the best path from the current version to the target version.

**Algorithm:**

1. Build an adjacency list: `{version_from: [PatchEntry, ...]}`.
2. Run a modified BFS (`_bfs_all_shortest`) that finds **all** shortest paths (fewest steps) simultaneously, pruning paths longer than the shortest found.
3. Among all shortest-length paths, select the one with the **smallest total download size**.
4. Wrap the selected path in `UpdateStep` objects with step numbering.

This strategy ensures users skip unnecessary intermediate versions when jump patches are available, and prefers smaller downloads when multiple equally-short paths exist.

```python
@dataclass
class UpdatePlan:
    current_version: str
    target_version: str
    steps: list[UpdateStep]

    total_download_size: int  # computed property
    step_count: int           # computed property
    is_up_to_date: bool       # computed property
```

`NoUpdatePathError` is raised if no path exists in the graph from `current_version` to `target_version`. This happens when the user's version is not covered by the available patches.

### 5.12 Patch: Downloader

**File:** `src/sims4_updater/patch/downloader.py`

`Downloader` handles all HTTP file transfers with production-quality reliability:

**Resume support:** If a `.partial` file exists from a previous interrupted download, the `Range: bytes=N-` header is sent to resume. HTTP 206 Partial Content is handled correctly; HTTP 200 (server does not support Range) triggers a fresh full download.

**MD5 verification:** If the `FileEntry.md5` field is non-empty, the downloaded file is verified before being renamed from `.partial` to final. A mismatch raises `IntegrityError` and deletes the corrupt file.

**Cancellation:** The `cancel_event` is checked between chunks (every 64 KB). A cancelled download raises `DownloadError("Download cancelled.")`.

**Session configuration:**

```python
def _create_session() -> requests.Session:
    # Custom SSL context with OP_LEGACY_SERVER_CONNECT for older CDN servers
    # Retry adapter: 5 total attempts, exponential backoff
    # Retries on: 429, 500, 502, 503, 504
    # User-Agent: "Sims4Updater/2.0"
    # Custom SSL adapter with default timeouts: connect=30s, read=60s
```

**Constants:**

```python
CHUNK_SIZE = 65536      # 64 KB read chunks
CONNECT_TIMEOUT = 30    # seconds
READ_TIMEOUT = 60       # seconds
```

### 5.13 DLC: Catalog

**File:** `src/sims4_updater/dlc/catalog.py`

`DLCCatalog` is the master database of all known Sims 4 DLCs. It loads from two sources:

1. **Bundled:** `data/dlc_catalog.json` — included in the exe and updated with each release.
2. **Custom:** `%LOCALAPPDATA%\ToastyToast25\sims4_updater\custom_dlcs.json` — DLCs added via `merge_remote()` from manifest `dlc_catalog` entries.

```python
@dataclass
class DLCInfo:
    id: str           # "EP01", "GP03", "SP15", "KIT01", etc.
    code: str         # "SIMS4.OFF.SOLP.0x0000000000011AC5"
    code2: str        # alternative code (some DLCs have two)
    pack_type: str    # "expansion", "game_pack", "stuff_pack", "kit", "free_pack"
    names: dict       # {"en_us": "World Adventures", "de_de": "Weltabenteuer"}
    description: str
    steam_app_id: int | None
```

`DLCStatus` (returned by `DLCManager.get_dlc_states()`) enriches `DLCInfo` with runtime state:

```python
@dataclass
class DLCStatus:
    dlc: DLCInfo
    installed: bool   # DLC ID folder exists in game_dir
    complete: bool    # SimulationFullBuild0.package present
    registered: bool  # has entry in crack config
    enabled: bool | None  # enabled in crack config; None if not registered
    owned: bool       # installed AND not registered (legitimately purchased)
    file_count: int   # number of files in DLC folder
```

The `status_label` property returns a human-readable string: `"Owned"`, `"Patched"`, `"Patched (disabled)"`, `"Missing files"`, `"Incomplete"`, or `"Not installed"`.

**Pack type taxonomy:**

| Code | Type | Description |
|---|---|---|
| EP__ | expansion | Full expansion packs |
| GP__ | game_pack | Game packs (smaller than EPs) |
| SP__ | stuff_pack | Stuff packs |
| KIT__ | kit | Mini content kits |
| FP__ | free_pack | Free for all players |

### 5.14 DLC: Manager

**File:** `src/sims4_updater/dlc/manager.py`

`DLCManager` is the unified facade for all DLC state operations. It auto-detects the crack config format and delegates read/write operations to the appropriate `DLCConfigAdapter`.

```python
class DLCManager:
    def get_dlc_states(game_dir, locale) -> list[DLCStatus]
    def apply_changes(game_dir, enabled_dlcs: set[str]) -> None
    def auto_toggle(game_dir) -> dict[str, bool]
    def export_states(game_dir) -> dict[str, bool]
    def import_states(game_dir, saved_states: dict[str, bool]) -> None
```

`apply_changes()` writes the enabled set to the crack config and mirrors the result to `Bin_LE\RldOrigin.ini` if that directory exists (required for the 32-bit game variant).

`auto_toggle()` computes the desired state from disk reality: installed DLCs are enabled, missing ones are disabled. It returns only the entries that actually changed.

`export_states` / `import_states` are used during patching to preserve user customizations across the update cycle.

### 5.15 DLC: Formats (Crack Config Adapters)

**File:** `src/sims4_updater/dlc/formats.py`

Five crack config formats are supported. All implement the `DLCConfigAdapter` abstract base:

```python
class DLCConfigAdapter(ABC):
    def detect(self, game_dir: Path) -> bool
    def get_config_path(self, game_dir: Path) -> Path | None
    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]
    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str
    def get_format_name(self) -> str
    def get_encoding(self) -> str
```

**Format implementations:**

| Class | Config File | Detection Marker | Enabled Indicator | Disabled Indicator |
|---|---|---|---|---|
| `RldOriginAdapter` | `Game/Bin/RldOrigin.ini` | File exists | No `;` prefix | `;IIDxx=code` |
| `CodexAdapter` | `Game/Bin/codex.cfg` | File exists | `Group "THESIMS4PC"` | `Group "_"` |
| `RuneAdapter` | `Game/Bin/rune.ini` | File exists | `[CODE]` | `[CODE_]` |
| `AnadiusSimpleAdapter` | `Game/Bin/anadius.cfg` | File exists + no `"Config2"` | No `//` prefix | `//code` |
| `AnadiusCodexAdapter` | `Game/Bin/anadius.cfg` | File exists + has `"Config2"` | Same as CODEX | Same as CODEX |

Both `Game/Bin/` and `Game-cracked/Bin/` variants are checked for each format.

**Detection order** (`ALL_ADAPTERS` list, checked first to last):

```python
ALL_ADAPTERS = [
    AnadiusCodexAdapter(),  # checked first -- must distinguish from AnadiusSimple
    AnadiusSimpleAdapter(),
    RuneAdapter(),
    CodexAdapter(),
    RldOriginAdapter(),     # checked last -- most common
]
```

`detect_format(game_dir)` iterates this list and returns the first adapter that reports `detect() == True`. Only one format is expected to be active in any given game installation.

All state mutations operate on the **full config file content as a string** using regular expressions. The modified string is written back atomically. This approach avoids INI parser libraries and is resilient to non-standard formatting.

### 5.16 DLC: Downloader

**File:** `src/sims4_updater/dlc/downloader.py`

`DLCDownloader` runs each DLC through a three-phase pipeline:

```
Phase 1: DOWNLOADING
    DLCDownloadEntry.to_file_entry() -> FileEntry
    Downloader.download_file(file_entry) -> DownloadResult

Phase 2: EXTRACTING
    zipfile.ZipFile(archive_path).extractall()
    Path traversal protection: verify target is under game_dir
    Validate: game_dir/dlc_id/SimulationFullBuild0.package must exist

Phase 3: REGISTERING
    DLCManager.get_dlc_states() -> collect currently-enabled set
    Add new dlc_id to enabled_set
    DLCManager.apply_changes(game_dir, enabled_set)
```

The `DLCDownloadState` enum tracks task progress: `PENDING -> DOWNLOADING -> EXTRACTING -> REGISTERING -> COMPLETED` (or `FAILED` / `CANCELLED` on error).

Registration failure is non-fatal — the DLC files are on disk and can be manually registered via "Apply Changes" in the DLC tab. The task still reports `COMPLETED` but with an informational message.

`download_multiple()` runs DLCs sequentially but continues to the next DLC on individual failure (does not abort the entire queue).

### 5.17 DLC: Packer

**File:** `src/sims4_updater/dlc/packer.py`

`DLCPacker` creates redistribution-ready ZIP archives from installed DLC folders.

**Pack layout:**

For DLC `EP01`, the ZIP contains:
```
EP01/                          (all files from game_dir/EP01/)
__Installer/DLC/EP01/          (installer metadata, if present)
```

Paths inside the ZIP use forward slashes for cross-platform compatibility.

**File naming convention:**
```
Sims4_DLC_{ID}_{SafeName}.zip
# e.g. Sims4_DLC_EP01_World_Adventures.zip
```

Non-ASCII and special characters are stripped from the name; spaces become underscores.

**Manifest generation** (`generate_manifest()`) produces a JSON file suitable for insertion into the server manifest's `dlc_downloads` section:

```json
{
  "EP01": {
    "url": "<UPLOAD_URL>/Sims4_DLC_EP01_World_Adventures.zip",
    "size": 987654321,
    "md5": "ABCDEF...",
    "filename": "Sims4_DLC_EP01_World_Adventures.zip"
  }
}
```

`import_archive()` extracts ZIP or RAR archives into the game directory:
- **ZIP:** Uses Python's `zipfile` with path traversal protection.
- **RAR:** Shells out to the bundled `unrar.exe` (`-p-` no password, `-o+` overwrite).

After extraction, `_detect_dlc_dirs()` scans for newly present DLC ID folders and returns the list of found DLC IDs.

### 5.18 DLC: Steam Price Service

**File:** `src/sims4_updater/dlc/steam.py`

`SteamPriceCache` and `fetch_prices_batch()` provide optional Steam pricing display in the Home frame.

**API endpoint:** `https://store.steampowered.com/api/appdetails?appids={id}&cc=US&filters=price_overview`

**Concurrency:** Up to 8 simultaneous workers (`ThreadPoolExecutor(max_workers=8)`). Steam allows approximately 200 requests per 5 minutes, so batching all ~109 DLC lookups completes in roughly 3 seconds.

**Cache TTL:** 30 minutes (`CACHE_TTL_SECONDS = 1800`). The cache is in-memory only; it resets on application restart.

```python
@dataclass
class SteamPrice:
    app_id: int
    currency: str          # "USD"
    initial_cents: int     # original price in cents
    final_cents: int       # current price in cents (same as initial if not on sale)
    discount_percent: int  # 0-100
    initial_formatted: str # "$29.99"
    final_formatted: str   # "$14.99"
    is_free: bool

    on_sale: bool          # computed: discount_percent > 0
    store_url: str         # computed: Steam store URL
```

### 5.19 Language Changer

**File:** `src/sims4_updater/language/changer.py`

18 language codes are supported (matching EA's Sims 4 locale strings):

```python
LANGUAGES = {
    "cs_CZ": "Cestina", "da_DK": "Dansk",   "de_DE": "Deutsch",
    "en_US": "English", "es_ES": "Espanol",  "fr_FR": "Francais",
    "it_IT": "Italiano","nl_NL": "Nederlands","no_NO": "Norsk",
    "pl_PL": "Polski",  "pt_BR": "Portugues (Brasil)", "fi_FI": "Suomi",
    "sv_SE": "Svenska", "ru_RU": "Russky",   "ja_JP": "Japanese",
    "zh_TW": "Traditional Chinese",  "zh_CN": "Simplified Chinese",
    "ko_KR": "Korean",
}
```

`get_current_language()` reads `HKLM\SOFTWARE\Maxis\The Sims 4` then the `Locale` value. Returns `"en_US"` if not found or not on Windows.

`set_language(language_code, game_dir)`:
1. Writes `Locale` to the registry in both 32-bit and 64-bit views.
2. If `game_dir` is provided, updates `Language = <code>` in all `RldOrigin.ini` variants found in `Game/Bin/`, `Game-cracked/Bin/`, `Game/Bin_LE/`, and `Game-cracked/Bin_LE/`.

### 5.20 GreenLuma Package

**Directory:** `src/sims4_updater/greenluma/`

The `greenluma/` package provides all backend logic for integrating with GreenLuma 2025, the Steam-compatible DLC unlocking tool. It is a self-contained sub-package with no dependencies on the patching or DLC-toggling subsystems. The GUI (`GreenLumaFrame`) is the only consumer of these modules; all six modules can also be used independently via the CLI or tests.

#### greenluma/steam.py

Responsible for locating the Steam installation and gathering GreenLuma presence information into a single `SteamInfo` dataclass.

```python
@dataclass
class SteamInfo:
    steam_path: Path
    applist_dir: Path         # steam_path / "AppList"
    config_vdf_path: Path     # steam_path / "config" / "config.vdf"
    depotcache_dir: Path      # steam_path / "depotcache"
    steamapps_dir: Path       # steam_path / "steamapps"
    greenluma_installed: bool
    greenluma_mode: str       # "normal" | "stealth" | "none"
```

`detect_steam_path()` checks the Windows registry (`SOFTWARE\Valve\Steam`, both 64-bit and 32-bit views) and then falls back to a list of hard-coded common paths (`C:\Program Files (x86)\Steam`, etc.), returning the first directory that contains `steam.exe`.

GreenLuma presence is detected by checking for the DLL files `GreenLuma_2025_x64.dll` and `GreenLuma_2025_x86.dll` in the Steam directory. Stealth mode is distinguished from normal mode by the absence of the standard `DLLInjector.exe` entry point.

`is_steam_running()` enumerates running processes via `tasklist` subprocess output and returns `True` if any `steam.exe` process is found. This guard is checked before any mutation of Steam configuration files.

#### greenluma/applist.py

Manages GreenLuma's `AppList/` directory, which contains one numbered text file per registered Steam App/Depot ID (e.g., `0.txt` contains `"1222670"`).

```python
@dataclass
class AppListState:
    entries: dict[str, str]           # filename -> app_id ("0.txt" -> "1222670")
    unique_ids: set[str]              # deduplicated set of all IDs
    count: int                        # total file count
    duplicates: list[tuple[str, str]] # (filename, duplicate_id) pairs
```

**Public API:**

| Function | Description |
|---|---|
| `read_applist(applist_dir)` | Parse all `N.txt` files into an `AppListState` |
| `write_applist(applist_dir, ids)` | Write a set of IDs as consecutively numbered files |
| `backup_applist(applist_dir)` | Copy the directory to `AppList_backup_YYYYMMDD_HHMMSS/` |
| `add_ids(applist_dir, new_ids)` | Add IDs not already present; returns count added |
| `remove_ids(applist_dir, ids_to_remove)` | Remove specific IDs and renumber remaining files |

The hard limit `APPLIST_LIMIT = 130` enforces GreenLuma's maximum supported entry count. `add_ids()` raises `ValueError` if adding the requested IDs would exceed this limit.

#### greenluma/config_vdf.py

Parses and mutates Steam's `config/config.vdf` file to read and write per-depot decryption keys. The VDF format uses brace-depth nesting with quoted string keys and values.

```python
@dataclass
class VdfKeyState:
    keys: dict[str, str]  # depot_id -> hex_key
    total_keys: int
```

The parser locates the `"depots"` block using a brace-depth counter (`_find_depots_section()`), validates balanced braces before writing (`_validate_braces()`), and uses regex substitution to insert or update individual depot key entries. Backups (`config_backup_YYYYMMDD_HHMMSS.vdf`) are written before any mutation when `greenluma_auto_backup` is `True`.

All writes are guarded by a `is_steam_running()` check — writing `config.vdf` while Steam is open risks Steam overwriting the changes on exit.

#### greenluma/lua_parser.py

Parses GreenLuma/SteamTools LUA manifest files that declare app IDs, depot decryption keys, and manifest IDs via two LUA function calls:

- `addappid(ID, FLAGS, "HEX_KEY")` — registers an App or Depot ID with a 64-character hex decryption key
- `addappid(ID)` / `addappid(ID, FLAGS)` — registers an ID without a key
- `setManifestid(DEPOT_ID, "MANIFEST_ID")` — pins a specific depot manifest version

```python
@dataclass
class DepotEntry:
    depot_id: str
    decryption_key: str  # 64-char hex string, empty if none
    manifest_id: str     # large numeric string, empty if none

@dataclass
class LuaManifest:
    app_id: str                          # first addappid = base game
    entries: dict[str, DepotEntry]       # depot_id -> DepotEntry
    all_app_ids: list[str]               # all IDs in declaration order
```

`parse_lua_file(path)` reads the file, applies the three compiled regex patterns, and assembles the `LuaManifest`. It is tolerant of comments, whitespace variations, and mixed `addappid`/`setManifestid` ordering. The `keys_count` and `manifests_count` computed properties give quick summary statistics.

#### greenluma/manifest_cache.py

Manages binary `.manifest` files in Steam's `depotcache/` directory. These files are named `{depot_id}_{manifest_id}.manifest` and are required for Steam to recognize specific depot versions without downloading them. The module does not parse binary content — it copies and verifies files by name only.

```python
@dataclass
class ManifestState:
    files: dict[str, str]  # depot_id -> full filename
    depot_ids: set[str]    # set of all depot IDs present
    total_count: int
```

**Public API:**

| Function | Description |
|---|---|
| `read_manifest_state(depotcache_dir)` | Scan directory and return `ManifestState` |
| `copy_manifests(src_dir, depotcache_dir, depot_ids)` | Copy matching `.manifest` files from a source directory |
| `get_manifest_filename(depot_id, manifest_id)` | Canonical filename for a depot/manifest pair |
| `has_manifest(depotcache_dir, depot_id)` | Check whether a depot's manifest is present |

#### greenluma/installer.py

Manages GreenLuma installation and launch lifecycle. GreenLuma is distributed as a 7z archive and extracted into the Steam root directory.

**Install flow (`install_greenluma(archive_path, steam_path, stealth)`):**

1. Confirm Steam is not running (`is_steam_running()`)
2. Extract the 7z archive using the `7z` command-line tool
3. Copy extracted files to the Steam root directory
4. Record installed file paths in an install manifest (`greenluma_install.json`) saved to the app data directory
5. In stealth mode, the `DLLInjector.exe` entry point is omitted and only the core DLLs are installed

**Uninstall flow (`uninstall_greenluma(steam_path)`):**

1. Load the install manifest to determine exactly which files were installed
2. Delete those files from the Steam directory
3. Remove the install manifest
4. Gracefully handle missing files (already deleted by the user)

**Launch (`launch_via_greenluma(steam_path)`):**

Spawns `DLLInjector.exe` as a detached subprocess. Steam is not pre-started — the injector handles that. Returns immediately; the caller is responsible for monitoring the process if needed.

`kill_steam(timeout)` terminates all `steam.exe` processes via `taskkill /F /IM steam.exe` and waits for up to `timeout` seconds for them to exit.

#### greenluma/orchestrator.py

The high-level facade that combines all five modules into coherent operations for the GUI. All methods are designed to be called from a background thread and return result dataclasses that can be safely handed back to the GUI thread.

```python
@dataclass
class DLCReadiness:
    dlc_id: str
    name: str
    steam_app_id: int
    in_applist: bool
    has_key: bool
    has_manifest: bool

    @property
    def ready(self) -> bool:
        return self.in_applist and self.has_key and self.has_manifest

@dataclass
class ApplyResult:
    keys_added: int
    keys_updated: int
    manifests_copied: int
    manifests_skipped: int
    applist_entries_added: int
    lua_total_keys: int
    lua_total_manifests: int
    errors: list[str]

@dataclass
class VerifyResult:
    # Cross-reference report of AppList, config.vdf, and depotcache consistency
    ...
```

**Operations:**

`check_readiness(steam_info, catalog)` — For each DLC in the catalog that has a `steam_app_id`, checks whether the ID appears in the AppList, whether a decryption key is present in `config.vdf`, and whether a `.manifest` file exists in `depotcache/`. Returns a `list[DLCReadiness]` sorted by ready status.

`apply_lua(lua_path, steam_info, manifest_src_dir, log)` — The primary user-facing operation. Parses the LUA file, optionally backs up AppList and `config.vdf`, writes all depot keys into `config.vdf`, copies matching `.manifest` files from `manifest_src_dir` into `depotcache/`, and adds all app IDs to the AppList. Returns `ApplyResult` with counts of each action taken and any non-fatal errors.

`verify(lua_path, steam_info)` — Parses the LUA file and cross-references its declared depot IDs against the current AppList, `config.vdf`, and `depotcache/`. Returns a `VerifyResult` detailing any discrepancies.

`fix_applist(steam_info, catalog)` — Reads the AppList, removes duplicates, and adds any DLC Steam App IDs from the catalog that are missing. Returns `(added_count, removed_duplicates_count)`.

---

## 6. Layer 3: GUI

### 6.1 App Class and Window Structure

**File:** `src/sims4_updater/gui/app.py`

```
App(ctk.CTk)                     [900 x 600, min 750 x 500]
├── Sidebar (column 0, fixed 180px wide)
│     ├── Logo label "TS4 Updater"
│     ├── Separator
│     ├── Nav buttons x 5 (Home, DLCs, DLC Packer, Unlocker, Settings)
│     │     Each: [3px indicator frame | CTkButton]
│     ├── Spacer (expands)
│     ├── Separator
│     └── Footer (version, copyright, GitHub link)
│
└── Content area (column 1, expands)
      └── _content (CTkFrame, transparent)
            └── All frames gridded to row=0, col=0
                  HomeFrame
                  DLCFrame
                  PackerFrame
                  UnlockerFrame
                  SettingsFrame
                  ProgressFrame    <-- no nav button, shown programmatically
```

**Initialization sequence:**

```
App.__init__()
  1. Window geometry + icon (PNG via wm_iconphoto, subsampled 1024 to 32)
  2. ctk.set_appearance_mode("dark")
  3. Create Animator, toast state
  4. Create ThreadPoolExecutor(max_workers=1)
  5. Create callback deque
  6. Load Settings
  7. Create SteamPriceCache
  8. Create Sims4Updater(ask_question, callback, settings)
  9. _build_sidebar()
  10. _build_content_area()
  11. _create_frames()          <-- all 6 frames instantiated here
  12. _show_frame("home")      <-- first frame shown
  13. after(100, _poll_callbacks)
  14. protocol("WM_DELETE_WINDOW", _on_close)
  15. after(200, _on_startup)   <-- trigger HomeFrame.refresh() on next tick
```

### 6.2 Threading Model

The GUI runs on the main thread (required by tkinter). All blocking operations — version detection, HTTP downloads, patch application — run in a background thread. A deque-based callback queue bridges the two.

```
Main Thread (tkinter event loop)
        |
        |  run_async(func, *args, on_done, on_error)
        |        |
        |        v
        |  ThreadPoolExecutor.submit(wrapper)
        |        |
        |        v                     Background Thread
        |                              func(*args) executes
        |                              result = func()
        |                                   |
        |                              _enqueue_gui(on_done, result)
        |                                   |
        |  _poll_callbacks()  <-------------+
        |  (every 100ms via .after)
        |        |
        |        v
        |  on_done(result)  <-- runs on main thread
```

**Key thread primitives:**

| Component | Type | Purpose |
|---|---|---|
| `_executor` | `ThreadPoolExecutor(max_workers=1)` | Serializes all background jobs |
| `_callback_queue` | `collections.deque` | Thread-safe FIFO for GUI callbacks |
| `_poll_callbacks()` | `after(100, ...)` loop | Drains the queue on the main thread |
| `_cancel` | `threading.Event` | Signals all downloaders to abort |
| DLC download thread | `threading.Thread(daemon=True)` | Runs DLC downloads outside the executor |

The single-worker executor prevents concurrent operations (e.g., two simultaneous update checks). DLC downloads are launched as separate daemon threads rather than executor jobs so they do not block a potential game update check from being submitted.

**Two callback entry points in the queue:**

```python
# For GUI functions: enqueue a callable + args
_callback_queue.append(("gui", func, args))

# For patcher callbacks: enqueue CallbackType events
_callback_queue.append(("patcher", args, kwargs))
```

`_poll_callbacks()` dispatches "gui" items directly and routes "patcher" items to `ProgressFrame.handle_callback()`.

**Public threading API for frame authors:**

```python
# Run func in background; call on_done(result) or on_error(exc) on main thread
self.app.run_async(func, *args, on_done=..., on_error=...)

# Schedule a callable on the main thread from a background thread
self.app._enqueue_gui(func, *args)

# Show a toast notification (must be called from main thread)
self.app.show_toast(message, style="success")  # style: success/warning/error/info
```

### 6.3 Frame Lifecycle and Navigation

All frames are instantiated at startup in `_create_frames()` and all placed at grid position `(row=0, col=0)` in the content area. Only the topmost frame is visible at any time.

```python
# Startup
self._frames["home"] = HomeFrame(self._content, self)
self._frames["dlc"] = DLCFrame(self._content, self)
# ...
for frame in self._frames.values():
    frame.grid(row=0, column=0, sticky="nsew")
```

**Navigation flow:**

1. User clicks a sidebar button — `_show_frame(name)` is called.
2. Nav button colors update: active = `accent` fg + `accent` indicator bar; inactive = transparent + muted text.
3. If this is the first navigation (no previous frame), the new frame is raised immediately.
4. Otherwise, a slide transition animation plays (see Section 6.4).
5. After the animation completes, `frame.on_show()` is called on the new frame.

`on_show()` is the frame's lifecycle hook for loading or refreshing data. It is called every time the frame becomes visible, not just on first show.

The `_transitioning` flag prevents navigation while an animation is in progress, avoiding visual glitches from concurrent transitions.

### 6.4 Slide Transition Animation

When switching frames, the new frame slides in from the right:

```
1. frame.place(x=content_w, y=0, relwidth=1.0, relheight=1.0)
   -- New frame positioned off-screen to the right

2. Animator.animate(frame, ANIM_NORMAL=250ms, easing=ease_out_cubic)
   on_tick: frame.place(x=int(content_w * (1-t)), ...)
   -- Each tick moves frame left by eased increment

3. on_done (finalize):
   frame.place_forget()
   frame.grid(row=0, column=0, sticky="nsew")
   frame.tkraise()
   frame.on_show()
   _transitioning = False
```

A safety timer `after(ANIM_NORMAL + 500, finalize)` force-finalizes in case the animation callback does not fire (e.g., widget destruction).

### 6.5 Theme System

**File:** `src/sims4_updater/gui/theme.py`

All visual constants are centralized. Color names are semantic rather than literal:

```python
COLORS = {
    # Backgrounds (dark blue palette)
    "bg_dark":     "#1a1a2e",   # Main window background
    "bg_sidebar":  "#16213e",   # Sidebar background
    "bg_card":     "#0f3460",   # Card/panel background
    "bg_card_alt": "#0a2a50",   # Alternate card background
    "bg_deeper":   "#0d1526",   # Deeper depth level
    "bg_surface":  "#1a2744",   # Surface elements

    # Accent colors
    "accent":         "#e94560",  # Primary action color (red-pink)
    "accent_hover":   "#ff6b81",  # Hover state
    "accent_glow":    "#e94560",  # Glow effect color
    "accent_subtle":  "#2a1a2e",  # Muted accent background

    # Status colors
    "success": "#2ed573",   # Green
    "warning": "#ffa502",   # Orange
    "error":   "#ff4757",   # Red

    # Text
    "text":       "#eaeaea",  # Primary text
    "text_muted": "#a0a0b0",  # Secondary/disabled text
    "text_dim":   "#6a6a8a",  # Very muted text

    # Structure
    "border":    "#2a2a4a",  # Widget borders
    "separator": "#1a3a6a",  # Separator lines

    # Toast backgrounds
    "toast_success": "#1a3d2a",
    "toast_warning": "#3d2a1a",
    "toast_error":   "#3d1a1a",
    "toast_info":    "#1a2a3d",
}
```

**Fonts** (Segoe UI on Windows):

```python
FONT_TITLE     = ("Segoe UI", 20, "bold")   # Page titles
FONT_HEADING   = ("Segoe UI", 15, "bold")   # Section headers
FONT_BODY      = ("Segoe UI", 12)           # Regular text
FONT_BODY_BOLD = ("Segoe UI", 12, "bold")   # Emphasized body text
FONT_SMALL     = ("Segoe UI", 10)           # Labels, captions
FONT_MONO      = ("Consolas", 10)           # Log output, paths
```

**Sizing:**

```python
SIDEBAR_WIDTH       = 180
SIDEBAR_BTN_HEIGHT  = 38
CORNER_RADIUS       = 10
CORNER_RADIUS_SMALL = 6
BUTTON_HEIGHT       = 38
BUTTON_HEIGHT_SMALL = 30
CARD_PAD_X = 18
CARD_PAD_Y = 14
SECTION_PAD = 30
```

**Animation timing (milliseconds):**

```python
ANIM_FAST    = 150    # Quick transitions (hover effects)
ANIM_NORMAL  = 250    # Standard frame slide
ANIM_SLOW    = 400    # Entrance animations
ANIM_STAGGER = 80     # Delay between staggered elements
TOAST_DURATION  = 3000  # How long toast stays visible
TOAST_SLIDE_MS  = 300   # Toast slide-in/out duration
```

### 6.6 Component Library

**File:** `src/sims4_updater/gui/components.py`

**InfoCard**

A `CTkFrame` subclass with an animated border glow on hover. The border color smoothly transitions from `COLORS["border"]` to `COLORS["accent_glow"]` over `ANIM_FAST` milliseconds on `<Enter>`, and back on `<Leave>`.

```python
card = InfoCard(parent, fg_color=theme.COLORS["bg_card"])
# Use like any CTkFrame -- add child widgets via grid/pack
```

**StatusBadge**

A colored pill-shaped badge with a filled dot indicator and a text label. Style determines the color set.

```python
badge = StatusBadge(parent, text="Up to date", style="success")
badge.set_status("Checking...", "info")  # Animates background color change
# Styles: "success", "warning", "error", "info", "muted"
```

**ToastNotification**

A slide-in notification that appears from the top-right corner of the content area, displays for `TOAST_DURATION` ms, then slides out and destroys itself. Only one toast is shown at a time; showing a new one dismisses the previous one.

```python
# Called via App.show_toast() which manages the active_toast reference
self.app.show_toast("DLC downloaded successfully!", style="success")
```

Each toast style has an icon character: check mark (success), warning triangle (warning), x mark (error), info circle (info).

### 6.7 Animation Engine

**File:** `src/sims4_updater/gui/animations.py`

The `Animator` class drives all GUI animations using tkinter's `.after()` scheduler at approximately 60 fps (`FRAME_MS = 16`).

```python
class Animator:
    def animate(widget, duration_ms, on_tick, on_done, easing, tag) -> _Animation
    def animate_color(widget, prop, start, end, duration_ms, easing, tag) -> _Animation
    def cancel_all(widget=None, tag="")
```

`animate()` calls `on_tick(eased_t)` repeatedly where `t` goes from 0.0 to 1.0 over `duration_ms` milliseconds. The easing function maps raw `t` to a perceptually smoother `eased_t`.

**Easing functions:**

| Function | Formula | Use Case |
|---|---|---|
| `ease_linear` | `t` | Uniform speed |
| `ease_out_cubic` | `1 - (1-t)^3` | Frame slides (decelerates at end) |
| `ease_in_out_cubic` | Cubic S-curve | Progress bar pulse |
| `ease_out_back` | Overshoots slightly | Playful feel |
| `ease_out_quad` | `1 - (1-t)^2` | Faster deceleration |

`lerp_color(hex_a, hex_b, t)` linearly interpolates between two `#RRGGBB` hex colors. Used internally by `animate_color()`.

Tag-based cancellation (`cancel_all(widget, tag)`) prevents conflicting animations on the same widget. For example, `InfoCard` cancels any running `"card_hover"` animation before starting the reverse.

A global `_animator` instance is shared by all component-level animations via `get_animator()`. The `App` class has its own `self._animator` instance for frame-level transitions.

### 6.8 Frame Reference: HomeFrame

**File:** `src/sims4_updater/gui/frames/home_frame.py`

The Home tab is the primary dashboard. It has two areas:

**Scrollable content area (row 0):**
- App update banner (hidden by default — shown if GitHub has a newer updater version)
- Title / subtitle
- `InfoCard` with: Game Directory, Installed Version, Latest Patch, Game Latest (conditional), DLCs summary
- Pricing summary `InfoCard` (hidden until Steam prices load)
- Banner area (patch pending notices, new DLC announcements)
- `StatusBadge`

**Pinned button bar (row 1, always visible):**
- "Check for Updates" / "Update Now" / "Patch Pending" button (state-dependent)
- "Refresh" button

**State machine for the update button:**

```
Initial: text="Check for Updates", command=_on_check_updates

After check (update available):
  text="Update Now", command=_start_update(info)

After check (patch pending -- at patchable latest but game is ahead):
  text="Patch Pending", state=disabled

After check (fully up to date):
  text="Check for Updates", command=_on_check_updates
```

**Self-update banner** is displayed at the top of the scrollable area when `check_for_app_update()` finds a newer version. It transforms into a download progress view with: title label, speed label, progress bar, size/percentage labels. After download, a confirmation dialog appears before applying the update.

**Entrance animation:** On first `on_show()`, the title and subtitle fade in with a staggered delay using `animate_color` from `bg_dark` to the target text colors.

### 6.9 Frame Reference: DLCFrame

**File:** `src/sims4_updater/gui/frames/dlc_frame.py`

The DLCs tab displays the full DLC catalog with per-DLC status and download controls.

Key features:
- Filter controls: search by name, filter by pack type, toggle "installed only" / "available for download"
- Per-DLC rows with `StatusBadge`, enable/disable toggle, download button
- "Apply Changes" button writes the current enabled set to the crack config
- Pending DLC notifications from the manifest `new_dlcs` field
- Steam price integration: per-DLC price display with sale highlighting

`set_pending_dlcs(dlcs)` is called by `HomeFrame` when the manifest reports new DLCs awaiting a patch, adding notification banners to the DLC list.

### 6.10 Frame Reference: PackerFrame

**File:** `src/sims4_updater/gui/frames/packer_frame.py`

The DLC Packer tab allows power users to create distributable DLC ZIP archives.

Features:
- Game directory selection
- DLC selection list (installed DLCs only, checkboxes)
- Output directory selection
- "Pack Selected" button: runs `DLCPacker.pack_multiple()` in background
- Pack results table: filename, size, MD5
- "Generate Manifest" button: runs `DLCPacker.generate_manifest()`, shows output in a text widget
- "Import Archive" button: browses for ZIP/RAR and runs `DLCPacker.import_archive()`

### 6.11 Frame Reference: UnlockerFrame

**File:** `src/sims4_updater/gui/frames/unlocker_frame.py`

The Unlocker tab manages the PandaDLL EA DLC Unlocker.

Features:
- Status display: detected client name/path, DLL installed?, config installed?, scheduled task exists?
- "Install" button: calls `unlocker.install(log)` in background (requires admin)
- "Uninstall" button: calls `unlocker.uninstall(log)` in background (requires admin)
- "Open Config Folder" button: opens `%APPDATA%\ToastyToast25\EA DLC Unlocker\` in Explorer
- Scrollable log textarea showing installation steps in real-time

If not running as administrator, the install/uninstall buttons show an error message asking the user to relaunch as administrator.

### 6.12 Frame Reference: GreenLumaFrame

**File:** `src/sims4_updater/gui/frames/greenluma_frame.py`

The GreenLuma Manager tab is the primary interface for all GreenLuma operations.

**Status card** (always visible at the top):

- Steam Path — detected path with install status badge
- GreenLuma — installed/not-installed badge with mode indicator (Normal or Stealth)
- Steam — running/not-running badge (mutations are blocked while Steam is running)
- Summary — count of ready DLCs vs. total catalog entries

**Action button bar** (six buttons, full-width):

| Button | Action |
| --- | --- |
| Install (Normal) | Extract GL archive to Steam dir in normal mode |
| Install (Stealth) | Extract GL archive to Steam dir in stealth mode |
| Uninstall GL | Remove all installed GL files using the install manifest |
| Launch via GL | Spawn `DLLInjector.exe` as a detached process |
| Apply LUA | Run the full `orchestrator.apply_lua()` pipeline |
| Fix AppList | Deduplicate AppList and fill in any missing catalog IDs |

**DLC Readiness list** — a scrollable list showing every catalog DLC that has a `steam_app_id`, with three inline indicators (AppList, Key, Manifest) displayed as colored checkmarks or dashes. A filter segmented control allows switching between All / Ready / Incomplete views.

**Activity log** — a `CTkTextbox` below the readiness list that receives timestamped log output from all background operations.

All operations follow the standard async pattern: `self.app.run_async(bg_func, on_done=..., on_error=...)`. Buttons are disabled while any operation is in progress (`self._busy = True`) to prevent concurrent mutations.

### 6.13 Frame Reference: SettingsFrame

**File:** `src/sims4_updater/gui/frames/settings_frame.py`

The Settings tab is structured as two `InfoCard` sections within a scrollable body.

#### Card 1: Game & Updates

- **Game Directory** — text entry with "Browse", "Auto Detect" buttons. "Auto Detect" invokes the same registry + filesystem probe used by `VersionDetector`.
- **Patch Manifest URL** — text entry for the patch manifest endpoint
- **Language** — dropdown of all 18 language codes
- **Theme** — appearance mode selector
- **Check Updates on Start** — checkbox

#### Card 2: GreenLuma

- **Steam Path** — text entry with "Browse" button (leave blank for auto-detection)
- **Steam Username** — text entry for DepotDownloader authentication (password is never stored)
- **GreenLuma Archive** — file picker for the `.7z` distribution archive
- **LUA Manifest Path** — file picker for the `.lua` file to apply
- **Manifest Files Directory** — directory picker for `.manifest` binary files
- **Auto Backup** — checkbox that controls whether `config.vdf` and AppList are backed up before modification

"Save" button writes `Settings.save()` and shows a toast confirmation. `on_show()` calls `Settings.load()` to refresh the displayed values each time the tab is opened.

### 6.14 Frame Reference: ProgressFrame

**File:** `src/sims4_updater/gui/frames/progress_frame.py`

The Progress frame is shown programmatically during game updates (not in the nav sidebar).

Structure (top to bottom):
- Title row: "Update Progress" + step count label
- Stage header: current operation name (colored accent)
- Progress card: percentage label + size label + progress bar
- Current file label (short path of file being processed)
- Scrollable `CTkTextbox` activity log with color-coded entries
- Button bar: "Cancel" (red, enabled during update) + stats label + "Back to Home" (enabled when done)

**Log color tags:**

```python
"header"  --> accent color, bold    # Section dividers
"success" --> success color          # Completion messages
"warning" --> warning color          # Non-fatal issues
"error"   --> error color            # Failures
"muted"   --> text_muted color       # EXTRACT/HASH operations
```

**Pulse animation:** During active updates, the progress bar breathes between `accent` and `accent_hover` colors using `ease_in_out_cubic` at 850ms half-cycle. The pulse stops and the bar turns green on success, or red on error.

**Callback routing:** `handle_callback(callback_type, *args)` maps `CallbackType` events to UI updates. `INFO` callbacks update both the current-file label and the log. `PROGRESS` callbacks update the bar and size labels.

---

## 7. Configuration and App Data

### 7.1 App Data Directory

```
%LOCALAPPDATA%\ToastyToast25\sims4_updater\
    settings.json             # User settings
    learned_hashes.json       # Locally accumulated version fingerprints
    downloads\                # Downloaded patch ZIPs (temporary)
        {from}_to_{to}\       # Per-step subdirectory
            patch.zip
            crack.zip
    dlcs\                     # Downloaded DLC archives
    updates\                  # Self-update downloaded exes + scripts
    custom_dlcs.json          # DLC catalog additions from remote manifest
```

Fallback on non-Windows: `~/.config/sims4_updater/`.

`get_app_dir()` in `config.py` creates this directory on first call (`mkdir(parents=True, exist_ok=True)`).

### 7.2 Settings Dataclass

**File:** `src/sims4_updater/config.py`

```python
@dataclass
class Settings:
    game_path: str = ""
    language: str = "English"
    check_updates_on_start: bool = True
    last_known_version: str = ""
    enabled_dlcs: list[str] = field(default_factory=list)
    manifest_url: str = ""
    theme: str = "dark"
    steam_username: str = ""              # Steam username for depot downloads (password NOT stored)
    steam_path: str = ""                  # Steam installation directory (auto-detected or manual)
    greenluma_archive_path: str = ""      # Path to GreenLuma 7z archive
    greenluma_auto_backup: bool = True    # Backup config.vdf/AppList before modifications
    greenluma_lua_path: str = ""          # Path to .lua manifest file
    greenluma_manifest_dir: str = ""      # Path to directory containing .manifest files
    download_concurrency: int = 3         # Number of parallel segment downloads
    download_speed_limit: int = 0         # MB/s cap; 0 = unlimited
```

`Settings.load()` reads `settings.json`, ignores any unknown keys (forward-compatibility), and returns a default `Settings()` instance on any parse error.

`Settings.save()` uses atomic write: the new JSON is written to a `.json_tmp` file first, then `os.replace()` swaps it into place. This prevents a corrupt settings file from a crash mid-write.

### 7.3 Settings Migration

When the app data directory was renamed from `anadius` to `ToastyToast25`, a one-time migration was added in `config.py`. The migration runs at module import time and is transparent to the rest of the application.

```python
_OLD_DIR_NAME = "anadius"
_NEW_DIR_NAME = "ToastyToast25"

def _migrate_from_old_dir():
    # If old dir exists and new dir has no settings.json yet:
    # Copy settings.json and learned_hashes.json to new location
```

This runs at module import time (before any settings are loaded), so it is transparent to the rest of the application.

### 7.4 Bundled Data Paths

**File:** `src/sims4_updater/constants.py`

The application distinguishes between frozen (PyInstaller) and source mode:

```python
def get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "data"
    return Path(__file__).resolve().parent.parent.parent / "data"

def get_tools_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "tools"
    return Path(__file__).resolve().parent.parent.parent / "tools"

def get_icon_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "sims4.png"
    return Path(__file__).resolve().parent.parent.parent / "sims4.png"
```

`sys._MEIPASS` is PyInstaller's temporary extraction directory for the single-file executable's bundled assets.

When running from source, `data/`, `tools/`, and `sims4.png` are resolved relative to the repository root (`../../../` from the `constants.py` location inside `src/sims4_updater/`).

---

## 8. CLI Entry Point

**File:** `src/sims4_updater/__main__.py`

Running the package without arguments (`python -m sims4_updater` or the exe) launches the GUI. Passing a subcommand invokes the corresponding CLI function:

```
sims4-updater                              Launch GUI
sims4-updater status [game_dir]            Show overall status
sims4-updater detect <game_dir>            Detect installed version
sims4-updater check [game_dir]             Check for updates
  [--manifest-url URL]
sims4-updater manifest <url|file>          Inspect a manifest
sims4-updater dlc <game_dir>               Show DLC states
sims4-updater dlc-auto <game_dir>          Auto-toggle DLCs
sims4-updater pack-dlc <game_dir> <ids...> Pack DLC zip archives
  [-o OUTPUT_DIR]
  [all]                                    Pack all installed DLCs
sims4-updater learn <game_dir> <version>   Learn version hashes
sims4-updater language [code]              Show or set language
  [--game-dir DIR]
```

`_fix_console_encoding()` is called at module load to wrap `stdout`/`stderr` with UTF-8 encoding on Windows, preventing Unicode errors when printing DLC names in non-English languages.

The GUI is imported lazily (`from sims4_updater.gui.app import launch`) so that the CLI commands work even if `customtkinter` is not installed.

---

## 9. Exception Hierarchy

**File:** `src/sims4_updater/core/exceptions.py`

```
Exception
└── UpdaterError                   Base for all updater errors
      ├── ExitingError             User cancelled (from BasePatcher.check_exiting())
      ├── WritePermissionError     Cannot write to game directory
      ├── NotEnoughSpaceError      Insufficient disk space
      ├── FileMissingError         Expected file not found
      ├── VersionDetectionError    Cannot determine game version
      ├── ManifestError            Manifest fetch or parse failure
      ├── DownloadError            HTTP download failure or cancellation
      ├── IntegrityError           MD5 verification failure
      ├── NoUpdatePathError        No patch path from current to target version
      ├── NoCrackConfigError       No crack config found in game directory
      ├── XdeltaError              xdelta3.exe returned non-zero exit code
      └── AVButtinInError          Antivirus interfered with file operations
```

**GUI error handling pattern:**

```python
# In any frame:
self.app.run_async(
    self._background_func,
    on_done=self._on_success,
    on_error=self._on_error,   # optional -- default shows messagebox
)

def _on_error(self, error: Exception):
    # Called on GUI thread
    if isinstance(error, ManifestError):
        # Show specific guidance
        self.app.show_toast(f"Manifest error: {error}", "error")
    else:
        # Default fallback
        self.app._show_error(error)
```

When no `on_error` is provided to `run_async()`, the default handler calls `tkinter.messagebox.showerror()`.

---

## 10. Manifest Format Specification

A complete reference for operators who host their own patch manifests.

**Required fields:**

```json
{
  "latest": "1.120.xxx.1020"
}
```

**Full structure with all optional fields:**

```json
{
  "latest": "1.120.xxx.1020",

  "game_latest": "1.121.yyy.1020",
  "game_latest_date": "2026-01-15",

  "report_url": "https://your-server.com/api/report-hashes",
  "fingerprints_url": "https://your-server.com/api/fingerprints",

  "fingerprints": {
    "1.120.xxx.1020": {
      "Game/Bin/TS4_x64.exe":   "UPPER_HEX_MD5",
      "Game/Bin/Default.ini":   "UPPER_HEX_MD5",
      "delta/EP01/version.ini": "UPPER_HEX_MD5"
    }
  },

  "patches": [
    {
      "from":  "1.118.xxx.1020",
      "to":    "1.119.xxx.1020",
      "files": [
        {
          "url":      "https://cdn.example.com/patch_118_to_119.zip",
          "size":     123456789,
          "md5":      "UPPER_HEX_MD5",
          "filename": "patch_118_to_119.zip"
        }
      ],
      "crack": {
        "url":  "https://cdn.example.com/crack_119.zip",
        "size": 12345,
        "md5":  "UPPER_HEX_MD5"
      }
    }
  ],

  "new_dlcs": [
    { "id": "EP18", "name": "Businesses & Hobbies", "status": "pending" }
  ],

  "dlc_catalog": [
    {
      "id":   "EP18",
      "code": "SIMS4.OFF.SOLP.0x...",
      "code2": "",
      "type": "expansion",
      "names": {
        "en_us": "Businesses & Hobbies",
        "de_de": "Berufe und Hobbys"
      },
      "description": "Optional short description"
    }
  ],

  "dlc_downloads": {
    "EP01": {
      "url":      "https://cdn.example.com/Sims4_DLC_EP01_World_Adventures.zip",
      "size":     987654321,
      "md5":      "UPPER_HEX_MD5",
      "filename": "Sims4_DLC_EP01_World_Adventures.zip"
    }
  }
}
```

**Field reference:**

| Field | Required | Purpose |
|---|---|---|
| `latest` | Yes | Highest version with a complete patch chain |
| `game_latest` | No | Actual EA-released version; triggers patch-pending UI if different from `latest` |
| `game_latest_date` | No | Human-readable release date shown in UI |
| `patches[].from` | Yes | Source version string |
| `patches[].to` | Yes | Target version string |
| `patches[].files[].url` | Yes | Direct download URL |
| `patches[].files[].size` | Yes | Byte size for progress tracking |
| `patches[].files[].md5` | No | Uppercase hex MD5 for verification |
| `patches[].files[].filename` | No | Derived from URL if omitted |
| `patches[].crack` | No | Optional crack archive for this patch step |
| `fingerprints` | No | Version hash entries merged into local LearnedHashDB |
| `fingerprints_url` | No | URL for crowd-sourced fingerprint endpoint |
| `report_url` | No | POST endpoint for learned hash reporting |
| `new_dlcs` | No | Announced but not yet patchable DLCs for UI notification |
| `dlc_catalog` | No | New DLC entries merged into the in-memory catalog |
| `dlc_downloads` | No | Per-DLC download entries for individual DLC acquisition |

---

## 11. DLC Catalog and Custom DLCs

**File:** `data/dlc_catalog.json`

The bundled catalog structure:

```json
{
  "dlcs": [
    {
      "id":   "EP01",
      "code": "SIMS4.OFF.SOLP.0x0000000000011AC5",
      "code2": "",
      "type": "expansion",
      "names": {
        "en_us": "World Adventures",
        "de_de": "Weltabenteuer",
        "fr_fr": "Destination Aventure"
      },
      "description": "Travel to exotic locations.",
      "steam_app_id": 1227400
    }
  ]
}
```

**Custom DLC persistence:**

When the manifest's `dlc_catalog` field introduces new DLC entries not in the bundled file, they are appended in-memory and persisted to `%LOCALAPPDATA%\ToastyToast25\sims4_updater\custom_dlcs.json`. On next startup, this file is merged back into the catalog. This allows the catalog to grow without requiring a new app release.

**DLC ID conventions:**

| Prefix | Type |
|---|---|
| EP01 - EP__ | Expansion Packs |
| GP01 - GP__ | Game Packs |
| SP01 - SP__ | Stuff Packs |
| KIT01 - KIT__ | Kits |
| FP01 - FP__ | Free Packs |

---

## 12. Build System

### 12.1 PyInstaller Spec

**File:** `sims4_updater.spec`

The spec file defines a single-file (`onefile`) Windows executable without a console window.

**Data files bundled:**

| Source | Destination in exe |
|---|---|
| `data/version_hashes.json` | `data/` |
| `data/dlc_catalog.json` | `data/` |
| `../patcher/tools/xdelta3-x64.exe` | `tools/` |
| `../patcher/tools/xdelta3-x86.exe` | `tools/` |
| `../patcher/tools/unrar.exe` | `tools/` |
| `../patcher/tools/unrar-license.txt` | `tools/` |
| `sims4.png` | `.` (root) |
| `customtkinter/` package directory | `customtkinter/` |

**Hidden imports** (not automatically detected by PyInstaller):

```python
hiddenimports = [
    'customtkinter',
    'pywintypes', 'win32file', 'win32timezone', 'win32api',  # pywin32
    'patcher', 'patcher.patcher', 'patcher.myzipfile',
    'patcher.cache', 'patcher.subprocess_', 'patcher.files',
    'patcher.utils', 'patcher.exceptions',
]
```

**Excluded packages** (significantly reduce exe size):

```python
excludes = ['matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'cv2', 'pytest', 'ruff']
```

**Build command:**

```bash
python -m PyInstaller sims4_updater.spec --noconfirm
```

Output: `dist/Sims4Updater.exe`

The spec also defines UPX compression (`upx=True`) which reduces the final exe size by approximately 30 to 40 percent.

### 12.2 Runtime Path Resolution

PyInstaller sets `sys.frozen = True` and `sys._MEIPASS` to the temporary extraction directory when the exe is running. This is used throughout the codebase for asset path resolution:

```python
# constants.py pattern used by get_data_dir(), get_tools_dir(), get_icon_path()
if getattr(sys, "frozen", False):
    base = Path(sys._MEIPASS)   # e.g. C:\Users\...\AppData\Local\Temp\_MEI12345\
else:
    base = Path(__file__).resolve().parent.parent.parent  # repository root
```

The `sys.path` injection in `updater.py` for the patcher package is guarded: if the patcher directory does not exist (frozen exe), the injection is skipped, and the hidden imports in the spec ensure `patcher.*` is already available.

### 12.3 Excluded Packages

The following Python packages are explicitly excluded to keep the exe size manageable. If you add a dependency that transitively imports any of these, you must either add the package back or restructure the import:

- `matplotlib` — plotting library
- `numpy`, `pandas`, `scipy` — scientific computing
- `PIL` / `Pillow` — image processing (CustomTkinter uses tkinter's PhotoImage instead)
- `cv2` — OpenCV
- `pytest`, `ruff` — dev tools

---

## 13. Developer Guides

### 13.1 Adding a New GUI Frame

To add a new tab to the sidebar navigation:

**Step 1: Create the frame class**

```python
# src/sims4_updater/gui/frames/my_frame.py
from __future__ import annotations
from typing import TYPE_CHECKING
import customtkinter as ctk
from .. import theme

if TYPE_CHECKING:
    from ..app import App


class MyFrame(ctk.CTkFrame):

    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._data_loaded = False

        self.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            self,
            text="My Feature",
            font=ctk.CTkFont(*theme.FONT_TITLE),
        ).grid(row=0, column=0, padx=theme.SECTION_PAD, pady=(20, 10), sticky="w")

        # ... build your UI widgets here ...

    def on_show(self):
        """Called every time this tab becomes active."""
        if not self._data_loaded:
            self._load_data()

    def _load_data(self):
        """Load data in the background."""
        self.app.run_async(
            self._fetch_data_bg,
            on_done=self._on_data_loaded,
            on_error=self._on_error,
        )

    def _fetch_data_bg(self):
        """Runs on background thread -- do blocking work here."""
        return {"key": "value"}

    def _on_data_loaded(self, data: dict):
        """Runs on GUI thread -- update widgets here."""
        self._data_loaded = True
        # self._some_label.configure(text=data["key"])

    def _on_error(self, error: Exception):
        self.app.show_toast(f"Error: {error}", "error")
```

**Step 2: Register in App**

```python
# src/sims4_updater/gui/app.py

# Add import at the top:
from .frames.my_frame import MyFrame

# In _build_sidebar(), add to nav_items:
nav_items = [
    ("home",     "Home"),
    ("dlc",      "DLCs"),
    ("packer",   "DLC Packer"),
    ("unlocker", "Unlocker"),
    ("my_key",   "My Feature"),   # <-- Add here
    ("settings", "Settings"),
]

# In _create_frames(), add instantiation:
self._frames["my_key"] = MyFrame(self._content, self)
```

**Step 3: Access shared state**

Within your frame, the following are always available via `self.app`:

```python
self.app.settings          # Settings dataclass
self.app.updater           # Sims4Updater instance
self.app.price_cache       # SteamPriceCache
self.app.run_async(...)    # Background execution
self.app._enqueue_gui(...) # GUI thread scheduling
self.app.show_toast(...)   # Toast notifications
self.app.show_message(...) # Modal info dialog
self.app.switch_to_progress()  # Navigate to progress frame
self.app.switch_to_home()      # Navigate back to home
```

### 13.2 Adding a New Crack Config Format

To support a new DLC toggling format:

**Step 1: Create the adapter in `formats.py`**

```python
# In src/sims4_updater/dlc/formats.py

class MyFormatAdapter(DLCConfigAdapter):

    CONFIG_PATHS = [
        "Game/Bin/myformat.cfg",
        "Game-cracked/Bin/myformat.cfg",
    ]

    def detect(self, game_dir: Path) -> bool:
        return self.get_config_path(game_dir) is not None

    def get_config_path(self, game_dir: Path) -> Path | None:
        for p in self.CONFIG_PATHS:
            path = game_dir / p.replace("/", os.sep)
            if path.is_file():
                return path
        return None

    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        """Return {code: True/False} for each code that appears in the config."""
        result = {}
        for code in dlc_codes:
            pattern = re.compile(rf"(?i)your_regex_for_{re.escape(code)}")
            match = pattern.search(config_content)
            if match:
                result[code] = True  # or False based on match groups
        return result

    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        """Return modified config_content with the DLC enabled or disabled."""
        pattern = re.compile(rf"(?i)your_regex_for_{re.escape(dlc_code)}")
        replacement = "enabled_text" if enabled else "disabled_text"
        return pattern.sub(replacement, config_content)

    def get_format_name(self) -> str:
        return "MyFormat"

    def get_encoding(self) -> str:
        return "utf-8"
```

**Step 2: Register in the detection chain**

```python
# In formats.py, update ALL_ADAPTERS:
ALL_ADAPTERS = [
    AnadiusCodexAdapter(),
    AnadiusSimpleAdapter(),
    MyFormatAdapter(),      # <-- Insert at appropriate priority
    RuneAdapter(),
    CodexAdapter(),
    RldOriginAdapter(),
]
```

Priority note: Adapters checked earlier take precedence. If your format's config file name could conflict with an existing format's detection, order it carefully and add content-based disambiguation in `detect()` (as `AnadiusCodexAdapter` does with the `"Config2"` string check).

**Step 3: Test**

```bash
python -m sims4_updater dlc <game_dir_with_your_format>
# Should show "Crack config format: MyFormat"
```

### 13.3 Adding a New CLI Subcommand

```python
# In src/sims4_updater/__main__.py

def my_command(args):
    """Implementation of my-command."""
    from sims4_updater.some_module import SomeClass
    # ... implementation ...


def main():
    # ... existing parsers ...

    # Add new subparser:
    my_parser = subparsers.add_parser("my-command", help="Description of my command")
    my_parser.add_argument("required_arg", help="...")
    my_parser.add_argument("--optional-flag", help="...")

    args = parser.parse_args()

    # Add dispatch in the if/elif chain:
    elif args.command == "my-command":
        my_command(args)
```

### 13.4 Extending the DLC Catalog

To add a new DLC to the bundled catalog:

1. Edit `data/dlc_catalog.json` and add an entry to the `"dlcs"` array:

```json
{
  "id":   "EP20",
  "code": "SIMS4.OFF.SOLP.0x...",
  "code2": "",
  "type": "expansion",
  "names": {
    "en_us": "My New Pack",
    "de_de": "Mein neues Paket"
  },
  "description": "Short description.",
  "steam_app_id": 1234567
}
```

2. Find the `code` value by examining the crack config file for an installed copy and locating the `IIDxx=SIMS4.OFF.SOLP.0x...` line (RldOrigin format) or equivalent in the target format.

3. Rebuild the executable for the new entry to be bundled.

Alternatively, for DLCs added after release, add them to the server manifest's `dlc_catalog` field. They will be downloaded and persisted to `custom_dlcs.json` automatically on the user's next manifest fetch.

### 13.5 Working with the Version Hash DB

**Adding a version manually (CLI):**

```bash
python -m sims4_updater learn "C:\Path\To\Sims 4" 1.120.xxx.1020
```

**Inspecting the learned DB:**

```python
from sims4_updater.core.learned_hashes import LearnedHashDB
db = LearnedHashDB()
print(f"Total learned: {db.version_count}")
for version, hashes in db.versions.items():
    print(f"  {version}: {len(hashes)} sentinel(s)")
```

**Adding a version programmatically:**

```python
from sims4_updater.core.learned_hashes import LearnedHashDB
from sims4_updater.core.files import hash_file
from pathlib import Path

game_dir = Path("C:/Path/To/Sims 4")
version = "1.120.xxx.1020"

hashes = {}
for sentinel in ["Game/Bin/TS4_x64.exe", "Game/Bin/Default.ini"]:
    path = game_dir / sentinel.replace("/", "\\")
    if path.is_file():
        hashes[sentinel] = hash_file(str(path))

db = LearnedHashDB()
db.add_version(version, hashes)
db.save()
```

**Adding a new sentinel file to the bundled DB:**

Edit `data/version_hashes.json`:

```json
{
  "sentinel_files": [
    "Game/Bin/TS4_x64.exe",
    "Game/Bin/Default.ini",
    "delta/EP01/version.ini",
    "Game/Bin/MyNewSentinel.dll"
  ],
  "versions": {
    "1.120.xxx.1020": {
      "Game/Bin/TS4_x64.exe":          "...",
      "Game/Bin/Default.ini":           "...",
      "delta/EP01/version.ini":         "...",
      "Game/Bin/MyNewSentinel.dll":     "..."
    }
  }
}
```

---

## 14. Security Considerations

**Path traversal protection in ZIP extraction:**

Both `DLCDownloader._extract_zip()` and `DLCPacker._extract_zip()` resolve every ZIP member's target path and verify it remains under the game directory before extraction:

```python
target = (self.game_dir / member).resolve()
if not str(target).startswith(str(game_dir_resolved)):
    logger.warning("Skipping unsafe zip path: %s", member)
    continue
```

**MD5 verification:**

All downloaded patch files and DLC archives are verified against expected MD5 hashes from the manifest. A mismatch raises `IntegrityError` and deletes the corrupt file. This is a defense against CDN corruption and man-in-the-middle data modification.

Note: MD5 is used here for data integrity, not cryptographic security. The manifest itself is fetched over HTTPS.

**HTTPS with retry and legacy TLS:**

The downloader's session uses a custom SSL context with `ssl.OP_LEGACY_SERVER_CONNECT` to support CDN servers with older TLS configurations. While this slightly reduces strict TLS enforcement, all connections are still encrypted. The option is equivalent to disabling `OP_NO_SSLv2` checks that are not relevant to modern servers.

**Self-update executable validation:**

Before swapping executables, the batch script validates:
1. File exists on disk.
2. File size is at least 1 MB (1,000,000 bytes).
3. First 2 bytes are `MZ` (Windows PE header).
4. Final exe size matches the expected size after the move.

**Administrator privilege escalation:**

The DLC Unlocker installer explicitly checks `ctypes.windll.shell32.IsUserAnAdmin()` and raises `PermissionError` if not elevated. This prevents silent failures when trying to write to `Program Files`.

**Registry access:**

Language setting and game directory detection use `winreg`. Registry writes use `try/except OSError` to gracefully handle environments where the user lacks write permission to `HKLM` (the function returns `False` and the user is informed).

**Antivirus interference:**

The `AVButtinInError` exception class exists for cases where antivirus software blocks file operations. The self-update batch script proactively triggers a Windows Defender scan of the new exe (`powershell ReadAllBytes`) and waits 5 seconds before launching, to reduce false-positive AV blocks on launch.

---

## 15. Performance Characteristics

**Version detection:**

- Hashes 3 sentinel files sequentially using 64 KB chunks.
- On SSD: typically under 1 second total.
- On HDD: 2 to 5 seconds depending on file sizes.
- Detection is parallelizable (all files are independent) but the sequential implementation is sufficient given the small file count.

**Manifest fetch:**

- Single HTTP GET with 30-second timeout.
- Cached in-memory for the session lifetime.
- Subsequent `check_update()` calls within the same session use the cached manifest without a network request.

**Update path planning:**

- BFS on the patch graph.
- Graph size is bounded by the number of patch entries in the manifest (typically fewer than 50).
- Planning completes in milliseconds for any practical manifest size.

**Download throughput:**

- 64 KB chunks, streaming.
- Resume support avoids re-downloading on interruption.
- Retry adapter handles transient 5xx errors with exponential backoff.
- No download rate limiting; speed is determined by the CDN and network.

**DLC toggle (config write):**

- Reads the entire config file into memory.
- Applies regex substitutions for all DLCs in a single pass.
- Writes back atomically.
- Typically completes in under 50 ms for any config file size.

**Steam price fetch:**

- Up to 8 concurrent HTTP requests.
- Approximately 109 DLCs divided by 8 workers equals approximately 14 requests per worker.
- Each request takes approximately 200 to 500 ms.
- Total batch: approximately 3 to 8 seconds.
- Results are cached for 30 minutes.

**GUI responsiveness:**

- The `ThreadPoolExecutor(max_workers=1)` ensures only one background operation runs at a time, preventing resource contention.
- The 100 ms polling interval for the callback queue introduces up to 100 ms latency on GUI updates from background threads — acceptable for this use case.
- Animations run at approximately 60 fps (16 ms intervals) using `.after()`.

---

## 16. Glossary

| Term | Definition |
|---|---|
| **Sentinel file** | A game binary file whose MD5 hash changes reliably between versions, used for fingerprint-based version detection |
| **Fingerprint** | The set of MD5 hashes of a game version's sentinel files; uniquely identifies a specific game version |
| **Manifest** | A JSON file hosted at a configurable URL describing available patches, DLC downloads, and catalog updates |
| **Patch** | A binary diff (xdelta3 format) packaged in a ZIP archive that updates game files from one version to the next |
| **Crack config** | A configuration file used by game cracks (RldOrigin, CODEX, Rune, anadius) to control which DLCs are unlocked |
| **DLC Unlocker** | A DLL (version.dll / PandaDLL) that hooks into the EA Desktop client to spoof DLC entitlements |
| **Adapter** | A class implementing `DLCConfigAdapter` that knows how to read and write one specific crack config format |
| **Pack type** | Category of DLC content: `expansion`, `game_pack`, `stuff_pack`, `kit`, `free_pack` |
| **Learned hash** | A version fingerprint acquired at runtime (post-patch, from manifest, or from crowd-sourcing) and stored locally |
| **UpdatePlan** | The computed sequence of patch steps needed to upgrade from the current to the target version |
| **UpdateStep** | A single version-to-version transition within an UpdatePlan, referencing a specific PatchEntry |
| **patch_pending** | State where the actual EA game version is newer than the latest available patch; the UI shows a "patch coming soon" notice |
| **CallbackType** | Enum of event types emitted by the BasePatcher during patch operations (HEADER, INFO, PROGRESS, WARNING, FAILURE, FINISHED) |
| **DLCStatus** | Runtime enrichment of DLCInfo with disk presence, crack config registration, and enabled state |
| **SteamPrice** | Pricing data for a DLC from the Steam Store API, including current/original prices and discount percentage |
| **Sentinel DB** | The merged in-memory database of version fingerprints combining bundled, learned, and remote-sourced entries |
| **_MEIPASS** | PyInstaller runtime attribute pointing to the temporary directory where a frozen exe's bundled assets are extracted |
| **on_show()** | Frame lifecycle method called each time a frame becomes the active visible tab |
| **run_async()** | App method that submits a function to the background executor and routes the result back to the GUI thread |

---

*This document covers the Sims 4 Updater v2.1.0 codebase as it existed in February 2026. For questions or contributions, see the GitHub repository at https://github.com/ToastyToast25/sims4-updater.*
