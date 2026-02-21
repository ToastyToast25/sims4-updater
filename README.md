# Sims 4 Updater

A standalone Windows application for updating, managing, and maintaining cracked installations of The Sims 4. Detects your installed version, downloads and applies binary delta patches, manages DLC toggles across 5 crack config formats, integrates with GreenLuma 2025 for Steam DLC unlocking, handles language settings, and manages mods — all from a single portable executable with a modern dark-mode GUI.

Built on top of anadius's patcher engine using xdelta3 binary delta patching.

---

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
  - [GUI Mode](#gui-mode)
  - [CLI Mode](#cli-mode)
- [Hosting Patches](#hosting-patches)
  - [Manifest Format](#manifest-format)
  - [Creating Patches](#creating-patches)
  - [Version Fingerprints](#version-fingerprints)
  - [Crowd-Sourced Hash Reporting](#crowd-sourced-hash-reporting)
- [Features](#features)
  - [Version Detection](#version-detection)
  - [Auto-Learning Hash System](#auto-learning-hash-system)
  - [Update Pipeline](#update-pipeline)
  - [DLC Management](#dlc-management)
  - [GreenLuma Integration](#greenluma-integration)
  - [Language Changer](#language-changer)
  - [Configuration](#configuration)
- [Building from Source](#building-from-source)
- [Project Structure](#project-structure)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## Installation

Download the latest `Sims4Updater.exe` from [Releases](../../releases). No installation required — it's a single portable executable.

### Requirements

- Windows 10/11 (64-bit)
- An existing installation of The Sims 4

### From source

```bash
git clone https://github.com/ToastyToast25/sims4-updater.git
cd sims4-updater
pip install -r requirements.txt
PYTHONPATH=src python -m sims4_updater
```

---

## Usage

### GUI Mode

Double-click `Sims4Updater.exe` or run it with no arguments. The GUI provides:

- **Home** — Displays detected game directory, installed version, latest available version, and DLC count. One-click "Check for Updates" / "Update Now" button.
- **DLCs** — Scrollable checkbox list of all 103 DLCs grouped by type (Expansions, Game Packs, Stuff Packs, Kits). Auto-toggle, per-DLC downloads, Steam pricing, and GreenLuma readiness indicators.
- **DLC Packer** — Pack installed DLCs into distributable ZIP archives or import DLC archives from others.
- **DLC Unlocker** — Install/uninstall the EA DLC Unlocker with status detection and admin elevation.
- **GreenLuma** — Install/uninstall GreenLuma 2025, apply LUA manifests, verify configuration, manage AppList, and launch Steam via DLLInjector.
- **DLC Downloader** — Download DLC content from Steam depots using DepotDownloader with progress tracking.
- **Language** — Change game language with Steam depot-based language file downloads.
- **Mods** — Manage game modifications.
- **Settings** — Configure game directory, patch manifest URL, GreenLuma paths (Steam, archive, LUA, manifests), language, and theme.
- **Progress** — Download and patch progress bars, scrollable log, and cancel button during updates.

### CLI Mode

```text
Sims4Updater.exe <command> [options]
```

| Command | Description |
|---------|-------------|
| `status [game_dir]` | Show game directory, installed version, language, crack config, and DLC summary |
| `detect <game_dir>` | Detect the installed version by hashing sentinel files |
| `check [game_dir]` | Check for available updates against the manifest |
| `manifest <url\|file>` | Inspect a manifest file or URL — show patches, sizes, versions |
| `dlc <game_dir>` | Show all DLC states (enabled/disabled, installed/missing) |
| `dlc-auto <game_dir>` | Auto-enable installed DLCs and disable missing ones |
| `learn <game_dir> <version>` | Manually teach the updater a version's file hashes |
| `language` | Show current language and all available languages |
| `language <code> [--game-dir DIR]` | Set the game language (registry + config files) |

#### Examples

```bash
# Auto-detect game and show status
Sims4Updater.exe status

# Detect version of a specific install
Sims4Updater.exe detect "D:\Games\The Sims 4"

# Check for updates using a custom manifest
Sims4Updater.exe check --manifest-url https://example.com/manifest.json

# Auto-toggle DLCs after manual patching
Sims4Updater.exe dlc-auto "D:\Games\The Sims 4"

# Teach the updater your current version's hashes
Sims4Updater.exe learn "D:\Games\The Sims 4" 1.121.372.1020

# Change language to French
Sims4Updater.exe language fr_FR --game-dir "D:\Games\The Sims 4"
```

---

## Hosting Patches

The updater is **backend-agnostic** — it only needs a single manifest URL. Patch files can be hosted anywhere: a web server, CDN, cloud storage bucket, file host, or even a local network share. To switch hosts, just update the URLs in the manifest.

### Manifest Format

Host a JSON file at any URL. Configure this URL in the updater's Settings or via `--manifest-url`.

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
          "url": "https://your-host.com/patches/ts4_1.119_to_1.120.patch",
          "size": 524288000,
          "md5": "ABC123DEF456..."
        },
        {
          "url": "https://your-host.com/patches/ts4_1.119_to_1.120_part2.patch",
          "size": 314572800,
          "md5": "789GHI012JKL..."
        }
      ],
      "crack": {
        "url": "https://your-host.com/cracks/crack_1.120.rar",
        "size": 1048576,
        "md5": "MNO345PQR678..."
      }
    },
    {
      "from": "1.120.250.1020",
      "to": "1.121.372.1020",
      "files": [
        {
          "url": "https://your-host.com/patches/ts4_1.120_to_1.121.patch",
          "size": 412000000,
          "md5": "STU901VWX234..."
        }
      ]
    }
  ],

  "new_dlcs": [
    {"id": "EP15", "name": "New Expansion Pack"},
    {"id": "GP12", "name": "New Game Pack"}
  ],

  "fingerprints": {
    "1.121.372.1020": {
      "Game/Bin/TS4_x64.exe": "1E45D4A27DC56134689A306FA92EF115",
      "Game/Bin/Default.ini": "3000759841368CC356E2996B98F33610",
      "delta/EP01/version.ini": "43BF3EAABEBCC513615F5F581567DFC9"
    }
  },

  "fingerprints_url": "https://your-api.com/fingerprints.json",
  "report_url": "https://your-api.com/report"
}
```

#### Field reference

| Field | Required | Description |
|-------|----------|-------------|
| `latest` | Yes | The newest version with patches available |
| `game_latest` | No | The actual latest game version released by EA (shown to users when ahead of `latest`) |
| `game_latest_date` | No | Release date of `game_latest` (displayed in the GUI) |
| `patches` | Yes | Array of patch entries |
| `patches[].from` | Yes | Source version |
| `patches[].to` | Yes | Target version |
| `patches[].files` | Yes | Array of downloadable patch archives (supports multi-part) |
| `patches[].files[].url` | Yes | Direct download URL |
| `patches[].files[].size` | Yes | File size in bytes (for progress bars) |
| `patches[].files[].md5` | Yes | MD5 checksum for integrity verification |
| `patches[].crack` | No | Optional crack archive for this version step |
| `new_dlcs` | No | Array of DLCs announced but not yet patchable (`{"id": "...", "name": "..."}`) |
| `fingerprints` | No | Version hashes for auto-detection (see below) |
| `fingerprints_url` | No | URL to a crowd-sourced fingerprints JSON |
| `report_url` | No | URL where clients POST learned hashes |

#### Multi-step updates

The updater uses BFS pathfinding to find the shortest chain of patches from the user's current version to `latest`. If a direct patch doesn't exist, it chains intermediate steps automatically. Among equal-length paths, it picks the one with the smallest total download size.

### Creating Patches

Patches are created using the patcher tool (included as a sibling `patcher/` directory), which uses xdelta3 to produce binary delta files. You need both the **source version** and **target version** of the game files on your machine.

#### Step-by-step: creating a patch

1. **Obtain both game versions.** You need a clean copy of the old version and the new version. The patcher compares them file by file and generates a binary delta.

2. **Run the patcher tool** to create the delta patch:

   ```bash
   cd patcher
   python patcher.py create --old "D:\TS4_1.119" --new "D:\TS4_1.120" --output ts4_1.119_to_1.120.patch
   ```

3. **Hash the sentinel files** for the new version so users can auto-detect it:

   ```bash
   Sims4Updater.exe learn "D:\TS4_1.120" 1.120.250.1020
   ```

   This outputs MD5 hashes for the 3 sentinel files:

   - `Game/Bin/TS4_x64.exe` — Main executable, changes every update
   - `Game/Bin/Default.ini` — Config with version number embedded
   - `delta/EP01/version.ini` — DLC version marker

4. **Get the file size and MD5** of the patch archive:

   ```bash
   certutil -hashfile ts4_1.119_to_1.120.patch MD5
   ```

5. **Upload the patch file** to your hosting provider (see below).

6. **Update the manifest** with the new patch entry and fingerprints.

#### When a new game update comes out

1. Update the manifest's `game_latest` field immediately — users will see "patch coming soon" in the GUI.
2. Create the patch archive from the old version to the new version.
3. Upload the patch files to your hosting.
4. Add the patch entry to the manifest and set `latest` to the new version.
5. Users will now see "Update Now" on their next check.

#### When new DLC is released

1. Add the DLC to the manifest's `new_dlcs` array — users will see it in the DLC list as "pending".
2. Once the patch is created and uploaded, move the DLC from `new_dlcs` to the regular patch.
3. Update `data/dlc_catalog.json` in the repo and rebuild the exe for the DLC to have proper localized names.

### Hosting with Cloudflare (Recommended)

Cloudflare's free tier provides everything needed for global patch distribution with minimal cost.

#### Hosting the manifest and patch files

##### Option A: Cloudflare R2 (object storage) — recommended for large files

R2 has no egress fees (unlike S3/GCS), making it ideal for large game patches.

1. Create a Cloudflare account and enable R2 in the dashboard.
2. Create an R2 bucket (e.g., `ts4-patches`).
3. Connect a custom domain or use the R2 public access URL.
4. Upload your patch files to the bucket:

   ```bash
   # Using rclone (recommended for large files)
   rclone copy ts4_1.119_to_1.120.patch r2:ts4-patches/patches/

   # Or use the Cloudflare dashboard upload
   ```

5. Upload your `manifest.json` to the same bucket:

   ```bash
   rclone copy manifest.json r2:ts4-patches/
   ```

6. Your manifest URL will be: `https://your-domain.com/manifest.json`

##### Option B: Cloudflare Pages (static hosting) — good for manifest only

If your patch files are hosted elsewhere (e.g., Google Drive, Mega, GitHub Releases), you can host just the manifest on Cloudflare Pages:

1. Create a GitHub repo with your `manifest.json`.
2. Connect it to Cloudflare Pages.
3. Every push automatically deploys the updated manifest.

#### Hosting the fingerprint API (crowd-sourced hashes)

Use a Cloudflare Worker + KV to receive hash reports and serve validated fingerprints. The free tier handles 100K requests/day.

**1. Create a KV namespace** in the Cloudflare dashboard called `TS4_FINGERPRINTS`.

**2. Create a Worker** (`ts4-fingerprints-worker`) with this code:

```javascript
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // GET /fingerprints.json — serve validated fingerprints
    if (request.method === "GET" && url.pathname === "/fingerprints.json") {
      const data = await env.TS4_FINGERPRINTS.get("validated", "json") || {};
      return Response.json({ versions: data });
    }

    // POST /report — receive hash reports from clients
    if (request.method === "POST" && url.pathname === "/report") {
      try {
        const body = await request.json();
        const { version, hashes } = body;
        if (!version || !hashes) {
          return new Response("Missing version or hashes", { status: 400 });
        }

        // Store reports per version with IP-based dedup
        const ip = request.headers.get("CF-Connecting-IP") || "unknown";
        const reportKey = `reports:${version}`;
        const existing = await env.TS4_FINGERPRINTS.get(reportKey, "json") || [];

        // Deduplicate by IP
        if (existing.some(r => r.ip === ip)) {
          return Response.json({ status: "already_reported" });
        }

        existing.push({ ip, hashes, ts: Date.now() });
        await env.TS4_FINGERPRINTS.put(reportKey, JSON.stringify(existing));

        // Auto-validate after 3 matching reports
        if (existing.length >= 3) {
          const hashStrings = existing.map(r => JSON.stringify(r.hashes));
          const counts = {};
          hashStrings.forEach(h => counts[h] = (counts[h] || 0) + 1);
          const majority = Object.entries(counts).find(([, c]) => c >= 3);

          if (majority) {
            const validated = await env.TS4_FINGERPRINTS.get("validated", "json") || {};
            validated[version] = JSON.parse(majority[0]);
            await env.TS4_FINGERPRINTS.put("validated", JSON.stringify(validated));
          }
        }

        return Response.json({ status: "ok", reports: existing.length });
      } catch (e) {
        return new Response("Invalid request", { status: 400 });
      }
    }

    return new Response("Not found", { status: 404 });
  }
};
```

**3. Bind the KV namespace** to the Worker in the Cloudflare dashboard (Settings > Variables > KV Namespace Bindings > variable name: `TS4_FINGERPRINTS`).

**4. Deploy** and set the URLs in your manifest:

```json
{
  "fingerprints_url": "https://ts4-fingerprints-worker.your-account.workers.dev/fingerprints.json",
  "report_url": "https://ts4-fingerprints-worker.your-account.workers.dev/report"
}
```

#### Cost

| Service | Free tier | Notes |
|---------|-----------|-------|
| Cloudflare R2 | 10 GB storage, 10M reads/mo | No egress fees |
| Cloudflare Workers | 100K requests/day | Fingerprint API |
| Cloudflare KV | 100K reads/day, 1K writes/day | Hash storage |
| Cloudflare Pages | Unlimited bandwidth | Manifest hosting |

For most Sims 4 update distributions, the free tier is more than sufficient.

### Version Fingerprints

When you create a patch, you have access to the target version's game files. Hash the 3 sentinel files and include them in the manifest's `fingerprints` section. This lets all users auto-detect the new version immediately, even before they've applied the patch themselves.

```bash
# Quick way to get the hashes (on the machine with the target version):
Sims4Updater.exe learn "D:\Games\The Sims 4" 1.121.372.1020
```

This outputs the MD5 hashes — copy them into your manifest's `fingerprints` field.

### Crowd-Sourced Hash Reporting

For fully automatic hash distribution across all users, set up the two optional endpoints described in the Cloudflare Worker section above:

1. **`report_url`** — Receives POST requests with `{"version": "...", "hashes": {...}}` from clients after successful patches or `learn` commands. The Worker validates by requiring 3+ matching reports from different IPs.

2. **`fingerprints_url`** — Serves a JSON file of validated hashes. The updater fetches this on every manifest check and merges new hashes into each user's local database.

Example response for `fingerprints_url`:

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

---

## Features

### Version Detection

Identifies the installed game version by hashing 3 sentinel files and matching against a database of 135+ known versions. Detection takes under 2 seconds on SSD.

**How it works:**

1. Hashes `Game/Bin/TS4_x64.exe`, `Game/Bin/Default.ini`, and `delta/EP01/version.ini` using MD5.
2. Looks up the hash combination in the version database.
3. Returns a confidence level:
   - **Definitive** — unique match on all sentinels (1 version matches)
   - **Probable** — matched but ambiguous (multiple versions share some hashes)
   - **Unknown** — no match found

**Game directory auto-detection:** Checks the Windows registry (`HKLM/HKCU\SOFTWARE\Maxis\The Sims 4`) and common install paths automatically.

### Auto-Learning Hash System

The version database stays up to date through 4 complementary sources:

| Source | When it runs | Scope |
|--------|-------------|-------|
| **Bundled database** | Always loaded | 135 versions shipped with the exe |
| **Manifest fingerprints** | On update check | Hashes you include in the manifest JSON |
| **Self-learning** | After successful patch | Hashes sentinel files automatically, saves locally |
| **Crowd-sourced** | On update check | Fetches validated hashes from `fingerprints_url` |

Learned hashes are stored at `%LocalAppData%\ToastyToast25\sims4_updater\learned_hashes.json` and persist across sessions. The local database takes priority over the bundled database for overlapping versions.

After every successful patch, the updater automatically hashes the sentinel files, saves them locally, and reports them to the `report_url` (if configured) as a fire-and-forget background request.

### Update Pipeline

The full update process runs in 5 stages:

1. **Detect** — Find game directory, hash sentinels, identify installed version
2. **Check** — Fetch manifest, compare versions, plan update path (BFS shortest chain)
3. **Download** — Stream patch files with resume support, MD5 verification, and cancellation
4. **Patch** — Apply binary delta patches via the patcher engine (xdelta3)
5. **Finalize** — Learn new version hashes, auto-toggle DLCs, update settings

Downloads support HTTP Range headers for resuming interrupted transfers. Each file is verified against its MD5 checksum. The download can be cancelled at any point.

**Patch-pending awareness:** When the manifest includes `game_latest` (the actual EA release version) ahead of `latest` (the latest patchable version), the GUI shows a "patch coming soon" banner and disables the update button. Users are informed that a new version exists without being able to attempt an update that would fail. Once the maintainer creates the patch and updates the manifest, the update button automatically becomes available on the next check.

### DLC Management

Manages DLC enable/disable state across **5 crack config formats**:

| Format | Config File | Toggle Method |
|--------|------------|---------------|
| **RldOrigin** | `RldOrigin.ini` | Comment prefix (`;`) |
| **Codex** | `codex.cfg` | Group value swap |
| **Rune** | `rune.ini` | Underscore suffix on section names |
| **Anadius Simple** | `anadius.cfg` | Comment prefix (`//`) |
| **Anadius Codex-like** | `anadius.cfg` | Group value swap |

The format is auto-detected by scanning for config files in the game directory (tries paths in reverse priority order).

**Auto-toggle** scans the game directory for installed DLC folders, enables DLCs that are present, and disables those that are missing. Config changes are mirrored to the `Bin_LE` (Legacy Edition) variant automatically.

The DLC catalog contains **103 DLCs** with localized names in 18 languages, categorized as Expansions, Game Packs, Stuff Packs, Kits, and Free Packs.

### GreenLuma Integration

Full integration with [GreenLuma 2025](https://cs.rin.ru/forum/viewtopic.php?f=29&t=103825) for Steam DLC unlocking. The GreenLuma tab provides:

- **Install/Uninstall** — Extract GreenLuma from a `.7z` archive into the Steam directory (normal or stealth mode). Tracks installed files for clean uninstall.
- **Apply LUA Manifest** — Parse `.lua` manifest files to automatically add depot decryption keys to `config.vdf`, copy `.manifest` files to `depotcache`, and populate the `AppList` directory.
- **Verify Configuration** — Cross-reference keys, manifests, and AppList entries against a LUA file to identify missing or mismatched components.
- **Fix AppList** — Remove duplicates and add missing DLC entries to the numbered `AppList/*.txt` files.
- **Launch via GreenLuma** — Launch Steam through `DLLInjector.exe` with automatic Steam-restart dialog if Steam is already running.
- **DLC Readiness Indicators** — The DLCs tab shows green/yellow "GL" pill badges next to each DLC indicating whether AppList, decryption key, and manifest are all present.

**Backend modules:** `greenluma/steam.py` (Steam detection), `greenluma/installer.py` (install/uninstall/launch), `greenluma/applist.py` (AppList management), `greenluma/config_vdf.py` (depot key management), `greenluma/lua_parser.py` (LUA parsing), `greenluma/manifest_cache.py` (depotcache), `greenluma/orchestrator.py` (high-level operations).

### Language Changer

Supports 18 languages with native display names:

| Code | Language | Code | Language |
|------|----------|------|----------|
| `cs_CZ` | Cestina | `nl_NL` | Nederlands |
| `da_DK` | Dansk | `no_NO` | Norsk |
| `de_DE` | Deutsch | `pl_PL` | Polski |
| `en_US` | English | `pt_BR` | Portugues (Brasil) |
| `es_ES` | Espanol | `fi_FI` | Suomi |
| `fr_FR` | Francais | `sv_SE` | Svenska |
| `it_IT` | Italiano | `ru_RU` | Russian |
| `ja_JP` | Japanese | `zh_TW` | Traditional Chinese |
| `ko_KR` | Korean | `zh_CN` | Simplified Chinese |

Sets the `Locale` registry value and updates `RldOrigin.ini` config files in both the main and Legacy Edition directories.

### Configuration

Persistent settings stored at `%LocalAppData%\ToastyToast25\sims4_updater\settings.json`:

| Setting | Description |
|---------|-------------|
| `game_path` | Path to The Sims 4 installation |
| `manifest_url` | URL to the patch manifest JSON |
| `language` | Selected game language |
| `theme` | GUI theme (dark / light / system) |
| `check_updates_on_start` | Auto-check for updates on launch |
| `last_known_version` | Last detected version (cached) |
| `enabled_dlcs` | List of enabled DLC IDs |
| `steam_path` | Steam installation directory |
| `steam_username` | Steam username for depot downloads |
| `greenluma_archive_path` | Path to GreenLuma `.7z` archive |
| `greenluma_lua_path` | Path to `.lua` manifest file |
| `greenluma_manifest_dir` | Directory containing `.manifest` files |
| `greenluma_auto_backup` | Auto-backup config.vdf/AppList before changes |
| `download_concurrency` | Number of parallel download segments |
| `download_speed_limit` | Download speed cap in MB/s (0 = unlimited) |

The Settings tab is organized into two cards: **Game & Updates** (game path, patch manifest URL, language, theme) and **GreenLuma** (Steam path, archive, LUA manifest, manifest directory, auto-backup).

---

## Building from Source

### Build Requirements

- Python 3.12+
- The `patcher/` directory placed as a sibling (i.e. `../patcher/` relative to this repo)

### Setup

```bash
pip install -r requirements-dev.txt
```

### Build

```bash
pyinstaller --clean --noconfirm Sims4Updater.spec
```

The executable is output to `dist/Sims4Updater.exe`. It bundles:

- CustomTkinter GUI assets
- xdelta3 binaries (x64 and x86)
- unrar executable
- Version hash database (135+ versions)
- DLC catalog (103 DLCs)
- Bundled mod resources

### CI/CD

Pushes to `main` trigger a GitHub Actions build. Tagged pushes (`v*`) automatically create a GitHub Release with the built executable.

---

## Project Structure

```text
sims4-updater/
├── src/sims4_updater/
│   ├── __main__.py              # CLI entry point + GUI launcher
│   ├── constants.py             # Paths, URLs, sentinel files
│   ├── config.py                # Persistent settings
│   ├── updater.py               # Main updater engine (Patcher subclass)
│   ├── core/
│   │   ├── version_detect.py    # Hash-based version detection
│   │   ├── learned_hashes.py    # Local writable hash database
│   │   ├── self_update.py       # GitHub Releases self-update pipeline
│   │   ├── unlocker.py          # EA DLC Unlocker install/uninstall/status
│   │   ├── rate_limiter.py      # Download rate limiting
│   │   ├── exceptions.py        # Exception hierarchy
│   │   ├── files.py             # File hashing, copying utilities
│   │   ├── myzipfile.py         # ZIP with LZMA metadata
│   │   ├── cache.py             # JSON cache with atomic writes
│   │   ├── subprocess_.py       # Subprocess with Ctrl+C handling
│   │   └── utils.py             # Size parsing utilities
│   ├── patch/
│   │   ├── manifest.py          # Manifest dataclasses + parser
│   │   ├── planner.py           # BFS update path planner
│   │   ├── downloader.py        # HTTP download with resume + MD5
│   │   └── client.py            # Patch client orchestrator
│   ├── dlc/
│   │   ├── catalog.py           # DLC info + localized names
│   │   ├── formats.py           # 5 crack config format adapters
│   │   ├── manager.py           # DLC state management
│   │   ├── downloader.py        # DLC download/extract/register pipeline
│   │   ├── packer.py            # DLC Packer — ZIP creation + manifest gen
│   │   └── steam.py             # Steam price cache + batch fetching
│   ├── greenluma/
│   │   ├── steam.py             # Steam path detection, process checks, SteamInfo
│   │   ├── installer.py         # GreenLuma install/uninstall/launch, install manifest
│   │   ├── applist.py           # AppList (numbered .txt files) read/write/backup
│   │   ├── config_vdf.py        # Steam config.vdf parsing, depot key management
│   │   ├── lua_parser.py        # LUA manifest file parser
│   │   ├── manifest_cache.py    # depotcache .manifest file management
│   │   └── orchestrator.py      # High-level GL operations (readiness, apply, verify)
│   ├── language/
│   │   ├── changer.py           # Registry + INI language setter
│   │   ├── downloader.py        # Steam depot-based language file downloads
│   │   ├── packer.py            # Language file packing
│   │   └── steam.py             # Steam language depot configuration
│   ├── mods/
│   │   └── manager.py           # Mod management
│   └── gui/
│       ├── app.py               # Main CustomTkinter window
│       ├── theme.py             # Colors, fonts, dimensions
│       ├── components.py        # InfoCard, StatusBadge, ToastNotification
│       ├── animations.py        # Animator, color interpolation, easing
│       └── frames/
│           ├── home_frame.py    # Version display, update button
│           ├── dlc_frame.py     # DLC catalog, filters, GL readiness
│           ├── packer_frame.py  # Pack/import DLC archives
│           ├── unlocker_frame.py # EA DLC Unlocker management
│           ├── greenluma_frame.py # GreenLuma install/apply/verify
│           ├── downloader_frame.py # DLC download interface
│           ├── language_frame.py # Language management
│           ├── mods_frame.py    # Mod management
│           ├── settings_frame.py # Configuration UI (2-card layout)
│           └── progress_frame.py # Progress bars, log, cancel
├── data/
│   ├── version_hashes.json      # Bundled version fingerprints
│   └── dlc_catalog.json         # DLC database with names
├── mods/                        # Bundled mod resources
├── Sims4Updater.spec            # PyInstaller build config
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Dev/build dependencies
└── .github/workflows/build.yml  # CI/CD pipeline
```

---

## Documentation

Full technical documentation is available in the `Documentation/` directory:

| Document | Scope |
| -------- | ----- |
| [User Guide](Documentation/User_Guide.md) | End-user reference — all tabs, CLI, troubleshooting, FAQ |
| [Architecture & Developer Guide](Documentation/Architecture_and_Developer_Guide.md) | 3-layer architecture, module map, threading, GUI patterns, build system |
| [Update & Patching System](Documentation/Update_and_Patching_System.md) | Version detection, manifest format, BFS planning, downloads, hash learning |
| [DLC Management System](Documentation/DLC_Management_System.md) | DLC catalog, 5 crack formats, download pipeline, unlocker, Steam pricing, GL readiness |
| [DLC Packer & Distribution](Documentation/DLC_Packer_and_Distribution.md) | Packer class, ZIP format, manifest generation, import flow |
| [GreenLuma Integration](Documentation/GreenLuma_Integration.md) | Steam detection, AppList, config.vdf keys, LUA parsing, manifest cache, orchestrator |

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
