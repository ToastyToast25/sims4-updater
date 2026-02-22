# GreenLuma Integration — Technical Reference

**Project:** Sims 4 Updater
**Document Version:** 2.1.0
**Date:** 2026-02-21
**Scope:** GreenLuma 2025 Steam DLC integration — detection, installation, AppList management, config.vdf depot keys, LUA manifest parsing, depotcache manifest files, orchestration, and GUI

---

## Table of Contents

1. [Overview](#1-overview)
2. [Module Map](#2-module-map)
3. [Steam Detection (steam.py)](#3-steam-detection-steampy)
   - 3.1 [SteamInfo Dataclass](#31-steaminfo-dataclass)
   - 3.2 [detect_steam_path()](#32-detect_steam_path)
   - 3.3 [GreenLuma Presence Detection](#33-greenluma-presence-detection)
   - 3.4 [is_steam_running()](#34-is_steam_running)
   - 3.5 [validate_steam_path()](#35-validate_steam_path)
   - 3.6 [get_steam_info()](#36-get_steam_info)
4. [AppList Management (applist.py)](#4-applist-management-applistpy)
   - 4.1 [AppList File Format](#41-applist-file-format)
   - 4.2 [AppListState Dataclass](#42-appliststate-dataclass)
   - 4.3 [read_applist()](#43-read_applist)
   - 4.4 [write_applist()](#44-write_applist)
   - 4.5 [add_ids() and remove_ids()](#45-add_ids-and-remove_ids)
   - 4.6 [backup_applist()](#46-backup_applist)
   - 4.7 [Hard Entry Limit](#47-hard-entry-limit)
   - 4.8 [Duplicate Handling](#48-duplicate-handling)
5. [Config VDF (config_vdf.py)](#5-config-vdf-config_vdfpy)
   - 5.1 [VDF File Format Overview](#51-vdf-file-format-overview)
   - 5.2 [VdfKeyState Dataclass](#52-vdfkeystate-dataclass)
   - 5.3 [read_depot_keys()](#53-read_depot_keys)
   - 5.4 [add_depot_keys()](#54-add_depot_keys)
   - 5.5 [verify_keys()](#55-verify_keys)
   - 5.6 [backup_config_vdf()](#56-backup_config_vdf)
   - 5.7 [Brace-Depth-Aware Parser](#57-brace-depth-aware-parser)
6. [LUA Parser (lua_parser.py)](#6-lua-parser-lua_parserpy)
   - 6.1 [LUA Manifest Format](#61-lua-manifest-format)
   - 6.2 [DepotEntry Dataclass](#62-depotentry-dataclass)
   - 6.3 [LuaManifest Dataclass](#63-luamanifest-dataclass)
   - 6.4 [Regex Patterns](#64-regex-patterns)
   - 6.5 [parse_lua_string() and parse_lua_file()](#65-parse_lua_string-and-parse_lua_file)
   - 6.6 [Parsing Logic and Pass Order](#66-parsing-logic-and-pass-order)
7. [Manifest Cache (manifest_cache.py)](#7-manifest-cache-manifest_cachepy)
   - 7.1 [Depotcache File Format](#71-depotcache-file-format)
   - 7.2 [ManifestState Dataclass](#72-manifeststate-dataclass)
   - 7.3 [read_depotcache()](#73-read_depotcache)
   - 7.4 [copy_manifests()](#74-copy_manifests)
   - 7.5 [copy_matching_manifests()](#75-copy_matching_manifests)
   - 7.6 [find_missing_manifests()](#76-find_missing_manifests)
8. [Installer (installer.py)](#8-installer-installerpy)
   - 8.1 [GreenLumaStatus Dataclass](#81-greenlumastatus-dataclass)
   - 8.2 [detect_greenluma()](#82-detect_greenluma)
   - 8.3 [install_greenluma()](#83-install_greenluma)
   - 8.4 [Path Traversal Protection](#84-path-traversal-protection)
   - 8.5 [Subdirectory Flattening](#85-subdirectory-flattening)
   - 8.6 [Install Manifest Tracking](#86-install-manifest-tracking)
   - 8.7 [uninstall_greenluma()](#87-uninstall_greenluma)
   - 8.8 [kill_steam()](#88-kill_steam)
   - 8.9 [launch_steam_via_greenluma()](#89-launch_steam_via_greenluma)
   - 8.10 [Version Detection](#810-version-detection)
9. [Orchestrator (orchestrator.py)](#9-orchestrator-orchestratorpy)
   - 9.1 [DLCReadiness Dataclass](#91-dlcreadiness-dataclass)
   - 9.2 [ApplyResult Dataclass](#92-applyresult-dataclass)
   - 9.3 [VerifyResult Dataclass](#93-verifyresult-dataclass)
   - 9.4 [GreenLumaOrchestrator Class](#94-greenlumacorchestrator-class)
   - 9.5 [check_readiness()](#95-check_readiness)
   - 9.6 [apply_lua() — Five-Step Pipeline](#96-apply_lua--five-step-pipeline)
   - 9.7 [verify()](#97-verify)
   - 9.8 [fix_applist()](#98-fix_applist)
10. [GUI Frame (greenluma_frame.py)](#10-gui-frame-greenluma_framepy)
    - 10.1 [Frame Layout and Widget Structure](#101-frame-layout-and-widget-structure)
    - 10.2 [Status Card Fields](#102-status-card-fields)
    - 10.3 [Action Buttons](#103-action-buttons)
    - 10.4 [DLC Readiness Panel](#104-dlc-readiness-panel)
    - 10.5 [Activity Log](#105-activity-log)
    - 10.6 [Async Execution Model](#106-async-execution-model)
    - 10.7 [Install Flow](#107-install-flow)
    - 10.8 [Steam-Restart Dialog Flow](#108-steam-restart-dialog-flow)
    - 10.9 [Apply LUA Pre-Population from Settings](#109-apply-lua-pre-population-from-settings)
11. [DLC Tab Integration (dlc_frame.py)](#11-dlc-tab-integration-dlc_framepy)
    - 11.1 [Header Badge](#111-header-badge)
    - 11.2 [GL Pill Badges on DLC Rows](#112-gl-pill-badges-on-dlc-rows)
    - 11.3 [Readiness Data Loading](#113-readiness-data-loading)
12. [Settings Integration (config.py and settings_frame.py)](#12-settings-integration-configpy-and-settings_framepy)
    - 12.1 [New Settings Fields](#121-new-settings-fields)
    - 12.2 [GreenLuma Card in Settings Frame](#122-greenluma-card-in-settings-frame)
    - 12.3 [Save and Load Behavior](#123-save-and-load-behavior)
13. [Data Flow Diagrams](#13-data-flow-diagrams)
    - 13.1 [Install Flow](#131-install-flow)
    - 13.2 [Apply LUA Flow](#132-apply-lua-flow)
    - 13.3 [DLC Readiness Check Flow](#133-dlc-readiness-check-flow)
14. [Known GreenLuma File Inventory](#14-known-greenluma-file-inventory)
15. [Error Handling Summary](#15-error-handling-summary)
16. [Glossary](#16-glossary)

---

## 1. Overview

### What GreenLuma Is

GreenLuma 2025 is a DLL injection tool for Steam that intercepts Steam's internal licensing checks to present purchased DLC entitlements to the Steam client and game processes. It operates by injecting two DLLs (`GreenLuma_2025_x64.dll`, `GreenLuma_2025_x86.dll`) into the Steam process via a separate loader executable, `DLLInjector.exe`. The injected DLLs respond to Steam's ownership queries with a configured list of App IDs and Depot IDs sourced from a numbered plain-text directory called `AppList/`, located inside the Steam installation root.

GreenLuma also uses Steam's `config/config.vdf` file to supply depot decryption keys, which Steam requires to decompress downloaded depot archives. When depot decryption keys are present in `config.vdf` and matching binary `.manifest` files exist in Steam's `depotcache/` directory, Steam can download and install DLC content that it understands the user owns through the GreenLuma-spoofed entitlement.

### Two Operating Modes

| Mode | Description | Artifacts |
|------|-------------|-----------|
| `normal` | GreenLuma DLLs and `DLLInjector.exe` placed directly in the Steam installation root. | `<Steam>/GreenLuma_2025_x64.dll`, `<Steam>/GreenLuma_2025_x86.dll`, `<Steam>/DLLInjector.exe` |
| `stealth` | GreenLuma resides in a sibling directory (e.g. `<Steam>/../GreenLuma/`) and is invoked from there. `DLLInjector.ini` configures injection from outside the Steam directory. | `<Steam>/../GreenLuma/DLLInjector.ini`, `<Steam>/../GreenLuma/DLLInjector.exe` |

Stealth mode is preferred by users who want to avoid having GreenLuma files appear directly inside the Steam installation folder, which some anti-cheat integrations scan.

### What the Integration Provides

The Sims 4 Updater GreenLuma integration subsystem provides:

1. **Steam path detection** — Locating the Steam installation automatically via Windows registry with filesystem fallbacks.
2. **GreenLuma presence detection** — Identifying whether GreenLuma is installed and which mode is active.
3. **Installation** — Extracting GreenLuma from a user-provided `.7z` archive into the Steam directory (normal or stealth), with path traversal protection and install manifest recording.
4. **Uninstallation** — Removing all GreenLuma files precisely via the recorded install manifest, or by fallback scanning of known filenames.
5. **AppList management** — Reading, writing, backing up, and repairing the numbered `AppList/*.txt` files that declare which App IDs GreenLuma presents to Steam.
6. **config.vdf depot key injection** — Parsing Steam's VDF-formatted configuration file to insert or update depot decryption keys with brace-balanced text surgery.
7. **LUA manifest parsing** — Parsing the `addappid()`/`setManifestid()` call format used by GreenLuma companion tools to extract depot IDs, hex decryption keys, and manifest IDs.
8. **Depotcache manifest management** — Copying binary `.manifest` files into Steam's `depotcache/` directory so Steam can locate DLC depot metadata.
9. **Orchestration** — A single high-level `GreenLumaOrchestrator` class that composes the above operations into user-visible pipelines: apply a LUA manifest, verify the configuration, fix the AppList.
10. **GUI** — A dedicated `GreenLumaFrame` tab in the application with a status card, six action buttons, a DLC readiness table, and an activity log.
11. **DLC tab integration** — GreenLuma readiness indicators embedded into each DLC row in the existing DLC management tab.
12. **Settings** — Five new `Settings` fields for the Steam path, GreenLuma archive, LUA file, manifest directory, and auto-backup toggle.

---

## 2. Module Map

```text
src/sims4_updater/
├── greenluma/
│   ├── __init__.py           — Package docstring; no exports
│   ├── steam.py              — SteamInfo, detect_steam_path(), get_steam_info(),
│   │                           is_steam_running(), validate_steam_path()
│   ├── applist.py            — AppListState, read/write/backup/add/remove AppList
│   ├── config_vdf.py         — VdfKeyState, read/add/backup/verify depot keys in config.vdf
│   ├── lua_parser.py         — DepotEntry, LuaManifest, parse_lua_string(), parse_lua_file()
│   ├── manifest_cache.py     — ManifestState, read/copy/verify depotcache .manifest files
│   ├── installer.py          — GreenLumaStatus, detect/install/uninstall GreenLuma,
│   │                           kill_steam(), launch_steam_via_greenluma()
│   └── orchestrator.py       — DLCReadiness, ApplyResult, VerifyResult,
│                               GreenLumaOrchestrator (check_readiness, apply_lua, verify,
│                               fix_applist)
├── gui/frames/
│   ├── greenluma_frame.py    — GreenLumaFrame GUI tab
│   ├── dlc_frame.py          — DLC tab with GL header badge and per-row GL pill indicators
│   └── settings_frame.py     — Settings frame with GreenLuma card
└── config.py                 — Settings dataclass with 5 new GreenLuma fields
```

**Source file locations (absolute):**

| Module | Absolute Path |
|--------|---------------|
| `greenluma/steam.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\greenluma\steam.py` |
| `greenluma/applist.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\greenluma\applist.py` |
| `greenluma/config_vdf.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\greenluma\config_vdf.py` |
| `greenluma/lua_parser.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\greenluma\lua_parser.py` |
| `greenluma/manifest_cache.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\greenluma\manifest_cache.py` |
| `greenluma/installer.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\greenluma\installer.py` |
| `greenluma/orchestrator.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\greenluma\orchestrator.py` |
| `gui/frames/greenluma_frame.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\gui\frames\greenluma_frame.py` |
| `gui/frames/dlc_frame.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\gui\frames\dlc_frame.py` |
| `gui/frames/settings_frame.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\gui\frames\settings_frame.py` |
| `config.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\config.py` |

---

## 3. Steam Detection (steam.py)

`steam.py` is a pure detection module. It has no side effects — it does not write any files or modify any state. Its sole responsibility is discovering where Steam is installed, identifying whether GreenLuma is present, and checking whether the Steam process is currently running.

### 3.1 SteamInfo Dataclass

`SteamInfo` is the central value object produced by `get_steam_info()`. It bundles all path computations and the GreenLuma detection result into a single immutable snapshot that is passed to downstream modules (notably `GreenLumaOrchestrator`) to avoid repeated path construction.

```python
@dataclass
class SteamInfo:
    steam_path: Path
    applist_dir: Path             # steam_path / "AppList"
    config_vdf_path: Path         # steam_path / "config" / "config.vdf"
    depotcache_dir: Path          # steam_path / "depotcache"
    steamapps_dir: Path           # steam_path / "steamapps"
    greenluma_installed: bool
    greenluma_mode: str           # "normal" | "stealth" | "none"
```

**Field semantics:**

| Field | Type | Description |
|-------|------|-------------|
| `steam_path` | `Path` | Root of the Steam installation containing `steam.exe`. |
| `applist_dir` | `Path` | `<steam_path>/AppList/` — GreenLuma's numbered .txt files. Always derived as a child of `steam_path`, even if GreenLuma is installed in stealth mode elsewhere. |
| `config_vdf_path` | `Path` | `<steam_path>/config/config.vdf` — Steam's internal VDF configuration file. |
| `depotcache_dir` | `Path` | `<steam_path>/depotcache/` — Binary `.manifest` files keyed by `{depotId}_{manifestId}`. |
| `steamapps_dir` | `Path` | `<steam_path>/steamapps/` — The Steam library directory. Not used by the GL integration directly but included for completeness. |
| `greenluma_installed` | `bool` | `True` if any GreenLuma artifacts were found. |
| `greenluma_mode` | `str` | One of `"normal"`, `"stealth"`, or `"none"`. `"none"` implies `greenluma_installed` is `False`. |

### 3.2 detect_steam_path()

```python
def detect_steam_path() -> Path | None
```

Returns the first Steam installation root directory where `steam.exe` is present, or `None` if Steam cannot be found.

**Detection strategy (in order):**

1. **Registry — 64-bit view**: Opens `HKLM\SOFTWARE\Valve\Steam` with `KEY_WOW64_64KEY`, reads the `InstallPath` value.
2. **Registry — 32-bit view**: Retries with `KEY_WOW64_32KEY` if the 64-bit read fails or yields an invalid path.
3. **Filesystem fallbacks**: Probes three hard-coded paths in sequence:
   - `C:\Program Files (x86)\Steam`
   - `C:\Program Files\Steam`
   - `D:\Steam`

Each candidate is validated by `_has_steam_exe()`, which checks that the directory exists and contains `steam.exe`. The first passing candidate is returned.

The registry constant used is:

```python
_STEAM_REGISTRY_KEY = r"SOFTWARE\Valve\Steam"
_STEAM_REGISTRY_VALUE = "InstallPath"
```

Both registry views are tried because Steam itself is a 32-bit process on 64-bit Windows and writes to the 32-bit (`WOW6432Node`) hive, but some configurations may also have the 64-bit key populated.

### 3.3 GreenLuma Presence Detection

`_detect_greenluma(steam_path)` inspects the Steam directory tree for GreenLuma artifacts and returns a `(bool, str)` tuple of `(installed, mode)`.

**Normal mode detection:**

Both DLLs must be present simultaneously in the Steam root:

```python
_GREENLUMA_DLLS = ("GreenLuma_2025_x64.dll", "GreenLuma_2025_x86.dll")

has_dlls = all(
    (steam_path / dll).is_file() for dll in _GREENLUMA_DLLS
)
if has_dlls:
    return True, "normal"
```

Both DLLs must be present to declare normal mode. A partial DLL set (one DLL missing) does not match.

**Stealth mode detection:**

The code searches for `DLLInjector.ini` or `DLLInjector.exe` in two directories: the Steam root itself, and its immediate parent directory.

```python
for search_dir in (steam_path, steam_path.parent):
    if (search_dir / "DLLInjector.ini").is_file():
        return True, "stealth"
    if (search_dir / "DLLInjector.exe").is_file():
        return True, "stealth"
```

The rationale for checking `steam_path.parent` is that stealth installations commonly place GreenLuma in a sibling directory of the Steam folder (e.g., `C:\Program Files (x86)\GreenLuma\`) alongside the Steam installation at `C:\Program Files (x86)\Steam\`.

### 3.4 is_steam_running()

```python
def is_steam_running() -> bool
```

Uses the Windows `tasklist` command to enumerate all running processes and checks whether `steam.exe` appears in the output (case-insensitive). Returns `False` on any error condition, including non-Windows environments, `tasklist` not found, or timeouts (10-second limit).

This function is called as a guard before any mutation of `config.vdf` (in `config_vdf.add_depot_keys()`) and before the Apply LUA pipeline begins in the orchestrator, because Steam holds an exclusive write lock on `config.vdf` while running.

### 3.5 validate_steam_path()

```python
def validate_steam_path(path: Path) -> bool
```

Performs a four-condition structural validation on a given path to confirm it is a genuine Steam installation, not merely a directory that happens to exist. All four conditions must be met:

1. `path.is_dir()` — The path exists and is a directory.
2. `(path / "steam.exe").is_file()` — The Steam executable is present.
3. `(path / "config").is_dir()` — The `config/` subdirectory exists (this is where `config.vdf` lives).
4. `(path / "depotcache").is_dir()` — The `depotcache/` directory exists.

Returns `False` on any `OSError`.

### 3.6 get_steam_info()

```python
def get_steam_info(steam_path: Path) -> SteamInfo
```

Constructs a `SteamInfo` from a known-valid `steam_path`. Internally calls `_detect_greenluma()` to determine the mode, then assembles all derived paths as attributes. This function does not validate that `steam_path` is a real Steam install — callers are expected to have already run `validate_steam_path()` or `detect_steam_path()` before calling this.

---

## 4. AppList Management (applist.py)

### 4.1 AppList File Format

The AppList is a flat directory (`<Steam>/AppList/`) containing one plain-text file per registered App ID or Depot ID. Files are named with consecutive zero-based integers and a `.txt` extension. Each file contains exactly one numeric Steam ID as its entire content (no extra whitespace, no newlines beyond what is stripped on read).

```
AppList/
  0.txt    "1222670"   # The Sims 4 base app
  1.txt    "1222671"   # A depot ID or DLC app ID
  2.txt    "1222672"
  ...
  N.txt    "..."
```

> **Important:** GreenLuma enforces a hard upper limit of 130 entries. Attempting to write more than 130 files results in a `ValueError` from `write_applist()`.

File naming uses numeric sort order, not lexicographic. The sequence must be contiguous starting from `0`; gaps are avoided by always rewriting the entire directory when adding or removing entries.

### 4.2 AppListState Dataclass

```python
@dataclass
class AppListState:
    entries: dict[str, str]             # filename -> app_id  (e.g. "0.txt" -> "1222670")
    unique_ids: set[str]                # deduplicated set of all IDs
    count: int                          # total file count (including duplicates)
    duplicates: list[tuple[str, str]]   # (filename, duplicate_id) for each duplicate found
```

**Field semantics:**

| Field | Type | Description |
|-------|------|-------------|
| `entries` | `dict[str, str]` | Maps each filename (e.g. `"3.txt"`) to the string App ID stored in that file. Order is not guaranteed by the dict; use `ordered_ids_from_state()` when sequence matters. |
| `unique_ids` | `set[str]` | The set of distinct IDs encountered. Useful for O(1) membership checks. |
| `count` | `int` | Total number of valid (numeric, non-empty) AppList files read. Equal to `len(entries)`. |
| `duplicates` | `list[tuple[str, str]]` | List of `(filename, id)` pairs for every file whose ID was already in `unique_ids` at the time it was read. An AppList with no duplicates has an empty list. |

### 4.3 read_applist()

```python
def read_applist(applist_dir: Path) -> AppListState
```

Reads all AppList files from `applist_dir`. Files are sorted by numeric stem value (`int(p.stem)`) so iteration proceeds in index order. Each file's content is stripped and validated as a pure numeric string (`content.isdigit()`). Files that are empty, non-numeric, or unreadable are skipped with a `WARNING`-level log entry; they do not raise exceptions.

If `applist_dir` does not exist, an empty `AppListState` is returned rather than raising an error. This allows callers to handle the first-run case (no AppList directory yet) without special casing.

### 4.4 write_applist()

```python
def write_applist(applist_dir: Path, app_ids: list[str]) -> int
```

Completely replaces the contents of `applist_dir` with a fresh sequential set of files.

**Procedure:**

1. Deduplicate `app_ids` while preserving the order of first occurrence (using a seen-set pattern).
2. Raise `ValueError` if the deduplicated count exceeds `APPLIST_LIMIT` (130).
3. Create `applist_dir` with `mkdir(parents=True, exist_ok=True)` if it does not exist.
4. Delete all existing AppList files (files matching the `{digit}.txt` pattern).
5. Write each ID to `{idx}.txt` using UTF-8 encoding.

Returns the number of files written (after deduplication). The caller is responsible for creating a backup before calling `write_applist()` if preservation of the previous state is required.

### 4.5 add_ids() and remove_ids()

```python
def add_ids(applist_dir: Path, new_ids: list[str]) -> int
def remove_ids(applist_dir: Path, ids_to_remove: set[str]) -> int
```

Both functions read the current state, compute the new ID list, and call `write_applist()`. They do not perform partial writes — the entire AppList is rewritten on every call.

**`add_ids()` semantics:**

- Reads current state and extracts an ordered ID list via `ordered_ids_from_state()`.
- Iterates `new_ids` and appends any ID not already in `state.unique_ids`.
- If the combined count would exceed `APPLIST_LIMIT`, raises `ValueError` before writing.
- Returns the count of IDs that were actually new (not already present).

**`remove_ids()` semantics:**

- Reads current state and extracts an ordered ID list.
- Filters out all IDs present in `ids_to_remove`.
- Calls `write_applist()` only if at least one ID was actually removed.
- Returns the count of IDs removed. Returns 0 without writing if no IDs matched.

### 4.6 backup_applist()

```python
def backup_applist(applist_dir: Path) -> Path
```

Creates a timestamped sibling directory named `AppList_backup_YYYYMMDD_HHMMSS` alongside `applist_dir`. All `.txt` files in `applist_dir` are copied into the backup directory using `shutil.copy2` (preserving metadata). Returns the `Path` to the backup directory.

The backup is a sibling, not a subdirectory:

```
<Steam>/
  AppList/                        ← active AppList
    0.txt
    1.txt
  AppList_backup_20260221_143022/ ← backup
    0.txt
    1.txt
```

### 4.7 Hard Entry Limit

`APPLIST_LIMIT = 130` is a module-level constant. GreenLuma 2025 stops reading the AppList at index 130, meaning entry `130.txt` and beyond are silently ignored. The `write_applist()` and `add_ids()` functions enforce this limit by raising `ValueError` before writing if it would be exceeded. The error message includes both the would-be count and the limit for clarity.

### 4.8 Duplicate Handling

Duplicates in the AppList cause GreenLuma to process the same App ID twice, which is harmless but wasteful. `read_applist()` detects and records duplicates in `AppListState.duplicates`. The `write_applist()` function always deduplicates before writing. The orchestrator's `fix_applist()` method explicitly reads and rewrites the AppList to collapse duplicates, reporting the count removed.

---

## 5. Config VDF (config_vdf.py)

### 5.1 VDF File Format Overview

Steam's `config/config.vdf` is a hierarchical key-value text file using Valve's VDF (Valve Data Format) syntax. The outer structure is a series of nested `"key" { ... }` blocks delimited by quoted keys and curly-brace bodies. The `"depots"` section within `config.vdf` holds per-depot decryption material:

```
"InstallConfigStore"
{
    "Software"
    {
        "Valve"
        {
            "Steam"
            {
                "depots"
                {
                    "1222671"
                    {
                        "DecryptionKey"    "a1b2c3d4...64hexchars..."
                    }
                    "1222672"
                    {
                        "DecryptionKey"    "e5f6a7b8...64hexchars..."
                        "EncryptedManifests"
                        {
                            ...
                        }
                    }
                }
            }
        }
    }
}
```

Each depot block is identified by its numeric string depot ID as the block name. The `DecryptionKey` field value is a 64-character lowercase hexadecimal string. Depot blocks may optionally contain sub-blocks such as `EncryptedManifests`, which is why a simple regex cannot be used to extract or splice blocks — brace depth tracking is required.

### 5.2 VdfKeyState Dataclass

```python
@dataclass
class VdfKeyState:
    keys: dict[str, str]    # depot_id -> hex_key (64-char hex string)
    total_keys: int         # len(keys)
```

`VdfKeyState` is a read-only snapshot. It is returned by `read_depot_keys()` and used by the orchestrator's `check_readiness()` and `verify()` methods to perform membership checks without re-reading the file on each call.

### 5.3 read_depot_keys()

```python
def read_depot_keys(config_vdf_path: Path) -> VdfKeyState
```

Reads the entire `config.vdf` file as UTF-8 text, then uses `_extract_depot_blocks()` (brace-depth-aware) to locate all top-level depot blocks within the `"depots"` section. For each block, `_extract_key_from_block()` applies a regex to extract the `DecryptionKey` value.

**Raises:**
- `FileNotFoundError` — File does not exist.
- `PermissionError` — File cannot be read.
- `ValueError` — File content is empty after stripping.

The function does not raise if the `"depots"` section is missing or contains no keys — it returns an empty `VdfKeyState` in that case.

### 5.4 add_depot_keys()

```python
def add_depot_keys(
    config_vdf_path: Path,
    new_keys: dict[str, str],
    auto_backup: bool = True,
) -> tuple[int, int]
```

The primary mutation function. Inserts new depot decryption keys or updates existing ones within `config.vdf`.

**Pre-conditions checked before any modification:**
1. `is_steam_running()` — raises `RuntimeError` if Steam is running. Steam holds `config.vdf` open for writing; modifying it while Steam is active produces a corrupted file.
2. `_validate_braces(content)` — raises `ValueError` if the existing file has unbalanced braces, signalling a pre-existing corruption that the function should not compound.

**Per-key decision logic:**
- If `depot_id` is already in the file with the **same key** (case-insensitive hex comparison): skip (no write).
- If `depot_id` is already in the file with a **different key**: update the key value in-place using string replacement within the existing block.
- If `depot_id` does **not** exist in the file: accumulate into `to_insert` and inject all new blocks together before the closing `}` of the `"depots"` section.

**Post-modification validation:** `_validate_braces()` is run again on the modified content before writing. If the resulting content would have unbalanced braces, the function raises `ValueError` and does **not** write the file. The backup (if created) remains intact.

**Returns:** `(added_count, updated_count)` — the counts of newly inserted depot blocks and updated existing keys, respectively.

**Important detail on re-parsing after in-place updates:** After each in-place key update, the function re-parses `existing_blocks` from the modified content because character positions shift. This re-parse loop processes updates one at a time to maintain correct absolute positions for subsequent updates.

### 5.5 verify_keys()

```python
def verify_keys(
    config_vdf_path: Path,
    expected: dict[str, str],
) -> dict
```

Reads the current state of `config.vdf` and compares the found keys against an `expected` mapping (depot ID to expected hex key). Comparison is case-insensitive. Returns a dict with three keys:

| Key | Type | Description |
|-----|------|-------------|
| `"matching"` | `int` | Count of depot IDs found with the correct key value. |
| `"mismatched"` | `list[str]` | Depot IDs found but with a different key value. |
| `"missing"` | `list[str]` | Depot IDs in `expected` not found in the file at all. |

Used by the orchestrator's `verify()` method to produce a `VerifyResult`.

### 5.6 backup_config_vdf()

```python
def backup_config_vdf(config_vdf_path: Path) -> Path
```

Copies `config.vdf` to a timestamped sibling file named `config.vdf.backup_YYYYMMDD_HHMMSS` in the same `config/` directory. Returns the backup path. Raises `FileNotFoundError` if the source does not exist, `PermissionError` if it cannot be copied.

### 5.7 Brace-Depth-Aware Parser

The module implements its own minimal VDF parser rather than relying on an external library. The parser consists of four internal functions:

**`_validate_braces(content)`** — Counts open and close braces character-by-character. Returns `True` if all braces are balanced (depth reaches exactly 0 at end of string with no underflows).

**`_find_depots_section(content)`** — Uses a regex `r'"depots"\s*\{'` to locate the start of the depots block, then tracks brace depth to find the matching closing brace. Returns `(open_brace_pos, close_brace_pos)` as absolute character positions. Raises `ValueError` if no depots section is found or if braces are unbalanced within it.

**`_extract_depot_blocks(content)`** — Locates all top-level depot entries within the depots section body. Each entry is identified by `r'"(\d+)"\s*\{'` and then bounded by tracking brace depth from the opening `{` to the matching `}`. Returns a dict mapping `depot_id -> (block_text, abs_start, abs_end)`. This correctly handles depot blocks that contain nested sub-blocks (e.g. `EncryptedManifests`).

**`_detect_depot_indent(content, depots_start, depots_end)`** — Inspects existing depot entries to determine their indentation level (the number of tab characters prefixed to `"DEPOT_ID"` lines). Falls back to five tabs (`"\t\t\t\t\t"`) if no existing entries are found. This ensures that newly inserted blocks match the surrounding indentation style.

---

## 6. LUA Parser (lua_parser.py)

### 6.1 LUA Manifest Format

GreenLuma companion tools (SteamTools, DepotDownloader wrappers, and various community scripts) distribute DLC information in `.lua` manifest files. These files use a subset of LUA syntax consisting primarily of three types of function call statements:

```lua
-- Base game app ID (no decryption key)
addappid(1222670)

-- Depot with decryption key and optional flag
addappid(1222671, 1, "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2")

-- Manifest ID for the depot
setManifestid(1222671, "7614085668674953551")

-- Additional app IDs
addappid(1222672, 1, "...")
setManifestid(1222672, "...")
```

The three call signatures recognized are:

| Call | Pattern | Captures |
|------|---------|---------|
| `addappid(ID)` or `addappid(ID, FLAGS)` | `_RE_ADDAPPID_NOKEY` | App ID (numeric) |
| `addappid(ID, FLAGS, "HEXKEY")` | `_RE_ADDAPPID_KEY` | App ID and 64-char hex key |
| `setManifestid(DEPOT_ID, "MANIFEST_ID")` | `_RE_MANIFEST` | Depot ID and numeric manifest ID |

The parser treats the first `addappid()` call (with or without a key) as the base app ID. All subsequent IDs are depot IDs or DLC sub-app IDs.

### 6.2 DepotEntry Dataclass

```python
@dataclass
class DepotEntry:
    depot_id: str
    decryption_key: str = ""   # 64-char hex string, or empty string if none
    manifest_id: str = ""      # large numeric string, or empty string if none
```

| Field | Description |
|-------|-------------|
| `depot_id` | The Steam depot ID as a numeric string. |
| `decryption_key` | The hex decryption key from `addappid(..., "key")`. Empty if the depot has no key in the LUA file. |
| `manifest_id` | The manifest ID from `setManifestid(depot_id, "id")`. Empty if no manifest call exists for this depot. |

### 6.3 LuaManifest Dataclass

```python
@dataclass
class LuaManifest:
    app_id: str                                          # first addappid (base game)
    entries: dict[str, DepotEntry]                       # depot_id -> DepotEntry
    all_app_ids: list[str]                               # all IDs in declaration order

    @property
    def keys_count(self) -> int: ...     # entries with non-empty decryption_key
    @property
    def manifests_count(self) -> int: ... # entries with non-empty manifest_id
```

| Field | Description |
|-------|-------------|
| `app_id` | The first App ID declared in the file. For a Sims 4 LUA this will be `"1222670"` (the base game Steam App ID). |
| `entries` | Dict of depot IDs to `DepotEntry` objects for all depots that have a decryption key or manifest ID. Depots with only an `addappid()` call and no key or manifest are represented in `all_app_ids` but not in `entries`. |
| `all_app_ids` | Ordered, deduplicated list of every App ID declared by any `addappid()` call. This list is what the orchestrator inserts into the AppList. |

### 6.4 Regex Patterns

```python
# addappid with decryption key: addappid(ID, FLAGS, "HEX_KEY")
_RE_ADDAPPID_KEY = re.compile(
    r'addappid\(\s*(\d+)\s*,\s*\d+\s*,\s*"([0-9a-fA-F]+)"\s*\)'
)

# addappid without key: addappid(ID) or addappid(ID, FLAGS)
_RE_ADDAPPID_NOKEY = re.compile(
    r'addappid\(\s*(\d+)\s*(?:,\s*\d+\s*)?\)'
)

# setManifestid: setManifestid(DEPOT_ID, "MANIFEST_ID")
_RE_MANIFEST = re.compile(
    r'setManifestid\(\s*(\d+)\s*,\s*"(\d+)"\s*\)'
)
```

The `_RE_ADDAPPID_NOKEY` pattern is a superset: it matches both `addappid(ID)` and `addappid(ID, FLAGS)`. It is used first in a pass to collect all App IDs in order (for `all_app_ids`). The `_RE_ADDAPPID_KEY` pattern is then used in a second pass to extract only the keyed entries (for `entries`).

The `_RE_ADDAPPID_NOKEY` pattern will also match calls that have a key, because `(?:,\s*\d+\s*)?` only captures one optional argument. This is intentional — the NOKEY pass is used only for collecting IDs, not for key extraction. The KEY pass uses a separate, stricter pattern with the quoted hex argument.

### 6.5 parse_lua_string() and parse_lua_file()

```python
def parse_lua_string(content: str) -> LuaManifest
def parse_lua_file(path: Path) -> LuaManifest
```

`parse_lua_file()` reads the file as UTF-8 text and delegates to `parse_lua_string()`. Both raise `ValueError` if the content is empty or if no `addappid()` calls are found. `parse_lua_file()` additionally raises `ValueError` (wrapping the `OSError`) if the file cannot be opened.

### 6.6 Parsing Logic and Pass Order

The parser makes three linear passes over the content, in order:

**Pass 1 — Collect all App IDs (NOKEY pattern):**
Iterates all `addappid()` matches using `_RE_ADDAPPID_NOKEY.finditer()`. Adds each numeric group to `all_app_ids`, skipping duplicates. The first ID encountered becomes `base_app_id`.

**Pass 2 — Extract depot keys (KEY pattern):**
Iterates all `addappid()` matches using `_RE_ADDAPPID_KEY.finditer()`. Creates a `DepotEntry(depot_id, decryption_key=key)` for each match.

**Pass 3 — Associate manifest IDs (MANIFEST pattern):**
Iterates all `setManifestid()` matches using `_RE_MANIFEST.finditer()`. If the depot ID is already in `entries` (from pass 2), sets `manifest_id` on the existing entry. If the depot ID is not in `entries` (i.e. a manifest call exists for a depot with no key), creates a new `DepotEntry(depot_id, manifest_id=manifest_id)`.

This three-pass design means the relative order of `addappid()` and `setManifestid()` calls in the file does not matter.

---

## 7. Manifest Cache (manifest_cache.py)

### 7.1 Depotcache File Format

Steam's `depotcache/` directory holds binary `.manifest` files that describe the content of a specific depot version. These files are referenced by Steam during download and update operations to determine which chunks to fetch. Each file is named using the pattern:

```
{depot_id}_{manifest_id}.manifest
```

For example: `1222671_7614085668674953551.manifest`

The module does **not** parse the binary content of these files. It identifies them purely by filename pattern (underscore separator, `.manifest` extension) and copies them as opaque binary blobs. A depot ID is considered "present" in the depotcache when a file whose name starts with that depot ID followed by an underscore exists.

> **Note:** Only one manifest file per depot ID is tracked. If multiple manifest files for the same depot exist (different manifest ID versions), `read_depotcache()` maps the depot ID to whichever filename it encounters last during iteration. This is a deliberate simplification — Steam's depotcache may contain multiple versions, but the integration only needs to know whether at least one manifest is present.

### 7.2 ManifestState Dataclass

```python
@dataclass
class ManifestState:
    files: dict[str, str]         # depot_id -> full filename
    depot_ids: set[str]           # set of all depot IDs present
    total_count: int              # total .manifest file count
```

| Field | Description |
|-------|-------------|
| `files` | Maps each depot ID (e.g. `"1222671"`) to the full filename of its manifest (e.g. `"1222671_7614085668674953551.manifest"`). Only the most recently iterated file per depot ID is retained when duplicates exist. |
| `depot_ids` | Fast membership-check set equivalent to `set(files.keys())`. |
| `total_count` | Total count of `.manifest` files found (before deduplication by depot ID). May exceed `len(files)` if multiple manifests for the same depot exist. |

### 7.3 read_depotcache()

```python
def read_depotcache(depotcache_dir: Path) -> ManifestState
```

Scans `depotcache_dir` for files with the `.manifest` extension. For each file, extracts the depot ID as the substring before the first underscore (`_parse_depot_id()`). Files without an underscore in their name are skipped.

Returns an empty `ManifestState` if the directory does not exist or cannot be read.

### 7.4 copy_manifests()

```python
def copy_manifests(
    source_dir: Path,
    depotcache_dir: Path,
    overwrite: bool = False,
) -> tuple[int, int]
```

Copies all `.manifest` files from `source_dir` into `depotcache_dir`. Returns `(copied_count, skipped_count)`.

When `overwrite=False` (the default), files whose depot ID already exists in `depotcache_dir` are skipped. The pre-scan of the destination is performed once before the copy loop. When `overwrite=True`, the pre-scan is replaced with an empty `ManifestState`, causing all files to be copied.

Individual copy failures (e.g. permission errors on a single file) are logged as warnings and counted in `skipped_count` rather than aborting the entire operation.

### 7.5 copy_matching_manifests()

```python
def copy_matching_manifests(
    source_dir: Path,
    depotcache_dir: Path,
    depot_ids: set[str],
    overwrite: bool = False,
) -> tuple[int, int]
```

Like `copy_manifests()` but only copies files whose depot ID is a member of `depot_ids`. Files whose depot ID is not in `depot_ids` are ignored entirely (not counted as skipped). Useful when only a specific subset of manifests should be installed.

Returns `(0, 0)` immediately if `depot_ids` is empty.

### 7.6 find_missing_manifests()

```python
def find_missing_manifests(
    depotcache_dir: Path,
    expected_depots: dict[str, str],
) -> list[str]
```

Checks each entry in `expected_depots` (mapping `depot_id -> manifest_id`) against the live depotcache state. A depot is considered missing if the expected filename `{depot_id}_{manifest_id}.manifest` does not match the actual filename found for that depot ID (or no file exists at all for that depot ID).

Returns a list of depot IDs that are missing or have an incorrect manifest version. Used by the orchestrator's `verify()` method to populate `VerifyResult.manifests_missing`.

---

## 8. Installer (installer.py)

`installer.py` handles the binary installation and removal of GreenLuma itself, as well as Steam process management. Unlike the other modules, it requires the third-party `py7zr` package for archive extraction and uses `ctypes` to read Windows PE version resources.

### 8.1 GreenLumaStatus Dataclass

```python
@dataclass
class GreenLumaStatus:
    installed: bool
    version: str            # e.g. "1.7.0", "2025", or "unknown"
    mode: str               # "normal" | "stealth" | "not_installed"
    dll_injector_path: Path | None
    steam_path: Path | None
```

| Field | Description |
|-------|-------------|
| `installed` | `True` if any GreenLuma artifacts were detected. |
| `version` | Version string read from the PE `ProductVersion` resource of `GreenLuma_2025_x64.dll`, or inferred from filenames, or `"unknown"` if detection fails. |
| `mode` | `"normal"` if DLLs are in the Steam dir; `"stealth"` if detected via `DLLInjector.ini` in a sibling dir; `"not_installed"` if absent. |
| `dll_injector_path` | Absolute path to `DLLInjector.exe`, or `None` if not found. This path is passed to `launch_steam_via_greenluma()`. |
| `steam_path` | The Steam root path this status was computed against. |

### 8.2 detect_greenluma()

```python
def detect_greenluma(steam_path: Path) -> GreenLumaStatus
```

Inspects `steam_path` and its surrounding directory for GreenLuma artifacts. The detection is more detailed than `steam.py`'s `_detect_greenluma()`: it also checks for a partial installation (DLLs present but no injector) and attempts to resolve the `dll_injector_path`.

**Detection priority:**
1. Both DLLs and `DLLInjector.exe` in `steam_path` → `mode="normal"`, `dll_injector_path=<steam_path>/DLLInjector.exe`.
2. `DLLInjector.ini` and `DLLInjector.exe` in any stealth candidate directory → `mode="stealth"`, `dll_injector_path=<candidate>/DLLInjector.exe`.
3. Only DLLs in `steam_path` (no injector) → `mode="normal"`, `dll_injector_path=None` (partial install).
4. No artifacts → `installed=False`, `mode="not_installed"`.

Stealth candidates are enumerated by `_stealth_candidates()`: sibling directories of `steam_path` whose names contain `"greenluma"` (case-insensitive), plus `steam_path.parent` itself. The literal string `"greenluma"` is required; the shorter `"gl"` prefix was rejected because it matches too many unrelated directory names (e.g. `opengl`, `anglegl`).

### 8.3 install_greenluma()

```python
def install_greenluma(
    archive_path: Path,
    steam_path: Path,
    stealth: bool = False,
) -> GreenLumaStatus
```

Extracts a GreenLuma `.7z` archive. Requires `py7zr` to be installed; raises `RuntimeError` with an install hint if it is absent.

**Target directory determination:**
- `stealth=False`: `target_dir = steam_path` (normal mode — files go directly into Steam).
- `stealth=True`: `target_dir = steam_path.parent / "GreenLuma"` (stealth mode — sibling directory created if needed).

**Extraction procedure:**
1. Validate `archive_path` exists and `steam_path` is a directory.
2. Open the archive with `py7zr.SevenZipFile` in read mode.
3. Call `_validate_archive_paths()` on all entry names before extraction (path traversal protection — see section 8.4).
4. Detect whether the archive has a single root subdirectory (e.g. `GreenLuma_2025_1.7.0/`) by checking whether all filenames share a common prefix.
5. Extract all files to `target_dir`.
6. If a single root subdirectory was detected, call `_move_gl_files_up()` to flatten the files into `target_dir` (see section 8.5).
7. Ensure `<steam_path>/AppList/` exists (always in Steam root, regardless of stealth mode).
8. Record the install manifest via `_save_install_manifest()`.
9. Call `detect_greenluma(steam_path)` and return the result.

### 8.4 Path Traversal Protection

Before extraction begins, `_validate_archive_paths()` is called with the full list of filenames from the archive:

```python
def _validate_archive_paths(names: list[str], target_dir: Path) -> None:
    resolved_target = target_dir.resolve()
    for name in names:
        entry_path = (target_dir / name).resolve()
        if not str(entry_path).startswith(str(resolved_target)):
            raise ValueError(
                f"Archive contains path traversal entry: {name!r}"
            )
```

Each archive entry is resolved to an absolute path and checked against the resolved target directory. Any entry that resolves outside the target (e.g. via `../` sequences) raises `ValueError` before extraction begins, leaving no files on disk.

### 8.5 Subdirectory Flattening

GreenLuma archives commonly contain a root subdirectory named with the version string (e.g. `GreenLuma_2025_1.7.0/`). After extraction this produces:

```
<target_dir>/
  GreenLuma_2025_1.7.0/
    GreenLuma_2025_x64.dll
    GreenLuma_2025_x86.dll
    DLLInjector.exe
    ...
```

The installer detects this pattern by checking whether all archive entries share a common first path component. If so, `_move_gl_files_up()` is called to move only the known GreenLuma files and directories up one level:

```python
_GL_KNOWN_FILES = {
    "GreenLuma_2025_x64.dll",
    "GreenLuma_2025_x86.dll",
    "DLLInjector.exe",
    "DLLInjector.ini",
    "GreenLumaSettings_2025.exe",
    "AchievementUnlocker_2025.exe",
    "User32.dll",
}
_GL_KNOWN_DIRS = {"AppList"}
```

Only files and directories in these sets are moved. Any files in the subdirectory that are not in the known-file set (and do not already exist in `target_dir`) are also moved, but known-file-set files always overwrite. Critically, directories not in `_GL_KNOWN_DIRS` (e.g. `config/`, `steamapps/`) are never moved, preventing accidental overwriting of existing Steam directories.

### 8.6 Install Manifest Tracking

After installation, `_save_install_manifest()` writes a JSON file at `get_app_dir() / "greenluma_install.json"`:

```json
{
  "install_dir": "C:\\Program Files (x86)\\Steam",
  "files": [
    "GreenLuma_2025_x64.dll",
    "GreenLuma_2025_x86.dll",
    "DLLInjector.exe",
    "AppList\\0.txt"
  ],
  "installed_at": "2026-02-21T14:30:22.123456"
}
```

The `files` list contains paths relative to `install_dir`, collected by `_collect_gl_files()`. This manifest is used by `uninstall_greenluma()` to remove exactly the files that were installed, avoiding accidental deletion of non-GreenLuma files.

### 8.7 uninstall_greenluma()

```python
def uninstall_greenluma(steam_path: Path) -> tuple[int, int]
```

Returns `(files_removed, files_failed)`.

**Primary path — manifest-based removal:**
If `greenluma_install.json` exists, loads it and deletes each listed file path. AppList `.txt` files are also cleaned from `<steam_path>/AppList/` (the directory itself is preserved).

**Fallback path — scanning removal:**
If no install manifest exists, scans `steam_path` and all stealth candidate directories for files in `_GL_KNOWN_FILES` and deletes them.

In both cases, the install manifest itself is deleted at the end (best-effort; no error if missing).

### 8.8 kill_steam()

```python
def kill_steam() -> bool
```

Terminates the Steam process using `taskkill /F /IM steam.exe`. Returns `True` if Steam is not running after the operation (either because it was not running before, or because `taskkill` succeeded). Waits 2 seconds after the kill command before checking again. Returns `False` if the process could not be terminated.

### 8.9 launch_steam_via_greenluma()

```python
def launch_steam_via_greenluma(
    dll_injector_path: Path,
    force: bool = False,
) -> bool
```

Starts `DLLInjector.exe` as a detached process using `subprocess.Popen` with `DETACHED_PROCESS` creation flag. The working directory is set to `dll_injector_path.parent` so the injector can locate its configuration files relative to itself.

When `force=False` (default), the function refuses to launch if Steam is already running. The `force=True` flag bypasses this check and is used by the GUI's kill-then-launch flow (see section 10.8), where the caller has already confirmed that Steam was terminated before calling this function.

Returns `True` if `Popen` succeeds, `False` on `OSError`.

### 8.10 Version Detection

`_detect_version(search_dir)` attempts to read the `ProductVersion` from the PE version resource of `GreenLuma_2025_x64.dll` using the Windows `version.dll` API via `ctypes`. The `VS_FIXEDFILEINFO` structure is queried with `VerQueryValueW`. If successful, the major/minor/patch fields are formatted as `"{major}.{minor}.{patch}"`.

If PE version reading fails, the function falls back to scanning filenames in `search_dir` for version hints (`"1.7"` → `"1.7.0"`, `"1.6"` → `"1.6.x"`). If the DLL is present but no version hint matches, `"2025"` is returned as a generic label. If no DLL is found, `"unknown"` is returned.

---

## 9. Orchestrator (orchestrator.py)

`GreenLumaOrchestrator` is the facade that composes all backend modules into the three high-level operations exposed to the GUI: checking DLC readiness, applying a LUA manifest, and verifying the configuration. It holds a `SteamInfo` reference and calls the appropriate module functions with the correct paths.

### 9.1 DLCReadiness Dataclass

```python
@dataclass
class DLCReadiness:
    dlc_id: str
    name: str
    steam_app_id: int
    in_applist: bool = False
    has_key: bool = False
    has_manifest: bool = False

    @property
    def ready(self) -> bool:
        return self.in_applist and self.has_key and self.has_manifest
```

One `DLCReadiness` instance is produced per DLC that has a `steam_app_id` in the catalog. The `ready` property is `True` only when all three conditions are satisfied simultaneously:

| Condition | Source |
|-----------|--------|
| `in_applist` | `steam_app_id` as a string is in `AppListState.unique_ids` |
| `has_key` | `steam_app_id` as a string is in `VdfKeyState.keys` |
| `has_manifest` | `steam_app_id` as a string is in `ManifestState.depot_ids` |

Note that the readiness check uses `steam_app_id` (the DLC's Steam store ID) for all three checks. This means readiness reflects whether GreenLuma is configured for the DLC's Steam App ID, not the individual depot IDs that may make up the DLC's content.

### 9.2 ApplyResult Dataclass

```python
@dataclass
class ApplyResult:
    keys_added: int = 0
    keys_updated: int = 0
    manifests_copied: int = 0
    manifests_skipped: int = 0
    applist_entries_added: int = 0
    lua_total_keys: int = 0
    lua_total_manifests: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0
```

| Field | Description |
|-------|-------------|
| `keys_added` | New depot blocks inserted into `config.vdf`. |
| `keys_updated` | Existing depot blocks whose key value was changed. |
| `manifests_copied` | `.manifest` files successfully copied to `depotcache/`. |
| `manifests_skipped` | `.manifest` files that were already present (or failed to copy). |
| `applist_entries_added` | New App IDs written to the AppList. |
| `lua_total_keys` | Count of keyed `addappid()` entries in the parsed LUA. |
| `lua_total_manifests` | Count of `setManifestid()` entries in the parsed LUA. |
| `errors` | List of error message strings from any step that failed. Non-empty means `success` is `False`. |

### 9.3 VerifyResult Dataclass

```python
@dataclass
class VerifyResult:
    keys_in_vdf: int = 0
    keys_expected: int = 0
    keys_matching: int = 0
    keys_mismatched: list[str] = field(default_factory=list)
    keys_missing: list[str] = field(default_factory=list)
    manifests_in_cache: int = 0
    manifests_expected: int = 0
    manifests_missing: list[str] = field(default_factory=list)
    applist_count: int = 0
    applist_duplicates: int = 0
    errors: list[str] = field(default_factory=list)
```

| Field | Description |
|-------|-------------|
| `keys_in_vdf` | Total depot keys present in `config.vdf` (regardless of LUA). |
| `keys_expected` | Number of keyed entries from the provided LUA file. |
| `keys_matching` | Entries from LUA where the key in `config.vdf` matches (case-insensitive). |
| `keys_mismatched` | Depot IDs present in `config.vdf` with a different key than the LUA. |
| `keys_missing` | Depot IDs from the LUA not found in `config.vdf` at all. |
| `manifests_in_cache` | Total `.manifest` files in `depotcache/` (all depots, not just Sims 4). |
| `manifests_expected` | Number of `setManifestid()` entries from the LUA. |
| `manifests_missing` | Depot IDs from the LUA for which the expected manifest file is absent or mismatched. |
| `applist_count` | Total AppList entry count. |
| `applist_duplicates` | Count of duplicate entries in the AppList. |
| `errors` | Read errors from any of the three data sources. |

When `verify()` is called without a `lua_path`, the `*_expected`, `*_matching`, `*_mismatched`, and `*_missing` fields remain at their zero/empty defaults. Only the structural counts (`keys_in_vdf`, `manifests_in_cache`, `applist_count`, `applist_duplicates`) are populated.

### 9.4 GreenLumaOrchestrator Class

```python
class GreenLumaOrchestrator:
    def __init__(self, steam_info: SteamInfo): ...
    def check_readiness(self, catalog) -> list[DLCReadiness]: ...
    def apply_lua(
        self,
        lua_path: Path,
        manifest_source_dir: Path | None = None,
        auto_backup: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> ApplyResult: ...
    def verify(self, lua_path: Path | None = None) -> VerifyResult: ...
    def fix_applist(self, catalog) -> tuple[int, int]: ...
```

The orchestrator is constructed with a `SteamInfo` instance and uses `self.steam.*` paths for all file operations. It has no mutable state beyond the constructor argument.

### 9.5 check_readiness()

```python
def check_readiness(self, catalog) -> list[DLCReadiness]
```

Performs three reads at the start:

```python
al_state = applist.read_applist(self.steam.applist_dir)
vdf_state = config_vdf.read_depot_keys(self.steam.config_vdf_path)
mc_state = manifest_cache.read_depotcache(self.steam.depotcache_dir)
```

Then iterates all DLCs in the catalog that have a `steam_app_id`, performing O(1) membership checks against the pre-read state objects. This single-pass design means the three files are each read exactly once regardless of how many DLCs are in the catalog.

### 9.6 apply_lua() — Five-Step Pipeline

The `apply_lua()` method is the primary user-facing operation in the GreenLuma tab. It executes five steps in sequence:

**Step 0 — Steam process check:**
Calls `is_steam_running()`. If Steam is running, appends an error to `result.errors` and returns immediately. `config.vdf` cannot be safely modified while Steam holds it open.

**Step 1 — Parse LUA:**
Calls `lua_parser.parse_lua_file(lua_path)`. Populates `result.lua_total_keys` and `result.lua_total_manifests`. On failure, appends error and returns.

**Step 2 — Backup:**
If `auto_backup=True`, creates backups of `config.vdf` and the AppList directory. Backup failures are logged as warnings but do not abort the pipeline (non-fatal).

**Step 3 — Add keys to config.vdf:**
Builds `keys_to_add = {depot_id: entry.decryption_key for ...}` from all entries that have a non-empty decryption key. Calls `config_vdf.add_depot_keys()` with `auto_backup=False` (the orchestrator already created the backup in step 2). Populates `result.keys_added` and `result.keys_updated`.

**Step 4 — Copy manifests:**
If `manifest_source_dir` is provided and exists, calls `manifest_cache.copy_manifests()`. Populates `result.manifests_copied` and `result.manifests_skipped`. If the directory was provided but does not exist, a warning is logged but the step is skipped without error.

**Step 5 — Update AppList:**
Calls `applist.add_ids(self.steam.applist_dir, lua.all_app_ids)`. This adds all App IDs from the LUA — both keyed depots and non-keyed app IDs — to the AppList, skipping any already present. Populates `result.applist_entries_added`.

**Progress callbacks:** If `progress` is provided, each step logs a human-readable message through it. The GUI uses this to stream messages to the Activity Log in real time from the background thread.

### 9.7 verify()

```python
def verify(self, lua_path: Path | None = None) -> VerifyResult
```

Always reads the three data sources (AppList, `config.vdf`, `depotcache`). If `lua_path` is provided, performs a detailed cross-reference:

- **Key verification**: Extracts expected keys from the LUA's keyed entries, then calls `config_vdf.verify_keys()` for case-insensitive comparison.
- **Manifest verification**: Extracts expected `{depot_id: manifest_id}` from the LUA's manifest entries, then calls `manifest_cache.find_missing_manifests()` to identify gaps.

Read errors from any data source are appended to `result.errors` and do not abort the verify — the other sources are still checked.

### 9.8 fix_applist()

```python
def fix_applist(self, catalog) -> tuple[int, int]
```

Returns `(duplicates_removed, missing_added)`.

Reads the current AppList state, collects expected IDs from all catalog DLCs that have a `steam_app_id`, computes the set difference to find missing IDs, then calls `write_applist()` with a merged, deduplicated ordered list. The write happens only if there are duplicates to remove or missing IDs to add — otherwise no file I/O occurs.

---

## 10. GUI Frame (greenluma_frame.py)

`GreenLumaFrame` is a `ctk.CTkFrame` subclass that follows the standard frame lifecycle defined in the application's GUI layer (see Architecture and Developer Guide, section 6.3).

### 10.1 Frame Layout and Widget Structure

The frame is divided into two vertical zones using a `grid_rowconfigure(1, weight=1)` split:

```
Row 0 (fixed height): "top" container
  ├── Heading label ("GreenLuma Manager")
  ├── Subheading label
  ├── Status Card (InfoCard)
  └── Action Button Row (6 buttons)
Row 1 (weight=1, expands): "body" container
  ├── Row 0 (weight=1): DLC Readiness Panel
  │   ├── Header row (label + filter buttons)
  │   └── Readiness textbox (CTkTextbox, monospace)
  └── Row 1 (weight=1): Activity Log
      ├── Header row (label + Clear button)
      └── Log textbox (CTkTextbox, monospace)
```

All widgets use `padx=30` horizontal insets from the frame edges. No scrollable container wraps the top section — the status card and buttons are always visible. The body section splits its available height equally between the readiness panel and the log.

### 10.2 Status Card Fields

The `InfoCard` in the top section has four rows:

| Row | Label | Widget | Initial State |
|-----|-------|--------|---------------|
| 0 | "Steam Path" | `StatusBadge` (`_steam_path_badge`) | `"Detecting..."` / `muted` |
| 1 | "GreenLuma" | `StatusBadge` (`_gl_badge`) | `"Unknown"` / `muted` |
| 2 | "Steam" | `StatusBadge` (`_steam_status_badge`) | `"Checking..."` / `muted` |
| 3 | "Summary" | `StatusBadge` (`_summary_badge`) | `"..."` / `muted` |

After a successful `_refresh_status()` call:

- **Steam Path badge**: Shows a truncated path string (`"..." + last 37 chars` if over 40 chars) with `"success"` style, or `"Not Found"` with `"error"` style.
- **GreenLuma badge**: Shows `"v{version} ({Mode})"` with `"success"` style, or `"Not Installed"` with `"warning"` style.
- **Steam badge**: Shows `"Running"` with `"warning"` style (yellow — Steam must be closed to apply LUA), or `"Not Running"` with `"success"` style.
- **Summary badge**: Shows `"All N DLCs ready"` with `"success"`, or `"{ready}/{total} DLCs ready"` with `"warning"`, or `"No DLC data"` with `"muted"`.

### 10.3 Action Buttons

Six buttons are arranged in a single row with equal column weights:

| Button | Label | Color | Action |
|--------|-------|-------|--------|
| `_install_btn` | "Install (Normal)" | `accent` (bold) | `_on_install_gl(stealth=False)` |
| `_install_stealth_btn` | "Install (Stealth)" | `bg_card_alt` | `_on_install_gl(stealth=True)` |
| `_uninstall_btn` | "Uninstall GL" | `bg_card_alt` | `_on_uninstall_gl()` |
| `_launch_btn` | "Launch via GL" | `bg_card_alt` | `_on_launch_gl()` |
| `_apply_lua_btn` | "Apply LUA" | `accent` (bold) | `_on_apply_lua()` |
| `_fix_btn` | "Fix AppList" | `bg_card_alt` | `_on_fix_applist()` |

All six buttons are disabled simultaneously via `_set_busy(True)` when any background operation is running. The `_busy` flag prevents re-entrant operations.

### 10.4 DLC Readiness Panel

The readiness panel (`_readiness_box`) is a `CTkTextbox` in monospace font (`theme.FONT_MONO`) set to `state="disabled"` and `wrap="none"`. Content is written by `_update_readiness_display()`, which formats a fixed-width table:

```
DLC      Name                             App  Key  Man  Status
----------------------------------------------------------------------
EP01     Get to Work                        Y    Y    Y  Ready
EP02     Get Together                       Y    Y    -  Incomplete
GP01     Outdoor Retreat                    -    -    -  Incomplete
```

Column widths: DLC ID (`<8`), name (truncated to 30 chars, `<32`), App (`>3`), Key (`>3`), Man (`>3`), Status.

Three filter buttons above the textbox ("All", "Ready", "Incomplete") control which rows are displayed. Clicking a filter button calls `_set_filter(label)`, which updates the active button's color to `theme.COLORS["accent"]` and the others to `theme.COLORS["bg_card_alt"]`, then calls `_update_readiness_display()` to regenerate the table content.

### 10.5 Activity Log

The activity log (`_log_box`) is a `CTkTextbox` with `wrap="word"`. New entries are prepended with a `[HH:MM:SS]` timestamp. The `_log()` method temporarily sets the textbox to `state="normal"`, inserts the line, scrolls to end, and re-disables it. This is always called from the GUI thread.

The `_enqueue_log()` wrapper calls `self.app._enqueue_gui(self._log, msg)`, making it safe to call from background threads. The orchestrator's `progress` callback in `apply_lua()` is wired to `_enqueue_log`, so all pipeline step messages appear in the log in real time.

The "Clear" button calls `_clear_log()`, which deletes all content from the textbox.

### 10.6 Async Execution Model

All background work uses `self.app.run_async(bg_func, on_done=..., on_error=...)`. The `run_async` method submits `bg_func` to the application's single-worker `ThreadPoolExecutor`. The `on_done` callback is enqueued back to the GUI thread via `_enqueue_gui()` and executed within the 100ms polling loop.

Error callbacks are always defined on every `run_async()` call. They uniformly: call `_set_busy(False)`, log the error to the Activity Log via `_enqueue_log()`, and show a toast notification via `self.app.show_toast(message, "error")`.

Instance state that is set from `on_done` callbacks (`self._steam_info`, `self._gl_status`, `self._readiness`) is always set on the GUI thread, not in the background function. Background functions return their results as return values, which `run_async` passes to `on_done`.

### 10.7 Install Flow

`_on_install_gl(stealth)` implements the following logic:

1. If `_busy` or `_steam_info is None`: show a toast and return.
2. Read `self.app.settings.greenluma_archive_path`. If empty or the file does not exist, open a file dialog to let the user select the archive. Save the selection back to settings.
3. Call `_set_busy(True)` and log the operation start.
4. Background: call `installer.install_greenluma(archive_path, steam_path, stealth=stealth)`.
5. Done: update `_gl_status`, update `_gl_badge`, show a success or warning toast.
6. Error: call `_set_busy(False)`, log error, show error toast.

The uninstall flow (`_on_uninstall_gl`) additionally shows a `tkinter.messagebox.askyesno` confirmation dialog before proceeding. If the user declines, the function returns without any background work.

### 10.8 Steam-Restart Dialog Flow

`_on_launch_gl()` checks `is_steam_running()` synchronously on the GUI thread (acceptable because `tasklist` is fast). If Steam is running, it shows a `tkinter.messagebox.askyesno` dialog:

```
"Steam must be closed to launch via GreenLuma.
Would you like to close Steam and relaunch via GreenLuma?"
```

If the user confirms:
1. `_launch_gl_with_kill()` is called, which runs `installer.kill_steam()` in the background.
2. `on_done` checks success: if Steam was killed, calls `_launch_gl_direct()` as a second async operation.
3. `_launch_gl_direct()` calls `installer.launch_steam_via_greenluma(injector_path, force=True)`.

If Steam is not running, `_launch_gl_direct()` is called immediately without the kill step.

### 10.9 Apply LUA Pre-Population from Settings

When the user clicks "Apply LUA", two file dialogs are shown sequentially. Both are pre-populated from settings:

**LUA file dialog:**
```python
initial_lua = self.app.settings.greenluma_lua_path
if initial_lua:
    lua_kwargs["initialdir"] = str(Path(initial_lua).parent)
    lua_kwargs["initialfile"] = Path(initial_lua).name
```
The dialog opens in the directory of the previously selected LUA file with its name pre-filled. After selection, the path is saved back to `settings.greenluma_lua_path`.

**Manifest directory dialog:**
```python
initial_manifest = self.app.settings.greenluma_manifest_dir
if not initial_manifest and self._steam_info:
    initial_manifest = str(self._steam_info.depotcache_dir)
```
Defaults to the Steam depotcache directory if no manifest directory has been configured. The dialog title notes that it can be cancelled to skip manifest copying. If cancelled (`manifest_dir` is empty string), `manifest_dir_path` is set to `None`, and the orchestrator skips step 4.

After both dialogs are handled (regardless of cancellation of the manifest dialog), `settings.save()` is called to persist both the LUA path and manifest directory selections.

---

## 11. DLC Tab Integration (dlc_frame.py)

The DLC management tab integrates GreenLuma readiness indicators non-intrusively. The integration is "best-effort": if GreenLuma is not configured or the detection fails, no indicator is shown and no error is raised.

### 11.1 Header Badge

A `CTkLabel` widget is created in the DLC frame's header alongside the "DLC Management" title:

```python
self._gl_badge = ctk.CTkLabel(
    header_frame,
    text="\u2714 GreenLuma Installed",   # "✔ GreenLuma Installed"
    font=ctk.CTkFont(size=10, weight="bold"),
    text_color=theme.COLORS["success"],
)
```

The badge is **hidden by default** (no `.grid()` call at construction). When `_on_states_loaded()` receives a result with `gl_installed=True`, the badge is shown:

```python
if gl_installed:
    self._gl_badge.grid(row=1, column=0, sticky="w", pady=(2, 0))
else:
    self._gl_badge.grid_remove()
```

This places the checkmark badge as a subtitle line below the "DLC Management" heading, visible in green only when GreenLuma is detected.

### 11.2 GL Pill Badges on DLC Rows

Each DLC row card in the scrollable list receives an optional "GL" pill badge based on the DLC's `DLCReadiness` entry in `_gl_readiness`:

```python
gl_r = self._gl_readiness.get(dlc.id)
if gl_r is not None:
    gl_color = (
        theme.COLORS["success"] if gl_r.ready else theme.COLORS["warning"]
    )
    gl_pill = ctk.CTkFrame(
        row_frame,
        corner_radius=8,
        border_width=1,
        border_color=gl_color,
        ...
    )
    ctk.CTkLabel(gl_pill, text="GL", ...).pack(padx=5, pady=1)
```

The pill is:
- **Green border, green "GL" text** when `gl_r.ready` is `True` (all three: AppList, key, manifest).
- **Yellow/warning border, yellow "GL" text** when `gl_r.ready` is `False`.

A hover tooltip is attached to each pill that shows which specific components are missing:

```
"Missing: AppList, Key"
"Missing: Manifest"
"GreenLuma Ready"
```

The tooltip is a floating `CTkLabel` placed at the screen coordinates of the pill widget using `winfo_rootx()` / `winfo_rooty()`. It is created on `<Enter>` and destroyed on `<Leave>`.

### 11.3 Readiness Data Loading

GreenLuma readiness data is loaded inside `_get_dlc_states()`, which runs in the background thread alongside the DLC state scan. The code is wrapped in a bare `except Exception: pass` block to ensure that GL detection failures never break the DLC tab:

```python
try:
    from ...greenluma.orchestrator import GreenLumaOrchestrator
    from ...greenluma.steam import detect_steam_path, get_steam_info

    steam_path_str = self.app.settings.steam_path
    steam_path = (
        Path(steam_path_str) if steam_path_str else detect_steam_path()
    )
    if steam_path and steam_path.is_dir():
        info = get_steam_info(steam_path)
        gl_installed = info.greenluma_installed
        orch = GreenLumaOrchestrator(info)
        catalog = DLCCatalog()
        for r in orch.check_readiness(catalog):
            gl_readiness[r.dlc_id] = r
except Exception:
    pass
```

The result is returned as a three-tuple `(states, gl_readiness, gl_installed)` and unpacked in `_on_states_loaded()`.

---

## 12. Settings Integration (config.py and settings_frame.py)

### 12.1 New Settings Fields

Five fields were added to the `Settings` dataclass in `config.py`:

```python
@dataclass
class Settings:
    # ... existing fields ...
    steam_path: str = ""                    # Steam installation directory
    greenluma_archive_path: str = ""        # Path to GreenLuma 7z archive
    greenluma_auto_backup: bool = True      # Backup before mutations
    greenluma_lua_path: str = ""            # Path to .lua manifest file
    greenluma_manifest_dir: str = ""        # Path to .manifest source directory
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `steam_path` | `str` | `""` | Steam installation root (e.g. `C:\Program Files (x86)\Steam`). Auto-detected and stored on first successful detection in either the GreenLuma frame or DLC frame. |
| `greenluma_archive_path` | `str` | `""` | Absolute path to the GreenLuma `.7z` archive. Stored after the user selects it in the install dialog in `GreenLumaFrame`. |
| `greenluma_auto_backup` | `bool` | `True` | When `True`, the orchestrator creates timestamped backups of `config.vdf` and the AppList before each `apply_lua()` call. |
| `greenluma_lua_path` | `str` | `""` | Last-used `.lua` manifest file path. Used to pre-populate the LUA file dialog on subsequent Apply LUA invocations. |
| `greenluma_manifest_dir` | `str` | `""` | Last-used manifest source directory. Used to pre-populate the manifest directory dialog. Falls back to the Steam `depotcache/` directory if empty. |

All five fields are serialized as part of `settings.json` via the `asdict()` + `json.dump()` path in `Settings.save()`. Unknown keys in the JSON file are filtered out on load (future-proofing), but these five fields persist correctly across application restarts.

**Auto-save of `steam_path`:**
The GreenLuma frame auto-saves `steam_path` when it is detected automatically (and the settings field was previously empty):

```python
if steam_path and not self.app.settings.steam_path:
    self.app.settings.steam_path = str(steam_path)
    self.app.settings.save()
```

This is called from the `on_done` callback of `_refresh_status()`, which runs on the GUI thread.

### 12.2 GreenLuma Card in Settings Frame

The Settings frame has two cards: Card 1 (General settings) and Card 2 (GreenLuma settings). Card 2 is labeled "GreenLuma" with the subtitle "Settings for Steam DLC downloads via GreenLuma" and contains five form rows:

| Row | Control | Settings Field |
|-----|---------|----------------|
| Steam Path | Entry + Browse button (directory) | `steam_path` |
| GreenLuma Archive | Entry + Browse button (`.7z` files) | `greenluma_archive_path` |
| LUA Manifest File | Entry + Browse button (`.lua` files) | `greenluma_lua_path` |
| Manifest Files Directory | Entry + Browse button (directory) | `greenluma_manifest_dir` |
| Auto-backup toggle | `CTkCheckBox` | `greenluma_auto_backup` |

Each row with a Browse button shows a `filedialog.askopenfilename()` or `filedialog.askdirectory()` dialog filtered to the appropriate file type. The Manifest Files Directory row includes a descriptive subtitle label: "Directory containing .manifest files (defaults to Steam depotcache)".

Separator lines (`height=1, fg_color=theme.COLORS["separator"]`) appear between each row to visually organize the card.

### 12.3 Save and Load Behavior

`SettingsFrame._save_settings()` reads all GreenLuma card fields and writes them to the `Settings` object before calling `settings.save()`:

```python
settings.steam_path = self._steam_path_entry.get().strip()
settings.greenluma_archive_path = self._gl_archive_entry.get().strip()
settings.greenluma_lua_path = self._gl_lua_entry.get().strip()
settings.greenluma_manifest_dir = self._gl_manifest_dir_entry.get().strip()
settings.greenluma_auto_backup = self._gl_auto_backup_var.get()
```

`SettingsFrame._load_settings_to_ui()` populates the fields from the loaded settings:

```python
if settings.steam_path:
    self._steam_path_entry.insert(0, settings.steam_path)
if settings.greenluma_archive_path:
    self._gl_archive_entry.insert(0, settings.greenluma_archive_path)
if settings.greenluma_lua_path:
    self._gl_lua_entry.insert(0, settings.greenluma_lua_path)
if settings.greenluma_manifest_dir:
    self._gl_manifest_dir_entry.insert(0, settings.greenluma_manifest_dir)
self._gl_auto_backup_var.set(settings.greenluma_auto_backup)
```

---

## 13. Data Flow Diagrams

### 13.1 Install Flow

```
User clicks "Install (Normal)" or "Install (Stealth)"
    │
    ├── Read settings.greenluma_archive_path
    │       │
    │       ├── Path exists and is file?
    │       │   └── Yes → use it
    │       └── No → open filedialog.askopenfilename()
    │               └── User selects .7z → save to settings
    │
    ├── _set_busy(True)
    ├── _log("--- Installing GreenLuma (Normal|Stealth) ---")
    │
    └── run_async(_bg):
            │
            └── installer.install_greenluma(archive, steam_path, stealth)
                    │
                    ├── Validate archive exists
                    ├── Validate steam_path exists
                    ├── Determine target_dir
                    │   ├── normal: target_dir = steam_path
                    │   └── stealth: target_dir = steam_path.parent / "GreenLuma"
                    │
                    ├── py7zr.SevenZipFile.getnames()
                    ├── _validate_archive_paths()  ← path traversal check
                    ├── Detect single root subdirectory prefix
                    ├── z.extractall(target_dir)
                    ├── _move_gl_files_up() if prefix detected
                    ├── Ensure AppList/ directory exists
                    ├── _collect_gl_files() → _save_install_manifest()
                    └── detect_greenluma(steam_path) → GreenLumaStatus
                            │
                            └── on_done(_done):
                                    ├── _set_busy(False)
                                    ├── Update _gl_badge
                                    └── show_toast(success|warning)
```

### 13.2 Apply LUA Flow

```
User clicks "Apply LUA"
    │
    ├── Guard: _busy or not _steam_info? → toast and return
    │
    ├── filedialog.askopenfilename(*.lua)
    │   └── Pre-populate from settings.greenluma_lua_path
    │   └── Save path to settings.greenluma_lua_path
    │
    ├── filedialog.askdirectory()
    │   └── Pre-populate from settings.greenluma_manifest_dir
    │       or _steam_info.depotcache_dir
    │   └── Save to settings.greenluma_manifest_dir
    │
    ├── settings.save()
    ├── _set_busy(True)
    ├── _log("--- Applying LUA Manifest ---")
    │
    └── run_async(_bg):
            │
            └── GreenLumaOrchestrator(steam_info).apply_lua(
                    lua_path, manifest_source_dir, auto_backup, progress=_enqueue_log
                )
                    │
                    ├── Step 0: is_steam_running()?
                    │   └── Yes → error, return
                    │
                    ├── Step 1: lua_parser.parse_lua_file(lua_path)
                    │   ├── Parse addappid() calls (3 regex passes)
                    │   └── Returns LuaManifest (app_id, entries, all_app_ids)
                    │
                    ├── Step 2: Backup (if auto_backup=True)
                    │   ├── config_vdf.backup_config_vdf()
                    │   └── applist.backup_applist()
                    │
                    ├── Step 3: config_vdf.add_depot_keys(keys_to_add)
                    │   ├── Validate braces pre-modification
                    │   ├── For each key: skip / update / insert
                    │   ├── Validate braces post-modification
                    │   └── Write config.vdf
                    │
                    ├── Step 4: manifest_cache.copy_manifests()
                    │   └── Copy .manifest files to depotcache/
                    │
                    └── Step 5: applist.add_ids(all_app_ids)
                                └── Write AppList files

                    → ApplyResult
                            │
                            └── on_done(_done):
                                    ├── _set_busy(False)
                                    ├── Log summary counts
                                    ├── show_toast(success|warning)
                                    └── _refresh_status()
```

### 13.3 DLC Readiness Check Flow

```
GreenLumaFrame.on_show() or post-apply _refresh_status()
    │
    └── run_async(_bg):
            │
            ├── Read settings.steam_path (or auto-detect)
            ├── get_steam_info(steam_path) → SteamInfo
            ├── installer.detect_greenluma(steam_path) → GreenLumaStatus
            ├── is_steam_running() → bool
            │
            └── GreenLumaOrchestrator(info).check_readiness(DLCCatalog())
                    │
                    ├── applist.read_applist(applist_dir) → AppListState
                    ├── config_vdf.read_depot_keys(config_vdf_path) → VdfKeyState
                    ├── manifest_cache.read_depotcache(depotcache_dir) → ManifestState
                    │
                    └── For each DLC with steam_app_id:
                            DLCReadiness(
                                in_applist = app_id_str in al_state.unique_ids,
                                has_key    = app_id_str in vdf_state.keys,
                                has_manifest = app_id_str in mc_state.depot_ids,
                            )

            → (SteamInfo, GreenLumaStatus, bool, list[DLCReadiness], Path)
                    │
                    └── on_done(_done):
                            ├── Update _steam_info, _gl_status, _readiness
                            ├── Update all four StatusBadges
                            └── _update_readiness_display()
                                    └── Render readiness table in _readiness_box

─────────────────────────────────────────────────────────────────
DLC Tab (_get_dlc_states, runs in background alongside state scan):

    ├── Read settings.steam_path (or auto-detect)
    ├── get_steam_info(steam_path) → SteamInfo
    ├── GreenLumaOrchestrator(info).check_readiness(DLCCatalog())
    │   └── Same three reads + per-DLC membership checks
    └── Returns (states, {dlc_id: DLCReadiness}, gl_installed)
            │
            └── _on_states_loaded():
                    ├── Show/hide _gl_badge (header)
                    └── Per DLC row: render GL pill badge from _gl_readiness[dlc.id]
```

---

## 14. Known GreenLuma File Inventory

The installer tracks the following file and directory names for installation, movement, and removal:

**Known files (`_GL_KNOWN_FILES`):**

| Filename | Purpose |
|----------|---------|
| `GreenLuma_2025_x64.dll` | Main 64-bit injection payload |
| `GreenLuma_2025_x86.dll` | Main 32-bit injection payload |
| `DLLInjector.exe` | Loader that injects the DLLs into Steam |
| `DLLInjector.ini` | Injector configuration (stealth mode) |
| `GreenLumaSettings_2025.exe` | GreenLuma configuration GUI |
| `AchievementUnlocker_2025.exe` | Optional achievement unlocker tool |
| `User32.dll` | Stealth-mode DLL shim |

**Known directories (`_GL_KNOWN_DIRS`):**

| Name | Purpose |
|------|---------|
| `AppList` | Numbered `.txt` files declaring Steam App/Depot IDs |

**Detection files (used for mode identification, not removal):**

| Filename | Indicates |
|----------|-----------|
| `GreenLuma_2025_x64.dll` + `GreenLuma_2025_x86.dll` | Normal mode |
| `DLLInjector.ini` | Stealth mode |
| `DLLInjector.exe` in sibling dir | Stealth mode |

---

## 15. Error Handling Summary

| Scenario | Module | Behavior |
|----------|--------|---------|
| Steam not found | `steam.py` | `detect_steam_path()` returns `None`; GUI shows "Not Found" badge |
| Steam is running during VDF write | `config_vdf.py` | `add_depot_keys()` raises `RuntimeError`; orchestrator appends to `result.errors` |
| VDF has unbalanced braces before write | `config_vdf.py` | `add_depot_keys()` raises `ValueError`; no write occurs |
| VDF would have unbalanced braces after write | `config_vdf.py` | `add_depot_keys()` raises `ValueError`, backup preserved |
| AppList would exceed 130 entries | `applist.py` | `write_applist()` / `add_ids()` raises `ValueError`; orchestrator appends to `result.errors` |
| LUA file not found or empty | `lua_parser.py` | `parse_lua_file()` raises `ValueError`; orchestrator appends to `result.errors`, returns early |
| LUA has no `addappid()` calls | `lua_parser.py` | `parse_lua_string()` raises `ValueError` |
| GreenLuma archive not found | `installer.py` | `install_greenluma()` raises `FileNotFoundError` |
| Archive path traversal attempt | `installer.py` | `_validate_archive_paths()` raises `ValueError` before extraction |
| `py7zr` not installed | `installer.py` | `install_greenluma()` raises `RuntimeError` with install hint |
| Depotcache directory missing | `manifest_cache.py` | `read_depotcache()` returns empty `ManifestState` (not an error) |
| AppList directory missing | `applist.py` | `read_applist()` returns empty `AppListState` (not an error) |
| Backup fails | `orchestrator.py` | Warning logged; pipeline continues (non-fatal) |
| Single copy failure during manifest copy | `manifest_cache.py` | Logged as warning; counted in `skipped`; other files still copied |
| GL detection fails in DLC tab | `dlc_frame.py` | Caught by bare `except Exception: pass`; no GL indicators shown |

---

## 16. Glossary

| Term | Definition |
|------|-----------|
| **AppList** | The `<Steam>/AppList/` directory containing numbered `.txt` files. Each file declares one Steam App ID or Depot ID that GreenLuma will spoof as owned. |
| **config.vdf** | Steam's internal configuration file at `<Steam>/config/config.vdf`. Uses Valve Data Format (VDF) — a hierarchical key-value syntax delimited by quoted strings and curly braces. Contains depot decryption keys in the `"depots"` section. |
| **Depot** | A discrete downloadable unit of Steam content. A single game or DLC may consist of multiple depots (e.g., base content depot, language depot). Each depot has a numeric Depot ID. |
| **Depot Decryption Key** | A 64-character hexadecimal string used by Steam to decrypt downloaded depot archives. Must be present in `config.vdf` for Steam to process a depot's content. |
| **depotcache** | The `<Steam>/depotcache/` directory holding binary `.manifest` files. Each manifest file describes the chunk composition of a specific depot version, named `{depotId}_{manifestId}.manifest`. |
| **DLLInjector** | The GreenLuma loader executable (`DLLInjector.exe`) that starts Steam and injects the GreenLuma DLLs into the Steam process before it finishes initializing. |
| **DLCReadiness** | A per-DLC summary of whether all three GreenLuma requirements are met: AppList registration, config.vdf decryption key, and depotcache manifest presence. |
| **GreenLuma** | A DLL injection tool for Steam that intercepts ownership verification to present configured App IDs as legitimately owned, enabling DLC access without purchase. |
| **LUA Manifest** | A `.lua` file using `addappid()` and `setManifestid()` call syntax to declare a set of Steam App IDs, depot decryption keys, and manifest IDs. Distributed by GreenLuma companion tools. |
| **Manifest ID** | A large numeric string identifying a specific version of a depot's file tree. Together with the Depot ID, it forms the filename of the corresponding `.manifest` file in `depotcache/`. |
| **Normal mode** | GreenLuma installation where the DLLs and injector reside directly inside the Steam root directory. |
| **Stealth mode** | GreenLuma installation where the DLLs and injector reside in a sibling directory outside the Steam root, with `DLLInjector.ini` configuring the injection path. |
| **Steam App ID** | The numeric identifier Steam uses for a game or DLC in its store and licensing system. The Sims 4 base game is `1222670`. Each DLC has its own unique App ID. |
| **VDF** | Valve Data Format. A text-based hierarchical data format used by Steam for configuration files. Similar in structure to JSON but uses quoted string keys and curly-brace blocks rather than JSON objects. |
