# Sims 4 Updater — User Guide

**Application:** Sims 4 Updater (TS4 Updater)
**Version:** 2.0.8
**Author:** ToastyToast25
**Platform:** Windows 10/11 (64-bit)

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Requirements](#2-system-requirements)
3. [Installation and First Launch](#3-installation-and-first-launch)
   - 3.1 [Downloading the Application](#31-downloading-the-application)
   - 3.2 [First Launch and Game Detection](#32-first-launch-and-game-detection)
   - 3.3 [Application Data Location](#33-application-data-location)
4. [Interface Overview](#4-interface-overview)
   - 4.1 [Sidebar Navigation](#41-sidebar-navigation)
   - 4.2 [Status Badges](#42-status-badges)
   - 4.3 [Toast Notifications](#43-toast-notifications)
5. [Home Tab](#5-home-tab)
   - 5.1 [Information Cards](#51-information-cards)
   - 5.2 [DLC Pricing Summary](#52-dlc-pricing-summary)
   - 5.3 [Checking for Updates](#53-checking-for-updates)
   - 5.4 [Applying Game Updates](#54-applying-game-updates)
   - 5.5 [Updater Self-Update Banner](#55-updater-self-update-banner)
   - 5.6 [Patch-Pending State](#56-patch-pending-state)
   - 5.7 [New DLC Announcements](#57-new-dlc-announcements)
6. [DLCs Tab](#6-dlcs-tab)
   - 6.1 [DLC List Layout](#61-dlc-list-layout)
   - 6.2 [Status Pills Explained](#62-status-pills-explained)
   - 6.3 [Collapsible Section Headers](#63-collapsible-section-headers)
   - 6.4 [Expanding DLC Descriptions](#64-expanding-dlc-descriptions)
   - 6.5 [Steam Pricing Display](#65-steam-pricing-display)
   - 6.6 [Search and Filter Chips](#66-search-and-filter-chips)
   - 6.7 [Downloading Missing DLCs](#67-downloading-missing-dlcs)
   - 6.8 [Auto-Toggle](#68-auto-toggle)
   - 6.9 [Apply Changes](#69-apply-changes)
   - 6.10 [Status Bar](#610-status-bar)
7. [DLC Packer Tab](#7-dlc-packer-tab)
   - 7.1 [Purpose and Use Cases](#71-purpose-and-use-cases)
   - 7.2 [Selecting DLCs to Pack](#72-selecting-dlcs-to-pack)
   - 7.3 [Packing DLCs](#73-packing-dlcs)
   - 7.4 [Disk Space Warnings](#74-disk-space-warnings)
   - 7.5 [Overwrite Protection](#75-overwrite-protection)
   - 7.6 [Auto Manifest Generation](#76-auto-manifest-generation)
   - 7.7 [Importing Archives](#77-importing-archives)
   - 7.8 [Output Folder](#78-output-folder)
8. [Unlocker Tab](#8-unlocker-tab)
   - 8.1 [What Is the EA DLC Unlocker](#81-what-is-the-ea-dlc-unlocker)
   - 8.2 [Status Display](#82-status-display)
   - 8.3 [Installing the Unlocker](#83-installing-the-unlocker)
   - 8.4 [Uninstalling the Unlocker](#84-uninstalling-the-unlocker)
   - 8.5 [Activity Log](#85-activity-log)
   - 8.6 [Open Configs Button](#86-open-configs-button)
9. [Settings Tab](#9-settings-tab)
   - 9.1 [Game Directory](#91-game-directory)
   - 9.2 [Manifest URL](#92-manifest-url)
   - 9.3 [Language](#93-language)
   - 9.4 [Theme](#94-theme)
   - 9.5 [Check for Updates on Startup](#95-check-for-updates-on-startup)
   - 9.6 [Saving Settings](#96-saving-settings)
10. [Command-Line Interface (CLI)](#10-command-line-interface-cli)
    - 10.1 [When to Use the CLI](#101-when-to-use-the-cli)
    - 10.2 [Available Commands](#102-available-commands)
    - 10.3 [CLI Examples](#103-cli-examples)
11. [Crack Config Format Support](#11-crack-config-format-support)
12. [Version Detection System](#12-version-detection-system)
13. [Supported Languages](#13-supported-languages)
14. [Troubleshooting](#14-troubleshooting)
    - 14.1 [Game Directory Not Detected](#141-game-directory-not-detected)
    - 14.2 [Version Shows as Unknown](#142-version-shows-as-unknown)
    - 14.3 [Update Button Remains Disabled](#143-update-button-remains-disabled)
    - 14.4 [DLCs Not Showing Correct Status](#144-dlcs-not-showing-correct-status)
    - 14.5 [Unlocker Installation Fails](#145-unlocker-installation-fails)
    - 14.6 [Downloads Failing or Stalling](#146-downloads-failing-or-stalling)
    - 14.7 [Settings Not Saving](#147-settings-not-saving)
15. [Frequently Asked Questions](#15-frequently-asked-questions)
16. [Glossary](#16-glossary)
17. [Disclaimer](#17-disclaimer)

---

## 1. Introduction

Sims 4 Updater is a standalone Windows desktop application that serves as a single control panel for managing a cracked installation of The Sims 4. It handles four primary responsibilities:

- **Game Updates:** Detecting your installed version, checking the patch server for newer versions, and downloading and applying binary delta patches to bring your game up to date.
- **DLC Management:** Displaying all 103 known Sims 4 DLCs with their installation and unlock status, allowing you to enable or disable individual packs within the crack configuration, and downloading missing DLC content from a configured CDN.
- **DLC Packing:** Packaging installed DLC folders into distributable ZIP archives, generating manifest files, and importing DLC archives from external sources.
- **EA DLC Unlocker:** Installing and uninstalling the PandaDLL-based EA DLC Unlocker that allows legitimate EA app clients to access DLC content.

The application is distributed as a single portable executable (`Sims4Updater.exe`) with no installer required. It bundles all dependencies internally, including the patching engine (xdelta3), archive extraction tools (unrar), and the full DLC catalog database.

> **Note:** The Sims 4 Updater requires a manifest URL to check for updates. The application ships without a pre-configured URL. You must obtain a manifest URL from the community or patch server host and enter it in the Settings tab before the update functionality will operate. See [Section 9.2](#92-manifest-url) for details.

---

## 2. System Requirements

| Requirement | Minimum |
|---|---|
| Operating System | Windows 10 64-bit |
| Recommended OS | Windows 11 64-bit |
| Architecture | x64 only |
| Disk Space | Approximately 25 MB for the application itself |
| Additional Disk Space | Required for patch downloads and DLC content (varies per update) |
| The Sims 4 | An existing installation on the local machine |
| Internet Connection | Required for update checks and DLC downloads |
| Administrator Rights | Required only for the Unlocker tab installation feature |

The application does not require Python, .NET, or any external runtime to be installed separately. Everything is bundled inside the executable via PyInstaller.

---

## 3. Installation and First Launch

### 3.1 Downloading the Application

Download the latest `Sims4Updater.exe` from the releases page provided by the patch server maintainer. No installation wizard or setup process is involved. Place the executable anywhere convenient — your desktop, a dedicated tools folder, or alongside your game installation directory.

### 3.2 First Launch and Game Detection

On first launch, the application performs the following steps automatically:

1. **Game directory detection:** The application checks the Windows registry under `SOFTWARE\Maxis\The Sims 4` and `SOFTWARE\WOW6432Node\Maxis\The Sims 4` for a recorded installation path. If no registry key is found, it also probes the following default paths:
   - `C:\Program Files\EA Games\The Sims 4`
   - `C:\Program Files (x86)\EA Games\The Sims 4`
   - `D:\Games\The Sims 4`

2. **Version detection:** Once a game directory is confirmed (validated by the presence of `Game/Bin/TS4_x64.exe` and `Data/Client`), the application hashes three sentinel files to identify the installed version.

3. **Self-update check:** The application silently checks GitHub Releases in the background to see if a newer version of the updater itself is available. If one is found, a banner appears at the top of the Home tab.

4. **DLC state scan:** The application reads the crack configuration file to build an initial picture of which DLCs are enabled and which are disabled.

If the game directory is not found automatically, the Home and DLCs tabs will show placeholder messages prompting you to configure the path in Settings. See [Section 9.1](#91-game-directory) for instructions.

### 3.3 Application Data Location

The application stores all persistent data in a dedicated directory under your Windows user profile:

```
C:\Users\{YourUsername}\AppData\Local\ToastyToast25\sims4_updater\
```

Files created in this directory:

| File | Purpose |
|---|---|
| `settings.json` | All user preferences (game path, manifest URL, language, theme) |
| `learned_hashes.json` | Locally accumulated version fingerprints from self-learning |
| `packed_dlcs\` | Output folder for DLC archives created in the DLC Packer tab |

> **Migration note:** If you previously used an older version of this tool that stored data under `AppData\Local\anadius\sims4_updater\`, the application will automatically migrate your `settings.json` and `learned_hashes.json` to the new location on first launch. The original files are not deleted.

---

## 4. Interface Overview

The application window is divided into two areas: a dark sidebar on the left and a content panel on the right.

### 4.1 Sidebar Navigation

The sidebar contains five navigation entries, each corresponding to a tab:

| Tab | Purpose |
|---|---|
| **Home** | Game version status and update controls |
| **DLCs** | Full DLC catalog with enable/disable management |
| **DLC Packer** | Pack DLCs into ZIP archives or import archives |
| **Unlocker** | Install or uninstall the EA DLC Unlocker |
| **Settings** | Application configuration |

Clicking a tab label in the sidebar switches the content panel immediately. Tabs load their content lazily — the DLC list scan, for example, runs only when you navigate to the DLCs tab, not when the application starts.

### 4.2 Status Badges

Throughout the application, small colored pill-shaped badges communicate state at a glance. The color coding is consistent:

| Color | Meaning |
|---|---|
| Green | Success, installed, enabled, up to date |
| Blue | Informational, neutral status |
| Orange / Yellow | Warning, action needed, pending |
| Red | Error, not installed, failure |
| Grey | Muted, disabled, not applicable |

### 4.3 Toast Notifications

Brief pop-up messages appear in the lower portion of the window after actions complete. These toasts auto-dismiss after a few seconds and use the same color coding as badges (green for success, orange for warning, red for error). You do not need to dismiss them manually.

---

## 5. Home Tab

The Home tab is the main control panel for checking and applying game updates. It is the first tab displayed when the application opens.

### 5.1 Information Cards

The top section of the Home tab displays an information card with four rows of data:

**Game Directory**
The detected path to The Sims 4 installation. If the path is longer than 60 characters, it is displayed truncated with a leading ellipsis (e.g., `...Games\The Sims 4`). If no game directory was found, this row shows "Not found."

**Installed Version**
The version string detected from your game files (e.g., `1.121.372.1020`). Detection uses MD5 hashes of three sentinel files cross-referenced against a database of 135+ known versions. If the version cannot be matched, this row shows "Unknown."

**Latest Patch**
The newest version available for patching as reported by the configured manifest. This field shows "Use 'Check for Updates'" until you press the check button. After checking, it reflects the `latest` field from the manifest.

**Game Latest** (appears conditionally)
When EA has released a newer version of the game than the latest available patch, this row appears in orange, showing the EA release version and its release date. This indicates a patch is being prepared but is not yet available. See [Section 5.6](#56-patch-pending-state).

**DLCs**
A summary of DLC state in the format `X/Y installed, Z enabled`, derived from the installed DLC count versus total known DLCs, and how many are currently enabled in the crack configuration.

### 5.2 DLC Pricing Summary

After Steam prices are fetched (this occurs automatically when you visit the DLCs tab), the Home tab displays a secondary card below the main information card. This card summarizes pricing data for all DLCs:

| Field | Description |
|---|---|
| Total DLCs | Number of paid DLCs with known Steam prices |
| Patchable | How many DLCs in the catalog have a patchable code (shown only if a manifest URL is configured) |
| Total Original | Sum of all DLC prices at full retail price |
| Current Total | Sum of all DLC prices at current Steam sale prices |
| You Save | The difference between original and current total, expressed as a dollar amount and percentage |
| DLCs On Sale | Count of DLCs currently discounted on Steam |

The "You Save" and "Current Total" fields appear in green when any savings are active.

### 5.3 Checking for Updates

To check whether an update is available, press the **Check for Updates** button at the bottom of the Home tab.

Before this button will function, a manifest URL must be configured in Settings. If no manifest URL is set, the button displays an error dialog asking you to configure one first.

When clicked, the application:

1. Fetches the manifest JSON from the configured URL.
2. Compares your installed version against the manifest's `latest` field.
3. Uses breadth-first search pathfinding to find the shortest chain of patch steps from your current version to the latest. When multiple paths of equal length exist, the one with the smallest total download size is selected.
4. Updates the Home tab with the result.

The check runs in a background thread so the GUI remains responsive. A status badge below the information card shows "Checking for updates..." while the operation is in progress.

### 5.4 Applying Game Updates

When an update is available, the button label changes to **Update Now** and displays the number of patch steps and total download size in the status badge (e.g., "Update available: 1 step(s), 412 MB").

Pressing **Update Now** switches the view to a progress screen where you can monitor the multi-stage update pipeline:

1. **Download** — Patch archive files are downloaded one at a time with a real-time progress bar, percentage indicator, transfer speed, and estimated time remaining. Downloads support HTTP Range requests, meaning if a download is interrupted, the next attempt resumes from where it left off rather than restarting from zero. Each downloaded file is verified against its MD5 checksum before proceeding.

2. **Patch** — The patcher engine applies binary delta patches using xdelta3. This stage reads from the downloaded archives and writes the updated game files in place.

3. **Finalize** — After patching completes, the updater automatically hashes the sentinel files for the new version, stores the hashes locally in the learned hashes database, and re-runs the DLC auto-toggle to ensure all existing DLC states remain correct.

> **Important:** DLC toggle states are preserved across updates. If you had certain DLCs disabled before updating, they remain disabled after the update completes. The finalizer respects your existing crack configuration.

A **Cancel** button is available on the progress screen. Cancellation stops the download at the next safe checkpoint and leaves any partially downloaded files in place to support resumption on the next attempt.

### 5.5 Updater Self-Update Banner

When the application detects a newer version of `Sims4Updater.exe` on GitHub Releases, a banner appears at the very top of the Home tab scroll area (above the main title). The banner is colored with the application accent color and shows:

```
Updater v2.1.0 available (21 MB)   [Update Now]
```

Clicking **Update Now** within this banner downloads the new executable in the background. During download, the banner transitions to a progress display showing:

- The version being downloaded ("Downloading v2.1.0...")
- A progress bar
- Bytes downloaded versus total size
- Download speed and estimated time remaining

When the download completes, a confirmation dialog asks whether to close and relaunch with the new version. If you confirm, the application saves your current settings, closes, and launches the new executable in its place. If you decline, the banner reverts to its original state with the "Update Now" button.

### 5.6 Patch-Pending State

There is a distinction between the actual game version released by EA and the latest version for which a patch has been prepared and uploaded to the manifest server.

The manifest supports two separate version fields:
- `latest` — The newest version users can actually patch to right now.
- `game_latest` — The actual newest EA release (which may be ahead of `latest`).

When EA releases a new game update but the patch has not yet been prepared, the manifest maintainer updates `game_latest` immediately. Users then see this state in the Home tab:

- The **Game Latest** row appears in orange, showing the new EA version and its release date.
- A banner below the information card reads: *"New game version X.X.X.XXXX has been released — patch coming soon!"*
- The update button is disabled and reads **Patch Pending**.

This tells you: a newer game version exists, but you cannot update to it yet. Once the patch maintainer prepares and uploads the patch files and updates `latest` in the manifest, the button becomes active on your next check.

If both an update to `latest` is available AND a newer `game_latest` exists beyond that, the button reads **Update Now** and an additional banner notes that a further update is coming after you apply the current one.

### 5.7 New DLC Announcements

When new DLC has been announced and added to the manifest's `new_dlcs` list but a patch for it does not yet exist, a banner appears in the Home tab:

```
New DLC announced: Name of Pack — patch pending
```

The same pending DLC names also appear in the DLCs tab under a "Pending" section at the bottom of the list, labeled with `[PENDING]`. These rows are informational only and have no checkbox or download option.

---

## 6. DLCs Tab

The DLCs tab provides a complete view of all 103 known Sims 4 DLCs, organized by pack type, with tools to manage which ones are active in your crack configuration.

### 6.1 DLC List Layout

The list is displayed in a scrollable area. Each DLC appears as a card-style row with alternating dark and slightly lighter backgrounds for readability. Rows are organized into labeled sections by pack type in the following order:

1. Expansion Packs
2. Game Packs
3. Stuff Packs
4. Kits
5. Free Packs

Each row contains, from left to right:
- An expand arrow button (only if the DLC has a description)
- A checkbox with the DLC name
- Steam price information (if prices have been loaded)
- A Steam store link icon (if the DLC has a Steam App ID)
- A status pill badge
- A download button (if the DLC is downloadable and not installed)

Hovering over any row causes the row border to animate from grey to the application accent color. Moving the cursor away reverses the animation.

### 6.2 Status Pills Explained

Every DLC row displays a pill badge indicating the current state of that DLC. The possible statuses are:

| Status | Color | Meaning |
|---|---|---|
| **Owned** | Green | The DLC folder is installed and complete, and it is not registered in the crack config — this indicates a legitimately purchased DLC via EA |
| **Patched** | Blue | The DLC folder exists, is complete, and is registered and enabled in the crack config |
| **Patched (disabled)** | Grey | The DLC folder exists and is registered in the crack config, but is currently toggled off |
| **Incomplete** | Orange | The DLC folder exists but is missing key files (specifically `SimulationFullBuild0.package`) |
| **Missing files** | Orange | The DLC is registered in the crack config but its folder does not exist on disk |
| **Not installed** | Grey | No folder exists and no crack config entry exists |

Rows with "Owned" status display a permanently checked, disabled checkbox — these DLCs are legitimately purchased and should not be managed through the crack config toggle.

Rows with "Patched" or "Patched (disabled)" status have an active checkbox that you can toggle.

Rows with "Not installed", "Missing files", or "Incomplete" status have a disabled, unchecked checkbox. To enable these DLCs, you must first obtain and install their content.

### 6.3 Collapsible Section Headers

Each pack type group has a header bar showing:
- A triangle arrow indicator
- The group name in capitals (e.g., "EXPANSION PACKS")
- A count badge showing installed versus total (e.g., `8/18`)

Clicking anywhere on the header bar collapses or expands that group. When collapsed, the arrow points right; when expanded, it points down. Sections retain their collapsed/expanded state while navigating between tabs during the same session.

The counts in the header update dynamically when filters or searches narrow the visible list.

### 6.4 Expanding DLC Descriptions

DLC rows that have a description show a small triangular arrow on the far left of the row (before the checkbox). Clicking this arrow expands an additional panel below the row containing:

- A short English description of the pack's content and theme.
- A "View on Steam Store" link that opens the DLC's Steam page in your default browser.
- If the DLC is currently on sale on Steam, a sale summary line in green showing the original price, the discounted price, and the discount percentage.

Clicking the arrow again collapses the description panel.

### 6.5 Steam Pricing Display

Steam prices are fetched automatically in the background when you first navigate to the DLCs tab. The fetching is performed as a batch request to the Steam store API. Once prices are retrieved, they are cached for the session and shared with the Home tab pricing summary card.

Each DLC row with a known Steam App ID and a non-free price displays pricing information to the right of the DLC name:

- If not on sale: the current price is shown in muted grey text.
- If on sale: a green discount badge (e.g., `-40%`) appears, followed by the original price with a strikethrough in grey, followed by the sale price in bold green text.

Free DLCs (such as the Holiday Celebration Pack) do not display price information since they have no cost on Steam.

### 6.6 Search and Filter Chips

**Search Box**

A search field at the top of the DLC tab lets you filter rows by typing. The search matches against both the DLC display name and the DLC ID code (e.g., "EP01"). Matching is case-insensitive and updates in real time as you type. A small "X" button to the right of the search field clears the search term.

**Filter Chips**

Below the search box, a row of filter chip buttons allows you to narrow the list by category. Multiple chips can be active simultaneously — the list shows DLCs that match any of the active filters (OR logic between chips):

| Chip | Shows DLCs that are... |
|---|---|
| **Owned** | Legitimately purchased (status = Owned) |
| **Not Owned** | Not owned and not registered as patched |
| **Installed** | Physically present on disk |
| **Patched** | Installed and registered in the crack config |
| **Downloadable** | Available to download from the manifest CDN and not yet installed |
| **On Sale** | Currently discounted on Steam |

The **Downloadable** and **On Sale** chips display a count in parentheses after their label once the relevant data has been loaded (e.g., "Downloadable (5)" or "On Sale (12)"). If no active sale or downloadable content exists, the count is omitted.

Active filter chips are highlighted in the accent color (for most categories) or green (for Downloadable and On Sale). Clicking an active chip deactivates it and returns it to its default muted appearance.

When the search and filters together produce no matching DLCs, the list area displays a centered message: "No DLCs match your filters / Try adjusting your search or filters."

### 6.7 Downloading Missing DLCs

If the manifest includes download entries for DLC content (a `dlc_downloads` section), the DLC tab gains download capabilities.

**Download Missing button**
A green "Download Missing" button appears in the header row when there are DLCs available for download that are not currently installed. Clicking it queues and downloads all eligible DLCs sequentially.

**Per-row download buttons**
Individual green download arrow buttons appear on each eligible row. Clicking a per-row button downloads only that DLC.

**Progress display**
During download, each DLC's download button is replaced by a progress label showing:
- `Waiting...` — queued but not yet started
- `42%` — percentage downloaded
- `Extracting...` — archive is being extracted
- `Registering...` — being added to the crack config
- A green checkmark — completed successfully
- `Failed` in red — an error occurred; the download button reappears for retry

Downloads support resumption. If a download is interrupted (network loss, application closed), the partial file is preserved. The next download attempt for the same DLC continues from where it left off.

Once all downloads complete, the DLC list automatically refreshes to reflect the newly installed content.

### 6.8 Auto-Toggle

The **Auto-Toggle** button (in the header row, accent-colored) scans the game directory for DLC folder presence and automatically adjusts the crack configuration:

- DLCs with folders present on disk are enabled.
- DLCs with no folder on disk are disabled.

This is useful after manually copying DLC folders into the game directory, after a game update that may have changed file structures, or any time you want to ensure the crack config matches reality without reviewing each row individually.

After running, a toast notification reports how many DLCs were toggled. If everything was already correctly configured, the toast reads "All DLCs already correctly configured." The DLC list automatically refreshes after Auto-Toggle completes.

### 6.9 Apply Changes

The **Apply Changes** button saves whatever checkbox states are currently set in the DLC list to the crack configuration file on disk. Use this workflow when you want to manually select which DLCs to enable or disable:

1. Review the DLC list and check or uncheck DLC checkboxes as desired.
2. Press **Apply Changes**.
3. The application writes the updated enabled/disabled state to the crack config in the correct format for your detected crack type.
4. A toast notification confirms success.

Note that changes to checkboxes are not saved automatically — they are only applied when you explicitly press Apply Changes. Navigating away from the tab without pressing Apply Changes discards any unsaved checkbox state changes.

### 6.10 Status Bar

A status bar at the bottom of the DLC tab shows a running count of DLC states:

```
X owned, Y patched, Z missing  |  W enabled
```

These counts reflect the total across all DLCs, not just the currently visible filtered set.

---

## 7. DLC Packer Tab

The DLC Packer tab enables you to package installed DLC folders into standard ZIP archives for storage or distribution, and to import DLC archives into your game directory.

### 7.1 Purpose and Use Cases

The primary use cases for this tab are:

- **Content creators and server operators** who maintain patch servers and need to package DLC content into distributable archives with accompanying manifest files.
- **Users who receive DLC archives** from such servers and need to extract them into their game directory and register the DLCs in the crack config.
- **Personal backup** of your installed DLC content before performing major game updates or reinstalls.

### 7.2 Selecting DLCs to Pack

When you navigate to the DLC Packer tab, the application scans the game directory for installed DLC folders. Each found DLC appears as a checkbox row in the scrollable list with the following information:

```
[x]  EP01 — Get to Work                              15 files, 1.2 GB
[x]  EP02 — Get Together                              12 files, 980 MB
```

All discovered DLCs are checked by default.

Three selection shortcuts are available in the toolbar:

| Button | Action |
|---|---|
| **Select All** | Checks all DLC rows |
| **Deselect All** | Unchecks all DLC rows |
| *(manual)* | Click individual checkboxes to fine-tune selection |

If no game directory is configured or no DLC folders are found, the list area shows: "No game directory found. Set it in Settings."

### 7.3 Packing DLCs

Two buttons initiate packing:

**Pack Selected** — Processes only the DLCs that are currently checked. If no DLCs are checked, a warning toast appears and nothing happens.

**Pack All** — Processes every DLC in the list regardless of checkbox state.

During packing, a progress bar and status label at the bottom of the tab update in real time:

```
Packing 3/8: EP05
```

The progress bar fills from left to right as each DLC is processed. All other buttons are disabled during the operation.

Output ZIP files are written to:
```
C:\Users\{YourUsername}\AppData\Local\ToastyToast25\sims4_updater\packed_dlcs\
```

Each ZIP file is named after the DLC ID (e.g., `EP01.zip`).

### 7.4 Disk Space Warnings

Before packing begins, the application estimates the total size of the selected DLCs by summing the folder sizes displayed in the list. It then checks available disk space on the drive containing the output directory.

- If the estimated size exceeds the available free space, a dialog appears:
  > "Estimated pack size: X.X GB / Available disk space: Y.Y GB / You may run out of space. Continue anyway?"

  You can proceed or cancel. Proceeding without sufficient space may result in a corrupted or truncated ZIP file.

- If the estimated size exceeds 90% of available free space (but does not exceed it), a warning toast appears noting the space usage, and packing proceeds automatically without requiring confirmation.

### 7.5 Overwrite Protection

Before packing starts, the application checks whether any of the selected DLCs already have a ZIP file in the output directory. If existing files are found, a dialog offers three choices:

- **Yes** — Overwrite all existing ZIP files for the selected DLCs.
- **No** — Skip already-packed DLCs and pack only the remainder.
- **Cancel** — Abort the operation entirely.

If you select "No" and all selected DLCs are already packed, a toast confirms "All selected DLCs already packed" and packing does not run.

### 7.6 Auto Manifest Generation

After any pack operation completes successfully, the application automatically generates a `manifest_dlc_downloads.json` file in the output directory alongside the ZIP files. This manifest includes:

- The DLC ID for each packed archive.
- The download URL (populated as a placeholder; you update this with your actual hosting URL).
- The file size in bytes.
- The MD5 hash of each ZIP file.

This manifest file is formatted for direct use as the `dlc_downloads` section of a patch server manifest, allowing server operators to immediately reference the freshly packed DLC archives.

### 7.7 Importing Archives

The Import Archive section at the bottom of the tab allows you to extract a ZIP or RAR archive into your game directory.

**Steps:**

1. Click **Browse & Import...**.
2. A file browser dialog opens, filtered to show ZIP and RAR files.
3. Select the archive to import.
4. A confirmation dialog shows the filename and the target game directory:
   > "Extract 'EP05.zip' into: C:\Program Files\EA Games\The Sims 4 / Continue?"
5. Confirm to begin extraction. The status label and progress bar track the operation.
6. After extraction, the application analyzes which DLC folders were created. If it identifies known DLC IDs, it reports them and asks:
   > "The following DLCs were extracted: EP05 / Enable them in the crack config?"
7. Confirming enables the newly extracted DLCs in the crack configuration alongside any DLCs that were already enabled.

The import feature supports both ZIP and RAR archives. RAR extraction is performed by the bundled `unrar` tool.

### 7.8 Output Folder

The **Open Folder** button at the bottom right of the tab opens the output directory in Windows File Explorer. The output directory is created automatically if it does not exist when you click the button.

The full path is displayed in small text to the left of the Open Folder button:
```
Output: C:\Users\...\ToastyToast25\sims4_updater\packed_dlcs
```

---

## 8. Unlocker Tab

### 8.1 What Is the EA DLC Unlocker

The EA DLC Unlocker is a PandaDLL-based tool that uses a custom `version.dll` to intercept EA app entitlement checks and present the game with an entitlements list read from a local configuration file (`entitlements.ini`). This allows the game to grant access to DLC content without the DLC being purchased through an EA account.

This approach works with the EA app client (EA Desktop) and is distinct from crack-config-based DLC management. The two approaches can coexist: the crack config manages which DLC folders the game loads, while the EA DLC Unlocker manages the entitlement handshake that the EA app performs.

### 8.2 Status Display

The top section of the Unlocker tab shows a status card with three rows:

**Client**
The EA client type detected on your system. Typically "EA app". If no supported client is found, this shows "Not Found" in red.

**Status**
The installation state of the unlocker. Possible values:

| Status | Meaning |
|---|---|
| Installed | The DLL and config file are both present and the scheduled task exists |
| Installed (task missing) | DLL and config are present but the Windows scheduled task is missing |
| Partial (config missing) | The DLL is present but the entitlements config file is absent |
| Partial (DLL missing) | The config file is present but the DLL is absent |
| Not Installed | Neither the DLL nor the config file are present |

**Admin**
Whether the application is currently running with administrator privileges. The unlocker installer writes files to protected system directories and creates a Windows scheduled task, both of which require elevation.

- "Elevated" in green — administrator rights are active.
- "Not Elevated" in orange — administrator rights are absent; installation and uninstallation will be blocked.

### 8.3 Installing the Unlocker

1. Ensure the status card shows "Elevated" for Admin. If it shows "Not Elevated", close the application, right-click `Sims4Updater.exe`, and select "Run as administrator."

2. Click **Install Unlocker**.

3. The activity log below the status card updates in real time showing each step:
   - Detecting EA app client path from the registry
   - Copying `version.dll` to the EA app directory
   - Writing `entitlements.ini` to `%APPDATA%\ToastyToast25\EA DLC Unlocker\`
   - Creating a Windows scheduled task (`copy_dlc_unlocker`) for staged update compatibility

4. When installation completes, a green toast confirms success and the status card refreshes automatically.

### 8.4 Uninstalling the Unlocker

1. Ensure the application is running as administrator.

2. Click **Uninstall**.

3. A confirmation dialog appears:
   > "Are you sure you want to uninstall the DLC Unlocker? This will remove the unlocker DLL, config files, and scheduled task."

4. Confirming proceeds with removal. The activity log shows each step:
   - Removing `version.dll` from the EA app directory
   - Deleting the `entitlements.ini` configuration file
   - Deleting the Windows scheduled task

5. A toast confirms completion and the status card refreshes.

### 8.5 Activity Log

The activity log is a read-only scrollable text area that occupies the lower portion of the Unlocker tab. It captures all messages emitted by the installer and uninstaller in real time, including:

- Step-by-step progress messages
- File paths being written or deleted
- Any errors encountered with their specific reason
- Timestamps or labels for operation boundaries (e.g., "--- Installing DLC Unlocker ---")

The log persists for the session and accumulates messages across multiple install/uninstall operations. A **Clear** button in the log header erases the log content.

### 8.6 Open Configs Button

The **Open Configs** button opens the folder containing the `entitlements.ini` file in Windows File Explorer. This is located at:

```
C:\Users\{YourUsername}\AppData\Roaming\ToastyToast25\EA DLC Unlocker\
```

If the unlocker has not been installed and the folder does not exist, a warning toast appears: "Configs folder not found. Install the Unlocker first."

---

## 9. Settings Tab

The Settings tab stores your application preferences to disk when you explicitly press Save. All settings are written to `settings.json` in the application data directory.

### 9.1 Game Directory

A text field showing the current game directory path, with a **Browse** button that opens a folder selection dialog.

The path should point to the root of The Sims 4 installation — the folder that contains the `Game` and `Data` subdirectories and the main executable at `Game\Bin\TS4_x64.exe`.

Correct example:
```
C:\Program Files\EA Games\The Sims 4
```

If the auto-detection on startup found the correct path, this field is pre-populated. If it is wrong or empty, use Browse to navigate to the correct location.

> **Tip:** After changing the game directory, navigate to the Home tab and press Refresh to have the application re-detect the game version from the new path.

### 9.2 Manifest URL

A text field for the URL of the patch manifest JSON file. This must be a fully qualified HTTPS URL pointing to a JSON file in the [manifest format](../README.md#manifest-format) supported by the application.

The application ships without a default manifest URL. You must obtain this URL from the patch server or community source providing updates for your version of the game and paste it here.

Example format:
```
https://example.com/ts4/manifest.json
```

Leave this field empty if you do not have a patch server URL. The update check functionality will not work without it, but all other features (DLC management, DLC Packer, Unlocker) operate independently of the manifest URL.

### 9.3 Language

A dropdown menu for selecting the game language. The selection applies in two ways:

1. The game's `Locale` registry value is updated to the chosen language code, which controls the language the game loads on next launch.
2. The `RldOrigin.ini` configuration file in the game directory (and its `Bin_LE` counterpart if present) is updated with the language setting.

The dropdown displays languages in the format `{code} — {native name}`, for example:
```
fr_FR — Francais
de_DE — Deutsch
```

See [Section 13](#13-supported-languages) for the full list of supported languages.

> **Note:** Changing the language here changes it for the game. It does not affect the Sims 4 Updater's own interface language, which is English only.

### 9.4 Theme

Three radio buttons select the application's color theme:

| Option | Effect |
|---|---|
| **Dark** | Forces the dark color scheme (default) |
| **Light** | Forces the light color scheme |
| **System** | Follows the Windows system-wide dark/light mode preference |

Theme changes take effect immediately when you save settings — you do not need to restart the application.

### 9.5 Check for Updates on Startup

A checkbox that controls whether the application automatically contacts the manifest URL on startup to check for a game update. When enabled, the Home tab refreshes game information and checks the manifest in the background immediately after launch. When disabled, you must press "Check for Updates" manually.

This setting does not affect the updater self-update check — that check always runs silently on startup regardless of this toggle.

### 9.6 Saving Settings

Press **Save Settings** to write all current field values to `settings.json`. The button briefly flashes green upon success. A success toast also confirms the save. If a write error occurs (for example, the file is locked by another process), an error message appears below the Save button with the specific reason.

Settings are not auto-saved as you edit fields. Navigating away from the Settings tab without pressing Save discards any changes you made in that session.

---

## 10. Command-Line Interface (CLI)

`Sims4Updater.exe` can also be run from the command prompt or PowerShell with subcommand arguments. CLI mode is useful for automation, scripting, or when you need quick answers without opening the GUI.

### 10.1 When to Use the CLI

- Checking the status of a game installation in a batch script.
- Automating DLC toggling after scripted operations.
- Inspecting manifest files for debugging.
- Teaching the updater new version hashes after a manual patch.
- Changing the game language from a terminal.

### 10.2 Available Commands

| Command | Syntax | Description |
|---|---|---|
| `detect` | `detect <game_dir>` | Hash the sentinel files in the given directory and report the detected version |
| `check` | `check [game_dir] [--manifest-url URL]` | Check for available updates against the configured or specified manifest URL |
| `status` | `status [game_dir]` | Print a summary of game directory, version, language, detected crack config format, and DLC counts |
| `manifest` | `manifest <source>` | Inspect a manifest file or URL — lists all available patch steps, versions, and file sizes |
| `dlc` | `dlc <game_dir>` | List all DLC states (enabled/disabled, installed/missing) for the given game directory |
| `dlc-auto` | `dlc-auto <game_dir>` | Auto-enable installed DLCs and disable missing ones in the crack config |
| `pack-dlc` | `pack-dlc <game_dir> <dlc_ids...> [-o output_dir]` | Pack the specified DLC IDs into ZIP archives, optionally specifying an output directory. Use `all` for all installed DLCs. |
| `learn` | `learn <game_dir> <version>` | Hash sentinel files and save them under the given version string for future detection |
| `language` | `language [code] [--game-dir DIR]` | Without arguments, shows current language and all available codes. With a code, sets the game language. |

For commands that accept `[game_dir]` as optional, the application falls back to auto-detection from the registry and default paths if no directory is supplied. The `--manifest-url` flag on the `check` command overrides the URL stored in `settings.json` for a one-time check without changing your saved configuration.

### 10.3 CLI Examples

Check the status of a game installation at a non-default path:

```
Sims4Updater.exe status "D:\Games\The Sims 4"
```

Detect the version of a specific game directory:

```
Sims4Updater.exe detect "C:\Program Files\EA Games\The Sims 4"
```

Check for updates using the auto-detected game directory (uses the manifest URL from `settings.json`):

```
Sims4Updater.exe check
```

Inspect a manifest file stored locally:

```
Sims4Updater.exe manifest "C:\Downloads\manifest.json"
```

Inspect a manifest at a remote URL:

```
Sims4Updater.exe manifest https://example.com/ts4/manifest.json
```

Show all DLC states for a game directory:

```
Sims4Updater.exe dlc "C:\Program Files\EA Games\The Sims 4"
```

Auto-enable installed DLCs and disable missing ones:

```
Sims4Updater.exe dlc-auto "C:\Program Files\EA Games\The Sims 4"
```

Pack three specific DLCs into a custom output directory:

```
Sims4Updater.exe pack-dlc "C:\Program Files\EA Games\The Sims 4" EP01 GP05 SP10 -o "D:\Backups\DLCPacks"
```

Pack all installed DLCs into the current directory:

```
Sims4Updater.exe pack-dlc "C:\Program Files\EA Games\The Sims 4" all
```

Learn version hashes for a known game version:

```
Sims4Updater.exe learn "C:\Program Files\EA Games\The Sims 4" 1.121.372.1020
```

Show the current game language and all available language codes:

```
Sims4Updater.exe language
```

Change the game language to Brazilian Portuguese:

```
Sims4Updater.exe language pt_BR --game-dir "C:\Program Files\EA Games\The Sims 4"
```

Change the game language to German (registry only, no game directory provided):

```
Sims4Updater.exe language de_DE
```

---

## 11. Crack Config Format Support

The Sims 4 Updater automatically detects which crack configuration format your installation uses. It does this by scanning the game directory (and the `Bin_LE` subdirectory) for known configuration filenames and structures.

Five formats are supported:

| Format Name | Config File | Toggle Method |
|---|---|---|
| **RldOrigin** | `RldOrigin.ini` | Lines are commented out with a semicolon (`;`) prefix to disable a DLC |
| **CODEX** | `codex.cfg` | Group value is swapped between active and inactive values to enable/disable |
| **Rune** | `rune.ini` | Section names have an underscore suffix appended to disable a DLC |
| **Anadius Simple** | `anadius.cfg` | Lines are commented out with a double-slash (`//`) prefix to disable a DLC |
| **Anadius Codex-like** | `anadius.cfg` | Group value swap (structurally similar to CODEX but in the anadius file) |

Detection tries formats in reverse priority order. If multiple config files are present, the most specific match takes precedence.

When the Auto-Toggle or Apply Changes operations write changes to the config file, they apply the correct toggle method for the detected format. All operations also automatically mirror changes to the `Bin_LE` directory variant when present, ensuring that both standard and Legacy Edition installations stay in sync.

You do not need to know or specify which format your installation uses — detection is fully automatic.

---

## 12. Version Detection System

The application identifies your installed game version through a hash-based fingerprinting system rather than reading a version number from a text file. This approach is more reliable because cracked installations may have version strings that do not accurately reflect the patched binary state.

**Sentinel files hashed:**

| File | Role |
|---|---|
| `Game/Bin/TS4_x64.exe` | The main game executable; changes with every EA update |
| `Game/Bin/Default.ini` | A configuration file with version information embedded; changes each update |
| `delta/EP01/version.ini` | A DLC version marker; provides a third independent discriminator |

The MD5 hashes of these three files are computed and looked up in a database of known version fingerprints. The database is sourced from four layers:

1. **Bundled database** — A `version_hashes.json` file packed inside the executable with 135+ known version fingerprints.
2. **Manifest fingerprints** — Hashes provided directly in the manifest JSON under the `fingerprints` key, supplied by the patch maintainer for newly released versions.
3. **Self-learning** — After every successful patch, the updater hashes the sentinel files of the new version and saves them locally in `learned_hashes.json`. These persist across sessions and take priority over the bundled database.
4. **Crowd-sourced** — If the manifest includes a `fingerprints_url`, the application fetches a validated community hash database and merges it into the local learned hashes.

Detection returns one of three confidence levels:

| Confidence | Meaning |
|---|---|
| **Definitive** | The hash combination matches exactly one known version |
| **Probable** | The hashes match but with some ambiguity across versions sharing partial hashes |
| **Unknown** | No match found in any database layer |

"Unknown" typically means you have a version that has not been seen before. This can happen after a manual patch, a very new EA release, or a non-standard installation. In this case, the Home tab shows "Unknown" for the installed version and the update check will report that no update path exists from an unknown version.

---

## 13. Supported Languages

The language changer supports 18 languages:

| Language Code | Language (Native Name) |
|---|---|
| `cs_CZ` | Cestina |
| `da_DK` | Dansk |
| `de_DE` | Deutsch |
| `en_US` | English |
| `es_ES` | Espanol |
| `fr_FR` | Francais |
| `it_IT` | Italiano |
| `ja_JP` | Japanese |
| `ko_KR` | Korean |
| `nl_NL` | Nederlands |
| `no_NO` | Norsk |
| `pl_PL` | Polski |
| `pt_BR` | Portugues (Brasil) |
| `fi_FI` | Suomi |
| `sv_SE` | Svenska |
| `ru_RU` | Russian |
| `zh_TW` | Traditional Chinese |
| `zh_CN` | Simplified Chinese |

The language setting updates the Windows registry `Locale` value under the Sims 4 key and writes the language code to `RldOrigin.ini` configuration files where present.

---

## 14. Troubleshooting

### 14.1 Game Directory Not Detected

**Symptom:** The Home tab shows "Not found" for Game Directory, and the DLCs tab shows "No game directory found."

**Causes and solutions:**

- **Non-standard installation path.** If The Sims 4 is installed in a location other than the probed default paths and your registry key is absent or points to a different path, auto-detection will fail. Solution: Open the Settings tab, type or browse to the correct path, and save.

- **Moved game files.** If you moved the game directory after installation, the registry key still points to the old location. Solution: Set the path manually in Settings.

- **Registry key absent.** Some crack installations do not write a registry key. Solution: Set the path manually in Settings.

- **Drive not connected.** If the game is installed on an external or secondary drive that is not connected at launch time, detection fails. Connect the drive and restart the application, or set the path manually.

### 14.2 Version Shows as Unknown

**Symptom:** The Home tab displays "Unknown" for Installed Version.

**Causes and solutions:**

- **Very recent EA update.** EA may have released a new game version after the bundled hash database was compiled. Solution: Check if the manifest has an updated `fingerprints` section. If the manifest URL is configured and you check for updates, newly published fingerprints are merged automatically. If the manifest does not yet have fingerprints for your version, you may need to wait for the patch maintainer to add them.

- **Non-standard or manually patched game.** If the game files differ from any known reference state (partial manual patch, file corruption, custom modification), none of the sentinel file hashes will match. Solution: Verify game file integrity if possible, or report your hash values to the patch maintainer for inclusion in the database.

- **Incorrect game directory.** If the path in Settings points to a folder that contains some game files but not the correct sentinel files, detection will fail or return wrong results. Solution: Verify that the configured path contains `Game\Bin\TS4_x64.exe`.

### 14.3 Update Button Remains Disabled

**Symptom:** The "Check for Updates" button appears or the "Patch Pending" label shows, but you cannot apply an update.

**Causes and solutions:**

- **No manifest URL configured.** Solution: Enter the manifest URL in Settings and save.

- **Already up to date.** If your installed version matches `latest` in the manifest, there is nothing to apply. The button shows "Check for Updates" after confirming you are current.

- **Patch pending state.** EA released a newer version but the patch has not been prepared yet. The button shows "Patch Pending" and is intentionally disabled. Solution: Wait for the patch maintainer to publish the update.

- **No update path exists.** If the updater cannot find a BFS path from your current version to `latest` (for example, because your version is very old and only step-by-step patches exist that bridge known intermediate versions), the check may report no available update. Solution: Contact the patch server maintainer to confirm whether your version is supported.

- **Manifest URL unreachable.** A network error or URL change prevents the manifest from loading. Solution: Verify the URL is correct in Settings, and confirm you have internet access. Check if the manifest host has posted any status announcements.

### 14.4 DLCs Not Showing Correct Status

**Symptom:** DLCs show as "Not installed" even though their folders are present, or show as "Patched" even though they are missing.

**Causes and solutions:**

- **Crack config not detected.** If the application cannot find a recognized config file in the game directory, it cannot determine registration status. Status will show as "Not installed" for all DLCs. Solution: Ensure the game directory is correct and contains one of the supported config files (see [Section 11](#11-crack-config-format-support)).

- **DLC folder name mismatch.** The application looks for DLC folders matching the catalog's known IDs (e.g., `EP01`, `GP05`). Non-standard folder naming causes detection failures. Solution: Ensure DLC folders follow the standard naming convention.

- **Free packs.** The Holiday Celebration Pack and other free packs always report as "Owned" when their folder is present, regardless of crack config registration. This is correct behavior.

- **Stale data.** The DLC tab caches its state for the current navigation session. If you modify files on disk while the tab is open, press the Refresh button on the Home tab and then re-navigate to DLCs to reload.

### 14.5 Unlocker Installation Fails

**Symptom:** The Unlocker tab shows an error in the activity log after pressing Install Unlocker.

**Causes and solutions:**

- **Not running as administrator.** The most common cause. Solution: Close the application and relaunch by right-clicking `Sims4Updater.exe` and selecting "Run as administrator." The Admin badge should show "Elevated" before attempting installation.

- **EA app not installed.** The installer detects the EA app client via registry keys. If EA app is not installed, no client path is found. Solution: Install EA app (EA Desktop) before using the Unlocker tab.

- **Files in use.** If the EA app is running and has `version.dll` loaded, the installer cannot overwrite it. Solution: Close the EA app completely, then retry.

- **Antivirus interference.** Security software may block the creation of `version.dll` in the EA app directory. Solution: Add an exception for the Sims 4 Updater and the EA app directory in your security software, or temporarily disable real-time protection during installation.

### 14.6 Downloads Failing or Stalling

**Symptom:** A patch or DLC download stops at a certain percentage, fails with an error, or the progress bar stops moving.

**Causes and solutions:**

- **Network interruption.** Downloads support resume. If the application or network connection drops, simply retry the download. It will continue from the last successfully received byte.

- **CDN or server outage.** The hosting server may be temporarily unavailable. Solution: Wait and retry after some time.

- **MD5 verification failure.** If a downloaded file's checksum does not match the expected value in the manifest, the file is considered corrupt and the download fails. Solution: Delete any partial files from the app data directory and retry. If the problem persists, the manifest or server-side file may be corrupted — report it to the maintainer.

- **Antivirus quarantine.** Security software may intercept and alter downloaded patch files mid-stream, causing checksum failures. Solution: Add an exception for the Sims 4 Updater and its app data directory.

### 14.7 Settings Not Saving

**Symptom:** Settings revert to previous values after restarting the application.

**Causes and solutions:**

- **Did not press Save Settings.** Settings require an explicit save action. Solution: Always press the Save Settings button after making changes in the Settings tab.

- **Write permission error.** If the app data directory (`AppData\Local\ToastyToast25\sims4_updater\`) is not writable, the save fails silently or with an error message below the Save button. Solution: Check folder permissions. This directory is created automatically and should always be writable under your user account.

- **Disk full.** Solution: Free up disk space on the system drive.

---

## 15. Frequently Asked Questions

**Q: Do I need to run the application as administrator normally?**

A: No. Administrator rights are only required when using the Unlocker tab to install or uninstall the EA DLC Unlocker. All other features — game updates, DLC management, DLC packing, and settings — work without elevation.

**Q: What happens to my disabled DLCs after I apply an update?**

A: Your DLC toggle states are preserved. The update finalizer reads your existing crack config before patching and ensures disabled DLCs remain disabled after the update completes. You do not need to re-run Auto-Toggle after updating.

**Q: Can I use this application with a Steam or EA app legitimate installation?**

A: The DLC management features are designed for crack configuration formats (RldOrigin, CODEX, Rune, Anadius). Legitimate EA app or Steam installations do not have these config files, so the DLC enable/disable features will not function. However, the update detection and language features may still work if your game directory contains the sentinel files.

**Q: Why does the version show as "Unknown" right after EA releases an update?**

A: The bundled hash database is compiled at build time and cannot anticipate future EA versions. When EA releases a new version, the hash database will not yet contain fingerprints for it. Once the patch maintainer adds fingerprints to the manifest and you run a manifest check, the new version's hashes are downloaded and cached locally. After your own successful patch, the application hashes the new files and adds them to your local database automatically.

**Q: Can I have the DLC Packer output to a different folder?**

A: Not through the GUI — the output directory is fixed at `%LocalAppData%\ToastyToast25\sims4_updater\packed_dlcs\`. However, using the CLI `pack-dlc` command with the `-o` flag allows you to specify any output directory.

**Q: What does "Free Pack" mean in the DLC list?**

A: Free packs are DLCs that EA has made available to all players at no cost, such as the Holiday Celebration Pack. These are always shown as "Owned" when their folder is installed, because they are genuinely provided for free and do not require a crack config entry.

**Q: Will the application break if I manually edit the crack config file?**

A: The application re-reads the config file each time you navigate to the DLC tab or trigger a refresh. Manual edits are picked up on the next read. However, if your manual edit introduces a syntax error that the application cannot parse, the DLC list may show incorrect statuses or fail to load. In that case, run Auto-Toggle to reconstruct the config from the actual installed DLC state.

**Q: What is the difference between "Patched" and "Owned" in the DLC status?**

A: "Owned" means the DLC is installed and complete, but has no entry in the crack config file. This is the expected state for DLCs you purchased through EA. "Patched" means the DLC is installed, complete, and has an active entry in the crack config file — meaning it was enabled through the crack system rather than legitimate purchase.

**Q: Does the application send any data about me to external servers?**

A: The application contacts two types of external servers:
1. The manifest URL you configure in Settings (under your control).
2. The Steam Store API to fetch DLC prices (public, no authentication).
3. GitHub's releases API to check for application self-updates.
4. Optionally, a `report_url` configured in the manifest to submit version fingerprint hashes (fire-and-forget, no personal data — only the game version string and file hashes).

No user account information, personal identifiers, game save data, or system information beyond file hashes of Sims 4 executables is transmitted.

---

## 16. Glossary

**BFS (Breadth-First Search)**
The algorithm used to find the shortest chain of patch steps from your current game version to the latest available version. Among paths of equal length, the one with the smallest total download size is chosen.

**Crack Config**
A configuration file used by various game cracks (RldOrigin, CODEX, Rune, Anadius) to define which DLC entitlement codes are active. The Sims 4 Updater reads and writes these files to enable or disable individual DLC packs.

**Delta Patch**
A binary file describing only the differences between an old file and a new file. Applying a delta patch to the old file produces the new file. Delta patches are much smaller than the full game files because they only contain what changed. This application uses the xdelta3 format.

**DLC (Downloadable Content)**
Additional game content sold separately from the base game. For The Sims 4, DLCs include Expansion Packs, Game Packs, Stuff Packs, Kits, and Free Packs.

**EA DLC Unlocker**
A PandaDLL-based tool using a custom `version.dll` that intercepts the EA app's entitlement verification to grant DLC access without purchased licenses.

**Entitlements**
The list of products and DLCs that the EA app considers a user to have access to. The EA DLC Unlocker replaces this list with a local file containing all desired DLC codes.

**Fingerprint / Sentinel Files**
Three specific files whose MD5 hashes uniquely identify a given version of The Sims 4: `Game/Bin/TS4_x64.exe`, `Game/Bin/Default.ini`, and `delta/EP01/version.ini`.

**Manifest**
A JSON file hosted on a web server that describes available patches, their source and target versions, download URLs, file sizes, and checksums. The application fetches this file to determine what updates are available.

**MD5**
A cryptographic hash function used here for file integrity verification. Each downloadable file in the manifest includes its expected MD5 hash; after download, the application computes the hash of the received file and compares them to confirm the file was not corrupted or tampered with.

**Pack Type**
The category of a Sims 4 DLC pack. The five types in order of scope are: Expansion Pack (largest), Game Pack, Stuff Pack, Kit, and Free Pack.

**PandaDLL**
A technique of replacing a system DLL (`version.dll`) in an application's directory with a custom implementation that intercepts and modifies internal function calls. Used by the EA DLC Unlocker to intercept entitlement queries.

**PyInstaller**
The tool used to package the Python application and all its dependencies into a single standalone Windows executable. The executable bundles the Python interpreter, all required libraries, and application data.

**Scheduled Task**
A Windows mechanism for running programs at defined times or events. The EA DLC Unlocker creates a scheduled task (`copy_dlc_unlocker`) to ensure the unlocker DLL is re-applied when the EA app updates itself and potentially overwrites the modified file.

**xdelta3**
An open-source binary delta compression tool. Sims 4 update patches are stored in xdelta3 format, and the application uses a bundled xdelta3 binary to apply them during the patch step.

---

## 17. Disclaimer

**THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.**

By using this software, you acknowledge and agree to the following:

**No liability.** The author(s) and contributor(s) of this software shall not be held liable for any damages, losses, data corruption, account bans, legal consequences, or any other negative outcomes arising from the use, misuse, or inability to use this software. This includes, but is not limited to, damage to game installations, loss of save data, violation of terms of service, or any other direct or indirect consequences.

**Use at your own risk.** This software interacts with game files, the Windows registry, and network resources. You are solely responsible for any changes made to your system. Always maintain backups of your game files and save data before using this tool.

**No affiliation.** This project is not affiliated with, endorsed by, or associated with Electronic Arts Inc., Maxis, Valve Corporation, or any other company. "The Sims" is a registered trademark of Electronic Arts Inc. All other trademarks are the property of their respective owners.

**Terms of service.** Using this software may violate the terms of service of The Sims 4, EA, Steam, or other platforms. You are solely responsible for understanding and complying with all applicable terms of service and laws in your jurisdiction.

**No guarantee of functionality.** This software is provided for educational and personal use purposes. There is no guarantee that it will work with any specific version of the game, and it may cease to function at any time due to game updates, EA service changes, or other external changes.

**By downloading, installing, or using this software, you accept full responsibility for your actions and agree that the author(s) cannot be held liable for any consequences.**

---

*Sims 4 Updater v2.0.8 — User Guide*
*Document prepared: February 2026*
