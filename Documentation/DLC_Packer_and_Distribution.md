# DLC Packer and Distribution Subsystem

**Document version:** 1.0
**Last updated:** 2026-02-20
**Applies to:** Sims 4 Updater v2.0.0
**Primary source files:**

- `src/sims4_updater/dlc/packer.py`
- `src/sims4_updater/gui/frames/packer_frame.py`
- `src/sims4_updater/dlc/catalog.py`
- `src/sims4_updater/__main__.py`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture and Component Relationships](#2-architecture-and-component-relationships)
3. [DLC Catalog](#3-dlc-catalog)
   - 3.1 [DLCInfo Dataclass](#31-dlcinfo-dataclass)
   - 3.2 [DLCCatalog Class](#32-dlccatalog-class)
   - 3.3 [DLC ID Conventions](#33-dlc-id-conventions)
   - 3.4 [Custom DLC Merging](#34-custom-dlc-merging)
4. [DLCPacker Class](#4-dlcpacker-class)
   - 4.1 [Constructor](#41-constructor)
   - 4.2 [get_zip_filename()](#42-get_zip_filename)
   - 4.3 [get_zip_path()](#43-get_zip_path)
   - 4.4 [pack_single()](#44-pack_single)
   - 4.5 [pack_multiple()](#45-pack_multiple)
   - 4.6 [generate_manifest()](#46-generate_manifest)
   - 4.7 [import_archive()](#47-import_archive)
   - 4.8 [get_installed_dlcs()](#48-get_installed_dlcs)
5. [PackResult Dataclass](#5-packresult-dataclass)
6. [ZIP Archive Format](#6-zip-archive-format)
   - 6.1 [Filename Convention](#61-filename-convention)
   - 6.2 [Internal Directory Structure](#62-internal-directory-structure)
   - 6.3 [Compression Settings](#63-compression-settings)
   - 6.4 [Path Normalization](#64-path-normalization)
   - 6.5 [File Enumeration Order](#65-file-enumeration-order)
7. [Manifest Generation](#7-manifest-generation)
   - 7.1 [manifest_dlc_downloads.json Format](#71-manifest_dlc_downloadsjson-format)
   - 7.2 [Field Reference](#72-field-reference)
   - 7.3 [Placeholder URL Workflow](#73-placeholder-url-workflow)
   - 7.4 [Integration with the Main Manifest](#74-integration-with-the-main-manifest)
8. [Archive Import](#8-archive-import)
   - 8.1 [Supported Formats](#81-supported-formats)
   - 8.2 [Path Traversal Protection](#82-path-traversal-protection)
   - 8.3 [ZIP Extraction](#83-zip-extraction)
   - 8.4 [RAR Extraction and Bundled unrar.exe](#84-rar-extraction-and-bundled-unrarexe)
   - 8.5 [DLC Detection After Extraction](#85-dlc-detection-after-extraction)
9. [GUI: Packer Frame](#9-gui-packer-frame)
   - 9.1 [Frame Layout and Sections](#91-frame-layout-and-sections)
   - 9.2 [DLC Discovery and the Installed DLC List](#92-dlc-discovery-and-the-installed-dlc-list)
   - 9.3 [Disk Space Checking](#93-disk-space-checking)
   - 9.4 [Overwrite Protection](#94-overwrite-protection)
   - 9.5 [Progress Tracking](#95-progress-tracking)
   - 9.6 [Output Directory and Open Folder Button](#96-output-directory-and-open-folder-button)
   - 9.7 [Import Flow](#97-import-flow)
   - 9.8 [Post-Import DLC Registration](#98-post-import-dlc-registration)
   - 9.9 [Async Execution Model](#99-async-execution-model)
10. [CLI Usage](#10-cli-usage)
    - 10.1 [pack-dlc Command Syntax](#101-pack-dlc-command-syntax)
    - 10.2 [Arguments Reference](#102-arguments-reference)
    - 10.3 [Usage Examples](#103-usage-examples)
    - 10.4 [CLI Output Format](#104-cli-output-format)
11. [Distribution Workflow](#11-distribution-workflow)
    - 11.1 [End-to-End Workflow Overview](#111-end-to-end-workflow-overview)
    - 11.2 [Step 1 — Pack DLC Archives](#step-1--pack-dlc-archives)
    - 11.3 [Step 2 — Upload to CDN](#step-2--upload-to-cdn)
    - 11.4 [Step 3 — Update the Manifest URL](#step-3--update-the-manifest-url)
    - 11.5 [Step 4 — User Download and Install](#step-4--user-download-and-install)
    - 11.6 [Hosting Considerations](#116-hosting-considerations)
12. [Error Handling Reference](#12-error-handling-reference)
    - 12.1 [Pack Errors](#121-pack-errors)
    - 12.2 [Import Errors](#122-import-errors)
13. [Progress Callback Protocol](#13-progress-callback-protocol)
14. [MD5 Hashing Implementation](#14-md5-hashing-implementation)
15. [Appendix A — Full PackResult Field Reference](#appendix-a--full-packresult-field-reference)
16. [Appendix B — DLC ID Taxonomy](#appendix-b--dlc-id-taxonomy)
17. [Appendix C — File Layout Quick Reference](#appendix-c--file-layout-quick-reference)

---

## 1. Overview

The DLC Packer and Distribution subsystem allows a distribution operator (the person running the update server) to convert locally installed Sims 4 DLC folders into standardized, self-contained ZIP archives. These archives are designed to be uploaded to any HTTP-accessible CDN or file host. Once uploaded, the operator generates a manifest JSON file that records each archive's URL, size, and MD5 checksum. End users then download and install DLC archives either automatically through the application's DLC download tab, or manually by importing archives through the Packer tab's import feature.

The subsystem serves two distinct roles:

**Production role (operator-facing):** Pack installed DLC directories into distributable archives, generate a machine-readable manifest, and upload both to a content delivery network. This is performed using either the GUI Packer tab or the `pack-dlc` CLI command.

**Consumer role (user-facing):** Import a downloaded or locally obtained ZIP or RAR archive directly into the game directory, with optional automatic registration in the DLC configuration. This is performed through the GUI's "Browse & Import" button.

The design is deliberately hosting-agnostic. The packer embeds `<UPLOAD_URL>` as a placeholder in the generated manifest, which the operator replaces with the actual base URL before publishing. The updater application itself consumes the manifest's `dlc_downloads` section via the `DLCDownloadEntry` structures parsed in `patch/manifest.py`, meaning the packer and the downloader share a common data contract without direct coupling.

---

## 2. Architecture and Component Relationships

The following diagram describes the static relationships between the subsystem's components:

```text
src/sims4_updater/
│
├── dlc/
│   ├── catalog.py          DLCCatalog + DLCInfo (data layer)
│   │                       Loaded from data/dlc_catalog.json
│   │                       Merges custom_dlcs.json from app data dir
│   │
│   ├── packer.py           DLCPacker (core logic)
│   │                       Uses DLCCatalog for name lookups
│   │                       Uses get_tools_dir() for unrar.exe path
│   │                       Raises DownloadError on extraction failures
│   │
│   └── downloader.py       DLCDownloader (consumer side)
│                           Reads DLCDownloadEntry from parsed manifest
│                           Extracts archives using same zip logic as packer
│
├── gui/frames/
│   └── packer_frame.py     PackerFrame (GUI tab)
│                           Drives DLCPacker from the UI thread
│                           Runs all blocking operations via app.run_async()
│
├── __main__.py             pack_dlc() CLI handler
│                           Instantiates DLCCatalog + DLCPacker directly
│
└── patch/
    └── manifest.py         DLCDownloadEntry dataclass
                            Parsed from manifest.json dlc_downloads section
                            Consumed by DLCDownloader (not DLCPacker)
```

The packer is a pure producer. It writes archives and a manifest file; it never reads a remote manifest, contacts a network service, or modifies the game's crack configuration. The downloader is a pure consumer. It reads a parsed manifest, downloads archives, extracts them, and registers DLCs. These two halves of the distribution pipeline are deliberately decoupled.

---

## 3. DLC Catalog

**Source file:** `src/sims4_updater/dlc/catalog.py`

The DLC catalog is the authoritative registry of all known Sims 4 downloadable content packs. It maps DLC IDs (such as `EP01`, `GP01`, `SP01`) to human-readable names, unlock codes, pack types, and optional Steam application identifiers. The catalog is required by `DLCPacker` to translate IDs into proper display names for manifest generation and ZIP filename construction.

### 3.1 DLCInfo Dataclass

`DLCInfo` represents a single DLC entry:

```python
@dataclass
class DLCInfo:
    id: str           # e.g. "EP01"
    code: str         # e.g. "SIMS4.OFF.SOLP.0x0000000000011AC5"
    code2: str        # alternative unlock code (may be empty string)
    pack_type: str    # expansion, game_pack, stuff_pack, free_pack, kit
    names: dict[str, str]  # {locale: display_name}
    description: str = ""
    steam_app_id: int | None = None
```

The `names` dictionary uses lowercase locale keys as stored in `dlc_catalog.json`. For example, `"en_us"`, `"de_de"`, `"zh_cn"`. The `name_en` property retrieves the English name with a fallback:

```python
@property
def name_en(self) -> str:
    return self.names.get("en_us", self.names.get("en_US", self.id))
```

The `get_name()` method accepts a locale string and normalizes it to lowercase before lookup, falling back to English and then to the raw DLC ID if no match is found.

The `all_codes` property returns a list containing both `code` and `code2` (if non-empty), which is used by the DLC manager when writing unlock configuration files.

### 3.2 DLCCatalog Class

`DLCCatalog` is a container loaded at startup that holds the full list of `DLCInfo` objects. It exposes lookup methods by ID, by unlock code, and by pack type:

| Method | Signature | Description |
| --- | --- | --- |
| `get_by_id` | `(dlc_id: str) -> DLCInfo \| None` | Returns the DLC with the given ID string. |
| `get_by_code` | `(code: str) -> DLCInfo \| None` | Returns the DLC matching the given unlock code. |
| `all_dlcs` | `() -> list[DLCInfo]` | Returns all DLCs in catalog order. |
| `by_type` | `(pack_type: str) -> list[DLCInfo]` | Filters by `pack_type` string. |
| `get_installed` | `(game_dir: Path) -> list[DLCInfo]` | Returns DLCs whose folder exists on disk. |
| `get_missing` | `(game_dir: Path) -> list[DLCInfo]` | Returns DLCs without `SimulationFullBuild0.package`. |

The catalog maintains two internal dictionaries built at load time: `_by_id` and `_by_code`. Lookups in both are O(1).

### 3.3 DLC ID Conventions

The catalog uses a consistent ID naming scheme derived from EA's internal pack identifiers:

| Prefix | Pack Type | Examples |
| --- | --- | --- |
| `EP` | Expansion Pack | `EP01`, `EP02`, ..., `EP16` |
| `GP` | Game Pack | `GP01`, `GP02`, ..., `GP16` |
| `SP` | Stuff Pack | `SP01`, `SP02`, ..., `SP46` |
| `FP` | Free Pack | `FP01` |
| `KIT` | Kit | `KIT01`, `KIT02`, ..., `KIT30` |

These IDs correspond directly to the directory names that EA uses in the Sims 4 installation. For example, `EP01` is the Expansion Pack "Get to Work", and the game stores its files in `<game_dir>/EP01/`. This 1:1 correspondence between DLC ID and directory name is the fundamental assumption the entire subsystem relies on.

### 3.4 Custom DLC Merging

When the application fetches a remote manifest that contains a `dlc_catalog` section (see `patch/manifest.py`, `ManifestDLC`), the `DLCCatalog.merge_remote()` method integrates any new or updated entries. New entries (those with IDs not present in the bundled catalog) are persisted to `<app_data_dir>/custom_dlcs.json` so that they survive application restarts. On the next startup, `DLCCatalog.__init__` reads this file and merges it after loading the bundled catalog. This allows the server operator to introduce support for newly released DLCs without shipping a new application build.

The bundled catalog lives at `data/dlc_catalog.json` (resolved via `constants.get_data_dir()`), which works both when running from source and when frozen as a PyInstaller executable via `sys._MEIPASS`.

---

## 4. DLCPacker Class

**Source file:** `src/sims4_updater/dlc/packer.py`

`DLCPacker` is the central class of the subsystem. It is stateless beyond its catalog reference, meaning a single instance can be reused across multiple packing sessions without any cleanup between calls.

```python
class DLCPacker:
    """Packs DLC folders into standard zip archives and imports archives."""

    def __init__(self, catalog: DLCCatalog | None = None):
        self._catalog = catalog or DLCCatalog()
```

If no catalog is passed at construction time, a new `DLCCatalog` is instantiated, which reads `dlc_catalog.json` from disk. In the GUI, the packer receives the catalog that was already loaded by the updater's DLC manager, avoiding a redundant disk read. The CLI creates a fresh catalog.

### 4.1 Constructor

```python
DLCPacker(catalog: DLCCatalog | None = None)
```

**Parameters:**

- `catalog` — An already-loaded `DLCCatalog` instance. If `None`, a new catalog is instantiated from the default bundled data directory. Passing an existing catalog is preferred when the caller already has one loaded, as it avoids re-parsing the JSON file.

### 4.2 get_zip_filename()

```python
@staticmethod
def get_zip_filename(dlc: DLCInfo) -> str
```

Derives the canonical ZIP filename for a given DLC. This is a static method because the filename must be deterministic and reproducible without requiring an instance.

**Filename construction algorithm:**

1. Take `dlc.name_en` (the English display name).
2. Encode to ASCII and drop any characters that cannot be represented (non-ASCII characters are silently removed using `encode("ascii", "ignore")`).
3. Replace spaces with underscores.
4. Remove colons and apostrophes.
5. Retain only alphanumeric characters, underscores, and hyphens.
6. Assemble: `Sims4_DLC_{dlc.id}_{safe_name}.zip`

**Example transformations:**

| DLC | English Name | Resulting Filename |
| --- | --- | --- |
| `EP01` | Get to Work | `Sims4_DLC_EP01_Get_to_Work.zip` |
| `GP01` | Outdoor Retreat | `Sims4_DLC_GP01_Outdoor_Retreat.zip` |
| `SP01` | Luxury Party Stuff | `Sims4_DLC_SP01_Luxury_Party_Stuff.zip` |
| `KIT01` | Throwback Fit Kit | `Sims4_DLC_KIT01_Throwback_Fit_Kit.zip` |

The deterministic naming ensures that:

- The packer always produces the same filename for a given DLC, even across separate runs.
- The overwrite-detection logic in the GUI can check whether a file already exists before starting a pack operation.
- The manifest entries reference filenames that match the actual uploaded files without any renaming step.

### 4.3 get_zip_path()

```python
def get_zip_path(self, dlc: DLCInfo, output_dir: Path) -> Path
```

Returns a `Path` object for the expected ZIP file location by combining `output_dir` with `get_zip_filename(dlc)`. Used by the GUI's overwrite detection logic.

### 4.4 pack_single()

```python
def pack_single(
    self,
    game_dir: Path,
    dlc: DLCInfo,
    output_dir: Path,
    progress_cb: PackProgressCallback | None = None,
) -> PackResult
```

Packs a single DLC into a ZIP archive and returns a `PackResult`. This is the fundamental packing operation; `pack_multiple` is a sequential loop over this method.

**Execution sequence:**

1. Validate that `game_dir / dlc.id` exists as a directory. If not, raise `FileNotFoundError`.
2. Create `output_dir` (and any missing parents) if it does not exist.
3. Compute the output filename via `get_zip_filename(dlc)`.
4. Enumerate files recursively under `game_dir / dlc.id` using `dlc_dir.rglob("*")`. Only files (not directories) are included. For each file, compute its path relative to `game_dir`.
5. Check whether `game_dir / "__Installer" / "DLC" / dlc.id` exists. If so, recursively enumerate that directory as well. These files are also stored relative to `game_dir`, so their paths inside the archive begin with `__Installer/DLC/{dlc.id}/`.
6. If the combined file list is empty, raise `FileNotFoundError`.
7. Open the output ZIP in write mode with `zipfile.ZIP_DEFLATED` compression.
8. Write all files in sorted order (sorted by relative path), normalizing path separators to forward slashes.
9. Close the ZIP file.
10. Compute the file size using `stat().st_size`.
11. Compute the MD5 hash via `_hash_file()`.
12. Return a `PackResult` with all collected metadata.

**Error conditions:**

- `FileNotFoundError` — DLC directory not found or DLC directory has no files. The caller (`pack_multiple`) catches this and logs a warning rather than aborting the entire batch.
- `OSError` — Disk I/O failure during file enumeration or ZIP creation. Also caught by `pack_multiple`.

**Note on `progress_cb`:** The `pack_single` method accepts a `progress_cb` parameter to be consistent with the interface expected by callers, but it does not call it internally. Progress callbacks for individual file operations within a single DLC pack are not provided. The `progress_cb` is called by `pack_multiple` between DLC packs, not within them.

### 4.5 pack_multiple()

```python
def pack_multiple(
    self,
    game_dir: Path,
    dlcs: list[DLCInfo],
    output_dir: Path,
    progress_cb: PackProgressCallback | None = None,
) -> list[PackResult]
```

Packs a list of DLCs sequentially. Returns a list of `PackResult` objects for the DLCs that were successfully packed. DLCs that fail (due to `FileNotFoundError` or `OSError`) are skipped with a warning log; the remaining DLCs in the list continue to be processed.

**Execution sequence:**

For each DLC in the input list:

1. If `progress_cb` is provided, call it with the current index, total count, DLC ID, and a packing message.
2. Call `pack_single()` for this DLC.
3. If `pack_single()` raises `FileNotFoundError` or `OSError`, log a warning and continue to the next DLC.
4. On success, append the `PackResult` to the results list.

After all DLCs are processed, call `progress_cb(len(dlcs), len(dlcs), "", "Done")` to signal completion.

**Design rationale — sequential processing:** DLC archives can be several gigabytes each, and packing is CPU-bound (deflate compression) plus I/O-bound (reading the source files and writing the archive). Parallel packing would compete for disk bandwidth on a single spindle and for CPU time in CPython's GIL. Sequential processing keeps the implementation simple and predictable while producing a steady stream of progress updates that the GUI can display.

**Design rationale — soft failure:** If one DLC fails to pack (for example, because its directory was deleted between the time the list was built and the time the pack operation executes), the operator should still receive archives for all other DLCs. A hard abort would require the operator to determine which DLC failed and restart the entire operation.

### 4.6 generate_manifest()

```python
def generate_manifest(
    self,
    results: list[PackResult],
    output_dir: Path,
    url_prefix: str = "<UPLOAD_URL>",
) -> Path
```

Generates `manifest_dlc_downloads.json` in `output_dir` from a list of `PackResult` objects. Returns the `Path` to the generated manifest file.

**JSON structure:** The generated file is a flat JSON object keyed by DLC ID:

```json
{
  "EP01": {
    "url": "<UPLOAD_URL>/Sims4_DLC_EP01_Get_to_Work.zip",
    "size": 1234567890,
    "md5": "ABCDEF0123456789ABCDEF0123456789",
    "filename": "Sims4_DLC_EP01_Get_to_Work.zip"
  },
  "GP01": {
    "url": "<UPLOAD_URL>/Sims4_DLC_GP01_Outdoor_Retreat.zip",
    "size": 987654321,
    "md5": "FEDCBA9876543210FEDCBA9876543210",
    "filename": "Sims4_DLC_GP01_Outdoor_Retreat.zip"
  }
}
```

The file is written with `indent=2` for human readability. The encoding is UTF-8.

**The `url_prefix` parameter** defaults to the literal string `<UPLOAD_URL>`, which the operator must replace with the base URL of their file hosting service before incorporating the manifest into their main distribution manifest. This placeholder is intentional: the packer has no knowledge of where files will be hosted, so it cannot construct valid URLs itself.

The generated file is written to `output_dir / "manifest_dlc_downloads.json"`. In the GUI, `output_dir` is `<app_data_dir>/packed_dlcs/`. In the CLI, it defaults to the current working directory unless `--output` is specified.

### 4.7 import_archive()

```python
def import_archive(
    self,
    archive_path: Path,
    game_dir: Path,
    progress_cb: PackProgressCallback | None = None,
) -> list[str]
```

Extracts a ZIP or RAR archive into `game_dir` and returns a list of DLC IDs that were found in the game directory after extraction. This is the consumer-facing operation that allows users to install DLC content obtained from an external source.

**Execution sequence:**

1. Inspect the file extension of `archive_path` (lowercased).
2. If `.zip`, delegate to `_extract_zip()`.
3. If `.rar`, delegate to `_extract_rar()`.
4. If any other extension, raise `ValueError: Unsupported archive type`.
5. After extraction completes, call `_detect_dlc_dirs()` to scan `game_dir` for DLC folders that match known catalog entries.
6. Return the list of matched DLC IDs.

**Note on `progress_cb`:** The `progress_cb` parameter is accepted for API consistency but is not currently called during extraction. Extraction progress at the file level is not exposed through this interface. The GUI marks the progress bar as indeterminate (value 0) during the import operation.

### 4.8 get_installed_dlcs()

```python
def get_installed_dlcs(self, game_dir: Path) -> list[tuple[DLCInfo, int, int]]
```

Scans the game directory for installed DLCs and returns metadata for each. The return type is a list of three-tuples:

```text
(DLCInfo, file_count: int, folder_size_bytes: int)
```

**Scanning logic:**

For each DLC in `self._catalog.all_dlcs()`:

1. Check whether `game_dir / dlc.id` is a directory. If not, skip this DLC.
2. Walk the DLC directory recursively, counting files and summing their sizes via `stat().st_size`. `OSError` exceptions during the walk are caught and silently ignored (the DLC is still included with whatever partial count was accumulated).
3. Additionally, if `game_dir / "__Installer" / "DLC" / dlc.id` exists, walk that directory and add its files and sizes to the running totals.
4. Append the tuple to the results list.

The results are used by the GUI's `PackerFrame` to populate the DLC list and display size estimates. The file counts and sizes presented in the GUI represent the uncompressed source data, not the final archive sizes (which will be smaller after deflate compression).

**Why count `__Installer/DLC/{id}` separately:** The `__Installer` directory structure is present in some Sims 4 installations and contains setup metadata or supplementary files for specific DLCs. Omitting these files from both the inventory count and the pack operation would produce incomplete archives. The packer includes them so that the extracted archive faithfully replicates the on-disk state of the original installation.

---

## 5. PackResult Dataclass

**Source file:** `src/sims4_updater/dlc/packer.py`, lines 27–37

```python
@dataclass
class PackResult:
    """Result of packing a single DLC."""

    dlc_id: str
    dlc_name: str
    filename: str
    path: Path
    size: int
    md5: str
    file_count: int
```

`PackResult` is produced by `pack_single()` and consumed by `pack_multiple()`, `generate_manifest()`, and the GUI's `_on_pack_done()` handler. It carries all metadata needed to construct the manifest entry and to display a summary to the operator.

| Field | Type | Description |
| --- | --- | --- |
| `dlc_id` | `str` | The DLC identifier (e.g. `"EP01"`). |
| `dlc_name` | `str` | The English display name from the catalog (e.g. `"Get to Work"`). |
| `filename` | `str` | The basename of the generated ZIP file (e.g. `"Sims4_DLC_EP01_Get_to_Work.zip"`). |
| `path` | `Path` | The absolute path to the generated ZIP file on disk. |
| `size` | `int` | The size of the generated ZIP file in bytes. This is the compressed archive size, not the uncompressed source size. |
| `md5` | `str` | The uppercase hexadecimal MD5 hash of the generated ZIP file. Used for integrity verification when users download the archive. |
| `file_count` | `int` | The total number of source files that were written into the archive. This includes files from both the DLC directory and the `__Installer/DLC/{id}` directory if it exists. |

The `size` and `md5` fields are written directly into `manifest_dlc_downloads.json`. The downloader reads them from the manifest and uses them to verify downloaded archives before extraction.

---

## 6. ZIP Archive Format

### 6.1 Filename Convention

Every generated archive follows the filename pattern:

```text
Sims4_DLC_{DLC_ID}_{SafeName}.zip
```

Where `{SafeName}` is the ASCII-only, whitespace-collapsed, punctuation-stripped form of the English DLC name. The prefix `Sims4_DLC_` provides an unambiguous namespace so that archives can be identified at a glance and sorted together when uploaded to a file host that contains other content.

### 6.2 Internal Directory Structure

The archive preserves the directory structure of the game installation, rooted at the game directory level. The paths inside the archive are relative to `game_dir`, not to the DLC directory itself. This means:

**Primary DLC content:**

```text
{dlc_id}/
    {dlc_id}/SimulationFullBuild0.package
    {dlc_id}/ClientFullBuild0.package
    {dlc_id}/<additional game data files>
    {dlc_id}/<subdirectories>/...
```

**Supplementary installer data (if present):**

```text
__Installer/
    __Installer/DLC/
        __Installer/DLC/{dlc_id}/
            __Installer/DLC/{dlc_id}/<metadata files>
```

**Concrete example for EP01:**

```text
Sims4_DLC_EP01_Get_to_Work.zip
    EP01/
        EP01/SimulationFullBuild0.package
        EP01/ClientFullBuild0.package
        EP01/ClientFullBuild1.package
        EP01/Strings/
        EP01/Strings/English.package
        ... (additional game files)
    __Installer/
        __Installer/DLC/
            __Installer/DLC/EP01/
                __Installer/DLC/EP01/... (installer metadata)
```

This structure is intentional: when the archive is extracted into the game directory, each file lands at exactly the correct path. The extraction code in both `DLCPacker._extract_zip()` and `DLCDownloader._extract_zip()` extracts to `game_dir` directly, so `EP01/SimulationFullBuild0.package` in the archive becomes `<game_dir>/EP01/SimulationFullBuild0.package` on disk.

### 6.3 Compression Settings

Archives are created with `zipfile.ZIP_DEFLATED` compression. This is the standard deflate algorithm, offering a good balance between compression ratio and decompression speed. The Sims 4 game data files are primarily binary formats (`.package` files are EA's proprietary DBPF container format), which compresses well with deflate. No `compresslevel` override is specified, so Python's `zipfile` module uses its default level (typically equivalent to zlib level 6).

### 6.4 Path Normalization

The packer explicitly converts all path separators to forward slashes before writing entries into the archive:

```python
zf.write(abs_path, str(rel_path).replace("\\", "/"))
```

This is necessary because the packer runs on Windows, where `Path` produces backslash-separated strings. ZIP file format specifies that paths must use forward slashes. Without this normalization, archives created on Windows would contain backslash paths that extractors on other operating systems might not handle correctly, and the path traversal protection in the extraction code would compare paths using the wrong separator, potentially allowing traversal attacks through inconsistency.

### 6.5 File Enumeration Order

Files are sorted by their relative path before being written into the archive:

```python
for rel_path, abs_path in sorted(files):
```

Sorting is applied to the list of `(relative_path, absolute_path)` tuples. Python sorts `Path` objects lexicographically by their string representation. Consistent ordering ensures that two packs of the same DLC from the same source files produce byte-for-byte identical archives (modulo timestamps embedded by the ZIP format), which simplifies debugging and makes MD5 comparison possible across separate pack runs on identical source data.

---

## 7. Manifest Generation

### 7.1 manifest_dlc_downloads.json Format

The generated manifest is a JSON object where each key is a DLC ID and each value is an object with download metadata:

```json
{
  "EP01": {
    "url": "https://cdn.example.com/dlc/Sims4_DLC_EP01_Get_to_Work.zip",
    "size": 2147483648,
    "md5": "D41D8CD98F00B204E9800998ECF8427E",
    "filename": "Sims4_DLC_EP01_Get_to_Work.zip"
  },
  "GP01": {
    "url": "https://cdn.example.com/dlc/Sims4_DLC_GP01_Outdoor_Retreat.zip",
    "size": 1073741824,
    "md5": "B14A7B8059D9C055954C92674CE60032",
    "filename": "Sims4_DLC_GP01_Outdoor_Retreat.zip"
  }
}
```

Before editing, the URL fields contain `<UPLOAD_URL>/Sims4_DLC_EP01_Get_to_Work.zip`. After the operator edits the file (or incorporates it into their main manifest), the `<UPLOAD_URL>` prefix is replaced with the actual hosting base URL.

### 7.2 Field Reference

| Field | Source | Description |
| --- | --- | --- |
| `url` | Constructed: `f"{url_prefix}/{r.filename}"` | Full download URL for the archive. The default value uses the `<UPLOAD_URL>` placeholder. |
| `size` | `PackResult.size` | Archive size in bytes. Used by the downloader to pre-allocate space and to verify complete download. |
| `md5` | `PackResult.md5` | Uppercase hexadecimal MD5 of the archive. Used by the downloader for post-download integrity verification. |
| `filename` | `PackResult.filename` | Basename of the archive file. Allows the downloader to derive the local filename independently of the URL path. |

### 7.3 Placeholder URL Workflow

The `<UPLOAD_URL>` placeholder appears in the generated manifest because the packer has no knowledge of the hosting infrastructure. The operator workflow is:

1. Run the packer (GUI or CLI) to generate archives and `manifest_dlc_downloads.json`.
2. Upload the archive files to a CDN or file host (e.g., `https://cdn.example.com/dlc/`).
3. Open `manifest_dlc_downloads.json` and perform a global find-and-replace of `<UPLOAD_URL>` with the actual base URL (e.g., `https://cdn.example.com/dlc`).
4. Incorporate the contents of this file into the main distribution manifest's `dlc_downloads` section (see Section 7.4).
5. Upload the updated main manifest to its hosting location.

The `<` and `>` characters in the placeholder make it an invalid URL, so any system that tries to use the manifest before the operator updates it will fail clearly rather than silently downloading from an incorrect location.

### 7.4 Integration with the Main Manifest

The generated `manifest_dlc_downloads.json` content must be integrated into the main application manifest that the updater fetches. The main manifest format (defined in `src/sims4_updater/patch/manifest.py`) has a top-level `dlc_downloads` key that corresponds exactly to the format of the generated file:

```json
{
  "latest": "1.120.123.1020",
  "patches": [ ... ],
  "dlc_downloads": {
    "EP01": {
      "url": "https://cdn.example.com/dlc/Sims4_DLC_EP01_Get_to_Work.zip",
      "size": 2147483648,
      "md5": "D41D8CD98F00B204E9800998ECF8427E",
      "filename": "Sims4_DLC_EP01_Get_to_Work.zip"
    }
  }
}
```

The application's manifest parser (`parse_manifest()` in `patch/manifest.py`) reads the `dlc_downloads` section and creates `DLCDownloadEntry` objects that the `DLCDownloader` uses to download and install the archives.

The generated `manifest_dlc_downloads.json` is thus a staging artifact — not a complete manifest, but the portion of a complete manifest that covers DLC downloads.

---

## 8. Archive Import

### 8.1 Supported Formats

`import_archive()` supports two archive formats:

| Extension | Handler | Tool |
| --- | --- | --- |
| `.zip` | `_extract_zip()` | Python standard library `zipfile` module |
| `.rar` | `_extract_rar()` | Bundled `unrar.exe` subprocess |

Any other extension causes a `ValueError` to be raised with the message `"Unsupported archive type: {ext}"`.

### 8.2 Path Traversal Protection

The ZIP extraction implementation explicitly guards against path traversal attacks. A maliciously crafted ZIP could contain entries with paths like `../../Windows/System32/evil.dll` that, when extracted, would write files outside the intended destination directory.

The protection is implemented as a resolved-path prefix check:

```python
dest_resolved = dest_dir.resolve()
for member in zf.namelist():
    target = (dest_dir / member).resolve()
    if not str(target).startswith(str(dest_resolved)):
        logger.warning("Skipping unsafe zip path: %s", member)
        continue
    zf.extract(member, dest_dir)
```

`Path.resolve()` collapses all `..` components and resolves symlinks, producing an absolute canonical path. Checking that the resolved extraction target starts with the resolved destination directory prevents any member path from escaping the destination tree. Unsafe entries are skipped with a warning log entry rather than raising an exception, allowing the remaining valid entries to be extracted.

This same pattern is used in `DLCDownloader._extract_zip()` for the automated download path, ensuring consistent behavior across both extraction sites.

### 8.3 ZIP Extraction

```python
def _extract_zip(self, archive_path: Path, dest_dir: Path):
```

Opens the archive with `zipfile.ZipFile(archive_path, "r")` and iterates over all member names. After the path traversal check, each member is extracted using `zf.extract(member, dest_dir)`.

On `zipfile.BadZipFile`, the exception is re-raised as `DownloadError("Corrupt archive: {e}")`. This converts the stdlib exception into the application's error hierarchy, allowing callers to handle all extraction failures through the same exception type regardless of format.

### 8.4 RAR Extraction and Bundled unrar.exe

RAR extraction invokes the `unrar.exe` command-line tool as a subprocess. This tool must be present in the `tools/` directory of the application bundle:

```python
unrar = get_tools_dir() / "unrar.exe"
if not unrar.is_file():
    raise FileNotFoundError(
        "unrar.exe not found. Cannot extract RAR archives."
    )
```

`get_tools_dir()` resolves to `sys._MEIPASS / "tools"` when running as a PyInstaller frozen executable, or to the `tools/` directory relative to the source tree when running from source. In the built distribution, `unrar.exe` is bundled inside the executable (packed by PyInstaller) and unpacked to a temp directory at runtime.

The subprocess is invoked with the following arguments:

```text
unrar.exe x -p- -o+ <archive_path> <dest_dir>\
```

| Argument | Meaning |
| --- | --- |
| `x` | Extract with full paths (preserve directory structure). |
| `-p-` | No password prompt (fail if archive is password-protected). |
| `-o+` | Overwrite existing files without prompting. |

The trailing backslash after `dest_dir` is required by `unrar.exe` to recognize the argument as a destination directory rather than an archive filename.

A 600-second (10-minute) timeout is applied to the subprocess. If the process exits with a non-zero return code, both stdout and stderr are decoded and combined into a `DownloadError` message.

**Why RAR support:** Some users distribute DLC archives in RAR format, particularly multi-volume archives (`part01.rar`, `part02.rar`, etc.). Supporting RAR import allows the application to be useful even when the user has received content from a source that chose RAR packaging instead of ZIP.

**Licensing note:** `unrar.exe` is a proprietary tool distributed by RARLAB. Its license permits redistribution for free use. The application bundle includes the unrar license file alongside the binary as required by the license terms.

### 8.5 DLC Detection After Extraction

After extraction completes, `_detect_dlc_dirs()` scans the game directory for directories whose names match known DLC IDs:

```python
def _detect_dlc_dirs(self, game_dir: Path) -> list[str]:
    found = []
    for dlc in self._catalog.all_dlcs():
        dlc_dir = game_dir / dlc.id
        if dlc_dir.is_dir():
            found.append(dlc.id)
    return found
```

This returns only the DLC IDs present in the catalog that now have directories in the game folder. Unknown directories (not matching any catalog entry) are not reported. The returned list represents the DLCs that were successfully extracted from the archive.

The detected DLC IDs are returned to the GUI's `_on_import_done()` handler, which displays them to the user and offers to register them in the crack configuration.

---

## 9. GUI: Packer Frame

**Source file:** `src/sims4_updater/gui/frames/packer_frame.py`

`PackerFrame` is a `customtkinter.CTkFrame` that provides the graphical interface for all packing and import operations. It is displayed as a named tab within the main application window. The frame integrates with the application's async runner to keep all blocking operations off the GUI thread.

### 9.1 Frame Layout and Sections

The frame uses a grid layout with five rows:

| Row | Content |
| --- | --- |
| 0 | Header: title ("DLC Packer") and subtitle label |
| 1 | Top bar: Select All / Deselect All / Pack Selected / Pack All buttons |
| 2 | Scrollable DLC list (weight=1, expands to fill available height) |
| 3 | Import section: label, description, "Browse & Import..." button |
| 4 | Bottom bar: progress bar, status label, output path display, Open Folder button |

### 9.2 DLC Discovery and the Installed DLC List

When the frame becomes visible (`on_show()` is called by the tab system), it immediately initiates a background scan:

```python
def on_show(self):
    self._load_installed_dlcs()
```

`_load_installed_dlcs()` calls `app.run_async(_scan_bg, on_done=_on_scan_done, on_error=_on_scan_error)`.

**Background scan (`_scan_bg`):**

1. Calls `app.updater.find_game_dir()` to resolve the current game directory from settings.
2. If no game directory is configured, returns `None` to signal the empty state.
3. Calls `self._packer.get_installed_dlcs(Path(game_dir))` and returns the result list.

**UI update (`_on_scan_done`):**

1. Destroys any existing DLC row widgets.
2. Clears `_dlc_vars` (mapping of DLC ID to `BooleanVar`) and `_dlc_sizes` (mapping of DLC ID to folder size).
3. If the result is `None`, shows the empty-state label ("No game directory found. Set it in Settings.").
4. For each `(dlc, file_count, folder_size)` tuple, calls `_build_dlc_row()`.
5. Updates the status label with the total count.

**DLC row construction (`_build_dlc_row`):**

Each DLC is rendered as a card-style `CTkFrame` containing:

- A `CTkCheckBox` with the label `"{dlc.id} — {dlc.get_name()}"` and a `BooleanVar` defaulting to `True` (pre-selected).
- A size label on the right showing `"{file_count} files, {formatted_size}"`.

The checkbox's `BooleanVar` is stored in `self._dlc_vars[dlc.id]`. The folder size in bytes is stored in `self._dlc_sizes[dlc.id]` for disk space estimation.

Rows use alternating background colors (`bg_card` for even indices, `bg_card_alt` for odd indices) to aid visual separation. All rows are registered in `self._dlc_rows` for cleanup on the next scan.

### 9.3 Disk Space Checking

Before starting any pack operation, the frame estimates whether sufficient disk space is available:

```python
estimated_size = sum(self._dlc_sizes.get(d, 0) for d in dlc_ids)
self._output_dir.mkdir(parents=True, exist_ok=True)
free_space = shutil.disk_usage(self._output_dir).free
```

`estimated_size` is the sum of the uncompressed source sizes of all selected DLCs. The actual ZIP files will be somewhat smaller due to deflate compression, so this estimate is conservative (worst case).

Three tiers of response:

| Condition | Action |
| --- | --- |
| `estimated_size > free_space` | Show a `tk.messagebox.askyesno` asking whether to continue anyway. If the user answers No, the operation is aborted. |
| `estimated_size > free_space * 0.9` | Show a non-blocking warning toast: "Warning: packing will use ~X of Y free". The operation continues. |
| Neither | No disk space warning. The operation proceeds silently. |

If `shutil.disk_usage` raises an `OSError` (for example, if the output directory is on an unmounted network share), `free_space` is set to 0. When `free_space` is 0, neither condition triggers and the operation proceeds without disk space verification.

### 9.4 Overwrite Protection

After the disk space check, the frame checks whether any of the selected DLC archives already exist in the output directory:

```python
catalog = self._packer._catalog
existing = []
for dlc_id in dlc_ids:
    dlc = catalog.get_by_id(dlc_id)
    if dlc and self._packer.get_zip_path(dlc, self._output_dir).is_file():
        existing.append(dlc_id)
```

If any archives already exist, a three-option `tk.messagebox.askyesnocancel` dialog is shown:

| User choice | Behavior |
| --- | --- |
| Yes (Overwrite) | All selected DLCs are packed, overwriting existing archives. |
| No (Skip existing) | Only DLCs without existing archives are packed. If all selected DLCs already exist, a success toast is shown and no packing occurs. |
| Cancel | The entire operation is aborted. |

This prevents accidental re-packing of DLCs that have already been successfully packed and uploaded, which would invalidate any cached download on the CDN if the file changes.

### 9.5 Progress Tracking

During packing, the frame provides live feedback through two UI elements:

**Progress bar (`_progress_bar`):** A `CTkProgressBar` that displays the fraction of DLCs completed. It is updated via a callback that runs on the GUI thread:

```python
def _update_pack_progress(self, idx, total, dlc_id, pct):
    self._progress_bar.set(pct)
    if dlc_id:
        self._status_label.configure(text=f"Packing {idx + 1}/{total}: {dlc_id}")
    else:
        self._status_label.configure(text=f"Packing {idx}/{total}...")
```

`pct` is computed as `idx / total` where `idx` is the 0-based index of the DLC currently being packed.

**Status label (`_status_label`):** Displays the current DLC being packed ("Packing 3/15: EP07") and, upon completion, the total summary ("Packed 15 DLC(s), 18.3 GB total. Manifest saved to ...").

**Button state:** All five control buttons (Select All, Deselect All, Pack Selected, Pack All, Browse & Import) are disabled via `_set_buttons_state("disabled")` at the start of any operation and re-enabled via `_set_buttons_state("normal")` when the operation completes or fails. The `_busy` flag provides an additional guard to prevent concurrent operations if a button state update is delayed.

### 9.6 Output Directory and Open Folder Button

The output directory is fixed at application startup:

```python
self._output_dir = get_app_dir() / "packed_dlcs"
```

`get_app_dir()` resolves to `%LOCALAPPDATA%/ToastyToast25/sims4_updater/` on Windows, or `~/.config/sims4_updater/` on other platforms. The `packed_dlcs` subdirectory is created lazily (by `pack_single()` and by the disk space check's `mkdir`).

The output path is displayed in the bottom-right corner of the frame as a non-interactive label. Adjacent to it is the "Open Folder" button, which calls:

```python
def _open_output_folder(self):
    import os
    self._output_dir.mkdir(parents=True, exist_ok=True)
    os.startfile(self._output_dir)
```

`os.startfile` is Windows-specific and opens the directory in Windows Explorer. The directory is created by `mkdir` if it does not yet exist, ensuring that the Explorer window can always be opened even before the first pack operation.

### 9.7 Import Flow

The import process is initiated by the "Browse & Import..." button. The complete flow:

1. **File selection:** Opens a `tkinter.filedialog.askopenfilename` dialog filtered to `*.zip *.rar` files.
2. **Game directory check:** If no game directory is configured, shows an error toast and aborts.
3. **Confirmation dialog:** Shows a `tk.messagebox.askyesno` asking the user to confirm extraction into the displayed game directory path.
4. **Async extraction:** Calls `app.run_async(_import_bg, archive_path, game_dir, on_done=_on_import_done, on_error=_on_import_error)`.
5. **Status update:** Sets the status label to "Importing {filename}..." and disables all buttons.

`_import_bg` simply calls `self._packer.import_archive(Path(archive_path), Path(game_dir))` and returns the list of detected DLC IDs.

On completion, `_on_import_done` is called with the detected DLC ID list.

### 9.8 Post-Import DLC Registration

After a successful import, if at least one DLC was detected, the frame offers to register the extracted DLCs in the crack configuration:

```python
register = tk.messagebox.askyesno(
    "Register DLCs",
    f"The following DLCs were extracted:\n{dlc_list}\n\n"
    "Enable them in the crack config?",
    parent=self,
)
if register:
    self.app.run_async(
        self._register_bg, found_dlc_ids,
        on_done=lambda _: self.app.show_toast("DLCs registered", "success"),
        on_error=lambda e: self.app.show_toast(f"Registration error: {e}", "error"),
    )
```

`_register_bg` calls the DLC manager to build the current enabled set and then applies changes. The logic preserves all previously enabled DLCs while adding the newly extracted ones:

```python
def _register_bg(self, dlc_ids: list[str]):
    game_dir = self.app.updater.find_game_dir()
    mgr = self.app.updater._dlc_manager
    states = mgr.get_dlc_states(game_dir)
    enabled_set = set()
    for state in states:
        if state.enabled is True:
            enabled_set.add(state.dlc.id)
        elif state.dlc.id in dlc_ids and state.installed:
            enabled_set.add(state.dlc.id)
    mgr.apply_changes(game_dir, enabled_set)
```

This preserves the existing enabled/disabled state of all other DLCs while enabling any of the newly imported DLCs that have been verified as installed (`state.installed` is `True` only when the DLC directory exists on disk after extraction).

### 9.9 Async Execution Model

All blocking operations in `PackerFrame` are run on a background thread via `app.run_async(task_fn, *args, on_done=..., on_error=...)`. The background function returns a value (or raises an exception), which the application scheduler posts back to the GUI thread as a call to `on_done(result)` or `on_error(exception)`. This ensures that the GUI remains responsive during multi-gigabyte compression operations.

The internal progress callback routes GUI updates back to the main thread via `app._enqueue_gui(self._update_pack_progress, idx, total, dlc_id, pct)`, which schedules the call to run on the next GUI event loop iteration. This is safe because `CTkProgressBar.set()` and `CTkLabel.configure()` must only be called from the GUI thread.

---

## 10. CLI Usage

**Source file:** `src/sims4_updater/__main__.py`, `pack_dlc()` function (lines 413–475)

The `pack-dlc` command provides the same packing functionality as the GUI but is suitable for automation, scripting, and server environments where no graphical display is available.

### 10.1 pack-dlc Command Syntax

```sh
python -m sims4_updater pack-dlc <game_dir> <dlc_ids...> [-o <output_dir>]
```

or, when installed as a package entry point:

```sh
sims4-updater pack-dlc <game_dir> <dlc_ids...> [-o <output_dir>]
```

### 10.2 Arguments Reference

| Argument | Required | Description |
| --- | --- | --- |
| `game_dir` | Yes | Absolute or relative path to the Sims 4 installation directory. Must contain a subdirectory for each DLC to be packed (e.g., `<game_dir>/EP01`). |
| `dlc_ids` | Yes (one or more) | One or more DLC IDs to pack, separated by spaces (e.g., `EP01 GP01 SP01`). The special value `all` causes all installed DLCs to be packed. DLC IDs are matched case-insensitively (internally uppercased via `dlc_id.upper()`). |
| `-o <output_dir>` / `--output <output_dir>` | No | Output directory for the generated archives and manifest file. Defaults to `.` (the current working directory). The directory is created if it does not exist. |

The argument parser for `pack-dlc` is registered as:

```python
pack_parser = subparsers.add_parser(
    "pack-dlc", help="Create standard zip archives for DLCs",
)
pack_parser.add_argument("game_dir", ...)
pack_parser.add_argument("dlc_ids", nargs="+", ...)
pack_parser.add_argument("-o", "--output", default=".", ...)
```

### 10.3 Usage Examples

**Pack a single DLC:**

```sh
sims4-updater pack-dlc "C:\Program Files\EA Games\The Sims 4" EP01
```

**Pack multiple specific DLCs:**

```sh
sims4-updater pack-dlc "C:\Program Files\EA Games\The Sims 4" EP01 EP02 GP01 GP02 SP01
```

**Pack all installed DLCs into a specific output directory:**

```sh
sims4-updater pack-dlc "C:\Program Files\EA Games\The Sims 4" all -o D:\dlc_archives
```

**Pack all DLCs with a relative output path:**

```sh
sims4-updater pack-dlc "C:\Program Files\EA Games\The Sims 4" all -o .\output
```

### 10.4 CLI Output Format

The CLI provides step-by-step feedback to stdout.

**During packing:**

```text
[1/3] Packing EP01...
[2/3] Packing GP01...
[3/3] Packing SP01...
```

**Summary per DLC (after all packing completes):**

```text
  EP01: 47 files, 2341.8 MB, MD5: D41D8CD98F00B204E9800998ECF8427E
  GP01: 31 files, 1203.4 MB, MD5: B14A7B8059D9C055954C92674CE60032
  SP01: 18 files, 892.1 MB, MD5: 7215EE9C7D9DC229D2921A40E899EC5F
```

**Manifest output (printed to stdout after the separator):**

```text
============================================================
Manifest written to: D:\dlc_archives\manifest_dlc_downloads.json
============================================================
{
  "EP01": {
    "url": "<UPLOAD_URL>/Sims4_DLC_EP01_Get_to_Work.zip",
    "size": 2454678528,
    ...
  },
  ...
}
Replace <UPLOAD_URL> with the actual hosting URL.
```

**Warning conditions (printed and skipped, not fatal):**

```text
WARNING: Unknown DLC ID: XYZZY
WARNING: EP99 not installed (no folder at C:\...\EP99)
```

**Exit codes:**

| Condition | Exit code |
| --- | --- |
| All specified DLCs packed successfully | 0 |
| Game directory not found | 1 (via `sys.exit(1)`) |
| No valid DLCs to pack (all IDs unknown or uninstalled) | 1 (via `sys.exit(1)`) |
| No installed DLCs found when using `all` | 1 (via `sys.exit(1)`) |

Individual DLC failures (e.g., a DLC directory disappearing during packing) produce warnings but do not set a non-zero exit code, because `pack_multiple()` catches those errors internally.

---

## 11. Distribution Workflow

### 11.1 End-to-End Workflow Overview

The complete distribution workflow involves the operator (the person maintaining the update server) and the end users (players using the Sims 4 Updater application):

```text
[Operator machine]                         [CDN / File Host]             [User machine]

pack-dlc or GUI Pack
        |
        v
  EP01.zip, GP01.zip, ...
  manifest_dlc_downloads.json
        |
        v (upload)
                                      EP01.zip  <------ users download
                                      GP01.zip          via DLC tab
                                      manifest.json
                                           |
                                    (operator edits
                                     manifest URL
                                     in main manifest)
```

### Step 1 — Pack DLC Archives

The operator installs the complete set of Sims 4 DLCs they wish to distribute, then runs the packer:

**Via GUI:**

1. Open the Packer tab.
2. Verify that the DLC list shows all expected DLCs.
3. Select all (or a subset) and click "Pack All" or "Pack Selected".
4. Monitor progress in the status bar.
5. When complete, note the output directory shown in the bottom bar.

**Via CLI:**

```sh
sims4-updater pack-dlc "C:\Program Files\EA Games\The Sims 4" all -o C:\output\dlcs
```

The result is a set of ZIP files and one `manifest_dlc_downloads.json` file in the output directory.

### Step 2 — Upload to CDN

Upload all generated files to the file hosting service. The directory structure on the host does not matter as long as all files are accessible via HTTP. A flat directory structure is simplest:

```text
https://cdn.example.com/dlc/
    Sims4_DLC_EP01_Get_to_Work.zip
    Sims4_DLC_EP02_Get_Together.zip
    Sims4_DLC_GP01_Outdoor_Retreat.zip
    ...
```

Each file must be served with HTTP range request support (for resumable downloads) if the downloader is expected to support resume. The downloader uses standard range request headers.

### Step 3 — Update the Manifest URL

1. Open the generated `manifest_dlc_downloads.json`.
2. Replace all occurrences of `<UPLOAD_URL>` with the base URL of the upload location (e.g., `https://cdn.example.com/dlc`).
3. Incorporate the resulting JSON object into the `dlc_downloads` key of the main manifest JSON file.
4. Upload the updated main manifest to its URL.

Alternatively, use a command-line tool to perform the replacement and merge automatically:

**PowerShell example:**

```powershell
(Get-Content manifest_dlc_downloads.json) `
    -replace '<UPLOAD_URL>', 'https://cdn.example.com/dlc' `
    | Set-Content manifest_dlc_downloads_final.json
```

**Python example:**

```python
import json

with open("manifest_dlc_downloads.json") as f:
    dlc_downloads = json.load(f)

with open("main_manifest.json") as f:
    manifest = json.load(f)

base_url = "https://cdn.example.com/dlc"
for dlc_id, entry in dlc_downloads.items():
    entry["url"] = entry["url"].replace("<UPLOAD_URL>", base_url)

manifest["dlc_downloads"] = dlc_downloads

with open("main_manifest_updated.json", "w") as f:
    json.dump(manifest, f, indent=2)
```

### Step 4 — User Download and Install

Once the manifest is live, users with a configured manifest URL will see available DLC downloads in the application's DLC tab. The `DLCDownloader` reads the `dlc_downloads` section of the manifest, presents the download options, and handles the three-phase pipeline (download, extract, register) automatically.

Users can also use the Packer tab's "Browse & Import..." button to install a manually downloaded archive. This path does not require a manifest and works entirely offline.

### 11.6 Hosting Considerations

**MD5 verification:** The downloader verifies the MD5 of each downloaded archive before extraction. The MD5 values in the manifest are computed over the exact bytes of the ZIP file produced by the packer. If the file is modified after packing (for example, by a CDN that re-compresses or alters headers), the MD5 check will fail. Use a CDN that serves files as-is.

**File immutability:** Once a DLC ZIP is uploaded and its MD5 is in the manifest, the file should not be replaced with a different version at the same URL without also updating the manifest's `md5` field, `size` field, and potentially the `filename` and `url` fields. Users whose applications have cached the old manifest may attempt to verify the new file against the old MD5 and fail.

**Versioning:** The packer generates archives from the operator's current local DLC installation. If EA releases an update to a DLC (for example, a bug-fix to `EP01`), the operator must re-pack the affected DLCs, re-upload them, and update the manifest. Keeping the filename consistent (or changing it to include a version tag) and updating the MD5 and size are the only requirements for the distribution chain to function correctly.

**Archive size:** Individual DLC archives range from a few hundred megabytes (small Stuff Packs) to several gigabytes (full Expansion Packs). Ensure the hosting service supports large file uploads and has sufficient bandwidth. The application's downloader supports HTTP range requests for resumable downloads, so interrupted downloads can be resumed without re-downloading the entire archive.

---

## 12. Error Handling Reference

### 12.1 Pack Errors

| Error type | Condition | Behavior |
| --- | --- | --- |
| `FileNotFoundError` | DLC directory (`<game_dir>/<dlc_id>`) does not exist | Caught by `pack_multiple()`, logged as warning, DLC is skipped |
| `FileNotFoundError` | DLC directory exists but contains no files | Caught by `pack_multiple()`, logged as warning, DLC is skipped |
| `OSError` | Disk I/O failure reading source files or writing archive | Caught by `pack_multiple()`, logged as warning, DLC is skipped |
| `RuntimeError` | No game directory found (GUI only) | Propagated to `on_error` handler, displayed as error toast |

In the GUI, errors that reach `_on_pack_error` are displayed in the status label (in error color) and as a toast notification. The progress bar is reset to 0. All buttons are re-enabled.

### 12.2 Import Errors

| Error type | Condition | Behavior |
| --- | --- | --- |
| `ValueError` | Archive extension is not `.zip` or `.rar` | Propagated to `on_error` handler, displayed as error toast |
| `DownloadError("Corrupt archive: ...")` | ZIP file is malformed (bad magic bytes, CRC errors, truncated) | Propagated to `on_error` handler, displayed as error toast |
| `FileNotFoundError` | `unrar.exe` not found in tools directory | Propagated to `on_error` handler, displayed as error toast |
| `DownloadError("RAR extraction failed: ...")` | `unrar.exe` exits with non-zero return code | Propagated to `on_error` handler, displayed as error toast |
| `subprocess.TimeoutExpired` | `unrar.exe` does not complete within 600 seconds | Not explicitly caught; will surface as unhandled exception in `on_error` |

Unsafe ZIP paths (path traversal attempts) produce a `logger.warning` entry but do not raise an exception; extraction continues with the remaining safe entries.

---

## 13. Progress Callback Protocol

The `PackProgressCallback` type alias is defined as:

```python
PackProgressCallback = Callable[[int, int, str, str], None]
```

Callbacks receive four positional arguments:

| Position | Type | Description |
| --- | --- | --- |
| 0 | `int` | `current_index` — The 0-based index of the current DLC being processed. |
| 1 | `int` | `total_count` — The total number of DLCs in the operation. |
| 2 | `str` | `dlc_id` — The ID of the DLC currently being processed, or an empty string for the final "Done" callback. |
| 3 | `str` | `message` — A human-readable status message (e.g., `"Packing EP01..."`, `"Done"`). |

**Invocation sequence in `pack_multiple()`:**

```python
progress_cb(0, 3, "EP01", "Packing EP01...")   # before packing EP01
progress_cb(1, 3, "GP01", "Packing GP01...")   # before packing GP01
progress_cb(2, 3, "SP01", "Packing SP01...")   # before packing SP01
progress_cb(3, 3, "", "Done")                  # after all DLCs complete
```

The GUI derives the progress bar fraction as `current_index / total_count`. Note that the callback is fired before the pack operation begins, not after. This means the progress bar shows the fraction of DLCs that have been started, not completed. The progress bar reaches 1.0 only when `_on_pack_done()` is called after the background task finishes.

The final "Done" callback is always called, even if some DLCs failed. The GUI ignores this callback (relying instead on `_on_pack_done`) because `pack_multiple()` calls it from the background thread while `_on_pack_done` is dispatched through the GUI event queue.

---

## 14. MD5 Hashing Implementation

**Source file:** `src/sims4_updater/dlc/packer.py`, lines 271–277

```python
def _hash_file(path: Path) -> str:
    """Compute uppercase hex MD5 hash of a file."""
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            md5.update(chunk)
    return md5.hexdigest().upper()
```

The function reads the file in 64 KB chunks (65536 bytes) to avoid loading large archives into memory all at once. DLC archives can exceed several gigabytes, so streaming is essential.

The digest is returned as an uppercase hexadecimal string. This matches the format expected by the downloader's integrity verification routine, which compares the downloaded file's MD5 against the value from the manifest. The downloader uses `md5.hexdigest().upper()` for consistency.

**Why MD5:** MD5 is not suitable for cryptographic security, but it is entirely adequate for detecting accidental data corruption (bit rot, incomplete transfers, mismatched uploads). The use case here is integrity verification, not authentication. MD5 is fast enough on modern hardware to hash multi-gigabyte files without becoming a bottleneck relative to the underlying disk I/O.

---

## Appendix A — Full PackResult Field Reference

| Field | Python type | ZIP manifest key | Description |
| --- | --- | --- | --- |
| `dlc_id` | `str` | (key of manifest entry) | DLC identifier, e.g. `"EP01"`. |
| `dlc_name` | `str` | (not in manifest) | English display name, e.g. `"Get to Work"`. Used only for CLI display. |
| `filename` | `str` | `"filename"` | Basename of the archive file. |
| `path` | `Path` | (not in manifest) | Absolute path to the archive. Used only locally. |
| `size` | `int` | `"size"` | Compressed archive size in bytes. |
| `md5` | `str` | `"md5"` | Uppercase hex MD5 of the archive. |
| `file_count` | `int` | (not in manifest) | Number of source files written into the archive. |

---

## Appendix B — DLC ID Taxonomy

The catalog recognizes five `pack_type` values:

| `pack_type` value | Description | ID prefix | Count (as of catalog bundled with v2.0.0) |
| --- | --- | --- | --- |
| `expansion` | Expansion Pack — full-featured large DLC | `EP` | Up to EP16 |
| `game_pack` | Game Pack — mid-size DLC | `GP` | Up to GP16 |
| `stuff_pack` | Stuff Pack — small cosmetic DLC | `SP` | Up to SP46 |
| `kit` | Kit — smallest DLC category | `KIT` | Up to KIT30 |
| `free_pack` | Free DLC distributed at no cost | `FP` | FP01 (Holiday Celebration Pack) |

The `DLCCatalog.by_type(pack_type)` method accepts these string values. The CLI `dlc` command groups its output by type using the same values. The GUI DLC list in both the DLC frame and the Packer frame presents all types in a single unsorted list (filtered to installed DLCs only).

---

## Appendix C — File Layout Quick Reference

```text
<output_dir>/
    Sims4_DLC_EP01_Get_to_Work.zip
    Sims4_DLC_EP02_Get_Together.zip
    Sims4_DLC_GP01_Outdoor_Retreat.zip
    ... (one zip per DLC)
    manifest_dlc_downloads.json

<game_dir>/
    EP01/
        SimulationFullBuild0.package   <- presence validates DLC completeness
        ClientFullBuild0.package
        ClientFullBuild1.package
        ... (additional game files)
    __Installer/
        DLC/
            EP01/
                ... (installer metadata)

<tools_dir>/
    unrar.exe                          <- required for RAR import
    (unrar license file)

<app_data_dir>/                        <- %LOCALAPPDATA%\ToastyToast25\sims4_updater\
    packed_dlcs/                       <- GUI output directory
        Sims4_DLC_EP01_Get_to_Work.zip
        ...
        manifest_dlc_downloads.json
    custom_dlcs.json                   <- persisted remote catalog additions
    settings.json                      <- user settings including manifest URL

<data_dir>/                            <- bundled application data
    dlc_catalog.json                   <- master DLC registry (read-only)
    version_hashes.json                <- version fingerprint database
```

**Key path resolution functions:**

| Function | Source | Returns |
| --- | --- | --- |
| `get_app_dir()` | `config.py` | `%LOCALAPPDATA%/ToastyToast25/sims4_updater/` |
| `get_data_dir()` | `constants.py` | `sys._MEIPASS/data` (frozen) or `<repo>/data` (source) |
| `get_tools_dir()` | `constants.py` | `sys._MEIPASS/tools` (frozen) or `<repo>/tools` (source) |
