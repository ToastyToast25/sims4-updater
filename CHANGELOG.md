# Changelog

All notable changes to The Sims 4 Updater will be documented in this file.

## [2.11.0] - 2026-03-01

### Added

- **DLC version compatibility safeguards** — DLCs now carry a `min_version` field in the manifest indicating the earliest game version they support. On downgrade, incompatible DLCs are automatically disabled in the crack config; on upgrade back, they are re-enabled. Tracked via new `auto_disabled_dlcs` list in settings so user-toggled DLCs are never affected
- **Pre-downgrade DLC impact warning** — when the home screen detects a downgrade, a warning banner lists which DLCs will be auto-disabled (e.g., "3 DLC(s) will be auto-disabled (incompatible with 1.112.519.1020): EP18, SP63, SP64")
- **Version compatibility pill in DLC catalog** — DLCs incompatible with the current game version display a "v1.113.277.1030+" pill badge in the DLC list so users can see at a glance which packs require a newer game version
- **Download version guard** — downloading DLCs incompatible with the installed game version triggers a warning toast ("EP18 require a newer game version. Update your game first.")
- **CDN Manager: DLC version metadata pipeline** — new "Build DLC version metadata" checkbox in the depot pipeline scans downloaded game versions for Delta DLC folders, builds a `{dlc_id: min_version}` map sorted by numeric version, and publishes `min_version` to each DLC entry in the live manifest
- **CDN Manager: `scan_version_dlcs()`** — scans a version directory's `Delta/` folder for DLC subdirectories (EP, GP, SP, FP prefixes) and returns a sorted list of DLC IDs
- **CDN Manager: `build_dlc_version_map()`** — iterates versions oldest-to-newest (numeric sort) and records the first version each DLC appears in, producing the `min_version` mapping
- **CDN Manager: `update_dlc_min_versions()`** — fetches the live manifest, updates `min_version` on existing DLC download entries, and re-publishes
- **CDN Manager: batch pipeline version cleanup** — downloaded game versions are cleaned up incrementally during catch-up phase, freeing ~25 GB per version as soon as all adjacent patches are created
- **CDN Manager: partial download cleanup** — DepotDownloader preallocated files are deleted immediately on download failure or hash verification failure to reclaim disk space

### Fixed

- **Patching: DLC state lost on update** — replaced `auto_toggle` with `export_states`/`import_states` in the GUI update path so user's manual DLC enable/disable choices are preserved across patches instead of being overwritten
- **Patching: backup message when backups disabled** — `create_backup()` return value is now checked before logging "Backup created" so `max_count=0` shows the correct "Backups disabled" message
- **Patching: HTTP 416 on download resume** — corrupt partial files that cause 416 Range Not Satisfiable are now deleted and retried as fresh downloads instead of failing permanently
- **Patching: progress bar jump on resume** — progress callback now emitted after skipping cached files so the progress bar advances smoothly instead of jumping
- **CMD window flash** — all subprocess calls (`tasklist`, `taskkill`, `schtasks`, `unrar`) now use `CREATE_NO_WINDOW` creation flags to prevent console windows from briefly appearing while navigating tabs
- **CSV parsing robustness** — `tasklist` CSV output is now parsed with `csv.reader` instead of naive `split(",")` to handle quoted fields correctly
- **Version detection: oversized sentinels** — sentinel files larger than 50 MB are skipped during version detection to avoid slow hashing of unexpectedly large files
- **Fingerprint merge validation** — fingerprint type, MD5 format, and entry counts are validated before merging learned hashes to prevent corrupt data from poisoning the database
- **Backup disable setting** — `max_count=0` now correctly disables backups (no-op `create_backup`) instead of being treated as unlimited
- **URL validation** — manifest and contribute URLs in settings are validated to require HTTPS
- **Path validation** — game directory, Steam, and GreenLuma paths are validated before saving settings
- **Silent exception logging** — five modules that used bare `except: pass` now log exceptions at `DEBUG` level instead of swallowing them silently
- **CLI `check-update` subcommand** — new subcommand with exit codes (0=up-to-date, 1=update available, 2=error) for scripting

### CDN Manager

- **Depot pipeline** — full batch pipeline with concurrent DepotDownloader download, xdelta patch creation, and SFTP upload to the seedbox with streaming upload worker
- **Post-download verification** — file count, total size, zero-byte detection, and sentinel hash fingerprint checks after each DepotDownloader download
- **Upload integrity** — size + MD5 hash verification on seedbox; skip re-upload if already present with matching hash; detect truncated uploads
- **Bulk KV route registration** — all Cloudflare KV routes registered at pipeline end to avoid free-tier rate limits
- **Catch-up patching** — on resume, patches are created for already-downloaded versions that haven't been patched yet
- **SteamDB manifest scraper** — version registry populated from SteamDB depot manifests
- **Python 3.14 compatibility** — fixed `zipfile._EXTRA_FIELD_STRUCT` removal, `CTkSegmentedButton` negative pad workaround
- **PatchMaker integration** — correct `make_patch()` kwargs, xdelta3 binary resolution, hidden console windows
- **Steam auth fix** — credentials only cleared after successful download, not on failure

## [2.10.0] - 2026-02-27

### Added

- **Per-DLC download telemetry** — `dlc_item_started` event emitted when each individual DLC begins downloading (includes `dlc_id`, `pack_type`, `size_bytes`)
- **Download retry/resume tracking** — `DLCDownloadTask` now exposes `retry_count` and `resumed` fields; `dlc_download_complete` event includes `resumed`, `retries`, `registered`, and `pack_type` metadata
- **DLC batch enrichment** — `dlc_download_started` includes full `dlc_ids` list and `speed_limit_mb`; `dlc_batch_complete` includes `total_retries` and `dlc_ids`
- **DLC download failure details** — `dlc_download_failed` event now includes `pack_type` and `retries` metadata
- **Pause duration tracking** — `dlc_download_paused` includes `elapsed_seconds`; `dlc_download_resumed` includes `pause_duration_seconds`
- **Cancel context** — `dlc_download_cancelled` event includes `completed_before_cancel` and `total_requested`
- **Patch download phase tracking** — new `patch_download_complete` event with `from_version`, `to_version`, `total_size_bytes`, `duration_seconds`, `avg_speed_bps`; separates download time from apply time
- **Patch apply phase tracking** — new `patch_apply_complete` event with `to_version`, `duration_seconds`, `dlc_count`
- **Update completed enrichment** — `update_completed` event now includes `from_version`, `steps`, `total_size_bytes`
- **DLC toggle detail tracking** — `dlc_changes_applied` event now includes `enabled_ids`, `disabled_ids`, `enabled_count`, `disabled_count` (replacing generic `dlcs_changed` count)
- **Supabase analytics views** — new `dlc_downloads_by_pack_type`, `patch_download_stats`, `patch_apply_stats`, `dlc_toggle_stats` views; `get_stats()` RPC updated with `dlc_by_pack_type`, `patch_download_stats`, `patch_apply_stats`, `dlc_toggle_stats`, `download_reliability` sections
- **Performance indexes** — new partial indexes on `events` table for `pack_type` and `patch_download_complete` queries

## [2.9.0] - 2026-02-27

### Fixed

- **Shutdown hang: `_on_close()` doesn't cancel downloads** — window close now sets `updater._cancel` to unblock background download threads before destroying
- **Indefinite hang: `_proceed.wait()` without timeout** — download pause/resume in both `patch/downloader.py` and `dlc/downloader.py` now loops with 5s timeout + cancel check
- **Indefinite hang: `_ask_question` event.wait()** — added 120s timeout to prevent permanent hang if GUI thread dies while background thread waits for user answer
- **Non-atomic GreenLuma install manifest** — `_save_install_manifest()` now writes via temp file + `os.replace()` with cleanup on failure
- **Non-atomic AppList writes** — `write_applist()` now writes each numbered `.txt` file atomically via temp + `os.replace()`
- **Non-atomic anadius_override.cfg writes** — all 3 write paths in `_ensure_language_override()` now use `_atomic_write_cfg()` helper
- **Learned hash DB corruption swallowed silently** — corrupt JSON now logged as warning, backed up to `.json.corrupt`, and starts fresh instead of silently ignoring
- **DLC uninstall: silent exception swallowing** — `except Exception: pass` in crack config disable replaced with logged warning; non-atomic `shutil.copy2` for Bin_LE replaced with `_atomic_write()`
- **Cache encoding: system-default file encoding** — `cache.py` `load()`/`save()` now explicitly use `encoding="utf-8"`
- **Telemetry HTTPS enforcement** — `set_base_url()` rejects non-HTTPS URLs
- **CDN auth token key validation** — `_refresh()` validates `token` field exists and is a non-empty string before accepting
- **Telemetry unbounded threads** — replaced per-call `Thread` spawning with bounded `ThreadPoolExecutor(max_workers=2)`
- **5 frames missing on_show busy guards** — `greenluma_frame`, `language_frame`, `unlocker_frame`, `events_frame`, `mods_frame` now skip `on_show()` refresh if already busy
- **Unused import** — removed `shutil` from `dlc/manager.py`

## [2.8.0] - 2026-02-27

### Fixed

- **Security: Path traversal in GreenLuma uninstall** — validate file paths stay within install directory using `resolve()` + `is_relative_to()`
- **Thread safety: ModManager registry mutations** — added `_registry_lock` to prevent concurrent dict modifications from background threads
- **CDN auth: silent token failure** — `get_token()` now raises `RuntimeError` on refresh failure instead of silently returning empty string; `CDNTokenAuth` adapter catches and skips gracefully
- **Downloader: double-checked locking race** — session now fully configured before publishing to shared `_session` attribute
- **LearnedHashDB thread safety** — all mutations (`save`, `add_version`, `merge`) now protected by `threading.Lock`
- **GUI blocking: GreenLuma subprocess on main thread** — `is_steam_running()` calls in `greenluma_frame.py` moved to background thread via `run_async()`
- **Diagnostics: validator constructor outside try block** — `GameValidator()` now inside the exception handler so failures don't silently leave `_validator_running` stuck
- **Version detection: false DEFINITIVE confidence** — single-sentinel matches no longer report `DEFINITIVE`; requires at least 2 matching sentinels
- **DLC config: non-atomic Bin_LE write** — replaced `shutil.copy2` with `_atomic_write()` for crash safety
- **Language frame: async race condition** — removed duplicate `_refresh_status()` call that raced with `_apply_language()`
- **Steam detection: missing HKCU registry lookup** — `_read_steam_path_from_registry()` now checks both `HKEY_LOCAL_MACHINE` and `HKEY_CURRENT_USER`
- **Language changer: registry key creation** — use `CreateKeyEx` instead of `OpenKey` so the key is created if it doesn't exist
- **Language changer: non-atomic appmanifest write** — Steam manifest updates now use temp file + `os.replace()`
- **DepotDownloader: HTTPS validation** — reject download URLs that don't use HTTPS
- **Contribution URLs: HTTPS enforcement** — both DLC and GreenLuma contribution endpoints now reject non-HTTPS URLs

## [2.7.1] - 2026-02-27

### Fixed

- **Release build crash**: CI workflows installed standard customtkinter from PyPI instead of the CustomTkinter fork, causing the exe to crash with `ImportError` on startup (missing `CTkChip`, `CTkSearchEntry`, `CTkSkeleton`, `CTkToolTip` widgets)
- Nav animation crash when `cget("fg_color")` returns a `(light, dark)` tuple instead of a hex string
- Removed dead `_base_fg` and `_hover_fg` variables from `InfoCard`

## [2.7.0] - 2026-02-27

### Added

- **Modern UI overhaul** — theme refresh with centralized color system, spacing scale, and button style presets
- **New CTk widgets** — `CTkSearchEntry` with debounce in DLC search, `CTkChip` filter chips, `CTkSkeleton` loading shimmer, `CTkToolTip` on action buttons
- **Sidebar icons** — Unicode icons for all navigation items with hover animations
- **Lazy frame creation** — frames created on first navigation instead of all at startup (faster cold start)
- **Pulse animation** on progress bar during updates
- Helper functions in `components.py`: `make_section_header`, `make_separator`, `make_action_button`, `make_status_row`, `make_log_section`, `make_browse_entry`

### Fixed

- Replaced 30+ hardcoded hex colors across 5 frame files with theme constants
- Applied `BUTTON_STYLES` presets (previously defined but never used)

## [2.6.1] - 2026-02-27

### Fixed

- 8 DLC download bugs: extraction safety, auth, path traversal, UI state

## [2.6.0] - 2026-02-27

### Added

- Admin dashboard enhancements: RPC analytics, time range filters, sparklines
- Improved UI responsiveness: debounced DLC search, upgraded CustomTkinter

### Fixed

- 6 bugs: telemetry blocking UI, response leak, data corruption, crashes
- 20 bugs: crashes, thread safety, security, memory leaks, data integrity
- 5 bugs: path traversal, crash in backup progress, button stuck disabled
- Dashboard `feature_usage` bug

## [2.5.1] - 2026-02-26

### Added

- Event Rewards Unlocker for live-event reward claiming
- GitHub Pages event unlocker page
- Wonderland Playroom and Yard Charm kits to DLC catalog

### Fixed

- DLC Unlocker missing from exe: bundle `tools/DLC Unlocker for Windows` in spec
- CDN 403 error: derive SSRF hostname from `SEEDBOX_BASE_URL` dynamically
- CDN worker crash: redirect mode and top-level error handler
