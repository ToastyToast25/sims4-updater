# DLC Management System — Technical Reference

**Project:** Sims 4 Updater
**Document Version:** 1.0
**Date:** 2026-02-20
**Scope:** The complete DLC management subsystem, covering catalog data, state detection, crack config formats, download pipeline, unlocker integration, and GUI.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Module Map](#2-module-map)
3. [DLC Catalog](#3-dlc-catalog)
   - 3.1 [DLCInfo Dataclass](#31-dlcinfo-dataclass)
   - 3.2 [Pack Type Categories](#32-pack-type-categories)
   - 3.3 [Full DLC Catalog Reference](#33-full-dlc-catalog-reference)
   - 3.4 [DLCCatalog Class](#34-dlccatalog-class)
   - 3.5 [Custom DLC Merging via Remote Manifest](#35-custom-dlc-merging-via-remote-manifest)
4. [DLC State Management](#4-dlc-state-management)
   - 4.1 [DLCStatus Dataclass](#41-dlcstatus-dataclass)
   - 4.2 [Status Label Logic](#42-status-label-logic)
   - 4.3 [Installed vs. Owned vs. Registered vs. Enabled](#43-installed-vs-owned-vs-registered-vs-enabled)
5. [Crack Config Formats](#5-crack-config-formats)
   - 5.1 [DLCConfigAdapter Abstract Interface](#51-dlcconfigadapter-abstract-interface)
   - 5.2 [Format 1: RldOrigin (RldOrigin.ini)](#52-format-1-rldorigin-rldoriginini)
   - 5.3 [Format 2: CODEX (codex.cfg)](#53-format-2-codex-codexcfg)
   - 5.4 [Format 3: Rune (rune.ini)](#54-format-3-rune-runeini)
   - 5.5 [Format 4: Anadius Simple (anadius.cfg)](#55-format-4-anadius-simple-anadiuscfg)
   - 5.6 [Format 5: Anadius Codex-like (anadius.cfg with Config2)](#56-format-5-anadius-codex-like-anadiuscfg-with-config2)
   - 5.7 [Format Detection Order and Logic](#57-format-detection-order-and-logic)
   - 5.8 [Bin_LE Mirror Copy Behavior](#58-bin_le-mirror-copy-behavior)
6. [DLC Manager](#6-dlc-manager)
   - 6.1 [DLCManager Class](#61-dlcmanager-class)
   - 6.2 [get_dlc_states()](#62-get_dlc_states)
   - 6.3 [apply_changes()](#63-apply_changes)
   - 6.4 [auto_toggle()](#64-auto_toggle)
   - 6.5 [export_states() and import_states()](#65-export_states-and-import_states)
   - 6.6 [Error Handling](#66-error-handling)
7. [DLC Download Pipeline](#7-dlc-download-pipeline)
   - 7.1 [DLCDownloadState Enum](#71-dlcdownloadstate-enum)
   - 7.2 [DLCDownloadTask Dataclass](#72-dlcdownloadtask-dataclass)
   - 7.3 [DLCStatusCallback Type](#73-dlcstatuscallback-type)
   - 7.4 [DLCDownloader Class Construction](#74-dlcdownloader-class-construction)
   - 7.5 [Phase 1: Download](#75-phase-1-download)
   - 7.6 [Phase 2: Extract](#76-phase-2-extract)
   - 7.7 [Phase 3: Register](#77-phase-3-register)
   - 7.8 [Batch Download](#78-batch-download)
   - 7.9 [Cancellation](#79-cancellation)
   - 7.10 [Post-Extraction Validation](#710-post-extraction-validation)
   - 7.11 [Registration Failure as Non-Fatal](#711-registration-failure-as-non-fatal)
8. [DLC Packer](#8-dlc-packer)
   - 8.1 [Archive Naming Convention](#81-archive-naming-convention)
   - 8.2 [pack_single() and pack_multiple()](#82-pack_single-and-pack_multiple)
   - 8.3 [Manifest Generation](#83-manifest-generation)
   - 8.4 [import_archive()](#84-import_archive)
9. [DLC Unlocker](#9-dlc-unlocker)
   - 9.1 [Architecture Overview](#91-architecture-overview)
   - 9.2 [UnlockerStatus Dataclass](#92-unlockerstatus-dataclass)
   - 9.3 [Client Detection](#93-client-detection)
   - 9.4 [Installation Procedure](#94-installation-procedure)
   - 9.5 [Uninstallation Procedure](#95-uninstallation-procedure)
   - 9.6 [Scheduled Task Management](#96-scheduled-task-management)
   - 9.7 [Administrator Requirement](#97-administrator-requirement)
10. [Steam Price Integration](#10-steam-price-integration)
    - 10.1 [SteamPrice Dataclass](#101-steamprice-dataclass)
    - 10.2 [SteamPriceCache](#102-steampricecache)
    - 10.3 [Batch Fetching](#103-batch-fetching)
11. [GUI Integration — DLC Frame](#11-gui-integration--dlc-frame)
    - 11.1 [Layout Structure](#111-layout-structure)
    - 11.2 [Data Loading Flow](#112-data-loading-flow)
    - 11.3 [Widget-Reuse Filtering Architecture](#113-widget-reuse-filtering-architecture)
    - 11.4 [Filter Chips](#114-filter-chips)
    - 11.5 [DLC Row Cards](#115-dlc-row-cards)
    - 11.6 [Section Collapse](#116-section-collapse)
    - 11.7 [Action Buttons and Threading](#117-action-buttons-and-threading)
    - 11.8 [Download Progress UI](#118-download-progress-ui)
    - 11.9 [Status Bar](#119-status-bar)
    - 11.10 [GreenLuma Readiness Indicators](#1110-greenluma-readiness-indicators)
12. [GUI Integration — Unlocker Frame](#12-gui-integration--unlocker-frame)
13. [Data Flow Diagrams](#13-data-flow-diagrams)
    - 13.1 [State Detection Flow](#131-state-detection-flow)
    - 13.2 [Download Pipeline Flow](#132-download-pipeline-flow)
    - 13.3 [Apply Changes Flow](#133-apply-changes-flow)
14. [Exception Hierarchy](#14-exception-hierarchy)
15. [Configuration and Constants](#15-configuration-and-constants)
16. [Appendix A: Complete Crack Config Format Examples](#appendix-a-complete-crack-config-format-examples)
17. [Appendix B: DLC Catalog JSON Schema](#appendix-b-dlc-catalog-json-schema)
18. [Appendix C: Manifest DLC Download Schema](#appendix-c-manifest-dlc-download-schema)

---

## 1. Overview

The DLC Management System is the subsystem within the Sims 4 Updater responsible for:

1. **Cataloging** all known Sims 4 DLC packs (Expansion Packs, Game Packs, Stuff Packs, Kits, and Free Packs) with their names, codes, and Steam store links.
2. **Detecting** the current state of every DLC relative to the local game installation — whether each DLC folder is present on disk, whether `SimulationFullBuild0.package` exists to confirm completeness, whether it is registered and enabled in the crack configuration file, and whether it is legitimately owned through EA.
3. **Toggling** DLC enable/disable states by rewriting one of five supported crack configuration file formats, maintaining compatibility across multiple crack variants without requiring any external tools.
4. **Downloading** DLC pack archives from a remote manifest server through a structured three-phase pipeline: HTTP download with resume support and MD5 verification, ZIP extraction to the game directory with path traversal protection, and automatic registration in the crack config upon success.
5. **Packing** installed DLC folders into distributable ZIP archives and generating corresponding download manifests.
6. **Installing** the EA DLC Unlocker (a `version.dll` sideload for the EA app) to unlock DLC content independently of the crack config system.
7. **Integrating** all of the above capabilities into a card-style GUI tab with search, filter chips, inline Steam pricing, per-row download buttons, section collapse, and real-time download progress.

The system is designed around the principle that crack config parsing is purely a text-transformation operation. No external tools, no registry writes, no binary patching are involved in the toggling path. Each crack config format is represented by an adapter class that reads and rewrites the config content using regular expressions, and the system auto-detects which format is present.

---

## 2. Module Map

```text
src/sims4_updater/
├── dlc/
│   ├── __init__.py              — Empty package marker
│   ├── catalog.py               — DLCInfo, DLCStatus, DLCCatalog
│   ├── formats.py               — DLCConfigAdapter + 5 concrete format adapters
│   ├── manager.py               — DLCManager (get_dlc_states, apply_changes, auto_toggle, export/import)
│   ├── downloader.py            — DLCDownloader (3-phase download pipeline)
│   ├── packer.py                — DLCPacker (zip packing, manifest generation, import)
│   └── steam.py                 — SteamPrice, SteamPriceCache, fetch_prices_batch
├── core/
│   ├── unlocker.py              — EA DLC Unlocker install/uninstall
│   └── exceptions.py            — NoCrackConfigError, DownloadError, etc.
├── gui/frames/
│   ├── dlc_frame.py             — DLCFrame (main DLC management tab; deferred imports from greenluma.orchestrator, greenluma.steam, dlc.catalog for GL readiness)
│   └── unlocker_frame.py        — UnlockerFrame (unlocker install/uninstall tab)
├── constants.py                 — APP_NAME, registry paths, get_data_dir(), get_tools_dir()
└── data/
    └── dlc_catalog.json         — Bundled DLC catalog (109 DLC entries)
```

**Source file locations (absolute):**

| Module | Path |
|--------|------|
| `catalog.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\dlc\catalog.py` |
| `formats.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\dlc\formats.py` |
| `manager.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\dlc\manager.py` |
| `downloader.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\dlc\downloader.py` |
| `packer.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\dlc\packer.py` |
| `steam.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\dlc\steam.py` |
| `core/unlocker.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\core\unlocker.py` |
| `dlc_frame.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\gui\frames\dlc_frame.py` |
| `unlocker_frame.py` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\src\sims4_updater\gui\frames\unlocker_frame.py` |
| `dlc_catalog.json` | `C:\Users\Administrator\Pictures\Greenluma 1.7.0\sims4-updater\data\dlc_catalog.json` |

---

## 3. DLC Catalog

### 3.1 DLCInfo Dataclass

`DLCInfo` is the central value object representing a single DLC pack. It is defined in `catalog.py:40`.

```python
@dataclass
class DLCInfo:
    id: str           # e.g. "EP01"
    code: str         # e.g. "SIMS4.OFF.SOLP.0x0000000000011AC5"
    code2: str        # alternative code (may be empty)
    pack_type: str    # expansion, game_pack, stuff_pack, free_pack, kit
    names: dict[str, str]  # {locale: display_name}
    description: str = ""  # short English description of the pack
    steam_app_id: int | None = None  # Steam store app ID
```

**Field semantics:**

- **`id`** — The canonical directory-level identifier. This is also the name of the subfolder within the game installation where the DLC's files reside. For example, `EP01` maps to `<game_dir>/EP01/`.
- **`code`** — The primary entitlement code used in the crack configuration file. The format is `SIMS4.OFF.SOLP.0x<16-digit-hex>`. This code uniquely identifies the DLC to the Origin/EA entitlement system. Some newer DLCs (notably EP21 and certain Kits) have empty codes, which means they are not yet supported by the crack patching path.
- **`code2`** — A secondary entitlement code, present on some DLCs that have been re-released or use dual-code registration. This is the empty string when unused.
- **`pack_type`** — One of: `expansion`, `game_pack`, `stuff_pack`, `kit`, `free_pack`. Governs display grouping in the GUI.
- **`names`** — A dict mapping lowercase locale strings (e.g. `"en_us"`, `"de_de"`, `"zh_cn"`) to localized display names. The application defaults to `en_us`.
- **`description`** — A short human-readable description of the pack in English, used in the expandable detail row in the GUI.
- **`steam_app_id`** — The numeric Steam store application ID, used for fetching live pricing and building store URLs. `None` for DLCs not on Steam.

**Key properties:**

```python
@property
def name_en(self) -> str:
    # Returns the English name, falling back to the DLC ID if not found
    return self.names.get("en_us", self.names.get("en_US", self.id))

def get_name(self, locale: str = "en_US") -> str:
    # Case-insensitive locale lookup with en_us fallback
    key = locale.lower()
    return self.names.get(key, self.names.get("en_us", self.id))

@property
def all_codes(self) -> list[str]:
    # Returns [code] or [code, code2] — used when scanning crack configs
    codes = [self.code] if self.code else []
    if self.code2:
        codes.append(self.code2)
    return codes
```

The `all_codes` property is particularly important. When `DLCManager.get_dlc_states()` reads the crack config, it iterates over every code in `all_codes` to find whether any of them appear in the config and what their state is. This handles the case where a DLC may have been registered under either its primary or secondary code by a different crack version.

### 3.2 Pack Type Categories

The catalog uses five pack type strings, each corresponding to a tier of Sims 4 DLC content:

| `pack_type` Value | GUI Label | Description | Count |
|-------------------|-----------|-------------|-------|
| `expansion` | Expansion Packs | Full expansion packs (EP01-EP21), the largest content drops | 21 |
| `game_pack` | Game Packs | Mid-tier packs (GP01-GP12), focused on a single theme | 12 |
| `stuff_pack` | Stuff Packs | Smaller item/CAS collections (SP01-SP18, SP46, SP49) | 20 |
| `kit` | Kits | Smallest paid content tier (SP20-SP81 range) | 55 |
| `free_pack` | Free Packs | Free DLC available to all players (FP01) | 1 |

**Total: 109 DLC entries** in the bundled catalog as of version 2.0.0.

Note that Kits use the `SP` prefix rather than a dedicated `KT` prefix. This is because the EA entitlement system issues them as Stuff Pack slots. The `pack_type` field in the catalog, not the ID prefix, is authoritative for categorization.

The GUI renders these categories in the order defined by `_TYPE_ORDER` in `dlc_frame.py:50`:

```python
_TYPE_ORDER = ["expansion", "game_pack", "stuff_pack", "kit", "free_pack", "other"]
```

### 3.3 Full DLC Catalog Reference

The tables below enumerate every DLC in the bundled catalog. The `Code` column shows the truncated hex suffix of the entitlement code; the full format is `SIMS4.OFF.SOLP.0x<code>`.

#### Expansion Packs (21)

| ID | English Name | Hex Code Suffix | Steam App ID |
|----|-------------|----------------|-------------|
| EP01 | Get to Work | `0000000000011AC5` | — |
| EP02 | Get Together | `00000000000170FF` | — |
| EP03 | City Living | `000000000001D5ED` | — |
| EP04 | Cats & Dogs | `000000000002714B` | — |
| EP05 | Seasons | `000000000002E2C7` | — |
| EP06 | Get Famous | `0000000000030553` | — |
| EP07 | Island Living | `00000000000327AF` | — |
| EP08 | Discover University | `0000000000035113` | — |
| EP09 | Eco Lifestyle | `0000000000039AA7` | — |
| EP10 | Snowy Escape | `000000000003C344` | — |
| EP11 | Cottage Living | `00000000000405E6` | — |
| EP12 | High School Years | `000000000004AAD0` | — |
| EP13 | Growing Together | `00000000000530C0` | — |
| EP14 | Horse Ranch | `0000000000057E0A` | — |
| EP15 | For Rent | `000000000005CD3D` | — |
| EP16 | Lovestruck | `0000000000064B65` | — |
| EP17 | Life & Death | `0000000000069DFF` | — |
| EP18 | Businesses & Hobbies | `000000000006A9D8` | — |
| EP19 | Enchanted by Nature | `0000000000073123` | — |
| EP20 | Adventure Awaits | `000000000007789B` | — |
| EP21 | Royalty & Legacy | *(no code yet)* | — |

#### Game Packs (12)

| ID | English Name | Hex Code Suffix | Steam App ID |
|----|-------------|----------------|-------------|
| GP01 | Outdoor Retreat | `0000000000011A4B` | 1235741 |
| GP02 | Spa Day | `0000000000016C2A` | 1235740 |
| GP03 | Dine Out | `000000000001C03A` | 1235747 |
| GP04 | Vampires | `000000000002376D` | — |
| GP05 | Parenthood | `0000000000027890` | — |
| GP06 | Jungle Adventure | `000000000002B073` | — |
| GP07 | StrangerVille | `0000000000033910` | — |
| GP08 | Realm of Magic | `0000000000036EE8` | — |
| GP09 | Star Wars: Journey to Batuu | `000000000003B1C1` | — |
| GP10 | Dream Home Decorator | `0000000000040A01` | — |
| GP11 | My Wedding Stories | `0000000000047D7E` | — |
| GP12 | Werewolves | `0000000000048E3E` | — |

#### Stuff Packs (20)

| ID | English Name | Hex Code Suffix |
|----|-------------|----------------|
| SP01 | Luxury Party Stuff | `0000000000016390` |
| SP02 | Perfect Patio Stuff | `0000000000016B37` |
| SP03 | Cool Kitchen Stuff | `0000000000018B66` |
| SP04 | Spooky Stuff | `0000000000019B59` |
| SP05 | Movie Hangout Stuff | `000000000001A9A7` |
| SP06 | Romantic Garden Stuff | `000000000001C04E` |
| SP07 | Kids Room Stuff | `000000000001D5F2` |
| SP08 | Backyard Stuff | `0000000000020176` |
| SP09 | Vintage Glamour Stuff | `0000000000022C32` |
| SP10 | Bowling Night Stuff | `0000000000027128` |
| SP11 | Fitness Stuff | `0000000000028FE2` |
| SP12 | Toddler Stuff | `000000000002A4FE` |
| SP13 | Laundry Day Stuff | `000000000002CA06` |
| SP14 | My First Pet Stuff | `000000000002EA24` |
| SP15 | Moschino Stuff | `000000000003749F` |
| SP16 | Tiny Living Stuff Pack | `000000000003A92D` |
| SP17 | Nifty Knitting | `000000000003D4E9` |
| SP18 | Paranormal Stuff Pack | `000000000003FA50` |
| SP46 | Home Chef Hustle Stuff Pack | `0000000000058A09` |
| SP49 | Crystal Creations Stuff Pack | `000000000005B63F` |

#### Kits (55, SP20-SP81 range)

Notable entries include: Throwback Fit Kit (SP20), Country Kitchen Kit (SP21), Bust the Dust Kit (SP22), Fashion Street Kit (SP24), Incheon Arrivals Kit (SP26), Carnaval Streetwear Kit (SP30), Everyday Clutter Kit (SP37), Bathroom Clutter Kit (SP39), Book Nook Kit (SP43), Castle Estate Kit (SP47), Urban Homage Kit (SP50), SpongeBob's House Kit (SP68), SpongeBob Kid's Room Kit (SP70), and Prairie Dreams Set (SP81), among others. Several recent Kits (SP68, SP70, SP76, SP77, SP81) have empty code fields because their entitlement codes have not yet been cataloged.

#### Free Packs (1)

| ID | English Name | Hex Code Suffix | Steam App ID |
|----|-------------|----------------|-------------|
| FP01 | Holiday Celebration Pack | `000000000001266C` | 1235764 |

### 3.4 DLCCatalog Class

`DLCCatalog` (`catalog.py:79`) is the in-memory database of all DLC entries. It is instantiated once by `DLCManager` and reused throughout the application session.

```python
class DLCCatalog:
    def __init__(self, catalog_path: str | Path | None = None):
        # Loads from data/dlc_catalog.json if path not specified
        ...
        self.dlcs: list[DLCInfo] = []
        self._by_id: dict[str, DLCInfo] = {}
        self._by_code: dict[str, DLCInfo] = {}
```

**Internal indexes:**

- `_by_id` — maps `dlc.id` (e.g. `"EP01"`) to the `DLCInfo` object for O(1) lookup.
- `_by_code` — maps both `dlc.code` and `dlc.code2` to the `DLCInfo` object. This allows reverse lookup from an entitlement code string back to the DLC, which is used when parsing crack configs.

**Public API:**

```python
catalog.get_by_id("EP01")          # -> DLCInfo | None
catalog.get_by_code("SIMS4.OFF.SOLP.0x0000000000011AC5")  # -> DLCInfo | None
catalog.all_dlcs()                 # -> list[DLCInfo]
catalog.by_type("expansion")       # -> list[DLCInfo]
catalog.get_installed(game_dir)    # -> list[DLCInfo] (folder exists on disk)
catalog.get_missing(game_dir)      # -> list[DLCInfo] (SimulationFullBuild0.package absent)
```

**Completeness check:** `get_missing()` uses the presence of `SimulationFullBuild0.package` as its signal file. This is the primary simulation data package for every DLC and is reliably present in any complete installation.

### 3.5 Custom DLC Merging via Remote Manifest

The catalog supports runtime extension. When the application fetches a remote update manifest, the manifest may include new DLC entries that are not yet in the bundled `dlc_catalog.json`. These are merged into the running catalog via `DLCCatalog.merge_remote()`.

```python
def merge_remote(self, remote_dlcs) -> int:
    """
    Merges ManifestDLC objects from the remote manifest.
    Returns number of new DLC entries added.
    """
```

**Merge behavior:**

- If a DLC ID already exists in the catalog, only missing `description` and `names` fields are backfilled from the remote data. The existing entry is not replaced.
- If a DLC ID is genuinely new, a full `DLCInfo` is constructed and added.
- After any additions, `_save_custom()` is called to persist the new entries to `%APPDATA%/<app>/custom_dlcs.json`.

**Persistence:** On the next launch, `DLCCatalog.__init__` reads and merges `custom_dlcs.json` automatically after loading the bundled catalog, so new DLCs discovered from a previous manifest fetch survive application restarts. Bundled IDs are never written to `custom_dlcs.json` to avoid duplication.

---

## 4. DLC State Management

### 4.1 DLCStatus Dataclass

`DLCStatus` (`catalog.py:14`) is a rich snapshot of a single DLC's current state at a moment in time. It is computed by `DLCManager.get_dlc_states()` and consumed by the GUI.

```python
@dataclass
class DLCStatus:
    dlc: DLCInfo              # The underlying catalog entry
    installed: bool = False   # True if <game_dir>/<dlc.id>/ directory exists
    complete: bool = False    # True if SimulationFullBuild0.package is present
    registered: bool = False  # True if any of dlc.all_codes appears in the crack config
    enabled: bool | None = None  # True/False if registered; None if not registered
    owned: bool = False       # True if installed AND not in crack config (legitimate EA copy)
    file_count: int = 0       # Number of files in the DLC directory
```

**The `enabled` field uses a three-value logic:**

| `enabled` Value | Meaning |
|-----------------|---------|
| `True` | DLC is registered in the crack config and is enabled |
| `False` | DLC is registered in the crack config but is disabled |
| `None` | DLC has no entry in the crack config at all |

This distinction matters because `None` versus `False` have different implications. `None` may mean the DLC is legitimately owned (EA handles it), or simply not yet registered after a download. `False` means the crack config explicitly marks it as disabled.

### 4.2 Status Label Logic

The `status_label` property computes a display-ready string from the combination of state flags:

```python
@property
def status_label(self) -> str:
    if self.owned and self.complete:
        return "Owned"
    if self.installed and not self.complete:
        return "Incomplete"
    if self.installed and self.registered and self.enabled:
        return "Patched"
    if self.installed and self.registered and not self.enabled:
        return "Patched (disabled)"
    if not self.installed and self.registered:
        return "Missing files"
    return "Not installed"
```

**Label priority and meaning:**

| Label | Meaning |
|-------|---------|
| `Owned` | DLC is installed, `SimulationFullBuild0.package` exists, and it is not in the crack config — this indicates a legitimate EA purchase |
| `Incomplete` | The DLC directory exists but `SimulationFullBuild0.package` is absent — a partial or corrupt installation |
| `Patched` | Installed and enabled in the crack config — fully functional via the crack |
| `Patched (disabled)` | Installed but the crack config has explicitly disabled it |
| `Missing files` | An entry exists in the crack config but the DLC directory is absent on disk |
| `Not installed` | Neither the directory nor a crack config entry exists |

The GUI maps each label to a color in `_STATUS_COLORS` (`dlc_frame.py:27`):

```python
_STATUS_COLORS = {
    "Owned":              theme.COLORS["success"],    # green
    "Patched":            "#5b9bd5",                  # blue
    "Patched (disabled)": theme.COLORS["text_muted"], # grey
    "Incomplete":         theme.COLORS["warning"],    # amber
    "Missing files":      theme.COLORS["warning"],    # amber
    "Not installed":      theme.COLORS["text_muted"], # grey
}
```

### 4.3 Installed vs. Owned vs. Registered vs. Enabled

These four boolean-like fields form the state matrix that the rest of the system reasons about.

**Installed:** A DLC directory exists at `<game_dir>/<dlc_id>/`. The presence of the directory alone does not mean the DLC is complete or functional.

**Complete:** The sentinel file `<game_dir>/<dlc_id>/SimulationFullBuild0.package` exists. This file is required for the game engine to load the DLC. Without it, the game may crash or silently skip the DLC.

**Registered:** At least one of the DLC's entitlement codes appears in the crack configuration file. This is determined by the format-specific adapter's `read_enabled_dlcs()` method.

**Enabled:** If registered, whether the crack config entry is in the "active" state (as opposed to commented out or marked inactive by the format's convention). This is what the game's DRM emulation layer reads when deciding whether to grant access to DLC content.

**Owned:** Computed as:

```python
owned = installed and (not registered or dlc.pack_type == "free_pack")
```

An installed DLC that is not in the crack config is assumed to be legitimately purchased and managed by EA. Free packs are always marked as owned because they require no crack entry — EA provides them to all players.

---

## 5. Crack Config Formats

The Sims 4 piracy ecosystem has produced several different crack implementations over the years, each storing DLC entitlement data in a different format. The `formats.py` module provides a uniform adapter interface over all of them.

### 5.1 DLCConfigAdapter Abstract Interface

```python
class DLCConfigAdapter(ABC):
    def detect(self, game_dir: Path) -> bool:
        """Returns True if this format's config file exists in game_dir."""

    def get_config_path(self, game_dir: Path) -> Path | None:
        """Returns the path to the config file, or None if not found."""

    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        """
        Given the full file content and a list of DLC codes to look up,
        returns {code: enabled_bool} for each code found in the config.
        Codes not found in the config are not included in the result.
        """

    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        """
        Returns a new version of config_content with the DLC toggled.
        This is a pure string transformation — no file I/O occurs here.
        """

    def get_format_name(self) -> str:
        """Human-readable format name for logging and display."""

    def get_encoding(self) -> str:
        """File encoding for reading/writing the config file."""
```

All adapters read and write in `utf-8` encoding. All regex patterns use the `(?i)` inline flag for case-insensitive matching, which is necessary because some crack releases produce configs with mixed-case code strings.

### 5.2 Format 1: RldOrigin (RldOrigin.ini)

**Crack group:** ReLoaded
**Config file:** `Game/Bin/RldOrigin.ini` or `Game-cracked/Bin/RldOrigin.ini`

This is the INI-style format used by the ReLoaded crack group. Each DLC is represented as a numbered key-value pair:

```ini
[DLC]
IID1=SIMS4.OFF.SOLP.0x0000000000011AC5
IID2=SIMS4.OFF.SOLP.0x00000000000170FF
;IID3=SIMS4.OFF.SOLP.0x000000000001D5ED
IID4=SIMS4.OFF.SOLP.0x000000000002714B
```

**Enable/disable mechanism:** A semicolon (`;`) at the start of a line comments it out and disables the DLC. Removing the semicolon enables it.

**Detection regex (read):**

```python
pattern = re.compile(rf"(?i)(\n)(;?)(IID\d+={re.escape(code)})")
# Group 2 is the optional semicolon.
# enabled = (match.group(2) == "")  — no semicolon means enabled
```

**Modification regex (write):**

```python
pattern = re.compile(rf"(?i)(\n)(;?)(IID\d+={re.escape(dlc_code)})")
replacement = r"\1" + ("" if enabled else ";") + r"\3"
# Preserves the line prefix and the key=value pair; only changes the semicolon
```

### 5.3 Format 2: CODEX (codex.cfg)

**Crack group:** CODEX
**Config file:** `Game/Bin/codex.cfg` or `Game-cracked/Bin/codex.cfg`

The CODEX format uses a Valve KeyValues-style structure. Each DLC has a stanza with a `"Group"` field:

```text
"SIMS4.OFF.SOLP.0x0000000000011AC5"
{
    "DLC"           "1"
    "Group"         "THESIMS4PC"
    "Name"          "The Sims 4 Get to Work"
}
```

**Enable/disable mechanism:** The `"Group"` field is set to `"THESIMS4PC"` when enabled, or `"_"` when disabled.

**Constants:**

```python
VALID_GROUP = "THESIMS4PC"
INVALID_GROUP = "_"
```

**Detection regex:**

```python
pattern = re.compile(
    '(?i)("' + escaped + r'"[\s\n]+\{[^\}]+"Group"\s+")([^"]+)()',
    re.DOTALL,
)
# Group 2 is the current Group value.
# enabled = (match.group(2) == "THESIMS4PC")
```

**Modification regex:**

```python
group = "THESIMS4PC" if enabled else "_"
pattern.sub(r"\g<1>" + group + r"\3", content)
```

### 5.4 Format 3: Rune (rune.ini)

**Crack group:** Rune
**Config file:** `Game/Bin/rune.ini` or `Game-cracked/Bin/rune.ini`

The Rune format uses INI sections where the section header itself is the DLC code:

```ini
[SIMS4.OFF.SOLP.0x0000000000011AC5]
activated=1

[SIMS4.OFF.SOLP.0x00000000000170FF_]
activated=1
```

**Enable/disable mechanism:** A trailing underscore (`_`) after the closing bracket of the section header disables the DLC. No underscore means enabled.

**Detection regex (read):**

```python
pattern = re.compile(rf"(?i)(\[{re.escape(code)})(_?)(\])")
# Group 2 is the optional underscore.
# enabled = (match.group(2) == "")
```

**Modification regex (write):**

```python
replacement = r"\1" + ("" if enabled else "_") + r"\3"
```

### 5.5 Format 4: Anadius Simple (anadius.cfg)

**Crack source:** Anadius (v1, simple format)
**Config file:** `Game/Bin/anadius.cfg` or `Game-cracked/Bin/anadius.cfg`
**Detection condition:** File exists AND does NOT contain the string `"Config2"`

The Anadius simple format stores DLC codes as bare quoted string values inside a block:

```text
{
    "SIMS4.OFF.SOLP.0x0000000000011AC5"
    //"SIMS4.OFF.SOLP.0x00000000000170FF"
    "SIMS4.OFF.SOLP.0x000000000001D5ED"
}
```

**Enable/disable mechanism:** A `//` C-style comment prefix on the line disables the DLC.

**Detection regex (read):**

```python
pattern = re.compile(rf'(?i)(\s)(/*)("{re.escape(code)}")')
# Group 2 is the optional // prefix.
# enabled = (match.group(2) == "")
```

**Modification regex (write):**

```python
replacement = r"\1" + ("" if enabled else "//") + r"\3"
```

### 5.6 Format 5: Anadius Codex-like (anadius.cfg with Config2)

**Crack source:** Anadius (v2, codex-like format)
**Config file:** `Game/Bin/anadius.cfg` or `Game-cracked/Bin/anadius.cfg`
**Detection condition:** File exists AND DOES contain the string `"Config2"`

This is a subclass of `CodexAdapter` — it uses the exact same KeyValues structure and `"Group"` enable/disable mechanism as the CODEX format. The only difference is the filename (`anadius.cfg` vs. `codex.cfg`) and the presence of a `"Config2"` section that distinguishes it from the simpler Anadius format.

```python
class AnadiusCodexAdapter(CodexAdapter):
    CONFIG_PATHS = [
        "Game/Bin/anadius.cfg",
        "Game-cracked/Bin/anadius.cfg",
    ]

    def detect(self, game_dir: Path) -> bool:
        path = self.get_config_path(game_dir)
        if path is None:
            return False
        content = path.read_text(encoding="utf-8", errors="replace")
        return '"Config2"' in content  # the distinguishing marker
```

### 5.7 Format Detection Order and Logic

`detect_format()` (`formats.py:239`) iterates over the `ALL_ADAPTERS` list and returns the first adapter that reports `detect() == True`:

```python
ALL_ADAPTERS = [
    AnadiusCodexAdapter(),   # checked first
    AnadiusSimpleAdapter(),  # checked second
    RuneAdapter(),
    CodexAdapter(),
    RldOriginAdapter(),      # checked last
]

def detect_format(game_dir: str | Path) -> DLCConfigAdapter | None:
    game_dir = Path(game_dir)
    for adapter in ALL_ADAPTERS:
        if adapter.detect(game_dir):
            return adapter
    return None
```

The ordering is deliberate. Both Anadius adapters share the same filename (`anadius.cfg`), so the more specific one (`AnadiusCodexAdapter`, which requires `"Config2"` presence) is checked first. If neither Anadius variant matches, detection falls through to the other formats which each use distinct filenames.

`detect_format()` is called at the start of every public `DLCManager` method. It is not cached, which means every call re-checks the filesystem. This is intentional: it ensures correctness when a user swaps crack versions between operations.

### 5.8 Bin_LE Mirror Copy Behavior

After writing changes to the crack config, `DLCManager.apply_changes()` checks for a `Bin_LE` sibling directory and, if it exists, copies the updated config there as well:

```python
bin_le_path = Path(str(config_path).replace("Bin", "Bin_LE"))
if bin_le_path.parent.is_dir() and bin_le_path != config_path:
    shutil.copy2(config_path, bin_le_path)
```

This mirrors the behavior of the AutoIt-based `dlc-toggler.au3` script that predates this Python implementation. Some Sims 4 crack installations include both a `Game/Bin/` and a `Game/Bin_LE/` directory — the latter is used by the 32-bit executable variant. Both must be kept in sync or the game will use inconsistent DLC state depending on which executable is launched.

---

## 6. DLC Manager

### 6.1 DLCManager Class

`DLCManager` (`manager.py:14`) is the central coordinator for DLC state operations. It holds a `DLCCatalog` and routes all operations through the appropriate format adapter.

```python
class DLCManager:
    def __init__(self, catalog: DLCCatalog | None = None):
        self.catalog = catalog or DLCCatalog()
```

Instantiation is cheap. The `DLCCatalog` constructor reads `dlc_catalog.json` once. All subsequent calls use the in-memory catalog.

### 6.2 get_dlc_states()

```python
def get_dlc_states(
    self, game_dir: str | Path, locale: str = "en_US"
) -> list[DLCStatus]:
```

Returns a `DLCStatus` for every DLC in the catalog, in catalog order.

**Algorithm:**

1. Auto-detect the crack config format for `game_dir` using `detect_format()`.
2. If a format is detected, read the entire config file into memory as a string.
3. For each `DLCInfo` in the catalog:
   a. Check if the directory `<game_dir>/<dlc.id>/` exists (`installed`).
   b. Check if `<game_dir>/<dlc.id>/SimulationFullBuild0.package` exists (`complete`).
   c. Count files in the DLC directory (`file_count`).
   d. Call `adapter.read_enabled_dlcs(config_content, dlc.all_codes)` to check all codes.
   e. Compute `registered` (any code found) and `enabled` (state of first found code).
   f. Compute `owned` = `installed and (not registered or pack_type == "free_pack")`.
4. Return the assembled `DLCStatus` list.

**Performance:** The config file is read once and passed as a string to every adapter call, avoiding repeated file I/O. The file count uses `os.scandir`-equivalent iteration via `Path.iterdir()`.

**Important:** If no crack config is found, states are still returned for all DLCs, but `registered`, `enabled`, and `owned` will all use defaults (`False`, `None`, and the installed-only logic respectively).

### 6.3 apply_changes()

```python
def apply_changes(
    self,
    game_dir: str | Path,
    enabled_dlcs: set[str],
) -> None:
```

Writes the complete DLC enable/disable state to the crack config. This is a total overwrite of all DLC entries in the config — every DLC in the catalog is touched, either enabling or disabling it based on membership in `enabled_dlcs`.

**Algorithm:**

1. Detect the format. Raise `NoCrackConfigError` if none found.
2. Read the current config content.
3. For each DLC in the catalog:
   - For each code in `dlc.all_codes`: call `adapter.set_dlc_state(content, code, should_enable)`.
   - `should_enable` is `True` if `dlc.id` is in the `enabled_dlcs` set.
4. Write the modified content back to the same file.
5. Mirror-copy to `Bin_LE` if applicable.

**Usage pattern:** The GUI collects the checkbox states of all DLC rows into a set of DLC IDs and passes that set to `apply_changes()`. The manager does not diff against the previous state — it rewrites all entries, which is idempotent and avoids stale state issues.

```python
# Example: enable EP01, EP02, disable everything else
manager.apply_changes(game_dir, {"EP01", "EP02"})
```

### 6.4 auto_toggle()

```python
def auto_toggle(self, game_dir: str | Path) -> dict[str, bool]:
```

Automatically synchronizes the crack config with the actual on-disk installation state. DLCs that are installed but disabled get enabled; DLCs that are enabled but missing from disk get disabled.

**Algorithm:**

1. Call `get_dlc_states()` to get the full current state.
2. For each state:
   - If `installed == True`: add to `enabled_set`. If `enabled == False`: record as a change.
   - If `installed == False`: if `enabled == True`: record as a change.
3. If any changes were recorded, call `apply_changes(game_dir, enabled_set)`.
4. Return the `changes` dict mapping `dlc_id -> new_enabled_state`.

**Use case:** After manually copying DLC files into the game directory without going through the download pipeline, `auto_toggle()` will automatically register and enable the new DLCs, and disable any that were previously enabled but whose files have since been removed.

```python
changes = manager.auto_toggle(game_dir)
# Returns e.g.: {"EP15": True, "GP07": False}
# EP15 was enabled (installed but was disabled)
# GP07 was disabled (enabled but missing from disk)
```

### 6.5 export_states() and import_states()

These are used to save and restore DLC states around a patching operation, ensuring that a game version update does not inadvertently alter which DLCs are enabled.

```python
def export_states(self, game_dir: str | Path) -> dict[str, bool]:
    """Returns {dlc_id: enabled_bool} for all registered DLCs."""
    states = self.get_dlc_states(game_dir)
    return {
        s.dlc.id: s.enabled
        for s in states
        if s.enabled is not None  # exclude unregistered DLCs
    }

def import_states(self, game_dir: str | Path, saved_states: dict[str, bool]) -> None:
    """Restores previously exported states."""
    enabled_set = {dlc_id for dlc_id, enabled in saved_states.items() if enabled}
    self.apply_changes(game_dir, enabled_set)
```

**Typical workflow within the patch process:**

```python
# Before patching:
saved = manager.export_states(game_dir)

# ... patching operations that may reset or overwrite the crack config ...

# After patching:
manager.import_states(game_dir, saved)
```

### 6.6 Error Handling

`DLCManager` raises `NoCrackConfigError` from `core/exceptions.py` in two cases:

- `apply_changes()` is called but no crack config format is detected in `game_dir`.
- The format is detected but `get_config_path()` returns `None` (the file was deleted between detection and reading).

All other errors (filesystem permission errors, regex failures) propagate as standard Python exceptions and are handled by the caller (typically the GUI, which shows a toast notification).

---

## 7. DLC Download Pipeline

The `DLCDownloader` class (`downloader.py`) implements a structured three-phase pipeline for downloading, extracting, and registering DLC packs. It is designed to be used as a context manager and supports cooperative cancellation at every phase boundary.

### 7.1 DLCDownloadState Enum

```python
class DLCDownloadState(Enum):
    PENDING     = "pending"      # Task created but not started
    DOWNLOADING = "downloading"  # HTTP download in progress
    EXTRACTING  = "extracting"   # Zip extraction in progress
    REGISTERING = "registering"  # Writing crack config entry
    COMPLETED   = "completed"    # All three phases succeeded
    FAILED      = "failed"       # Any phase raised an exception
    CANCELLED   = "cancelled"    # Cancel event was set
```

These states map directly to the progress labels shown in the GUI row during a download.

### 7.2 DLCDownloadTask Dataclass

```python
@dataclass
class DLCDownloadTask:
    entry: DLCDownloadEntry   # The manifest entry being processed
    state: DLCDownloadState = DLCDownloadState.PENDING
    progress_bytes: int = 0   # Bytes downloaded so far
    total_bytes: int = 0      # Total expected bytes (from manifest)
    error: str = ""           # Error message if state == FAILED
```

One `DLCDownloadTask` is created per DLC download. It is updated in-place as the pipeline advances through phases.

### 7.3 DLCStatusCallback Type

```python
DLCStatusCallback = Callable[
    [str, DLCDownloadState, int, int, str], None
]
# Arguments: (dlc_id, state, progress_bytes, total_bytes, message)
```

This callback is invoked at every significant event during the download: phase transitions, per-chunk progress during download, and completion/failure. In the GUI, this callback is routed through `app._enqueue_gui()` to ensure the widget updates happen on the main thread.

### 7.4 DLCDownloader Class Construction

```python
class DLCDownloader:
    def __init__(
        self,
        download_dir: str | Path,   # Base directory; DLCs go to <download_dir>/dlcs/
        game_dir: str | Path,        # Game installation directory
        dlc_manager,                 # DLCManager instance (passed to avoid circular import)
        cancel_event: threading.Event | None = None,
    ):
        self.download_dir = Path(download_dir) / "dlcs"
        self.game_dir = Path(game_dir)
        self._dlc_manager = dlc_manager
        self._cancel = cancel_event or threading.Event()
        self._downloader = Downloader(
            download_dir=self.download_dir,
            cancel_event=self._cancel,
        )
```

The `DLCDownloader` wraps the lower-level `patch.downloader.Downloader`, which provides HTTP downloading with resume support and MD5 verification. The `dlc_manager` is passed in rather than imported directly to avoid a circular dependency (`downloader` -> `manager` -> `catalog` -> already loaded).

### 7.5 Phase 1: Download

```python
task.state = DLCDownloadState.DOWNLOADING
file_entry = entry.to_file_entry()  # Converts DLCDownloadEntry to FileEntry

result = self._downloader.download_file(
    file_entry,
    progress=dl_progress,  # (downloaded_bytes, total_bytes, filename) -> None
)
```

`DLCDownloadEntry.to_file_entry()` converts the manifest's DLC entry into the generic `FileEntry` format expected by the patch downloader. The patch downloader handles:

- HTTP GET with `Range` header support for resuming interrupted downloads.
- Comparing the downloaded file's MD5 hash against the manifest value.
- Storing the downloaded archive to `<download_dir>/dlcs/<filename>`.

If the cancel event is set after download completes, the task transitions to `CANCELLED` and returns before extraction begins.

### 7.6 Phase 2: Extract

```python
task.state = DLCDownloadState.EXTRACTING
self._extract_zip(result.path, entry.dlc_id)
```

```python
def _extract_zip(self, archive_path: Path, dlc_id: str):
    with zipfile.ZipFile(archive_path, "r") as zf:
        game_dir_resolved = self.game_dir.resolve()
        for member in zf.namelist():
            if self.cancelled:
                raise DownloadError("Extraction cancelled.")

            # Path traversal protection
            target = (self.game_dir / member).resolve()
            if not str(target).startswith(str(game_dir_resolved)):
                logger.warning("Skipping unsafe zip path: %s", member)
                continue

            zf.extract(member, self.game_dir)
```

**Path traversal protection:** Every archive member's resolved destination path is checked to ensure it falls within `game_dir`. Any member whose path would escape the game directory (e.g. `../../Windows/System32/evil.dll`) is skipped with a warning. This is a defense against malicious or corrupt archives.

**Archive structure expectation:** DLC archives must contain files at paths relative to the game directory root. For example, a well-formed EP01 archive would contain:

```text
EP01/SimulationFullBuild0.package
EP01/SimulationFullBuild1.package
EP01/...
__Installer/DLC/EP01/...
```

Extracting to `game_dir` places `EP01/` and `__Installer/` directly inside the game installation.

**Cancellation during extraction:** Checked on every file member. If cancelled mid-extraction, a `DownloadError` is raised, causing the task to transition to `CANCELLED`.

### 7.7 Phase 3: Register

```python
task.state = DLCDownloadState.REGISTERING
registered = self._register_dlc(entry.dlc_id)
```

```python
def _register_dlc(self, dlc_id: str) -> bool:
    try:
        states = self._dlc_manager.get_dlc_states(self.game_dir)
        enabled_set = set()
        for state in states:
            if state.enabled is True:
                enabled_set.add(state.dlc.id)
            elif state.dlc.id == dlc_id and state.installed:
                enabled_set.add(dlc_id)  # add the newly downloaded DLC
        self._dlc_manager.apply_changes(self.game_dir, enabled_set)
        return True
    except Exception as e:
        logger.warning("Could not register DLC %s: %s", dlc_id, e)
        return False
```

The registration step:

1. Reads the current state of all DLCs.
2. Builds the set of DLC IDs to enable: all currently enabled DLCs, plus the newly downloaded one.
3. Calls `apply_changes()` to write the updated crack config.

This is additive — it does not disable any currently enabled DLC. It only adds the new DLC to the enabled set.

### 7.8 Batch Download

```python
def download_multiple(
    self,
    entries: list[DLCDownloadEntry],
    progress: DLCStatusCallback | None = None,
) -> list[DLCDownloadTask]:
    """Download multiple DLCs sequentially."""
    results = []
    for entry in entries:
        if self.cancelled:
            break
        task = self.download_dlc(entry, progress=progress)
        results.append(task)
        if task.state == DLCDownloadState.FAILED:
            continue  # try next DLC anyway
    return results
```

DLCs are downloaded sequentially, not concurrently. This avoids overwhelming the server, simplifies progress reporting, and prevents partial installations from interfering with each other. A failure on one DLC does not abort the others — the comment `# try next DLC anyway` is the explicit design decision.

### 7.9 Cancellation

Cancellation is cooperative and based on a `threading.Event`:

```python
def cancel(self):
    self._cancel.set()        # signals the pipeline to stop
    self._downloader.cancel() # signals the HTTP layer to abort the current request

@property
def cancelled(self) -> bool:
    return self._cancel.is_set()
```

Cancellation is checked at three points:
1. After the download phase completes (before starting extraction).
2. On every file member during extraction.
3. In `download_multiple()` before starting each DLC.

### 7.10 Post-Extraction Validation

After extraction, the pipeline validates that the primary DLC file was successfully placed:

```python
expected = self.game_dir / entry.dlc_id / "SimulationFullBuild0.package"
if not expected.is_file():
    raise DownloadError(
        f"{entry.dlc_id} extraction incomplete: "
        f"SimulationFullBuild0.package not found"
    )
```

This provides a definitive check that the archive had the correct structure. If the archive extracted files to wrong paths, or if `SimulationFullBuild0.package` was absent from the archive, this raises a `DownloadError` before attempting registration, preventing a partially broken DLC from being registered as enabled.

### 7.11 Registration Failure as Non-Fatal

If `_register_dlc()` raises an exception (e.g., no crack config found), the task still transitions to `COMPLETED`. The message in this case is:

```text
"{dlc_id} extracted but registration failed — use Apply Changes to register manually"
```

This design decision treats file extraction as the primary success criterion. The DLC files are on disk and can be manually registered later via the "Apply Changes" button in the GUI. A missing crack config at this point is a configuration issue, not a download failure.

---

## 8. DLC Packer

`DLCPacker` (`packer.py`) is a complementary tool to the downloader. While the downloader consumes DLC archives, the packer produces them. This is used by server-side tooling to prepare DLC archives for distribution.

### 8.1 Archive Naming Convention

```python
@staticmethod
def get_zip_filename(dlc: DLCInfo) -> str:
    safe_name = dlc.name_en.encode("ascii", "ignore").decode()
    safe_name = safe_name.replace(" ", "_").replace(":", "").replace("'", "")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "_-")
    return f"Sims4_DLC_{dlc.id}_{safe_name}.zip"
```

**Example:** EP01 "The Sims 4 Get to Work" becomes:

```text
Sims4_DLC_EP01_The_Sims_4_Get_to_Work.zip
```

Non-ASCII characters are stripped, spaces become underscores, and only alphanumeric characters plus `_-` are retained. This produces safe, predictable filenames for HTTP distribution.

### 8.2 pack_single() and pack_multiple()

```python
def pack_single(
    self,
    game_dir: Path,
    dlc: DLCInfo,
    output_dir: Path,
    progress_cb: PackProgressCallback | None = None,
) -> PackResult:
```

**Pack procedure:**

1. Collect all files recursively from `<game_dir>/<dlc.id>/`.
2. Also collect files from `<game_dir>/__Installer/DLC/<dlc.id>/` if it exists. The `__Installer` subtree contains additional metadata and installer scripts that some crack setups require.
3. Create a ZIP archive with `ZIP_DEFLATED` compression.
4. Store archive members using forward-slash paths (Unix convention), regardless of the host OS.
5. Compute the archive's MD5 hash and byte size.
6. Return a `PackResult` with all metadata needed for manifest generation.

**Callback signature:** `PackProgressCallback = Callable[[int, int, str, str], None]` — called as `(current_index, total_count, dlc_id, message)`.

### 8.3 Manifest Generation

```python
def generate_manifest(
    self,
    results: list[PackResult],
    output_dir: Path,
    url_prefix: str = "<UPLOAD_URL>",
) -> Path:
```

Generates `manifest_dlc_downloads.json`:

```json
{
  "EP01": {
    "url": "https://example.com/dlcs/Sims4_DLC_EP01_The_Sims_4_Get_to_Work.zip",
    "size": 1234567890,
    "md5": "ABCDEF1234567890ABCDEF1234567890",
    "filename": "Sims4_DLC_EP01_The_Sims_4_Get_to_Work.zip"
  },
  "EP02": { ... }
}
```

The `url_prefix` is a placeholder to be filled in after the archives are uploaded to a distribution server.

### 8.4 import_archive()

```python
def import_archive(
    self,
    archive_path: Path,
    game_dir: Path,
    progress_cb: PackProgressCallback | None = None,
) -> list[str]:
```

Imports a local archive (ZIP or RAR) into the game directory. Used when a user has obtained a DLC archive through other means and wants to install it locally without the download pipeline.

- **ZIP:** Extracted using Python's `zipfile` module with the same path traversal protection as `DLCDownloader._extract_zip()`.
- **RAR:** Extracted using the bundled `tools/unrar.exe` via `subprocess`. The tool path is resolved from `constants.get_tools_dir()`.

After extraction, `_detect_dlc_dirs()` scans for any DLC directories that now exist and returns their IDs.

---

## 9. DLC Unlocker

The DLC Unlocker is a separate mechanism from the crack config toggling system. It installs a `version.dll` sideload into the EA app (EA Desktop client) that intercepts entitlement queries and grants access to DLC content without requiring the game files to be in a crack config.

### 9.1 Architecture Overview

The unlocker is implemented as a Windows DLL sideload using a technique called DLL proxying. A custom `version.dll` is placed in the EA Desktop client directory. When the client loads, it loads the custom DLL instead of the system `version.dll`. The custom DLL:

1. Reads `%APPDATA%\ToastyToast25\EA DLC Unlocker\entitlements.ini` to get a list of entitlement codes to grant.
2. Intercepts EA's entitlement check calls and returns positive results for those codes.
3. Forwards all other `version.dll` function calls to the actual system DLL to avoid breaking the client.

The actual DLL binary (`version.dll`) is bundled in `tools/DLC Unlocker for Windows/ea_app/version.dll` and is not compiled by this application — it is a third-party component (PandaDLL by ToastyToast25).

### 9.2 UnlockerStatus Dataclass

```python
@dataclass
class UnlockerStatus:
    client_name: str      # "EA app"
    client_path: str      # Path to the EA Desktop client directory
    dll_installed: bool   # version.dll exists in the client directory
    config_installed: bool  # entitlements.ini exists in %APPDATA%
    task_exists: bool     # Windows scheduled task "copy_dlc_unlocker" exists
```

A fully installed unlocker has `dll_installed == True`, `config_installed == True`, and `task_exists == True`.

The `task_exists` field reflects whether the scheduled task (used to maintain the DLL across EA app updates) is present. Its absence with the DLL installed is reported as `"Installed (task missing)"` — the unlocker works but will not survive an EA app update.

### 9.3 Client Detection

```python
def _detect_client() -> tuple[str, Path]:
    client_exe = _read_registry_value(
        r"SOFTWARE\Electronic Arts\EA Desktop", "ClientPath"
    )
    if client_exe:
        return "EA app", Path(client_exe).resolve().parent
    raise RuntimeError(
        "EA app not found. Please install the EA app first.\n"
        "Note: Origin is not supported by this unlocker."
    )
```

The EA Desktop client path is read from the Windows registry:

```text
HKLM\SOFTWARE\Electronic Arts\EA Desktop
    ClientPath = "C:\Program Files\Electronic Arts\EA Desktop\EADesktop.exe"
```

Both 64-bit and 32-bit registry views are tried (`KEY_WOW64_64KEY` and `KEY_WOW64_32KEY`) to handle installations on mixed-bitness systems. Only the EA app (EA Desktop) is supported — Origin is explicitly not supported.

### 9.4 Installation Procedure

The `install()` function (`core/unlocker.py:243`) requires administrator privileges and performs the following steps in order:

1. **Verify source files** — Check that `tools/DLC Unlocker for Windows/ea_app/version.dll` and `tools/DLC Unlocker for Windows/entitlements.ini` exist. If either is missing (possibly deleted by antivirus), raise `FileNotFoundError`.

2. **Stop client processes** — Force-terminate `EADesktop.exe`, `EABackgroundService.exe`, and `EALocalHostSvc.exe` using `taskkill /F`. Wait 2 seconds after killing any process to allow file locks to release.

3. **Remove old unlocker files** — Delete any previous unlocker DLL variants (`version_o.dll`, `winhttp.dll`, `winhttp_o.dll`) and any `w_*.ini` config files from the client directory. These are artifacts of older unlocker versions.

4. **Create config directory** — `%APPDATA%\ToastyToast25\EA DLC Unlocker\` created with `mkdir -p`.

5. **Copy entitlements config** — `entitlements.ini` to `%APPDATA%\ToastyToast25\EA DLC Unlocker\entitlements.ini`. No admin required for AppData.

6. **Copy version.dll to client** — `version.dll` to `<client_path>\version.dll`. This path is inside Program Files and requires administrator privileges. Uses retry logic with 3 attempts and 2-second delays between retries to handle file locks.

7. **Copy to staged directory** — If `<client_path>\..\StagedEADesktop\EA Desktop\` exists, copy `version.dll` there too. This is the directory used by EA Desktop during self-update staging.

8. **Create scheduled task** — Create a Windows scheduled task named `copy_dlc_unlocker`:

   ```text
   schtasks /Create /RL HIGHEST /SC ONCE /TN copy_dlc_unlocker
             /TR "xcopy.exe /Y \"<client_path>\version.dll\" \"<staged_dir>\*\""
   ```

   This task, when run, copies the unlocker DLL into the staged directory before EA Desktop installs an update, preserving the unlocker across updates.

9. **Disable background standalone** — Appends `machine.bgsstandaloneenabled=0` to `%PROGRAMDATA%\EA Desktop\machine.ini` if not already present. This prevents EA Desktop from running in background-standalone mode, which can cause the DLL sideload to not be loaded.

### 9.5 Uninstallation Procedure

The `uninstall()` function reverses the installation in order:

1. Detect the client and stop processes.
2. Remove old unlocker file variants from the client directory.
3. Delete `%APPDATA%\ToastyToast25\EA DLC Unlocker\` (and the parent `ToastyToast25\` if it becomes empty).
4. Delete `version.dll` from the client directory (with retry logic).
5. Delete `version.dll` from the staged directory if it exists.
6. Delete the `copy_dlc_unlocker` scheduled task.


Note that `machine.ini` is not reverted. The `machine.bgsstandaloneenabled=0` line is left in place after uninstall.

### 9.6 Scheduled Task Management

The task `copy_dlc_unlocker` ensures that the DLL survives EA Desktop self-updates. When EA Desktop downloads an update, it stages the new version in `StagedEADesktop\`. Before activating the update, the scheduled task copies `version.dll` into the staged directory so the new EA Desktop version also has the unlocker DLL.

The task is created with `/RL HIGHEST` (highest run level, i.e., administrative privileges) and `/SC ONCE` with a past date, making it a one-time task that can be triggered on demand. Two date formats are tried (`01/01/2000` and `2000/01/01`) because Windows `schtasks` date format expectations vary by locale:

```python
for date_fmt in ("01/01/2000", "2000/01/01"):
    result = subprocess.run(
        ["schtasks", "/Create", "/F", "/RL", "HIGHEST",
         "/SC", "ONCE", "/ST", "00:00", "/SD", date_fmt, ...],
        ...
    )
    if result.returncode == 0:
        return True
```

### 9.7 Administrator Requirement

Both `install()` and `uninstall()` begin with:

```python
if not is_admin():
    raise PermissionError("Administrator privileges required...")

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
```

Writing to `Program Files` (for `version.dll`) and creating scheduled tasks with `/RL HIGHEST` both require an elevated process. The GUI checks `is_admin()` at frame initialization and shows a warning badge and toast message if the user attempts to install or uninstall without elevation.

---

## 10. Steam Price Integration

### 10.1 SteamPrice Dataclass

```python
@dataclass
class SteamPrice:
    app_id: int
    currency: str = "USD"
    initial_cents: int = 0      # Original price in cents
    final_cents: int = 0        # Sale price in cents
    discount_percent: int = 0   # Discount percentage (0 if not on sale)
    initial_formatted: str = "" # Pre-formatted string from Steam (e.g. "$19.99")
    final_formatted: str = ""   # Pre-formatted string from Steam (e.g. "$9.99")
    is_free: bool = False        # True if the DLC is free

    @property
    def on_sale(self) -> bool:
        return self.discount_percent > 0

    @property
    def store_url(self) -> str:
        return f"https://store.steampowered.com/app/{self.app_id}"
```

### 10.2 SteamPriceCache

```python
class SteamPriceCache:
    def __init__(self, ttl: int = 1800):  # 30 minutes
        self._ttl = ttl
        self._data: dict[int, SteamPrice] = {}
        self._fetched_at: float = 0.0
        self.is_fetching: bool = False
```

The cache uses a monotonic clock timestamp and a 30-minute TTL. It is valid as long as `_data` is non-empty and the TTL has not expired. The `is_fetching` flag is used by the GUI to avoid launching multiple concurrent fetch operations.

The cache is stored on the `App` object and shared between the `DLCFrame` and the `HomeFrame` (which displays a pricing summary card).

### 10.3 Batch Fetching

```python
def fetch_prices_batch(
    app_ids: list[int],
    cc: str = "US",
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[int, SteamPrice]:
```

Prices for all DLCs with `steam_app_id` values are fetched concurrently using a `ThreadPoolExecutor` with up to 8 workers. The Steam Store API endpoint is:

```
GET https://store.steampowered.com/api/appdetails
    ?appids=<app_id>&cc=US&filters=price_overview
```

**API response handling:**

- If `success == False` for an app ID: returns `None` (DLC not found on Steam, or region-locked).
- If `price_overview` is absent: DLC is free, returns `SteamPrice(app_id=app_id, is_free=True)`.
- Otherwise: parses `initial`, `final`, `discount_percent`, and pre-formatted price strings.

Each fetch uses a 10-second timeout. Failures are silently ignored (logged at DEBUG level), meaning a partial result set is returned for network errors or rate limiting.

---

## 11. GUI Integration — DLC Frame

`DLCFrame` (`gui/frames/dlc_frame.py`) is the main DLC management tab in the application window. It presents a scrollable, filterable, searchable list of all DLC packs with their current state, and provides controls for toggling, downloading, and applying changes.

### 11.1 Layout Structure

```
DLCFrame (CTkFrame, transparent)
├── Row 0: header_frame
│   ├── Col 0: "DLC Management" heading label
│   └── Col 1: btn_frame
│       ├── Col 0: Download Missing button (hidden until manifest loads)
│       ├── Col 1: Auto-Toggle button
│       └── Col 2: Apply Changes button
├── Row 1: search_frame
│   ├── Col 0: search entry ("Search DLCs...")
│   └── Col 1: clear button (x)
├── Row 2: filter_frame
│   └── Chips: Owned | Not Owned | Installed | Patched | Downloadable | On Sale
├── Row 3: _scroll_frame (CTkScrollableFrame, weight=1)
│   └── [section headers + DLC rows, built dynamically]
└── Row 4: _status_label ("N owned, N patched, N missing | N enabled")
```

### 11.2 Data Loading Flow

```
on_show()
    -> _load_dlcs()
        -> _show_loading_skeleton()    (show 6 placeholder rows while loading)
        -> app.run_async(_get_dlc_states)
            background: updater._dlc_manager.get_dlc_states(game_dir)
        -> on_done: _on_states_loaded(states)
            -> _destroy_skeleton()
            -> _rebuild_rows()         (build all widgets from state list)
            -> _apply_filter()         (show/hide based on current filter)
            -> _load_dlc_downloads()   (fetch manifest in background)
            -> _fetch_steam_prices()   (if cache is stale)
```

`on_show()` is called each time the DLC tab becomes visible (tab switch). This re-fetches the state list, ensuring the display reflects any changes made externally (e.g., manual file operations) since the last view.

**Loading skeleton:** While the background state fetch is in progress, 6 placeholder card rows are shown using `CTkFrame` widgets sized to match real rows, with grey rectangle placeholders for the checkbox and label areas. This avoids a blank/empty appearance during loading.

### 11.3 Widget-Reuse Filtering Architecture

A key design decision in `DLCFrame` is widget reuse. Rather than destroying and recreating widgets every time the filter changes, the frame builds all row widgets once (`_build_all_rows()`) and then uses `grid()` / `grid_remove()` to show and hide them.

```python
# State tracking
self._built: bool = False                         # whether rows have been built
self._all_states: list[DLCStatus] = []            # full state list
self._row_widgets: dict[str, dict] = {}           # dlc_id -> widget reference dict
self._checkbox_vars: dict[str, ctk.BooleanVar] = {}
self._section_widgets: dict[str, dict] = {}       # pack_type -> section widget refs
self._section_collapsed: dict[str, bool] = {}     # pack_type -> is collapsed
self._desc_expanded: dict[str, bool] = {}         # dlc_id -> is description expanded
```

`_apply_filter()` is the central method that runs every time the search text or active chips change. It:

1. Filters the state list by search text (name or ID substring match).
2. Applies active chip filters (OR logic: a DLC passes if it matches any active chip).
3. For each pack type section: hides the entire section if no matching DLCs exist in it; shows and positions the section header; calls `grid()` on matching row frames and `grid_remove()` on non-matching ones.
4. Updates alternating row background colors after filtering.
5. Updates the status bar label.

This approach keeps filtering O(n) where n is the total number of DLCs, and avoids the overhead of Tkinter widget destruction and recreation.

**Full rebuild** (`_rebuild_rows()`) is only called when the underlying data changes (new states loaded, download completed, prices fetched). It destroys all existing row and section widgets and calls `_build_all_rows()` again.

### 11.4 Filter Chips

Six filter chips are defined in `_FILTER_DEFS`:

```python
_FILTER_DEFS = [
    ("owned",        "Owned"),
    ("not_owned",    "Not Owned"),
    ("installed",    "Installed"),
    ("patched",      "Patched"),
    ("downloadable", "Downloadable"),
    ("on_sale",      "On Sale"),
]
```

Chips use toggle behavior — clicking an active chip deactivates it. Multiple chips can be active simultaneously; the filter logic uses OR: a DLC is shown if it matches any of the active chips.

**Dynamic chip labels:** After prices and manifest downloads are fetched, the chips update their labels with counts:
- `"Downloadable (12)"` — DLCs available to download that are not installed.
- `"On Sale (8)"` — DLCs currently on sale on Steam.

**Chip color states:**

| State | Color |
|-------|-------|
| Inactive | `bg_card_alt` background, muted text |
| Active (general) | `accent` background, normal text |
| Active (`on_sale` / `downloadable`) | `success` (green) background, dark text |

### 11.5 DLC Row Cards

Each DLC row is built by `_build_dlc_row()`. The row is a `CTkFrame` with a `border_width=1` border that animates between `border` color (inactive) and `accent` color (hover) using the `Animator` component.

**Row element layout (left to right):**

1. **Expand arrow** (optional) — visible if the DLC has a `description`. Clicking toggles the description panel below the row.
2. **Checkbox** — reflects and controls the enabled state:
   - Owned DLCs: disabled, always checked.
   - Registered DLCs: interactive, reflects `state.enabled`.
   - Unregistered DLCs: disabled, unchecked.
3. **Price display** (optional) — shown if Steam price data is available. On sale shows discount badge, strikethrough original price, and sale price. Otherwise shows current price in muted text.
4. **Steam link button** (`arrow`) — opens `https://store.steampowered.com/app/<steam_app_id>` in the default browser.
5. **Status pill badge** — colored border with status label text (Owned, Patched, etc.).
6. **GreenLuma readiness pill** (optional) — a small "GL" pill badge placed immediately after the status pill. Appears only when GreenLuma is configured (Steam path set and GL detected) and the DLC has a `steam_app_id`. Color indicates completeness: green when all three components (AppList entry, depot decryption key, and `.manifest` file) are present; yellow when one or more are missing. Hovering displays a tooltip listing the missing components. See [Section 11.10](#1110-greenluma-readiness-indicators) for full details.
7. **Download button** — shown only if the DLC has a download available in the manifest AND its status is `Not installed`, `Missing files`, or `Incomplete`.
8. **Download progress label** — replaces the download button during an active download; shows percentage, phase name, or completion indicator.

**Description panel:** A `CTkFrame` below the row (in the content frame's grid) containing the `description` text and, if the DLC has a `steam_app_id`, a "View on Steam Store" link. If the DLC is on sale, the sale details are also shown.

### 11.6 Section Collapse

Each pack type section has a collapsible header. The header frame contains:
- An arrow label (down-arrow when expanded, right-arrow when collapsed).
- A pack type label (e.g. `"EXPANSION PACKS"`).
- An installed/total count badge (e.g. `"14/21"`).

Clicking anywhere on the header (frame, arrow, title, or count) calls `_toggle_section(pack_type)`. Collapse state is stored in `_section_collapsed` and survives filter changes. `_apply_filter()` checks the collapse state before placing the content frame:

```python
if is_collapsed:
    sw["content_frame"].grid_remove()
    continue
```

### 11.7 Action Buttons and Threading

All three header buttons route through `app.run_async()` to execute on a background thread, then call a `on_done` callback on the GUI thread:

**Auto-Toggle:**
```python
# Background:
changes = app.updater._dlc_manager.auto_toggle(game_dir)
# GUI thread (on_done):
if changes:
    app.show_toast(f"Toggled {len(changes)} DLC(s)", "success")
    _load_dlcs()  # refresh state display
```

**Apply Changes:**
```python
# Collect enabled set from checkboxes:
enabled_set = {dlc_id for dlc_id, var in self._checkbox_vars.items() if var.get()}
# Background:
app.updater._dlc_manager.apply_changes(game_dir, enabled_set)
# GUI thread (on_done):
app.show_toast("Changes applied successfully", "success")
```

### 11.8 Download Progress UI

Downloads use a raw `threading.Thread` (not the executor) to avoid blocking the single-worker `run_async` executor during long downloads:

```python
def _start_dlc_download(self, entries: list[DLCDownloadEntry]):
    self._is_downloading = True
    # Disable all action buttons while downloading
    thread = threading.Thread(target=self._download_dlcs_bg, args=(entries,), daemon=True)
    thread.start()
```

The `progress_cb` in `_download_dlcs_bg` routes all updates through `app._enqueue_gui()` to ensure widget updates happen on the main thread:

```python
def progress_cb(dlc_id, state, downloaded, total, message):
    app._enqueue_gui(
        self._update_row_download_state,
        dlc_id, state, downloaded, total, message,
    )
```

**Per-row progress display in `_update_row_download_state()`:**

| State | Label Text | Color |
|-------|-----------|-------|
| `DOWNLOADING` | `"42%"` (computed from bytes) | `accent` |
| `EXTRACTING` | `"Extracting..."` | `warning` |
| `REGISTERING` | `"Registering..."` | `warning` |
| `COMPLETED` | check mark | `success` |
| `FAILED` | cross mark + `"Failed"` | `error` |
| `CANCELLED` | `"Cancelled"` | `text_muted` |

On failure or cancellation, the download button is re-shown for retry. On completion, `_load_dlcs()` is called to refresh the state display and show the newly installed DLC as `"Patched"`.

### 11.9 Status Bar

The status label at the bottom of the frame provides an aggregate summary:

```
"14 owned, 22 patched, 73 missing  |  22 enabled"
```

This is recomputed by `_apply_filter()` every time the filter runs, using the full `_all_states` list (not the filtered subset). This means the counts always reflect the full installation, not just what is visible in the current filter view.

### 11.10 GreenLuma Readiness Indicators

The DLC frame supplements the standard status pill with a secondary "GL" pill that communicates whether each DLC is fully configured for use with GreenLuma. This feature is entirely additive and non-intrusive: if GreenLuma is not configured, no GL pills are rendered and no GL-related code runs in the hot path.

#### Data Loading

GL readiness data is fetched as part of the same background call that loads DLC states. `_get_dlc_states()` returns a three-element tuple rather than a bare state dict:

```python
# Background thread — called via app.run_async()
def _get_dlc_states(self) -> tuple[dict, dict, bool]:
    states = app.updater._dlc_manager.get_dlc_states(game_dir)
    gl_readiness, gl_installed = {}, False
    try:
        from greenluma.orchestrator import GreenLumaOrchestrator
        from dlc.catalog import DLCCatalog
        catalog = DLCCatalog.load()
        gl_readiness, gl_installed = GreenLumaOrchestrator.check_readiness(catalog)
    except Exception:
        pass  # GL not configured or not installed — silently suppress
    return states, gl_readiness, gl_installed
```

The `try/except` block makes the check best-effort. If GreenLuma's modules are not importable, the Steam path is not set, or any other error occurs, `gl_readiness` stays as an empty dict and no pills are shown. This ensures the DLC tab degrades gracefully on installations without GreenLuma.

The `on_done` callback unpacks the tuple and stores both values as instance attributes before triggering a row rebuild:

```python
def _on_states_loaded(self, result):
    states, gl_readiness, gl_installed = result
    self._all_states = states
    self._gl_readiness = gl_readiness    # dict[str, DLCReadiness]
    self._gl_installed = gl_installed    # bool
    self._rebuild_rows()
```

#### What `check_readiness()` Checks

`GreenLumaOrchestrator.check_readiness(catalog)` iterates over every DLC in the catalog that has a `steam_app_id` and checks three independent components for each one:

| Component | What is checked | Typical location |
|-----------|-----------------|------------------|
| **AppList** | Whether the DLC's Steam App ID has a corresponding entry file in GreenLuma's `AppList/` directory | `<GreenLuma_dir>/AppList/<app_id>.txt` |
| **Key** | Whether a depot decryption key for the DLC's depot is present in Steam's `config.vdf` | `<Steam_dir>/config/config.vdf` — `depots/<depot_id>/DecryptionKey` |
| **Manifest** | Whether a `.manifest` file for the DLC's depot exists in Steam's `depotcache` | `<Steam_dir>/steamapps/depotcache/<depot_id>_<manifest_id>.manifest` |

The result for each DLC is a `DLCReadiness` object:

```python
@dataclass
class DLCReadiness:
    has_applist: bool
    has_key: bool
    has_manifest: bool

    @property
    def is_ready(self) -> bool:
        return self.has_applist and self.has_key and self.has_manifest

    @property
    def missing(self) -> list[str]:
        parts = []
        if not self.has_applist: parts.append("AppList")
        if not self.has_key:     parts.append("Key")
        if not self.has_manifest: parts.append("Manifest")
        return parts
```

#### Visual Indicators

The GL pill is a small `CTkLabel` placed in the row grid immediately after the status pill (column index 5, with the download button pushed to column 6). It is only created when both conditions hold: `dlc.steam_app_id is not None` and `self._gl_installed` is `True`.

| Pill appearance | Condition | Tooltip on hover |
|----------------|-----------|-----------------|
| Green `"GL"` pill | `readiness.is_ready` — all three components present | `"GreenLuma ready"` |
| Yellow `"GL"` pill | `not readiness.is_ready` — one or more components missing | `"Missing: AppList, Key"` (lists only absent components) |
| No pill | DLC has no `steam_app_id`, or GreenLuma is not installed | — |

Colors come from `theme.COLORS` following the standard badge palette: `success` (green, `#2ECC71`) for a fully ready DLC and `warning` (yellow, `#F39C12`) for a partial configuration.

#### Hover Tooltips

Tooltips are implemented without any third-party library. When the user's cursor enters the GL pill label, a `CTkToplevel` window is created near the cursor position and destroyed on leave:

```python
def _show_gl_tooltip(self, event, text: str):
    self._gl_tooltip = ctk.CTkToplevel(self)
    self._gl_tooltip.wm_overrideredirect(True)
    self._gl_tooltip.geometry(f"+{event.x_root + 12}+{event.y_root + 4}")
    ctk.CTkLabel(self._gl_tooltip, text=text, ...).pack()

def _hide_gl_tooltip(self, event):
    if self._gl_tooltip:
        self._gl_tooltip.destroy()
        self._gl_tooltip = None
```

Each GL pill label binds `<Enter>` to `_show_gl_tooltip` and `<Leave>` to `_hide_gl_tooltip`. The tooltip window has no title bar (`wm_overrideredirect(True)`) and is positioned 12 pixels to the right of and 4 pixels below the cursor so it does not obscure the pill itself.

#### Header Badge

When `self._gl_installed` is `True`, a `"GreenLuma Installed"` badge is rendered in the DLC tab header alongside the existing action buttons. This badge uses `StatusBadge.set_status("GreenLuma Installed", "success")` and serves as a top-level confirmation that the GL readiness column is active. The badge is created once in `_build_header()` and toggled visible/hidden in `_on_states_loaded()` based on the `gl_installed` flag.

#### Instance Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `self._gl_readiness` | `dict[str, DLCReadiness]` | Maps DLC ID (e.g. `"EP01"`) to its `DLCReadiness` result. Empty dict when GL is not configured. |
| `self._gl_installed` | `bool` | `True` when GreenLuma was detected as installed during the last data load. Controls whether GL pills and the header badge are rendered at all. |
| `self._gl_tooltip` | `ctk.CTkToplevel \| None` | Reference to the currently visible tooltip window, if any. Held so `_hide_gl_tooltip` can destroy it. |

---

## 12. GUI Integration — Unlocker Frame

`UnlockerFrame` (`gui/frames/unlocker_frame.py`) is the DLC Unlocker management tab.

**Layout:**

```
UnlockerFrame
├── Row 0: top (fixed, non-scrolling)
│   ├── "DLC Unlocker" heading
│   ├── Subtitle label
│   ├── InfoCard (status card):
│   │   ├── Row 0: Client — badge (e.g. "EA app")
│   │   ├── Row 1: Status — badge (e.g. "Installed" / "Not Installed")
│   │   └── Row 2: Admin — badge ("Elevated" / "Not Elevated")
│   └── btn_frame:
│       ├── "Install Unlocker" button
│       ├── "Uninstall" button
│       └── "Open Configs" button
└── Row 1: log section (scrollable, fills remaining height)
    ├── "Activity Log" label + "Clear" button
    └── CTkTextbox (read-only log viewer)
```

**Status detection flow:**

```
on_show()
    -> _refresh_status()
        background: get_status(log=_enqueue_log)
        -> _done(status): _update_badges()
```

The `get_status()` function from `core/unlocker.py` logs each detection step via the callback, which routes through `_enqueue_log()` for thread-safe GUI updates.

**Install flow:**

```
_on_install()
    -> check is_admin — warn and return if not elevated
    -> _set_busy(True) — disable both action buttons
    -> log("--- Installing DLC Unlocker ---")
    background: install(log=_enqueue_log)
    -> done: show_toast("DLC Unlocker installed!"), _refresh_status()
    -> error: log(error), show_toast(error), _refresh_status()
```

**Uninstall flow:**

```
_on_uninstall()
    -> check is_admin — warn and return if not elevated
    -> tk.messagebox.askyesno confirmation dialog
    -> _set_busy(True)
    -> log("--- Uninstalling DLC Unlocker ---")
    background: uninstall(log=_enqueue_log)
    -> done: show_toast("DLC Unlocker uninstalled."), _refresh_status()
```

**"Open Configs" button:** Calls `open_configs_folder()` which runs `os.startfile()` on `%APPDATA%\ToastyToast25\EA DLC Unlocker\`. If the directory does not exist (unlocker not installed), a toast warning is shown.

**Admin badge:** The `is_admin()` check runs at frame construction time (not on `on_show()`). This is because elevation level is a fixed property of the process — it does not change during a session. The badge shows `"Elevated"` (success) or `"Not Elevated"` (warning).

---

## 13. Data Flow Diagrams

### 13.1 State Detection Flow

```
GUI: DLCFrame.on_show()
         |
         v
  run_async(_get_dlc_states)
         |
         v
  [background thread]
  updater.find_game_dir()
         |
         v
  DLCManager.get_dlc_states(game_dir)
         |
         +-- detect_format(game_dir)
         |       |
         |       +-- AnadiusCodexAdapter.detect()   check anadius.cfg + Config2
         |       +-- AnadiusSimpleAdapter.detect()  check anadius.cfg, no Config2
         |       +-- RuneAdapter.detect()            check rune.ini
         |       +-- CodexAdapter.detect()           check codex.cfg
         |       +-- RldOriginAdapter.detect()       check RldOrigin.ini
         |       +-- return first match, or None
         |
         +-- adapter.get_config_path(game_dir)
         |
         +-- config_path.read_text()  [once, into memory]
         |
         +-- for each DLC in catalog:
         |       +-- check game_dir / dlc.id / exists  -> installed
         |       +-- check SimulationFullBuild0.package -> complete
         |       +-- count files in dlc dir             -> file_count
         |       +-- adapter.read_enabled_dlcs(content, dlc.all_codes)
         |               -> {code: bool} for found codes
         |       +-- registered = any code found
         |       +-- enabled = state of first found code
         |       +-- owned = installed and not registered
         |       +-- yield DLCStatus
         |
         v
  [GUI thread]
  _on_states_loaded(states)
         |
         +-- _rebuild_rows()   [destroy old, build new widgets]
         +-- _apply_filter()   [show/hide rows per current filters]
```

### 13.2 Download Pipeline Flow

```
User clicks download button on EP15 row
         |
         v
  DLCFrame._on_download_single("EP15")
         |
         v
  _start_dlc_download([entry])
         |
         v
  [background thread: _download_dlcs_bg]
         |
         v
  DLCDownloader.download_dlc(entry)
         |
         +-- [PENDING -> DOWNLOADING]
         |   progress_cb("EP15", DOWNLOADING, 0, size, "Downloading EP15...")
         |       Downloader.download_file(file_entry, progress=dl_progress)
         |           [HTTP GET with Range, resume, MD5 check]
         |       progress_cb(dlc_id, DOWNLOADING, N, total, filename)  [per chunk]
         |
         +-- check cancelled -> CANCELLED if true
         |
         +-- [DOWNLOADING -> EXTRACTING]
         |   progress_cb("EP15", EXTRACTING, 0, 0, "Extracting EP15...")
         |       _extract_zip(archive_path, "EP15")
         |           [for each zip member: path traversal check, extract]
         |
         +-- validate SimulationFullBuild0.package exists
         |   raise DownloadError if not found
         |
         +-- check cancelled -> CANCELLED if true
         |
         +-- [EXTRACTING -> REGISTERING]
         |   progress_cb("EP15", REGISTERING, 0, 0, "Registering EP15...")
         |       _register_dlc("EP15")
         |           get_dlc_states(game_dir)
         |           enabled_set = currently_enabled | {"EP15"}
         |           apply_changes(game_dir, enabled_set)
         |
         +-- [REGISTERING -> COMPLETED]
         |   progress_cb("EP15", COMPLETED, size, size, "EP15 installed successfully")
         |
         v
  [GUI thread via _enqueue_gui]
  _update_row_download_state("EP15", COMPLETED, ...)
         |
         v
  _on_download_done(results)
         |
         +-- show_toast("Downloaded 1 DLC(s) successfully")
         +-- _load_dlcs()  [refresh state display]
```

### 13.3 Apply Changes Flow

```
User checks/unchecks DLC checkboxes, clicks "Apply Changes"
         |
         v
  DLCFrame._on_apply()
         |
         v
  enabled_set = {dlc_id for dlc_id, var in _checkbox_vars.items() if var.get()}
         |
         v
  run_async(_apply_bg, enabled_set)
         |
         v
  [background thread]
  DLCManager.apply_changes(game_dir, enabled_set)
         |
         +-- detect_format(game_dir)  [re-detect on every call]
         |
         +-- config_path.read_text()
         |
         +-- for each DLC in catalog:
         |       for each code in dlc.all_codes:
         |           should_enable = dlc.id in enabled_set
         |           content = adapter.set_dlc_state(content, code, should_enable)
         |
         +-- config_path.write_text(content)
         |
         +-- if Bin_LE exists: shutil.copy2(config_path, bin_le_path)
         |
         v
  [GUI thread]
  _on_apply_done()
         |
         v
  app.show_toast("Changes applied successfully")
```

---

## 14. Exception Hierarchy

All custom exceptions inherit from `UpdaterError` (`core/exceptions.py`):

```
UpdaterError (base)
├── ExitingError           — Application is shutting down
├── WritePermissionError   — Cannot write to target path (permission denied)
├── NotEnoughSpaceError    — Insufficient disk space
├── FileMissingError       — Required file not found
├── VersionDetectionError  — Cannot determine game version
├── ManifestError          — Manifest fetch or parse failure
├── DownloadError          — HTTP download or extraction failure
├── IntegrityError         — MD5/hash verification failure
├── NoUpdatePathError      — No update path found in manifest
├── NoCrackConfigError     — No supported crack config in game directory
├── XdeltaError            — Xdelta3 patch application failure
└── AVButtinInError        — Antivirus interference detected
```

**DLC-specific exception usage:**

- `NoCrackConfigError` — raised by `DLCManager.apply_changes()` when no crack config is found.
- `DownloadError` — raised by `DLCDownloader` for HTTP failures, corrupt archives, cancelled extractions, and failed post-extraction validation.

All other exceptions (OS errors, permission errors, network timeouts) propagate as their standard Python types and are caught at the GUI layer.

---

## 15. Configuration and Constants

The DLC system reads from `constants.py`:

```python
APP_NAME = "Sims 4 Updater"
APP_VERSION = "2.0.0"

# Registry keys for game directory auto-detection
REGISTRY_PATHS = [
    r"SOFTWARE\Maxis\The Sims 4",
    r"SOFTWARE\WOW6432Node\Maxis\The Sims 4",
]

# Default paths probed if registry lookup fails
DEFAULT_GAME_PATHS = [
    r"C:\Program Files\EA Games\The Sims 4",
    r"C:\Program Files (x86)\EA Games\The Sims 4",
    r"D:\Games\The Sims 4",
]

# Files that must exist for a directory to be recognized as a valid installation
SIMS4_INSTALL_MARKERS = [
    "Game/Bin/TS4_x64.exe",
    "Data/Client",
]
```

**Data directory resolution** (frozen PyInstaller bundle vs. source):
```python
def get_data_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "data"         # inside the .exe bundle
    return Path(__file__).resolve().parent.parent.parent / "data"  # repo root /data
```

**DLC-specific paths within the data dir:**
- `data/dlc_catalog.json` — bundled DLC catalog.
- `tools/DLC Unlocker for Windows/ea_app/version.dll` — unlocker DLL.
- `tools/DLC Unlocker for Windows/entitlements.ini` — entitlements config template.
- `tools/unrar.exe` — RAR extraction tool for `DLCPacker.import_archive()`.

**Steam pricing constants** (`steam.py`):
```python
STEAM_API_URL = "https://store.steampowered.com/api/appdetails"
CACHE_TTL_SECONDS = 1800   # 30 minutes
REQUEST_TIMEOUT = 10        # seconds per request
MAX_WORKERS = 8             # concurrent fetch threads
```

**Unlocker constants** (`core/unlocker.py`):
```python
_COMMON_DIR = r"ToastyToast25\EA DLC Unlocker"
_ENTITLEMENTS_FILE = "entitlements.ini"
_TASK_NAME = "copy_dlc_unlocker"
```

---

## Appendix A: Complete Crack Config Format Examples

### RldOrigin.ini

```ini
[Launcher]
Language=en_US

[DLC]
IID1=SIMS4.OFF.SOLP.0x000000000001266C
IID2=SIMS4.OFF.SOLP.0x0000000000011A4B
;IID3=SIMS4.OFF.SOLP.0x0000000000016C2A
IID4=SIMS4.OFF.SOLP.0x000000000001C03A
IID5=SIMS4.OFF.SOLP.0x0000000000011AC5
```

In this example: FP01, GP01, GP03, EP01 are enabled. GP02 (`;IID3=`) is disabled.

### codex.cfg (CODEX format)

```
"SIMS4.OFF.SOLP.0x0000000000011AC5"
{
    "DLC"           "1"
    "Group"         "THESIMS4PC"
    "Name"          "The Sims 4 Get to Work"
    "GroupLabel"    "1"
}

"SIMS4.OFF.SOLP.0x00000000000170FF"
{
    "DLC"           "1"
    "Group"         "_"
    "Name"          "The Sims 4 Get Together"
    "GroupLabel"    "1"
}
```

EP01 is enabled (`"THESIMS4PC"`). EP02 is disabled (`"_"`).

### rune.ini

```ini
[SIMS4.OFF.SOLP.0x0000000000011AC5]
activated=1

[SIMS4.OFF.SOLP.0x00000000000170FF_]
activated=1

[SIMS4.OFF.SOLP.0x000000000001D5ED]
activated=1
```

EP01 and EP03 are enabled (no trailing underscore). EP02 is disabled (`_` suffix in the section header).

### anadius.cfg (Simple format)

```
{
    "Config"
    {
        "SIMS4.OFF.SOLP.0x0000000000011AC5"
        //"SIMS4.OFF.SOLP.0x00000000000170FF"
        "SIMS4.OFF.SOLP.0x000000000001D5ED"
    }
}
```

EP01 and EP03 are enabled. EP02 (`//`) is disabled.

### anadius.cfg (Codex-like format, with Config2)

```
"Config"
{
    ...
}

"Config2"
{
    "SIMS4.OFF.SOLP.0x0000000000011AC5"
    {
        "DLC"    "1"
        "Group"  "THESIMS4PC"
    }
    "SIMS4.OFF.SOLP.0x00000000000170FF"
    {
        "DLC"    "1"
        "Group"  "_"
    }
}
```

Detected by presence of `"Config2"`. Same enable/disable mechanism as CODEX.

---

## Appendix B: DLC Catalog JSON Schema

**File:** `data/dlc_catalog.json`

```json
{
  "schema_version": 1,
  "dlcs": [
    {
      "id": "EP01",
      "code": "SIMS4.OFF.SOLP.0x0000000000011AC5",
      "code2": "",
      "names": {
        "en_us": "The Sims 4 Get to Work",
        "de_de": "Die Sims 4 An die Arbeit",
        "fr_fr": "Les Sims 4 Au Travail"
      },
      "type": "expansion",
      "description": "Adds three career tracks with active gameplay...",
      "steam_app_id": null
    }
  ]
}
```

**Field definitions:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | int | Yes | Currently `1` |
| `dlcs` | array | Yes | Array of DLC entry objects |
| `id` | string | Yes | Unique DLC identifier (e.g. `"EP01"`) |
| `code` | string | Yes | Primary entitlement code, or `""` if unknown |
| `code2` | string | No | Secondary entitlement code, or `""` |
| `names` | object | Yes | `{locale_lowercase: display_name}` |
| `type` | string | Yes | One of: `expansion`, `game_pack`, `stuff_pack`, `kit`, `free_pack` |
| `description` | string | No | Short English description |
| `steam_app_id` | int or null | No | Steam store App ID, or `null` |

**Custom DLC file** (`%APPDATA%/<app>/custom_dlcs.json`): Same structure as `dlc_catalog.json`, but without `schema_version`. Only contains DLC entries not present in the bundled catalog.

---

## Appendix C: Manifest DLC Download Schema

The remote manifest provides DLC download entries. The relevant portion of the manifest that the DLC downloader consumes is:

```json
{
  "dlc_downloads": {
    "EP01": {
      "url": "https://example.com/dlcs/Sims4_DLC_EP01_The_Sims_4_Get_to_Work.zip",
      "size": 1234567890,
      "md5": "ABCDEF1234567890ABCDEF1234567890",
      "filename": "Sims4_DLC_EP01_The_Sims_4_Get_to_Work.zip",
      "dlc_id": "EP01"
    }
  }
}
```

`manifest.dlc_downloads` is a `dict[str, DLCDownloadEntry]` keyed by DLC ID, fetched by `DLCFrame._fetch_dlc_downloads_bg()` and stored in `_dlc_downloads`.

`DLCDownloadEntry.to_file_entry()` converts the manifest entry into the `FileEntry` type used by the generic patch `Downloader`:

```python
# FileEntry has: url, size, md5, filename
file_entry = entry.to_file_entry()
result = downloader.download_file(file_entry, progress=...)
# result.path is the path to the downloaded archive
```

The `size` field is used to initialize `DLCDownloadTask.total_bytes` before the download begins, enabling accurate percentage display even before the HTTP response `Content-Length` header is received. The `md5` field is used by the `Downloader` for post-download integrity verification — if the MD5 does not match, a `DownloadError` or `IntegrityError` is raised.
