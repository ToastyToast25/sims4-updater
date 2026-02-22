# Update and Patching System — Technical Reference

**Project:** Sims 4 Updater
**Version Documented:** 2.1.0
**Date:** 2026-02-20
**Scope:** Core update pipeline, version detection, manifest parsing, update planning, download management, patch application, DLC state preservation, and hash learning

---

## Table of Contents

1. [Overview](#1-overview)
   - 1.1 [System Purpose](#11-system-purpose)
   - 1.2 [Full Pipeline at a Glance](#12-full-pipeline-at-a-glance)
   - 1.3 [Module Map](#13-module-map)
2. [Version Detection](#2-version-detection)
   - 2.1 [Sentinel File Strategy](#21-sentinel-file-strategy)
   - 2.2 [VersionDatabase — Merging Multiple Sources](#22-versiondatabase--merging-multiple-sources)
   - 2.3 [VersionDetector — Detection Logic](#23-versiondetector--detection-logic)
   - 2.4 [DetectionResult and Confidence Levels](#24-detectionresult-and-confidence-levels)
   - 2.5 [Game Directory Auto-Detection](#25-game-directory-auto-detection)
   - 2.6 [Detection Flow Diagram](#26-detection-flow-diagram)
3. [Manifest System](#3-manifest-system)
   - 3.1 [Manifest Purpose and Location](#31-manifest-purpose-and-location)
   - 3.2 [Manifest JSON Structure](#32-manifest-json-structure)
   - 3.3 [Data Classes](#33-data-classes)
   - 3.4 [Parsing Pipeline](#34-parsing-pipeline)
   - 3.5 [Patch-Pending State](#35-patch-pending-state)
   - 3.6 [DLC Catalog Integration](#36-dlc-catalog-integration)
4. [Update Planning](#4-update-planning)
   - 4.1 [The Patch Graph](#41-the-patch-graph)
   - 4.2 [BFS Shortest-Path Algorithm](#42-bfs-shortest-path-algorithm)
   - 4.3 [Tie-Breaking by Download Size](#43-tie-breaking-by-download-size)
   - 4.4 [UpdatePlan and UpdateStep](#44-updateplan-and-updatestep)
   - 4.5 [Planning Flow Diagram](#45-planning-flow-diagram)
   - 4.6 [Edge Cases](#46-edge-cases)
5. [Download System](#5-download-system)
   - 5.1 [Downloader Architecture](#51-downloader-architecture)
   - 5.2 [Resume Support](#52-resume-support)
   - 5.3 [MD5 Integrity Verification](#53-md5-integrity-verification)
   - 5.4 [Progress Callbacks](#54-progress-callbacks)
   - 5.5 [HTTP Session Configuration](#55-http-session-configuration)
   - 5.6 [Cancellation Model](#56-cancellation-model)
   - 5.7 [Download Flow Diagram](#57-download-flow-diagram)
   - 5.8 [PatchClient Download Orchestration](#58-patchclient-download-orchestration)
6. [Patch Application](#6-patch-application)
   - 6.1 [Inheritance from BasePatcher](#61-inheritance-from-basepatcher)
   - 6.2 [Metadata Loading Override](#62-metadata-loading-override)
   - 6.3 [The Patcher Pipeline Internals](#63-the-patcher-pipeline-internals)
   - 6.4 [xdelta3 Binary Delta Application](#64-xdelta3-binary-delta-application)
   - 6.5 [Crack Extraction via unrar](#65-crack-extraction-via-unrar)
   - 6.6 [File Move Strategy](#66-file-move-strategy)
   - 6.7 [Patch Application Flow Diagram](#67-patch-application-flow-diagram)
7. [DLC State Preservation](#7-dlc-state-preservation)
   - 7.1 [The Problem Being Solved](#71-the-problem-being-solved)
   - 7.2 [DLCManager Interface](#72-dlcmanager-interface)
   - 7.3 [Export States Before Patching](#73-export-states-before-patching)
   - 7.4 [Import States After Patching](#74-import-states-after-patching)
   - 7.5 [New DLC Detection and Auto-Enable](#75-new-dlc-detection-and-auto-enable)
   - 7.6 [DLC State Preservation Flow Diagram](#76-dlc-state-preservation-flow-diagram)
8. [Hash Learning](#8-hash-learning)
   - 8.1 [Why Hash Learning Exists](#81-why-hash-learning-exists)
   - 8.2 [LearnedHashDB Internals](#82-learnedhashdb-internals)
   - 8.3 [Persistence and Atomic Writes](#83-persistence-and-atomic-writes)
   - 8.4 [Sources of Learned Fingerprints](#84-sources-of-learned-fingerprints)
   - 8.5 [Crowd-Sourced Hash Reporting](#85-crowd-sourced-hash-reporting)
   - 8.6 [Hash Learning Flow Diagram](#86-hash-learning-flow-diagram)
9. [Error Handling](#9-error-handling)
   - 9.1 [Exception Hierarchy](#91-exception-hierarchy)
   - 9.2 [Exception Descriptions and Causes](#92-exception-descriptions-and-causes)
   - 9.3 [Error Propagation Strategy](#93-error-propagation-strategy)
10. [Sims4Updater Class](#10-sims4updater-class)
    - 10.1 [Class Overview and Inheritance](#101-class-overview-and-inheritance)
    - 10.2 [UpdateState Enum](#102-updatestate-enum)
    - 10.3 [Constructor and Dependency Wiring](#103-constructor-and-dependency-wiring)
    - 10.4 [Lazy PatchClient Initialization](#104-lazy-patchclient-initialization)
    - 10.5 [The update() Orchestration Method](#105-the-update-orchestration-method)
    - 10.6 [Full Orchestration Flow Diagram](#106-full-orchestration-flow-diagram)
    - 10.7 [Lifecycle and Cleanup](#107-lifecycle-and-cleanup)
11. [Configuration and Persistence](#11-configuration-and-persistence)
    - 11.1 [Settings Dataclass](#111-settings-dataclass)
    - 11.2 [App Data Directory](#112-app-data-directory)
    - 11.3 [Directory Migration](#113-directory-migration)
12. [Constants and Installation Markers](#12-constants-and-installation-markers)
13. [Appendix A — Manifest JSON Reference](#appendix-a--manifest-json-reference)
14. [Appendix B — File Layout Reference](#appendix-b--file-layout-reference)
15. [Appendix C — Callback Protocol](#appendix-c--callback-protocol)

---

## 1. Overview

### 1.1 System Purpose

The Sims 4 Updater is a self-contained offline/assisted patching system for The Sims 4. It replaces the need for EA's own update mechanism by:

1. Detecting the currently installed game version by fingerprinting sentinel files with MD5 hashes.
2. Fetching a remotely hosted manifest that describes the available patch chain.
3. Planning the minimal-step update path using BFS on the patch graph.
4. Downloading only the required patch archives with HTTP range-request resume support.
5. Applying binary delta patches (via xdelta3) and extracting crack/game files from RAR archives (via unrar).
6. Preserving user-configured DLC states across the update and auto-enabling any genuinely new DLC content.
7. Learning and caching new version fingerprints locally and reporting them back to the crowd-sourced API.

The system is structured as an extension of a general-purpose `Patcher` base class (from the sibling `patcher/` package). `Sims4Updater` inherits the raw patch-application machinery and adds all of the above network-aware orchestration on top.

### 1.2 Full Pipeline at a Glance

```text
 User triggers update
         |
         v
 +-------------------+
 |  1. DETECTING     |  VersionDetector hashes sentinel files,
 |  Find game dir    |  matches against VersionDatabase,
 |  Detect version   |  returns DetectionResult with confidence.
 +-------------------+
         |
         v
 +-------------------+
 |  2. CHECKING      |  PatchClient fetches remote manifest JSON.
 |  Fetch manifest   |  check_update() compares current vs latest.
 |  Plan update path |  plan_update() runs BFS on patch graph.
 +-------------------+
         |  update_available == False -> DONE
         v  update_available == True  -> continue
 +-------------------+
 |  3. DOWNLOADING   |  Downloader fetches each patch file in plan.
 |  Per-step download|  HTTP Range headers enable resume.
 |  MD5 verification |  .partial files renamed to final on success.
 +-------------------+
         |
         v
 +-------------------+
 |  4. PATCHING      |  BasePatcher pipeline:
 |  Load ZIP metadata|    load_all_metadata() scans download dir
 |  Hash local files |    hash_files() identifies current state
 |  Apply xdelta3    |    apply_patches() runs xdelta3 per file
 |  Extract crack    |    extract_crack() runs unrar
 |  Move to game dir |    move_updated_files() replaces game files
 +-------------------+
         |
         v
 +-------------------+
 |  5. FINALIZING    |  learn_version() hashes new sentinels,
 |  Learn new hashes |  saves to LearnedHashDB, reports to API.
 |  Restore DLC state|  import_states() restores user preferences,
 |  Enable new DLCs  |  new DLCs installed by patch are enabled.
 +-------------------+
         |
         v
       DONE
```

### 1.3 Module Map

```text
sims4-updater/
  src/sims4_updater/
    updater.py                  <- Sims4Updater — main orchestrator
    config.py                   <- Settings dataclass, app dir, migration
    constants.py                <- Sentinel files, registry paths, markers

    core/
      version_detect.py         <- VersionDatabase, VersionDetector, DetectionResult
      learned_hashes.py         <- LearnedHashDB — writable fingerprint cache
      exceptions.py             <- Custom exception hierarchy
      files.py                  <- hash_file(), write_check(), file utilities

    patch/
      client.py                 <- PatchClient — manifest + download orchestrator
      manifest.py               <- parse_manifest(), Manifest, PatchEntry, FileEntry
      planner.py                <- plan_update(), BFS, UpdatePlan, UpdateStep
      downloader.py             <- Downloader — HTTP download with resume + MD5

    dlc/
      manager.py                <- DLCManager — export/import states, apply_changes

patcher/ (sibling package, not part of sims4-updater source)
  patcher/
    patcher.py                  <- BasePatcher — xdelta3, unrar, file hashing
    exceptions.py               <- Base patcher exceptions
    files.py                    <- File utilities shared with updater
```

---

## 2. Version Detection

Version detection is the first step in the update pipeline. Its job is to determine precisely which version of The Sims 4 is currently installed, without relying on any metadata stored by the game itself (which may be absent, stale, or unreadable). The approach is based on MD5 hashing of a small set of well-chosen files whose content changes with every game update.

### 2.1 Sentinel File Strategy

A "sentinel file" is a file within the game installation that is known to change between versions. By hashing these files and comparing the hashes against a database of known version fingerprints, the installed version can be identified without parsing any game-internal versioning structures.

The sentinel files are defined in `constants.py`:

```python
# src/sims4_updater/constants.py, line 30
SENTINEL_FILES = [
    "Game/Bin/TS4_x64.exe",
    "Game/Bin/Default.ini",
    "delta/EP01/version.ini",
]
```

**Why these three files:**

- `Game/Bin/TS4_x64.exe` — the main game executable. This is the most reliable sentinel because it is always replaced on update and its size/content changes are guaranteed. However, it is the largest file and takes longest to hash.
- `Game/Bin/Default.ini` — a small configuration file that is updated alongside the executable. Hashing this alone is fast and usually sufficient.
- `delta/EP01/version.ini` — a version metadata file within the first expansion pack's data directory. Including this allows disambiguation when two base-game versions share the same executable hash (which is rare but possible after hotfixes).

Together, these three sentinels form a fingerprint for each version. A match on all three produces a `DEFINITIVE` confidence result. A match on fewer sentinels (because one or more files are missing from the installation) produces a `PROBABLE` result.

The hashing function, defined in `core/files.py`, is MD5 with 64 KB chunks:

```python
# src/sims4_updater/core/files.py, line 123
def hash_file(path, chunk_size=65536, progress=None):
    m = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            m.update(chunk)
    return m.hexdigest().upper()
```

The result is an uppercase hex string such as `"A3B2C1..."`. MD5 is used here not for cryptographic security but for speed — the intent is fingerprinting, not tamper detection (integrity checking for downloaded files uses the same mechanism via `_verify_md5` in the downloader).

### 2.2 VersionDatabase — Merging Multiple Sources

`VersionDatabase` (`core/version_detect.py`, line 35) is an in-memory registry of known version fingerprints. It is constructed by merging two data sources:

1. **Bundled database** — a `version_hashes.json` file shipped with the application, located at the path returned by `constants.get_data_dir() / "version_hashes.json"`. This file is compiled into the frozen executable by PyInstaller and contains fingerprints for all versions known at build time.

2. **Learned database** — the `LearnedHashDB` instance, which holds fingerprints accumulated at runtime (described in detail in Section 8). The learned database takes priority for overlapping version keys, meaning that if a user's machine has produced a more complete or corrected fingerprint for a known version, that corrected fingerprint is used.

```python
# src/sims4_updater/core/version_detect.py, line 42
class VersionDatabase:
    def __init__(self, db_path=None, learned_db=None):
        # Load bundled JSON
        with open(db_path, encoding="utf-8") as f:
            data = json.load(f)
        self.sentinel_files = data["sentinel_files"]
        self.versions = dict(data["versions"])

        # Merge learned hashes — learned wins on overlap
        if self._learned_db.versions:
            for version, hashes in self._learned_db.versions.items():
                if version in self.versions:
                    self.versions[version] = {**self.versions[version], **hashes}
                else:
                    self.versions[version] = dict(hashes)
            # Extend sentinel list with any new sentinels from learned DB
            for s in self._learned_db.sentinel_files:
                if s not in self.sentinel_files:
                    self.sentinel_files.append(s)
```

The merge semantics are deliberate: `{**bundled, **learned}` means the learned value wins for any key that exists in both. This allows corrections to be propagated without shipping a new build.

The `lookup()` method on `VersionDatabase` takes a dict of `{sentinel_path: md5_hash}` pairs (the hashes computed from the local installation) and matches them against all known version fingerprints:

```python
# src/sims4_updater/core/version_detect.py, line 69
def lookup(self, local_hashes):
    matches = []
    for version, fingerprint in self.versions.items():
        match = True
        matched_count = 0
        for sentinel, expected_hash in fingerprint.items():
            local_hash = local_hashes.get(sentinel)
            if local_hash is None:
                continue  # sentinel missing locally — skip, do not disqualify
            if local_hash != expected_hash:
                match = False
                break
            matched_count += 1

        if match and matched_count > 0:
            matches.append((version, matched_count))
```

The algorithm is conservative: a sentinel that is missing on disk does not disqualify a version — it is simply not counted. This handles installations that are missing optional DLC files used as sentinels. A version must have at least one matching sentinel to be a candidate.

### 2.3 VersionDetector — Detection Logic

`VersionDetector` (`core/version_detect.py`, line 124) owns a `VersionDatabase` and provides two public operations: `validate_game_dir()` and `detect()`.

**validate_game_dir()** checks for the presence of installation markers:

```python
# src/sims4_updater/constants.py, line 37
SIMS4_INSTALL_MARKERS = [
    "Game/Bin/TS4_x64.exe",
    "Data/Client",
]
```

Both `Game/Bin/TS4_x64.exe` (a file) and `Data/Client` (a directory) must exist. This guard prevents false-positive detection on arbitrary directories.

**detect()** iterates the sentinel file list, computes MD5 hashes for those that exist, then calls `db.lookup()`:

```python
# src/sims4_updater/core/version_detect.py, line 141
def detect(self, game_dir, progress=None):
    sentinels = self.db.sentinel_files
    local_hashes = {}

    for i, sentinel in enumerate(sentinels):
        file_path = game_dir / sentinel.replace("/", os.sep)
        if progress:
            progress(sentinel, i, total)
        if not file_path.is_file():
            continue
        local_hashes[sentinel] = hash_file(str(file_path))

    return self.db.lookup(local_hashes)
```

The optional `progress` callback receives `(sentinel_name, current_index, total_count)` on each sentinel and `("done", total, total)` at completion. This allows the UI to display a meaningful progress indicator during what may be a multi-second hashing operation (the main executable can be several hundred megabytes).

### 2.4 DetectionResult and Confidence Levels

```python
# src/sims4_updater/core/version_detect.py, line 21
class Confidence(Enum):
    DEFINITIVE = "definitive"  # unique match on all available sentinels
    PROBABLE   = "probable"    # matched but some sentinels missing
    UNKNOWN    = "unknown"     # no match found

@dataclass
class DetectionResult:
    version: str | None
    confidence: Confidence
    local_hashes: dict[str, str]
    matched_versions: list[str]
```

| Confidence | Condition |
| --- | --- |
| `DEFINITIVE`  | Exactly one version matched the local hashes.                             |
| `PROBABLE`    | One or more versions matched, with the best having two or more sentinels. |
| `UNKNOWN`     | No version in the database matched any local sentinel hash.               |

When confidence is `UNKNOWN`, `version` is `None` and the updater raises `VersionDetectionError`. When it is `PROBABLE`, the best match is returned but the system proceeds — this is the common case for users who do not have all DLC packs installed.

### 2.5 Game Directory Auto-Detection

`VersionDetector.find_game_dir()` attempts to locate the installation automatically:

1. **Windows Registry** (Windows only) — reads `HKLM\SOFTWARE\Maxis\The Sims 4` and `HKLM\SOFTWARE\WOW6432Node\Maxis\The Sims 4`, then `HKCU` for both paths, extracting the `Install Dir` value. This is the most reliable method for standard EA App installations.

2. **Default path probing** — iterates `constants.DEFAULT_GAME_PATHS`:

```python
# src/sims4_updater/constants.py, line 23
DEFAULT_GAME_PATHS = [
    r"C:\Program Files\EA Games\The Sims 4",
    r"C:\Program Files (x86)\EA Games\The Sims 4",
    r"D:\Games\The Sims 4",
]
```

Each candidate is validated with `validate_game_dir()`. The first valid path is returned.

In `Sims4Updater`, `find_game_dir()` first checks `settings.game_path` (a previously saved path) before delegating to the detector. If a valid path is found, it is saved back to settings for future use.

### 2.6 Detection Flow Diagram

```
 Sims4Updater.detect_version(game_dir)
         |
         | game_dir is None?
         |   Yes -> find_game_dir()
         |            -> check settings.game_path (validate_game_dir)
         |            -> Windows Registry (HKLM, then HKCU)
         |            -> Default path list
         |            -> return first valid path or None
         |   No  -> use provided game_dir
         |
         v
 VersionDetector.validate_game_dir(game_dir)
   checks: Game/Bin/TS4_x64.exe exists
           Data/Client exists
         |
         | Not valid -> raise VersionDetectionError
         | Valid     -> continue
         |
         v
 VersionDetector.detect(game_dir)
   for each sentinel in db.sentinel_files:
     if file exists:
       local_hashes[sentinel] = hash_file(file)
         |
         v
 VersionDatabase.lookup(local_hashes)
   for each (version, fingerprint) in self.versions:
     match = True
     matched_count = 0
     for sentinel, expected_hash in fingerprint:
       if local_hash missing: skip
       if local_hash != expected_hash: match=False; break
       matched_count += 1
     if match and matched_count > 0: append(version, count)
         |
         | no matches -> UNKNOWN
         | matches    -> sort by count desc; pick best
         |
         v
 DetectionResult(version, confidence, local_hashes, matched_versions)
         |
         v
 settings.last_known_version = result.version  (if not None)
```

---

## 3. Manifest System

### 3.1 Manifest Purpose and Location

The manifest is a JSON file hosted at a configurable remote URL (stored in `settings.manifest_url`). It serves as the single source of truth for:

- What version is the latest patchable version.
- What patches exist between which version pairs.
- Where to download each patch file.
- What fingerprints are known for each version (for hash learning).
- What DLC catalog updates are available.
- What DLCs are announced but not yet patchable.

Decoupling patch hosting from the application binary means patches can be published to any file host and the updater does not need to be recompiled to discover them.

### 3.2 Manifest JSON Structure

A complete manifest document has the following top-level keys:

```json
{
  "latest": "1.120.365.1020",
  "game_latest": "1.121.000.1020",
  "game_latest_date": "2025-11-15",
  "patches": [...],
  "fingerprints": {...},
  "fingerprints_url": "https://example.com/fingerprints.json",
  "report_url": "https://example.com/api/report_hashes",
  "new_dlcs": [...],
  "dlc_catalog": [...],
  "dlc_downloads": {...}
}
```

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `latest` | string | Yes | Highest version reachable via the current patch chain. |
| `game_latest` | string | No | Actual latest EA release. May be ahead of `latest` if a patch is pending. |
| `game_latest_date` | string | No | ISO date of the most recent EA release. |
| `patches` | array | No | List of patch entry objects. |
| `fingerprints` | object | No | Map of `{version: {sentinel: md5}}` for hash learning. |
| `fingerprints_url` | string | No | URL to a crowd-sourced fingerprints JSON endpoint. |
| `report_url` | string | No | URL to POST newly learned hashes to. |
| `new_dlcs` | array | No | DLCs announced but not yet patchable. |
| `dlc_catalog` | array | No | DLC metadata records for catalog updates. |
| `dlc_downloads` | object | No | Map of `{dlc_id: download_entry}` for individual DLC download support. |

**Patch entry format** (within the `patches` array):

```json
{
  "from": "1.119.265.1020",
  "to": "1.120.365.1020",
  "files": [
    {
      "url": "https://cdn.example.com/patch_119_to_120.zip",
      "size": 452100096,
      "md5": "A3B2C1D0E9F8A7B6C5D4E3F2A1B0C9D8",
      "filename": "patch_119_to_120.zip"
    }
  ],
  "crack": {
    "url": "https://cdn.example.com/crack_120.rar",
    "size": 8192000,
    "md5": "B4C3D2E1F0A9B8C7D6E5F4A3B2C1D0E9",
    "filename": "crack_120.rar"
  }
}
```

The `filename` field is optional in the JSON; if absent, it is derived from the last path segment of the `url` (stripping any query string). This is handled in `FileEntry.__post_init__()`.

### 3.3 Data Classes

The manifest module defines a hierarchy of dataclasses that mirror the JSON structure:

**FileEntry** — a single downloadable file:

```python
# src/sims4_updater/patch/manifest.py, line 17
@dataclass
class FileEntry:
    url: str
    size: int
    md5: str
    filename: str = ""   # derived from URL if not provided

    def __post_init__(self):
        if not self.filename:
            self.filename = self.url.rsplit("/", 1)[-1].split("?")[0]
```

**PatchEntry** — one step in the patch chain:

```python
# src/sims4_updater/patch/manifest.py, line 31
@dataclass
class PatchEntry:
    version_from: str
    version_to: str
    files: list[FileEntry] = field(default_factory=list)
    crack: FileEntry | None = None

    @property
    def total_size(self) -> int:
        total = sum(f.size for f in self.files)
        if self.crack:
            total += self.crack.size
        return total
```

Note that a `PatchEntry` may contain multiple `FileEntry` objects in `files`. This supports splitting large patches across several archives to work around file-hosting size limits or to allow partial re-downloads.

**DLCDownloadEntry** — a standalone DLC content archive:

```python
# src/sims4_updater/patch/manifest.py, line 69
@dataclass
class DLCDownloadEntry:
    dlc_id: str
    url: str
    size: int = 0
    md5: str = ""
    filename: str = ""

    def to_file_entry(self) -> FileEntry:
        """Convert to FileEntry for use with Downloader."""
        return FileEntry(url=self.url, size=self.size,
                         md5=self.md5, filename=self.filename)
```

**Manifest** — the root object:

```python
# src/sims4_updater/patch/manifest.py, line 91
@dataclass
class Manifest:
    latest: str
    patches: list[PatchEntry]
    fingerprints: dict[str, dict[str, str]]
    fingerprints_url: str
    report_url: str
    manifest_url: str
    game_latest: str
    game_latest_date: str
    new_dlcs: list[PendingDLC]
    dlc_catalog: list[ManifestDLC]
    dlc_downloads: dict[str, DLCDownloadEntry]

    @property
    def patch_pending(self) -> bool:
        """True when the game has a newer EA release that isn't yet patchable."""
        return bool(self.game_latest and self.game_latest != self.latest)
```

### 3.4 Parsing Pipeline

`parse_manifest()` (`patch/manifest.py`, line 126) is the entry point for turning a raw Python dict (from `resp.json()`) into a `Manifest` object. It validates required fields and delegates sub-object parsing to `_parse_patch_entry()`:

```python
def parse_manifest(data: dict, source_url: str = "") -> Manifest:
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON object.")

    latest = data.get("latest")
    if not latest or not isinstance(latest, str):
        raise ManifestError("Manifest missing 'latest' version string.")

    patches = []
    for i, entry in enumerate(data.get("patches", [])):
        try:
            patches.append(_parse_patch_entry(entry))
        except (KeyError, TypeError, ValueError) as e:
            raise ManifestError(f"Invalid patch entry at index {i}: {e}") from e
    ...
```

The parser applies defensive programming: every optional field has a safe default, and any parsing error for a patch entry wraps the underlying cause in a `ManifestError` with the index of the offending entry. This makes debugging malformed manifests straightforward.

### 3.5 Patch-Pending State

The `patch_pending` property signals that the real game has been updated by EA but no patch has yet been produced for the new version:

```python
@property
def patch_pending(self) -> bool:
    return bool(self.game_latest and self.game_latest != self.latest)
```

This state is surfaced to the user through `UpdateInfo.patch_pending`, allowing the UI to display a message such as "Game version 1.121.000 was released on 2025-11-15, patch coming soon." The updater does not attempt to update when in this state — `check_update()` returns `update_available=False` and `patch_pending=True`.

### 3.6 DLC Catalog Integration

When a manifest is fetched, its `dlc_catalog` list (if non-empty) is merged into the local `DLCCatalog` instance via `DLCCatalog.merge_remote()`. This allows the publisher to push DLC metadata (names, pack types, internal codes) to all clients as a side-channel of the manifest fetch, without requiring a separate catalog update mechanism.

```python
# src/sims4_updater/patch/client.py, line 138
if self._dlc_catalog and self._manifest.dlc_catalog:
    self._dlc_catalog.merge_remote(self._manifest.dlc_catalog)
```

---

## 4. Update Planning

### 4.1 The Patch Graph

The manifest's `patches` list describes a directed graph where each `PatchEntry` is a directed edge from `version_from` to `version_to`. A typical graph for a game that has gone through several major updates looks like:

```
1.116 --[P1]--> 1.117 --[P2]--> 1.118 --[P3]--> 1.119 --[P4]--> 1.120
                  \                                /
                   \--------[P5 cumulative]-------/
```

In this example, a user on 1.117 can reach 1.120 via two routes: stepping through P2 + P3 + P4 (three steps), or using the cumulative patch P5 (one step, but potentially a larger download). The planner finds the shortest path and, among ties, picks the smallest total download.

The graph is built from the manifest in `plan_update()`:

```python
# src/sims4_updater/patch/planner.py, line 75
graph: dict[str, list[PatchEntry]] = {}
for patch in manifest.patches:
    graph.setdefault(patch.version_from, []).append(patch)
```

This is a standard adjacency list representation. The graph may have multiple edges from the same source (alternative patches to the same or different targets).

### 4.2 BFS Shortest-Path Algorithm

The core planning function is `_bfs_all_shortest()` (`patch/planner.py`, line 104). It finds all shortest paths (in terms of hop count) from `start` to `end` using a standard BFS with path tracking:

```python
# src/sims4_updater/patch/planner.py, line 104
def _bfs_all_shortest(graph, start, end):
    queue = deque([(start, [])])
    best_dist = {start: 0}
    results = []
    shortest_found = float("inf")

    while queue:
        current, path = queue.popleft()

        if len(path) >= shortest_found:
            continue

        for patch in graph.get(current, []):
            next_version = patch.version_to
            new_path = path + [patch]
            new_dist = len(new_path)

            if next_version == end:
                if new_dist <= shortest_found:
                    shortest_found = new_dist
                    results.append(new_path)
                continue

            if next_version not in best_dist or new_dist <= best_dist[next_version]:
                best_dist[next_version] = new_dist
                queue.append((next_version, new_path))

    return results
```

Key properties of this implementation:

- **Completeness:** All shortest paths are collected (not just one). This is necessary to perform the download-size tie-breaking in the next step.
- **Pruning:** The `shortest_found` cut-off prevents exploring paths longer than the first solution found. The `best_dist` dict similarly prunes paths that reach an intermediate node via a longer route than already known.
- **Memory:** Each queue entry stores the full accumulated path as a list of `PatchEntry` objects. For typical patch graphs (which rarely exceed 10-20 versions at a time), this is negligible. For very long chains, the memory usage grows proportionally with the number of distinct shortest paths.

### 4.3 Tie-Breaking by Download Size

When multiple paths of equal length are found, `plan_update()` selects the one with the smallest total download:

```python
# src/sims4_updater/patch/planner.py, line 88
best_path = min(paths, key=lambda p: sum(patch.total_size for patch in p))
```

`PatchEntry.total_size` sums the sizes of all files (including the crack file, if present) for that patch step. This ensures that when a "full" patch to a version exists alongside an incremental chain, the incremental chain is preferred if it saves download bandwidth — or the full patch is chosen if it is actually smaller (common for the first patch after a major game update that touches most files).

### 4.4 UpdatePlan and UpdateStep

```python
# src/sims4_updater/patch/planner.py, line 17
@dataclass
class UpdateStep:
    patch: PatchEntry
    step_number: int    # 1-based index within the plan
    total_steps: int    # total number of steps in this plan

@dataclass
class UpdatePlan:
    current_version: str
    target_version: str
    steps: list[UpdateStep]

    @property
    def total_download_size(self) -> int:
        return sum(step.patch.total_size for step in self.steps)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def is_up_to_date(self) -> bool:
        return self.current_version == self.target_version
```

Each `UpdateStep` wraps one `PatchEntry` and adds positional metadata (`step_number`, `total_steps`) that the UI and logging use to display progress like "Step 2/3: 1.118 -> 1.119".

The `UpdatePlan` is the object handed between `PatchClient.check_update()` and `PatchClient.download_update()`. It is also embedded in the `UpdateInfo` returned from `check_update()` so the caller has both the summary metadata and the actionable plan in one place.

### 4.5 Planning Flow Diagram

```
 plan_update(manifest, current_version, target_version)
         |
         | current == target?
         |   Yes -> return empty UpdatePlan (is_up_to_date=True)
         |   No  -> continue
         |
         v
 Build adjacency list: graph[version_from] = [PatchEntry, ...]
         |
         v
 _bfs_all_shortest(graph, current_version, target_version)
   deque: [(current, [])]
   best_dist: {current: 0}
   shortest_found: inf

   loop while queue not empty:
     pop (current, path)
     if len(path) >= shortest_found: skip
     for patch in graph[current]:
       new_path = path + [patch]
       if patch.version_to == target:
         if new_dist <= shortest_found:
           shortest_found = new_dist
           results.append(new_path)
       elif new_dist <= best_dist[next_version]:
         best_dist[next_version] = new_dist
         queue.append((next_version, new_path))
         |
         v
 paths = [list[PatchEntry], ...]   (all shortest)
         |
         | empty? -> raise NoUpdatePathError
         | non-empty -> continue
         |
         v
 best_path = min(paths, key=total_size)
         |
         v
 steps = [UpdateStep(patch, i+1, total) for i, patch in enumerate(best_path)]
         |
         v
 return UpdatePlan(current_version, target_version, steps)
```

### 4.6 Edge Cases

| Situation                                           | Behaviour                                                                                   |
|-----------------------------------------------------|---------------------------------------------------------------------------------------------|
| `current_version == target_version`                 | Returns an empty `UpdatePlan` (0 steps). `is_up_to_date` is True.                         |
| No path from current to target in graph             | Raises `NoUpdatePathError` with descriptive message.                                        |
| Current version not present as `version_from`       | The BFS starts from a node with no outgoing edges; no paths found; raises `NoUpdatePathError`. |
| Multiple equal-length paths with same download size | Whichever path `min()` returns first (stable across Python runs for a given manifest).       |
| Circular patches (A->B->A->...)                     | `best_dist` prevents re-visiting a node via a longer path; BFS terminates.                  |

---

## 5. Download System

### 5.1 Downloader Architecture

The `Downloader` class (`patch/downloader.py`, line 42) manages all HTTP file downloads. It owns a lazily-initialized `requests.Session` and a shared `threading.Event` for cancellation:

```python
class Downloader:
    def __init__(self, download_dir, cancel_event=None):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._cancel = cancel_event or threading.Event()
        self._session = None
```

The session is created once on first use via the `session` property. Sharing a single session across all downloads within a `PatchClient` lifetime means TCP connections can be reused (HTTP keep-alive), reducing latency for sequential downloads from the same host.

### 5.2 Resume Support

The downloader supports HTTP range requests for resuming interrupted downloads. The mechanism uses a `.partial` file naming convention:

```
final_path   = download_dir / subdir / "patch_119_to_120.zip"
partial_path = download_dir / subdir / "patch_119_to_120.zip.partial"
```

The resume flow within `download_file()`:

```python
# src/sims4_updater/patch/downloader.py, line 111
resume_from = 0
if partial_path.is_file():
    resume_from = partial_path.stat().st_size

headers = {}
if resume_from > 0:
    headers["Range"] = f"bytes={resume_from}-"

resp = self.session.get(entry.url, headers=headers, stream=True, ...)
resp.raise_for_status()

if resp.status_code == 206:
    # Server honoured the Range header — resume mode
    content_range = resp.headers.get("Content-Range", "")
    total_size = int(content_range.rsplit("/", 1)[1])
    mode = "ab"   # append to existing partial
    resumed = True
else:
    # Server returned 200 (full content) — start fresh
    total_size = int(resp.headers.get("Content-Length", 0)) or entry.size
    mode = "wb"   # overwrite
    resume_from = 0
    resumed = False
```

If the server returns `206 Partial Content`, the `Content-Range` header is parsed to determine the total file size, and the partial file is opened in append mode (`"ab"`). If the server does not support range requests (returns `200 OK`), the partial file is discarded and the download starts from the beginning.

After a successful download, the partial file is atomically renamed to the final path:

```python
# src/sims4_updater/patch/downloader.py, line 184
partial_path.replace(final_path)
```

`Path.replace()` is an atomic rename on POSIX systems and on Windows within the same volume. This guarantees that `final_path` is never left in a partially-written state — it either does not exist (download incomplete) or contains a complete, verified file.

### 5.3 MD5 Integrity Verification

After writing completes but before the rename, the downloader verifies the file's MD5 against the expected hash from the manifest:

```python
# src/sims4_updater/patch/downloader.py, line 173
if entry.md5:
    if not _verify_md5(partial_path, entry.md5):
        partial_path.unlink(missing_ok=True)
        raise IntegrityError(
            f"MD5 mismatch for {entry.filename}.\n"
            f"Expected: {entry.md5}\n"
            f"The file may be corrupted or tampered with."
        )
    verified = True
```

If verification fails, the partial file is deleted (so a retry will restart the download) and `IntegrityError` is raised. The `DownloadResult` returned on success includes a `verified=True` flag.

There is also a fast-path skip: if `final_path` already exists and its MD5 matches, the download is skipped entirely and a result with `bytes_downloaded=0` is returned. This makes re-running the updater after an interrupted session (where some files completed) very efficient.

```python
# src/sims4_updater/patch/downloader.py, line 99
if final_path.is_file() and entry.md5:
    if _verify_md5(final_path, entry.md5):
        if progress:
            progress(entry.size, entry.size, entry.filename)
        return DownloadResult(entry=entry, path=final_path,
                              verified=True, resumed=False, bytes_downloaded=0)
```

### 5.4 Progress Callbacks

Progress is reported via the `ProgressCallback` type alias:

```python
# src/sims4_updater/patch/downloader.py, line 24
ProgressCallback = Callable[[int, int, str], None]
# Arguments: (bytes_downloaded, total_bytes, filename)
```

The callback is invoked:
- Once at the start of a download (with `downloaded=resume_from` if resuming).
- Once per chunk (every 65,536 bytes by default, controlled by `CHUNK_SIZE`).
- Not at completion — the final chunk write fires the last progress call.

For multi-file operations (`download_files()`), the callback receives cumulative bytes across all files, so the caller sees a single monotonically increasing counter for the full batch.

In `PatchClient.download_update()`, progress is further aggregated across all steps:

```python
# src/sims4_updater/patch/client.py, line 247
grand_total = plan.total_download_size
grand_downloaded = 0

for step in plan.steps:
    step_base = grand_downloaded
    def step_progress(downloaded, total, filename):
        if progress:
            progress(step_base + downloaded, grand_total, filename)
    # ... download step files
    grand_downloaded += entry.size
```

This means the UI always receives `(bytes_so_far_across_all_steps, grand_total, current_filename)` regardless of how many steps the update requires.

### 5.5 HTTP Session Configuration

The session is created by `_create_session()`:

```python
# src/sims4_updater/patch/downloader.py, line 238
def _create_session():
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT

    session = requests.Session()
    retry = requests.adapters.Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = _TimeoutSSLAdapter(ctx, retry=retry)
    session.mount("https://", adapter)
    session.mount("http://", requests.adapters.HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "Sims4Updater/2.0"
    return session
```

Key decisions:

- **`OP_LEGACY_SERVER_CONNECT`** — enables the `SSL_OP_LEGACY_SERVER_CONNECT` option in the SSL context. This is required to connect to some older CDN servers that do not support RFC 5746 (secure renegotiation) correctly. Without it, Python's `ssl` module rejects connections to these servers.
- **Retry with exponential backoff** — `backoff_factor=1` means retries wait 0s, 1s, 2s, 4s, 8s between attempts. The status code list covers rate-limiting (`429`) and transient server errors (`500`, `502`, `503`, `504`).
- **`_TimeoutSSLAdapter`** — a custom `HTTPAdapter` subclass that injects default timeouts `(CONNECT_TIMEOUT=30s, READ_TIMEOUT=60s)` for any request that does not specify its own timeout, and mounts a custom SSL context via `PoolManager`.

```python
CONNECT_TIMEOUT = 30   # seconds to establish TCP connection
READ_TIMEOUT    = 60   # seconds to receive each chunk after connection
```

### 5.6 Cancellation Model

Cancellation uses a `threading.Event` shared among the `Downloader`, `PatchClient`, and `Sims4Updater`:

```python
# Sims4Updater.__init__
self._cancel = threading.Event()

# Passed to PatchClient
PatchClient(cancel_event=self._cancel, ...)

# PatchClient passes it to Downloader
Downloader(cancel_event=self._cancel)
```

The event is checked at three levels:

1. **Before each file download** — `if self.cancelled: raise DownloadError("cancelled")`
2. **Per chunk** — `if self.cancelled: raise DownloadError("cancelled")` inside the streaming loop
3. **Before each step** — `if self.cancelled: raise DownloadError("cancelled")` in `download_update()`

When `Sims4Updater.exiting_extra()` is called (during application shutdown), it sets the event: `self._cancel.set()`. This causes the next cancellation check in the download loop to raise `DownloadError`, which propagates up through `download_update()` and `update()`, and is caught by the `except Exception` block in `update()` which transitions to `UpdateState.ERROR`.

### 5.7 Download Flow Diagram

```
 Downloader.download_file(entry, progress, subdir)
         |
         | self.cancelled? -> raise DownloadError
         |
         v
 Resolve paths:
   dest_dir     = download_dir / subdir
   final_path   = dest_dir / entry.filename
   partial_path = final_path + ".partial"
         |
         | final_path exists AND MD5 matches?
         |   Yes -> return DownloadResult(verified=True, bytes_downloaded=0)
         |   No  -> continue
         |
         v
 resume_from = partial_path.stat().st_size if partial exists else 0
         |
         v
 GET entry.url
   headers["Range"] = "bytes={resume_from}-"  (if resume_from > 0)
   stream=True, timeout=(30, 60)
         |
         | resp.status_code == 206?
         |   Yes -> mode="ab", total_size from Content-Range header
         |   No  -> mode="wb", total_size from Content-Length, resume_from=0
         |
         v
 open(partial_path, mode) and iterate resp.iter_content(65536):
   write chunk
   downloaded += len(chunk)
   progress(downloaded, total_size, filename)
   if cancelled: raise DownloadError
         |
         | network/IO error -> raise DownloadError
         |
         v
 entry.md5 provided?
   Yes -> _verify_md5(partial_path, entry.md5)
     MD5 mismatch -> partial_path.unlink(); raise IntegrityError
     MD5 match    -> verified = True
   No  -> verified = False
         |
         v
 partial_path.replace(final_path)   [atomic rename]
         |
         v
 return DownloadResult(path=final_path, verified, resumed, bytes_downloaded)
```

### 5.8 PatchClient Download Orchestration

`PatchClient.download_update()` (`patch/client.py`, line 213) iterates the steps in an `UpdatePlan` and downloads all files for each step into a version-pair-named subdirectory:

```python
for step in plan.steps:
    patch = step.patch
    subdir = f"{patch.version_from}_to_{patch.version_to}"

    for entry in patch.files:
        result = self.downloader.download_file(entry, progress=..., subdir=subdir)
        grand_downloaded += entry.size

    if patch.crack:
        result = self.downloader.download_file(patch.crack, progress=..., subdir=subdir)
        grand_downloaded += patch.crack.size
```

For a plan covering `1.118 -> 1.119 -> 1.120`, the download directory structure will be:

```
downloads/
  1.118_to_1.119/
    patch_118_to_119.zip
    crack_119.rar
  1.119_to_1.120/
    patch_119_to_120.zip
    crack_120.rar
```

This organisation makes it easy to retry individual steps, clean up partial downloads, and feed the correct files to the patcher.

---

## 6. Patch Application

### 6.1 Inheritance from BasePatcher

`Sims4Updater` inherits from `BasePatcher` (`patcher/patcher.py`), which provides the complete raw patch-application machinery. The relationship is:

```
patcher.patcher.Patcher (BasePatcher)
    |
    +-- sims4_updater.updater.Sims4Updater
```

`BasePatcher` is loaded at runtime by inserting the sibling `patcher/` package directory into `sys.path`:

```python
# src/sims4_updater/updater.py, line 21
_patcher_root = Path(__file__).resolve().parents[3] / "patcher"
if (
    _patcher_root.is_dir()
    and (_patcher_root / "patcher" / "__init__.py").is_file()
    and str(_patcher_root) not in sys.path
):
    sys.path.insert(0, str(_patcher_root))

from patcher.patcher import Patcher as BasePatcher, CallbackType
```

This dynamic path manipulation allows the updater to be developed and distributed independently from the base patcher package, with the relationship expressed as a filesystem sibling rather than an installed dependency.

The `Sims4Updater` overrides three methods from `BasePatcher`:

| Method                  | BasePatcher Behaviour                         | Sims4Updater Override                                        |
|-------------------------|-----------------------------------------------|--------------------------------------------------------------|
| `load_all_metadata()`   | Scans current working directory for ZIPs      | Scans `self._download_dir` (and subdirs) recursively         |
| `_get_crack_path(crack)` | Looks for crack file in CWD                  | Looks in `self._download_dir` and subdirs first, falls back to CWD |
| `do_after_extraction()` | Raises `PatcherError` on extraction failure   | Logs a warning but does not raise (allows retry)             |

### 6.2 Metadata Loading Override

The base patcher's `load_all_metadata()` scans the current working directory. This is appropriate for the standalone patcher where the user places ZIP files next to the executable. For the updater, downloaded files are in a dedicated `downloads/` directory managed by the application.

The override uses `rglob("*")` to find all files recursively within `self._download_dir`:

```python
# src/sims4_updater/updater.py, line 222
def load_all_metadata(self, types=None):
    if types is None:
        types = ("patch", "dlc")

    all_metadata = {}
    search_dirs = [self._download_dir]

    for search_dir in search_dirs:
        for file in search_dir.rglob("*"):
            if not file.is_file():
                continue
            try:
                metadata = self.load_metadata(file)
            except myzipfile.BadZipFile:
                continue
            ...
```

Each ZIP file's embedded metadata is read by `BasePatcher.load_metadata()`, which uses a custom `myzipfile.ZipFile` that reads the ZIP central directory to find a special metadata entry. Files that are not valid ZIPs, or ZIPs without metadata, are silently skipped.

### 6.3 The Patcher Pipeline Internals

Once metadata is loaded, the `BasePatcher.patch()` method executes a multi-phase pipeline:

**Phase 1: Metadata Parsing** — `parse_metadata()` extracts two data structures:
- `files_info`: `{filename: (expected_md5, expected_size)}` — the target state of every file.
- `all_delta`: `{delta_filename: delta_info_dict}` — all binary delta files with their metadata.

**Phase 2: File Checking** — `check_files()` scans three locations (game dir, final dir, extracted dir) to find existing copies of files that are candidates for patching. Files with the right size to be either the source or target of a delta are included. Files that are missing entirely and required (not optional) cause an immediate `FileMissingError`.

**Phase 3: Hash Files** — `hash_files()` / `_hash_files()` computes MD5 hashes for every candidate file, using a size/mtime cache to avoid rehashing unchanged files. After hashing, each file is classified as either "already at target state" (no patching needed), "patchable" (has the right source MD5 for a delta), or "useless" (wrong version, not needed). Useless files are marked for deletion.

**Phase 4: Find Best Updates** — `find_best_updates()` determines the optimal update strategy for each file. For a file that needs updating from MD5_A to MD5_B:
- If a full replacement file is available (downloaded "full" file), use it directly.
- If a binary delta is available, apply the delta to the existing file.
- If multiple paths are available (e.g., a cached partial update from a previous run), choose the path that minimises bytes to extract from the archive.

**Phase 5: Extract Files** — `extract_files()` streams files out of the ZIP archives into `self._extracted_dir`. Space is checked before each extraction.

**Phase 6: Apply Patches** — `apply_patches()` runs xdelta3 for each file that requires binary delta application. The output goes to `self._final_dir`.

**Phase 7: Extract Crack** — `extract_crack()` runs unrar to extract the crack RAR archive into `self._crack_dir`.

**Phase 8: Move Files** — `move_updated_files()` moves all updated files from `_final_dir` and `_crack_dir` into the live game directory, replacing the originals atomically.

### 6.4 xdelta3 Binary Delta Application

The `_xdelta()` method in `BasePatcher` calls the `xdelta3` executable as a subprocess:

```python
# patcher/patcher.py, line 1248
p = self.run(["xdelta3", "-v", "-f"] + args + [str(dst)])
```

For simple two-step patches (source + one delta): `xdelta3 -v -f -d -s {source} {delta} {output}`

For multi-step chains: xdelta3's merge mode is used first to combine deltas, then applied once. If the merge fails, deltas are applied one by one as a fallback.

Output from xdelta3 is parsed line by line to extract progress:

```
xdelta3: 0: in ./Game/Bin/TS4_x64.exe out 45.2 MiB
```

The regex `r"xdelta3: \d+: in .*? out (\d+(?:\.\d+)?) ((?:[KMGT]i)?B)"` extracts the output bytes written, which is used to update the progress indicator.

Windows paths containing non-ASCII characters are handled by first attempting to resolve the 8.3 short path using `win32file.FindFilesW()`. If no short path exists, the file is copied to a temporary ASCII-safe path before invoking xdelta3.

### 6.5 Crack Extraction via unrar

The crack file is a password-protected (or open) RAR archive containing modified game executables or configuration files that enable the patched game to run. It is extracted using the `unrar` command-line utility:

```python
# patcher/patcher.py, line 1539
args = [
    "unrar", "x", "-p-", "-o+",
    crack_path,
    str(self._crack_dir) + "/",
]
if (password := crack.get("pass")) is not None:
    args.insert(3, f"-p{password}")
```

`-o+` means "overwrite without asking". The password is embedded in the patch metadata if required.

Return codes from unrar are mapped to human-readable error messages. Codes not in the known map are raised as `UnhandledError` to surface the full output for debugging.

### 6.6 File Move Strategy

`move_updated_files()` moves files from the staging directories to the game directory. On the same volume, `Path.replace()` is used for an atomic rename. When source and destination are on different volumes (`errno.EXDEV`), the method falls back to a chunk-copy-then-delete approach, with space checks before the copy.

After all files are moved, obsolete files listed in the patch metadata's `deleted` key are removed from the game directory. These are files that existed in older versions but are not present in the new version.

### 6.7 Patch Application Flow Diagram

```
 Sims4Updater.update() calls:
   self.load_all_metadata()       -> scan downloads/ for ZIPs
   self.pick_game(game_name)      -> parse_patches(), filter_metadata()
   self.select_language(lang)     -> remove other language files from required set
   self.check_files_quick(game_dir) -> scan game dir, final dir, extracted dir
   self.patch(selected_dlcs)      -> BasePatcher.patch()
         |
         v
 BasePatcher.patch(selected_dlcs)
   add_selected_dlcs(metadata, selected_dlcs)
         |
         v
   parse_metadata(metadata)
     -> files_info = {file: (md5, size)}
     -> all_delta  = {file+ext: delta_info}
         |
         v
   check_files(metadata, files_info, all_delta)
     scan game_dir, final_dir, extracted_dir
     -> local_files  = {file: [candidate_info, ...]}
     -> local_patches = {delta_file: patch_info}
         |
         v
   hash_files(metadata, files_info, all_delta, local_files, local_patches)
     MD5 each candidate (cache by size+mtime)
     -> to_delete = [info, ...]  (superseded copies)
         |
         v
   find_best_updates(metadata, local_files, files_info, to_delete)
     for each file: find minimal-extraction update path
     -> best = {file: (full_file_info, [delta_infos...])}
         |
         v
   delete_unnecessary_files(to_delete)
         |
         v
   extract_files(to_extract)
     for each archive ZIP:
       check disk space
       stream each file from ZIP -> extracted_dir/
         |
         v
   apply_patches(best)
     for each file needing patching:
       if 1 delta:  xdelta3 -d -s src delta -> final_dir/file
       if N deltas: xdelta3 merge deltas -> combined -> final_dir/file
     -> updated = {file: (dst, game_dst, size)}
         |
         v
   extract_crack(crack, updated)
     unrar x crack.rar -> crack_dir/
     add crack files to updated dict
         |
         v
   move_updated_files(updated, extra_files)
     for each (src, dst, size):
       write_check(game_dir)
       check disk space
       dst.unlink() if exists
       src.replace(dst)  OR  copy+delete if cross-volume
         |
         v
   delete game files in metadata["deleted"]
         |
         v
   finished() -> callback(FINISHED)
```

---

## 7. DLC State Preservation

### 7.1 The Problem Being Solved

The Sims 4's crack/unlock mechanism uses a configuration file that lists which DLC packs are enabled. When a patch is applied, this configuration file may be overwritten with a new default state (all installed DLCs enabled, or a specific set defined by the crack). Any DLC that the user had manually disabled would be re-enabled.

Additionally, a game update might install new DLC directories that did not exist before. These should be enabled automatically (they represent new content the user is entitled to), but only if they are genuinely new — not if the user had previously installed and then manually disabled them.

The DLC state preservation system solves both problems:

1. Before patching: snapshot the current enabled/disabled state of every DLC.
2. After patching: restore the snapshot, preserving user preferences.
3. After restoring: identify DLCs that were not in the snapshot (genuinely new), and enable them.

### 7.2 DLCManager Interface

`DLCManager` (`dlc/manager.py`) provides the interface for reading and writing DLC states:

```python
class DLCManager:
    def export_states(self, game_dir) -> dict[str, bool]:
        """Snapshot: {dlc_id: enabled_bool} for all DLCs with a known state."""

    def import_states(self, game_dir, saved_states: dict[str, bool]) -> None:
        """Restore: enable/disable DLCs according to saved_states."""

    def get_dlc_states(self, game_dir, locale="en_US") -> list[DLCStatus]:
        """Full state query: installed, complete, registered, enabled, owned."""

    def apply_changes(self, game_dir, enabled_dlcs: set[str]) -> None:
        """Write: enable all DLCs in enabled_dlcs, disable all others."""
```

The actual read/write of the crack config file is delegated to a `DLCConfigAdapter` selected by `detect_format()`, which determines the crack format from the files present in the game directory. This abstraction allows the manager to work with multiple crack formats without the higher-level code caring about the format details.

`apply_changes()` writes the updated config back to disk and, as a compatibility measure, copies it to a `Bin_LE` variant if that directory exists:

```python
# src/sims4_updater/dlc/manager.py, line 119
bin_le_path = Path(str(config_path).replace("Bin", "Bin_LE"))
if bin_le_path.parent.is_dir() and bin_le_path != config_path:
    shutil.copy2(config_path, bin_le_path)
```

### 7.3 Export States Before Patching

`export_states()` calls `get_dlc_states()` and filters to only those DLCs that have a known state (i.e., are registered in the crack config — `enabled is not None`):

```python
# src/sims4_updater/dlc/manager.py, line 151
def export_states(self, game_dir):
    states = self.get_dlc_states(game_dir)
    return {
        s.dlc.id: s.enabled
        for s in states
        if s.enabled is not None
    }
```

A DLC with `enabled=None` is one that is installed on disk but does not appear in the crack config at all. This typically means it is a free pack that EA handles natively. Such packs are excluded from the snapshot because they do not need to be managed by the crack config.

The result is a simple `dict[str, bool]`, e.g.:

```python
{
    "EP01": True,   # Get to Work — enabled
    "EP02": False,  # Get Together — user disabled this
    "GP01": True,   # Outdoor Retreat — enabled
}
```

This snapshot is taken in `update()` immediately before calling `self.patch()`:

```python
# src/sims4_updater/updater.py, line 415
saved_dlc_states = self._dlc_manager.export_states(game_dir)
```

### 7.4 Import States After Patching

After the patch completes, the snapshot is restored:

```python
# src/sims4_updater/updater.py, line 436
if saved_dlc_states:
    self._dlc_manager.import_states(game_dir, saved_dlc_states)
```

`import_states()` constructs an `enabled_dlcs` set from the saved states and calls `apply_changes()`:

```python
# src/sims4_updater/dlc/manager.py, line 160
def import_states(self, game_dir, saved_states):
    enabled_set = {dlc_id for dlc_id, enabled in saved_states.items() if enabled}
    self.apply_changes(game_dir, enabled_set)
```

This re-writes the crack config to match the user's pre-patch preferences exactly.

### 7.5 New DLC Detection and Auto-Enable

After restoring, the code queries the current state of all DLCs and identifies those that were not in the saved snapshot:

```python
# src/sims4_updater/updater.py, line 439
current_states = self._dlc_manager.get_dlc_states(game_dir)
new_enabled = set()
changes = {}

for state in current_states:
    if state.dlc.id in saved_dlc_states:
        # Was known before the patch — keep user's previous choice
        if saved_dlc_states[state.dlc.id]:
            new_enabled.add(state.dlc.id)
    elif state.installed:
        # Not in snapshot AND now installed = new DLC from this patch
        new_enabled.add(state.dlc.id)
        changes[state.dlc.id] = True

if changes:
    self._dlc_manager.apply_changes(game_dir, new_enabled)
    if status:
        status(f"Enabled {len(changes)} new DLC(s)")
```

The logic has two branches for each DLC in `current_states`:

- **In `saved_dlc_states`**: The DLC existed before the patch. Preserve the user's original enabled/disabled choice. (The `import_states()` call already did this, but this loop reconstructs `new_enabled` to potentially merge new DLCs in.)
- **Not in `saved_dlc_states` AND installed**: This DLC was added by the patch itself. Enable it automatically. This ensures content the user is entitled to is available immediately after update.

If `changes` is non-empty (new DLCs were found), `apply_changes()` is called once more with the combined set.

### 7.6 DLC State Preservation Flow Diagram

```
 update() -- before patch:
   saved_dlc_states = dlc_manager.export_states(game_dir)
   #  {dlc_id: bool, ...} for all crack-config-registered DLCs
         |
         v
   self.patch(selected_dlcs)   <- BasePatcher pipeline runs
   # Crack config may be overwritten by crack extraction
         |
         v
 update() -- after patch:
   dlc_manager.import_states(game_dir, saved_dlc_states)
   #  Writes saved states back to crack config
         |
         v
   current_states = dlc_manager.get_dlc_states(game_dir)
         |
         v
   for each state in current_states:
     if state.dlc.id in saved_dlc_states:
       preserve user's old choice
     elif state.installed:
       mark as new (auto-enable)
         |
         v
   if any new DLCs:
     dlc_manager.apply_changes(game_dir, new_enabled_set)
     status("Enabled N new DLC(s)")
```

---

## 8. Hash Learning

### 8.1 Why Hash Learning Exists

The bundled `version_hashes.json` can only contain fingerprints for versions known at build time. When a new game version is released, users who update to it will have a version the detector does not recognise (confidence `UNKNOWN`). Before version detection can work for the new version, someone must hash the sentinel files and add them to the database.

The hash learning system automates this:

1. After a successful update, the updater hashes the new version's sentinel files and stores the result locally.
2. The local learned database is merged back into the `VersionDatabase` on next startup, so detection immediately works.
3. The hashes are also reported to a remote API endpoint, where they can be aggregated and eventually included in the next bundled database.

This creates a self-reinforcing cycle: every successful update improves detection accuracy for all future users.

### 8.2 LearnedHashDB Internals

`LearnedHashDB` (`core/learned_hashes.py`) is a thin wrapper around a JSON file on disk:

```python
# src/sims4_updater/core/learned_hashes.py, line 25
class LearnedHashDB:
    def __init__(self, path=None):
        self.path = path or _default_path()
        self.sentinel_files: list[str] = []
        self.versions: dict[str, dict[str, str]] = {}
        self._dirty = False
        self._load()
```

The `_dirty` flag tracks whether any in-memory changes need to be written to disk, avoiding unnecessary writes when nothing has changed.

`add_version()` handles both new and existing versions:

```python
# src/sims4_updater/core/learned_hashes.py, line 62
def add_version(self, version, hashes):
    if not version or not hashes:
        return
    for sentinel in hashes:
        if sentinel not in self.sentinel_files:
            self.sentinel_files.append(sentinel)
    existing = self.versions.get(version, {})
    if existing == hashes:
        return  # no change — do not mark dirty
    self.versions[version] = hashes
    self._dirty = True
```

`merge()` handles incoming data from the manifest's `fingerprints` block or the crowd-sourced API. The merge semantics are additive: new hashes are added and existing hashes are overwritten (more recent data wins), but keys not present in `other_versions` are preserved:

```python
# src/sims4_updater/core/learned_hashes.py, line 84
def merge(self, other_versions):
    for version, hashes in other_versions.items():
        existing = self.versions.get(version, {})
        merged = {**existing, **hashes}   # other_versions wins on overlap
        if merged != existing:
            self.versions[version] = merged
            self._dirty = True
```

### 8.3 Persistence and Atomic Writes

`save()` writes the database to a temporary file and atomically renames it:

```python
# src/sims4_updater/core/learned_hashes.py, line 46
def save(self):
    if not self._dirty and self.path.is_file():
        return
    data = {
        "sentinel_files": self.sentinel_files,
        "versions": self.versions,
        "updated": int(time.time()),
    }
    tmp = self.path.with_suffix(".json_tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, self.path)
    self._dirty = False
```

The `tmp -> final` atomic rename via `os.replace()` ensures the file on disk is never partially written. A power loss or crash during the write will leave either the complete old file or the complete new file, never a corrupted intermediate state.

The file is stored at:

```
%LocalAppData%\ToastyToast25\sims4_updater\learned_hashes.json
```

### 8.4 Sources of Learned Fingerprints

| Source                     | How it arrives                                                                            | When                                         |
|----------------------------|-------------------------------------------------------------------------------------------|----------------------------------------------|
| Manifest `fingerprints`    | `fetch_manifest()` calls `learned_db.merge(manifest.fingerprints)` after each fetch.    | Every time the manifest is fetched.           |
| Crowd-sourced API          | `_fetch_crowd_fingerprints(url)` fetches the crowd fingerprints URL and merges.           | On manifest fetch, if `fingerprints_url` set. |
| Post-update self-learning  | `learn_version()` hashes sentinels after a successful update, calls `add_version()`.     | After each successful update.                 |
| Manual CLI `learn` command | External callers may call `Sims4Updater.learn_version()` directly.                       | User-initiated.                               |

### 8.5 Crowd-Sourced Hash Reporting

After `learn_version()` stores new hashes locally, it fires a background HTTP POST to `manifest.report_url`:

```python
# src/sims4_updater/patch/client.py, line 328
def report_hashes(self, version, hashes, report_url=None):
    url = report_url or (self._manifest.report_url if self._manifest else None)
    if not url:
        return

    def _send():
        try:
            self.downloader.session.post(
                url,
                json={"version": version, "hashes": hashes},
                timeout=10,
            )
        except Exception:
            pass  # fire-and-forget

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()
```

This is deliberately fire-and-forget: it runs in a daemon thread (so it does not block application shutdown), swallows all exceptions, and has a 10-second timeout. Failure to report is silently ignored — the local database was already updated, so the report is only an improvement, not a requirement.

### 8.6 Hash Learning Flow Diagram

```
 Successful update completes
         |
         v
 Sims4Updater.learn_version(game_dir, target_version)
   for each sentinel in constants.SENTINEL_FILES:
     if file exists:
       hashes[sentinel] = hash_file(file)
         |
         | hashes is empty? -> return (nothing to learn)
         | hashes non-empty -> continue
         |
         v
   _learned_db.add_version(target_version, hashes)
   _learned_db.save()
   #  -> %LocalAppData%\ToastyToast25\sims4_updater\learned_hashes.json
         |
         v
   patch_client.report_hashes(target_version, hashes)
   #  -> POST {version, hashes} to manifest.report_url (background thread)

 ----

 Next application start:
   LearnedHashDB._load()    <- loads learned_hashes.json
   VersionDatabase.__init__ <- merges learned DB into bundled DB
   VersionDetector.detect() <- now recognises the new version
```

---

## 9. Error Handling

### 9.1 Exception Hierarchy

All custom exceptions inherit from `UpdaterError`, which itself inherits from Python's built-in `Exception`. This allows callers to catch all updater-specific errors with a single `except UpdaterError` clause, or to catch specific sub-types for finer-grained handling.

```
Exception
  +-- UpdaterError                 (base for all updater errors)
        +-- ExitingError           (raised when shutdown is in progress)
        +-- WritePermissionError   (cannot write to game dir or temp dir)
        +-- NotEnoughSpaceError    (insufficient disk space)
        +-- FileMissingError       (required file not found in game dir)
        +-- VersionDetectionError  (could not identify installed version)
        +-- ManifestError          (manifest fetch/parse failure)
        +-- DownloadError          (network or I/O error during download)
        +-- IntegrityError         (MD5 hash mismatch after download)
        +-- NoUpdatePathError      (no patch chain found in manifest)
        +-- NoCrackConfigError     (crack config file not found in game dir)
        +-- XdeltaError            (xdelta3 subprocess returned non-zero)
        +-- AVButtinInError        (anti-virus blocking file access)
```

### 9.2 Exception Descriptions and Causes

| Exception               | Module               | Raised When                                                                                        |
|-------------------------|----------------------|----------------------------------------------------------------------------------------------------|
| `UpdaterError`          | `core/exceptions.py` | Catch-all base class. Raised directly for generic logic errors.                                    |
| `ExitingError`          | `core/exceptions.py` | `check_exiting()` detects that the shutdown event is set. Propagates up to terminate cleanly.     |
| `WritePermissionError`  | `core/exceptions.py` | OS denies write access to game directory or temp directory. Often caused by anti-virus.            |
| `NotEnoughSpaceError`   | `core/exceptions.py` | `shutil.disk_usage()` reports insufficient free space before extraction or move.                   |
| `FileMissingError`      | `core/exceptions.py` | A file required for patching (not optional) is absent from all search locations.                   |
| `VersionDetectionError` | `core/exceptions.py` | No game directory found, invalid game directory, or no version match (confidence UNKNOWN).         |
| `ManifestError`         | `core/exceptions.py` | Network failure fetching manifest, invalid JSON, missing `latest` field, malformed patch entry.    |
| `DownloadError`         | `core/exceptions.py` | Network error during file download, or user-triggered cancellation.                                |
| `IntegrityError`        | `core/exceptions.py` | MD5 hash of downloaded file does not match the expected hash from the manifest.                    |
| `NoUpdatePathError`     | `core/exceptions.py` | BFS finds no path through the patch graph from current to target version.                          |
| `NoCrackConfigError`    | `core/exceptions.py` | `DLCManager.apply_changes()` called but no crack config format detected in game directory.         |
| `XdeltaError`           | `core/exceptions.py` | xdelta3 returns non-zero exit code. Includes parsed error message from xdelta3 output.             |
| `AVButtinInError`       | `core/exceptions.py` | File hash fails with `PermissionError` or `OSError` — likely anti-virus interference.             |

### 9.3 Error Propagation Strategy

The updater uses a simple but effective error propagation model:

1. **Specific exceptions are raised at the point of failure** — `ManifestError` in `fetch_manifest()`, `DownloadError` in `download_file()`, etc.

2. **`Sims4Updater.update()` has a single `except Exception` at the top level** that transitions state to `UpdateState.ERROR` and re-raises:

```python
# src/sims4_updater/updater.py, line 467
except Exception:
    self._state = UpdateState.ERROR
    raise
```

This ensures the state machine always reflects the actual outcome, even if an unexpected exception type is raised.

3. **The UI layer (not documented here) is responsible for catching exceptions** from `update()` and presenting them to the user with an appropriate message.

4. **Non-critical operations swallow exceptions silently** — crowd-sourced hash reporting, manifest fingerprint fetching, and settings saving in `exiting_extra()` all catch-and-ignore exceptions because they are best-effort operations whose failure should not abort the main workflow.

---

## 10. Sims4Updater Class

### 10.1 Class Overview and Inheritance

```python
# src/sims4_updater/updater.py, line 60
class Sims4Updater(BasePatcher):
    """The Sims 4 Updater — extends Patcher with download and auto-update."""

    VERSION = 1
    NAME = "Sims4Updater"
```

`VERSION = 1` is the patcher metadata version. ZIP archives embedded with `patcher_version > 1` will raise `NewerPatcherRequiredError`, ensuring forward compatibility — future updater versions can introduce new metadata formats without breaking older clients.

`NAME = "Sims4Updater"` appears in error messages, the hash cache filename (`sims4updater_files.cache`), and temporary directory names (`sims4updater_tmp/`).

### 10.2 UpdateState Enum

```python
# src/sims4_updater/updater.py, line 47
class UpdateState(Enum):
    IDLE       = "idle"
    DETECTING  = "detecting_version"
    CHECKING   = "checking_updates"
    DOWNLOADING = "downloading"
    PATCHING   = "patching"
    FINALIZING = "finalizing"
    DONE       = "done"
    ERROR      = "error"
```

The state is exposed via the read-only `state` property:

```python
@property
def state(self) -> UpdateState:
    return self._state
```

State transitions are one-way during a single `update()` call: `IDLE -> DETECTING -> CHECKING -> DOWNLOADING -> PATCHING -> FINALIZING -> DONE` (or to `ERROR` at any point). The state does not reset back to `IDLE` automatically; the caller must create a new `Sims4Updater` instance for a subsequent update, or reset state externally.

State transition mapping:

| Method Called           | Resulting State  |
|-------------------------|------------------|
| (constructor)           | `IDLE`           |
| `detect_version()`      | `DETECTING`      |
| `check_for_updates()`   | `CHECKING`       |
| `download_update()`     | `DOWNLOADING`    |
| (entering patch phase)  | `PATCHING`       |
| (entering finalize)     | `FINALIZING`     |
| (update() success)      | `DONE`           |
| (any exception in update()) | `ERROR`      |

### 10.3 Constructor and Dependency Wiring

```python
# src/sims4_updater/updater.py, line 66
def __init__(self, ask_question, callback=None, settings=None):
    super().__init__(ask_question, callback)

    self.settings = settings or Settings.load()
    self._learned_db = LearnedHashDB()
    self._detector = VersionDetector(learned_db=self._learned_db)
    self._dlc_manager = DLCManager()
    self._patch_client = None   # lazy-initialized
    self._dlc_downloader = None
    self._cancel = threading.Event()
    self._state = UpdateState.IDLE
    self._download_dir = get_app_dir() / "downloads"
```

Dependency relationships created in the constructor:

```
Sims4Updater
  |-- settings (Settings)          <- loaded from disk, saved on exit
  |-- _learned_db (LearnedHashDB)  <- shared between _detector and _patch_client
  |-- _detector (VersionDetector)  <- owns a VersionDatabase that uses _learned_db
  |-- _dlc_manager (DLCManager)    <- owns DLCCatalog, used for DLC state ops
  |-- _patch_client (PatchClient)  <- lazy; shares _cancel and _learned_db
  |-- _cancel (Event)              <- shared cancellation signal
  |-- _download_dir (Path)         <- download destination
```

The `ask_question` callback (inherited from `BasePatcher`) is a callable that presents yes/no questions to the user — used when the crack needs to be re-extracted when there are no game files to update.

The `callback` (also from `BasePatcher`) is the event sink for progress reporting. It is called with `(CallbackType, *args)` tuples throughout the pipeline. In GUI mode, this drives the progress frame.

### 10.4 Lazy PatchClient Initialization

`PatchClient` is not created until the first call to `self.patch_client`:

```python
# src/sims4_updater/updater.py, line 84
@property
def patch_client(self) -> PatchClient:
    if self._patch_client is None:
        self._patch_client = PatchClient(
            manifest_url=self.settings.manifest_url,
            download_dir=self._download_dir,
            cancel_event=self._cancel,
            learned_db=self._learned_db,
            dlc_catalog=self._dlc_manager.catalog,
        )
    return self._patch_client
```

Lazy initialization is used because:
- `settings.manifest_url` may be set after construction (by the settings UI).
- Creating a `PatchClient` (and thus a `Downloader` and `requests.Session`) has a non-trivial cost that should not be paid on every `Sims4Updater` construction.
- Tests can set `settings.manifest_url` to a test URL before triggering the first manifest fetch.

### 10.5 The update() Orchestration Method

`update()` is the central method of the entire system. It coordinates all subsystems through the five-stage pipeline described in Section 1.2. Below is the full annotated code flow:

**Stage 1 — Version Detection:**

```python
# updater.py:349
game_dir = game_dir or self.find_game_dir()
if not game_dir:
    raise UpdaterError("Could not find Sims 4 installation.")

self.settings.game_path = game_dir

detection = self.detect_version(game_dir)
if not detection.version:
    raise VersionDetectionError("Could not detect installed version.")
```

`find_game_dir()` is tried first (checking settings, registry, default paths). The game path is stored in settings immediately so it persists for the next run. `detect_version()` transitions state to `DETECTING` and raises on failure.

**Stage 2 — Update Check:**

```python
# updater.py:365
info = self.check_for_updates(detection.version)
if not info.update_available:
    self._state = UpdateState.DONE
    return
```

`check_for_updates()` fetches the manifest (using the `PatchClient` lazy init) and calls `plan_update()`. If `update_available` is False, the method exits immediately. The `patch_pending` flag on `info` can be inspected by the caller to display a "coming soon" message.

**Stage 3 — Downloading:**

```python
# updater.py:382
self.download_update(info.plan, progress=progress, status=status)
```

`download_update()` wraps `patch_client.download_update()` with `CallbackType.HEADER/INFO/PROGRESS` callbacks and the `check_exiting()` cancellation guard.

**Stage 4 — Patch Application:**

```python
# updater.py:390
self._state = UpdateState.PATCHING

game_names = self.load_all_metadata()
game_name = ... # find "sims" or "ts4" in names, or take first

versions, dlc_count, languages, cached_path = self.pick_game(game_name)

language = self.settings.language
if language and language in languages:
    self.select_language(language)
elif languages:
    self.select_language(languages[0])

all_dlcs, missing_dlcs = self.check_files_quick(game_dir)

saved_dlc_states = self._dlc_manager.export_states(game_dir)

selected_dlcs = [d for d in all_dlcs if d not in missing_dlcs]
self.patch(selected_dlcs)
```

`load_all_metadata()` scans the download directory. `pick_game()` parses the patch metadata and DLC list. `select_language()` removes non-selected language files from the required set. `check_files_quick()` identifies which DLCs are present on disk. DLC states are snapshotted before calling `patch()`.

**Stage 5 — Finalization:**

```python
# updater.py:422
self._state = UpdateState.FINALIZING

target_version = info.plan.target_version
if target_version:
    self.learn_version(game_dir, target_version)

if saved_dlc_states:
    self._dlc_manager.import_states(game_dir, saved_dlc_states)

# Enable newly installed DLCs
current_states = self._dlc_manager.get_dlc_states(game_dir)
# ... (see Section 7.5 for full logic)

new_detection = self.detect_version(game_dir)
if new_detection.version:
    self.settings.last_known_version = new_detection.version

self.settings.save()
self._state = UpdateState.DONE
```

After patching, the new sentinel hashes are learned, DLC states are restored, and a second version detection confirms the update succeeded. Settings are saved to disk.

### 10.6 Full Orchestration Flow Diagram

```
 update(game_dir, progress, status)
 try:
   |
   +-- [DETECTING] -----------------------------------------------
   |   find_game_dir()
   |     settings.game_path -> validate_game_dir -> return
   |     OR Windows Registry -> validate_game_dir -> return
   |     OR DEFAULT_GAME_PATHS -> validate_game_dir -> return
   |     OR None -> raise UpdaterError
   |   detect_version(game_dir)
   |     VersionDetector.detect() -> DetectionResult
   |     result.version is None -> raise VersionDetectionError
   |   settings.game_path = game_dir
   |
   +-- [CHECKING] ------------------------------------------------
   |   check_for_updates(detection.version)
   |     patch_client.fetch_manifest()
   |       GET manifest_url -> parse_manifest() -> Manifest
   |       learned_db.merge(manifest.fingerprints)
   |       _fetch_crowd_fingerprints(fingerprints_url)
   |       dlc_catalog.merge_remote(manifest.dlc_catalog)
   |     plan_update(manifest, current_version, manifest.latest)
   |       build graph; BFS; min by size -> UpdatePlan
   |     return UpdateInfo(update_available, plan, ...)
   |   if not update_available -> state=DONE; return
   |
   +-- [DOWNLOADING] ---------------------------------------------
   |   download_update(plan, progress, status)
   |     for step in plan.steps:
   |       for entry in step.patch.files:
   |         Downloader.download_file(entry, subdir)
   |           resume from .partial if exists
   |           stream to .partial
   |           verify MD5
   |           rename .partial -> final
   |       if step.patch.crack:
   |         Downloader.download_file(crack_entry, subdir)
   |
   +-- [PATCHING] ------------------------------------------------
   |   load_all_metadata()
   |     rglob download_dir for ZIPs
   |     read ZIP central directory -> metadata dict
   |   pick_game(game_name)
   |     parse_patches() -> sorted patch chain
   |     filter_metadata() -> DLC list
   |   select_language(lang)
   |   check_files_quick(game_dir)
   |   export_states(game_dir)  <- SNAPSHOT DLC STATES
   |   BasePatcher.patch(selected_dlcs)
   |     (full 8-phase pipeline -- see Section 6.3)
   |
   +-- [FINALIZING] ----------------------------------------------
   |   learn_version(game_dir, target_version)
   |     hash sentinels -> learned_db.add_version() -> save()
   |     patch_client.report_hashes() -> POST (background)
   |   import_states(game_dir, saved_dlc_states)
   |     apply_changes(game_dir, enabled_set)
   |   detect new DLCs -> apply_changes() if any new
   |   detect_version(game_dir) -> update settings.last_known_version
   |   settings.save()
   |   state = DONE
   |
 except Exception:
   state = ERROR
   raise
```

### 10.7 Lifecycle and Cleanup

**`exiting_extra()`** is called by `BasePatcher.check_exiting()` when the shutdown event is set. It cancels ongoing downloads, closes the HTTP session, and saves settings:

```python
# src/sims4_updater/updater.py, line 104
def exiting_extra(self):
    try:
        self._cancel.set()
        if self._patch_client:
            self._patch_client.cancel()
            self._patch_client.close()
        if self._dlc_downloader:
            self._dlc_downloader.close()
        self.settings.save()
    except Exception:
        pass  # may fail during interpreter shutdown
```

The broad `except Exception: pass` is intentional — during Python interpreter shutdown, built-in names may already be `None`, causing any operation to raise. This guard prevents spurious tracebacks on exit.

**`cleanup_downloads()`** removes the entire `downloads/` directory:

```python
# src/sims4_updater/updater.py, line 473
def cleanup_downloads(self):
    if self._download_dir.is_dir():
        shutil.rmtree(self._download_dir, ignore_errors=True)
```

This is not called automatically by `update()`. The caller decides when to clean up — for example, only after confirming the game launches correctly. The download directory can be left intact to enable re-patching without re-downloading if the first attempt fails at the patching stage.

**`close()`** closes the HTTP session:

```python
# src/sims4_updater/updater.py, line 481
def close(self):
    if self._patch_client:
        self._patch_client.close()
        self._patch_client = None
```

---

## 11. Configuration and Persistence

### 11.1 Settings Dataclass

```python
# src/sims4_updater/config.py, line 48
@dataclass
class Settings:
    game_path: str = ""
    language: str = "English"
    check_updates_on_start: bool = True
    last_known_version: str = ""
    enabled_dlcs: list[str] = field(default_factory=list)
    manifest_url: str = ""
    theme: str = "dark"
```

| Field                    | Purpose                                                                             |
|--------------------------|-------------------------------------------------------------------------------------|
| `game_path`              | Last validated game installation path. Used as first candidate in `find_game_dir`. |
| `language`               | Selected patch language. Used in `select_language()` during patching.              |
| `check_updates_on_start` | UI hint: whether to auto-check on app launch.                                       |
| `last_known_version`     | Cached version string. Used as fast-path in `check_for_updates()`.                 |
| `enabled_dlcs`           | Persisted DLC preferences (supplementary to crack config state).                   |
| `manifest_url`           | URL of the remote manifest JSON. Must be set before first use.                     |
| `theme`                  | UI theme preference ("dark" or "light").                                            |

Settings are loaded with `Settings.load()` (class method) and saved with `settings.save()` (instance method). Both operations use an atomic write via a `.json_tmp` temporary file.

Settings loading is forgiving: if the file is missing, malformed JSON, or contains unknown keys, a default `Settings()` instance is returned. Unknown keys are silently ignored (only `dataclass_fields` are accepted).

### 11.2 App Data Directory

```python
# src/sims4_updater/config.py, line 11
def get_app_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        p = Path(local) / "ToastyToast25" / "sims4_updater"
    else:
        p = Path.home() / ".config" / "sims4_updater"
    p.mkdir(parents=True, exist_ok=True)
    return p
```

On Windows: `%LocalAppData%\ToastyToast25\sims4_updater\`

On other platforms (or if `LOCALAPPDATA` is unset): `~/.config/sims4_updater/`

Files stored in this directory:

| File                       | Description                                          |
|----------------------------|------------------------------------------------------|
| `settings.json`            | User settings (see Section 11.1)                     |
| `learned_hashes.json`      | Local hash database (see Section 8)                  |
| `downloads/`               | Downloaded patch archives (see Section 5)            |
| `sims4updater_files.cache` | MD5 hash cache for patcher (avoids rehashing)        |

### 11.3 Directory Migration

The app directory was previously named `anadius` (the original developer handle). On startup, `_migrate_from_old_dir()` checks for this old location and copies `settings.json` and `learned_hashes.json` to the new `ToastyToast25` location if they exist and the new location does not yet have a `settings.json`:

```python
# src/sims4_updater/config.py, line 22
def _migrate_from_old_dir():
    old_dir = Path(local) / "anadius" / "sims4_updater"
    new_dir = Path(local) / "ToastyToast25" / "sims4_updater"
    if not old_dir.is_dir():
        return
    if (new_dir / "settings.json").is_file():
        return  # already migrated
    for name in ("settings.json", "learned_hashes.json"):
        src = old_dir / name
        if src.is_file():
            new_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, new_dir / name)
```

This is a one-shot migration that runs once per machine. The old directory is not deleted (so the old application version continues to work if reinstalled).

---

## 12. Constants and Installation Markers

`constants.py` centralises all deployment-sensitive values:

```python
# src/sims4_updater/constants.py
APP_NAME = "Sims 4 Updater"
APP_VERSION = "2.0.0"

MANIFEST_URL = ""              # configured at deployment time
FALLBACK_MANIFEST_URLS = []    # optional fallback list

EA_CLIENT_ID = "JUNO_PC_CLIENT"
EA_AUTH_URL  = "https://accounts.ea.com/connect/auth"
EA_TOKEN_URL = "https://accounts.ea.com/connect/token"

REGISTRY_PATHS = [
    r"SOFTWARE\Maxis\The Sims 4",
    r"SOFTWARE\WOW6432Node\Maxis\The Sims 4",
]

DEFAULT_GAME_PATHS = [
    r"C:\Program Files\EA Games\The Sims 4",
    r"C:\Program Files (x86)\EA Games\The Sims 4",
    r"D:\Games\The Sims 4",
]

SENTINEL_FILES = [
    "Game/Bin/TS4_x64.exe",
    "Game/Bin/Default.ini",
    "delta/EP01/version.ini",
]

SIMS4_INSTALL_MARKERS = [
    "Game/Bin/TS4_x64.exe",
    "Data/Client",
]
```

The `get_data_dir()` and `get_tools_dir()` functions handle the duality of running from source versus from a PyInstaller frozen executable:

```python
def get_data_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "data"    # frozen: temp extraction dir
    return Path(__file__).resolve().parent.parent.parent / "data"  # source: repo root

def get_tools_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "tools"
    return Path(__file__).resolve().parent.parent.parent / "tools"
```

When frozen by PyInstaller, `sys._MEIPASS` points to the temporary directory where the bundled data files are extracted. The `data/` directory contains `version_hashes.json` and the `tools/` directory contains `xdelta3.exe` and `unrar.exe`.

---

## Appendix A — Manifest JSON Reference

Complete annotated manifest JSON schema:

```json
{
  "latest": "1.120.365.1020",
  // REQUIRED. The highest version reachable via the patch chain in this manifest.
  // Clients use this to determine if an update is available.

  "game_latest": "1.121.000.1020",
  // OPTIONAL. The actual latest game version released by EA.
  // If present and != "latest", patch_pending = True.

  "game_latest_date": "2025-11-15",
  // OPTIONAL. ISO 8601 date of the most recent EA release.

  "patches": [
    {
      "from": "1.119.265.1020",
      // REQUIRED. Source version for this patch step.

      "to": "1.120.365.1020",
      // REQUIRED. Target version after applying this patch.

      "files": [
        {
          "url": "https://cdn.example.com/patch_119_to_120_part1.zip",
          // REQUIRED. Direct download URL.

          "size": 234881024,
          // REQUIRED. File size in bytes (used for progress and space checks).

          "md5": "A3B2C1D0E9F8A7B6C5D4E3F2A1B0C9D8",
          // OPTIONAL. Uppercase MD5 hex string for integrity verification.

          "filename": "patch_119_to_120_part1.zip"
          // OPTIONAL. If absent, derived from URL.
        }
      ],

      "crack": {
        "url": "https://cdn.example.com/crack_120.rar",
        "size": 8192000,
        "md5": "B4C3D2E1F0A9B8C7D6E5F4A3B2C1D0E9",
        "filename": "crack_120.rar"
      }
      // OPTIONAL. Crack RAR archive. "pass" key can be added for password.
    }
  ],

  "fingerprints": {
    "1.120.365.1020": {
      "Game/Bin/TS4_x64.exe": "C5D4E3F2A1B0C9D8E7F6A5B4C3D2E1F0",
      "Game/Bin/Default.ini": "D4E3F2A1B0C9D8E7F6A5B4C3D2E1F0C5"
    }
  },
  // OPTIONAL. Version fingerprints to merge into local learned DB on fetch.
  // Keys are version strings; values are {sentinel_path: md5_hash} maps.

  "fingerprints_url": "https://api.example.com/fingerprints.json",
  // OPTIONAL. URL of crowd-sourced fingerprints endpoint.
  // Fetched separately and merged into learned DB (best-effort).

  "report_url": "https://api.example.com/report_hashes",
  // OPTIONAL. URL to POST newly learned hashes to.
  // Used by Sims4Updater.learn_version() -> PatchClient.report_hashes().

  "new_dlcs": [
    {
      "id": "EP15",
      "name": "Upcoming Pack Name",
      "status": "pending"
    }
  ],
  // OPTIONAL. DLCs announced but not yet patchable.
  // Surfaced to the UI for informational display.

  "dlc_catalog": [
    {
      "id": "EP01",
      "code": "EP01",
      "code2": "EP01_0",
      "type": "expansion",
      "names": {"en_US": "Get to Work"},
      "description": "The first expansion pack."
    }
  ],
  // OPTIONAL. DLC metadata for updating the local DLC catalog.

  "dlc_downloads": {
    "EP01": {
      "url": "https://cdn.example.com/EP01_full.zip",
      "size": 1073741824,
      "md5": "E7F6A5B4C3D2E1F0C5D4E3F2A1B0C9D8",
      "filename": "EP01_full.zip"
    }
  }
  // OPTIONAL. Standalone DLC content downloads.
  // Used by DLCDownloader for installing individual packs.
}
```

---

## Appendix B — File Layout Reference

**Source tree — key files:**

```
src/sims4_updater/
  updater.py                       Main orchestrator class (Sims4Updater)
  config.py                        Settings, get_app_dir()
  constants.py                     SENTINEL_FILES, REGISTRY_PATHS, markers

  core/
    version_detect.py              VersionDetector, VersionDatabase, DetectionResult
    learned_hashes.py              LearnedHashDB
    exceptions.py                  Full exception hierarchy
    files.py                       hash_file(), write_check()

  patch/
    client.py                      PatchClient, UpdateInfo, format_size()
    manifest.py                    parse_manifest(), Manifest, PatchEntry, FileEntry
    planner.py                     plan_update(), UpdatePlan, UpdateStep, _bfs_all_shortest()
    downloader.py                  Downloader, DownloadResult, _create_session()

  dlc/
    manager.py                     DLCManager (export_states, import_states, apply_changes)
    catalog.py                     DLCCatalog, DLCInfo, DLCStatus
    formats.py                     DLCConfigAdapter, detect_format()

patcher/patcher/
  patcher.py                       BasePatcher (full patch application pipeline)
```

**Runtime data directories:**

```
%LocalAppData%\ToastyToast25\sims4_updater\
  settings.json                    User configuration
  learned_hashes.json              Locally learned version fingerprints
  sims4updater_files.cache         MD5 hash cache (size+mtime keyed)
  downloads\                       Downloaded patch archives
    1.118_to_1.119\
      patch_118_to_119.zip
      crack_119.rar
    1.119_to_1.120\
      patch_119_to_120.zip
      crack_120.rar

sims4updater_tmp\                  Temporary files (next to executable)
  extracted\                       Files extracted from patch ZIPs
  final\                           Patched files awaiting move to game dir
  crack\                           Files extracted from crack RAR
  TMP_xxxxxxxx\                    xdelta3 working directories (cleaned on exit)
```

**Frozen executable data directories (PyInstaller):**

```
%TEMP%\MEIxxxxxx\                  sys._MEIPASS
  data\
    version_hashes.json            Bundled version fingerprint database
  tools\
    xdelta3.exe                    Binary delta tool
    unrar.exe                      RAR extraction tool
  sims4.png                        Application icon
```

---

## Appendix C — Callback Protocol

`BasePatcher` (and therefore `Sims4Updater`) communicates with the UI through a single `callback` function passed to the constructor. The callback signature is:

```python
callback(callback_type: CallbackType, *args, **kwargs) -> None
```

`CallbackType` is an `Enum` with six values:

| CallbackType | Typical Arguments          | Purpose                                                          |
|--------------|----------------------------|------------------------------------------------------------------|
| `HEADER`     | `message: str`             | Section heading in the log (e.g., "Downloading patches").        |
| `INFO`       | `message: str`             | General status message or filename being processed.              |
| `FAILURE`    | `message: str`             | A non-fatal error or warning (e.g., "BAD METADATA").             |
| `WARNING`    | `message: str`             | Warning that does not stop the process.                          |
| `PROGRESS`   | `current: int, total: int` | Numerical progress (bytes or file count).                        |
| `FINISHED`   | `force_scroll=True`        | Signals completion of the full patching pipeline.                |

`Sims4Updater.update()` also accepts two simpler callback parameters for caller convenience:

- `progress(bytes_downloaded: int, total_bytes: int, filename: str)` — high-frequency download progress.
- `status(message: str)` — coarse-grained state messages suitable for a status bar.

These are wired through to the underlying `callback(CallbackType.PROGRESS, ...)` and `callback(CallbackType.INFO, ...)` calls, with the added feature that the raw `callback` sees all events while `progress` and `status` see only the events relevant to downloads.
