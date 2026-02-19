# Sims 4 Updater

A standalone Windows application for updating, managing, and maintaining cracked installations of The Sims 4. Detects your installed version, downloads and applies binary delta patches, manages DLC toggles across 5 crack config formats, and handles language settings — all from a single 21 MB executable with a modern dark-mode GUI.

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
- **DLCs** — Scrollable checkbox list of all 103 DLCs grouped by type (Expansions, Game Packs, Stuff Packs, Kits). Auto-toggle to enable installed DLCs and disable missing ones.
- **Settings** — Configure game directory, manifest URL, language, and theme (dark/light/system).
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
| `latest` | Yes | The newest available version string |
| `patches` | Yes | Array of patch entries |
| `patches[].from` | Yes | Source version |
| `patches[].to` | Yes | Target version |
| `patches[].files` | Yes | Array of downloadable patch archives (supports multi-part) |
| `patches[].files[].url` | Yes | Direct download URL |
| `patches[].files[].size` | Yes | File size in bytes (for progress bars) |
| `patches[].files[].md5` | Yes | MD5 checksum for integrity verification |
| `patches[].crack` | No | Optional crack archive for this version step |
| `fingerprints` | No | Version hashes for auto-detection (see below) |
| `fingerprints_url` | No | URL to a crowd-sourced fingerprints JSON |
| `report_url` | No | URL where clients POST learned hashes |

#### Multi-step updates

The updater uses BFS pathfinding to find the shortest chain of patches from the user's current version to `latest`. If a direct patch doesn't exist, it chains intermediate steps automatically. Among equal-length paths, it picks the one with the smallest total download size.

### Creating Patches

Patches are created using the patcher tool (included as a sibling `patcher/` directory), which uses xdelta3 to produce binary delta files. You need both the source and target game versions to create a patch.

Once created, upload the patch files to any HTTP-accessible location and add the corresponding entry to your manifest.

### Version Fingerprints

When you create a patch, you have access to the target version's game files. Hash the 3 sentinel files and include them in the manifest's `fingerprints` section:

| Sentinel File | Purpose |
|---------------|---------|
| `Game/Bin/TS4_x64.exe` | Main executable — changes every update |
| `Game/Bin/Default.ini` | Config with version number embedded |
| `delta/EP01/version.ini` | DLC version marker |

```bash
# Quick way to get the hashes (on the machine with the target version):
Sims4Updater.exe learn "D:\Games\The Sims 4" 1.121.372.1020
```

This outputs the MD5 hashes — copy them into your manifest's `fingerprints` field.

### Crowd-Sourced Hash Reporting

For fully automatic hash distribution across all users, set up two optional endpoints:

1. **`report_url`** — Receives POST requests with `{"version": "...", "hashes": {...}}` from clients after successful patches or `learn` commands. Implement consensus validation (accept only after 3+ matching reports from different IPs).

2. **`fingerprints_url`** — Serves a JSON file of validated hashes. The updater fetches this on every manifest check and merges new hashes into each user's local database.

A Cloudflare Worker with KV storage (free tier: 100K requests/day) is sufficient for global scale. Example response for `fingerprints_url`:

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

Learned hashes are stored at `%LocalAppData%\anadius\sims4_updater\learned_hashes.json` and persist across sessions. The local database takes priority over the bundled database for overlapping versions.

After every successful patch, the updater automatically hashes the sentinel files, saves them locally, and reports them to the `report_url` (if configured) as a fire-and-forget background request.

### Update Pipeline

The full update process runs in 5 stages:

1. **Detect** — Find game directory, hash sentinels, identify installed version
2. **Check** — Fetch manifest, compare versions, plan update path (BFS shortest chain)
3. **Download** — Stream patch files with resume support, MD5 verification, and cancellation
4. **Patch** — Apply binary delta patches via the patcher engine (xdelta3)
5. **Finalize** — Learn new version hashes, auto-toggle DLCs, update settings

Downloads support HTTP Range headers for resuming interrupted transfers. Each file is verified against its MD5 checksum. The download can be cancelled at any point.

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

Persistent settings stored at `%LocalAppData%\anadius\sims4_updater\settings.json`:

| Setting | Description |
|---------|-------------|
| `game_path` | Path to The Sims 4 installation |
| `manifest_url` | URL to the patch manifest JSON |
| `language` | Selected game language |
| `theme` | GUI theme (dark / light / system) |
| `check_updates_on_start` | Auto-check for updates on launch |
| `last_known_version` | Last detected version (cached) |
| `enabled_dlcs` | List of enabled DLC IDs |

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
pyinstaller --clean --noconfirm sims4_updater.spec
```

The executable is output to `dist/Sims4Updater.exe` (~21 MB). It bundles:

- CustomTkinter GUI assets
- xdelta3 binaries (x64 and x86)
- unrar executable
- Version hash database (135 versions)
- DLC catalog (103 DLCs)

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
│   │   └── manager.py           # DLC state management
│   ├── language/
│   │   └── changer.py           # Registry + INI language setter
│   └── gui/
│       ├── app.py               # Main CustomTkinter window
│       ├── theme.py             # Colors, fonts, dimensions
│       └── frames/
│           ├── home_frame.py    # Version display, update button
│           ├── dlc_frame.py     # DLC checkboxes
│           ├── settings_frame.py # Configuration UI
│           └── progress_frame.py # Progress bars, log, cancel
├── data/
│   ├── version_hashes.json      # Bundled version fingerprints
│   └── dlc_catalog.json         # DLC database with names
├── sims4_updater.spec           # PyInstaller build config
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Dev/build dependencies
└── .github/workflows/build.yml  # CI/CD pipeline
```

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
