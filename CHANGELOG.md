# Changelog

All notable changes to The Sims 4 Updater will be documented in this file.

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
