# CDN Infrastructure — Technical Reference

**Project**: The Sims 4 Updater
**CDN Domain**: cdn.example.com
**Last Updated**: 2026-02-22
**Applies to:** Sims 4 Updater v2.3.0

---

## Table of Contents

1. [Overview](#1-overview)
2. [Component Reference](#2-component-reference)
   - [Cloudflare Worker](#21-cloudflare-worker-workerjs)
   - [Cloudflare KV Namespace](#22-cloudflare-kv-namespace-cdn_routes)
   - [Backend Seedbox](#23-backend-seedbox)
3. [URL Structure](#3-url-structure)
4. [Environment Secrets and Configuration](#4-environment-secrets-and-configuration)
   - [Worker Environment Secrets](#41-worker-environment-secrets)
   - [cdn_config.json](#42-cdn_configjson)
   - [CDN Manager Config](#43-cdn-manager-config)
5. [CDN Manager GUI](#5-cdn-manager-gui)
6. [Manifest Format](#6-manifest-format)
7. [App Download Flow](#7-app-download-flow)
8. [Deployment Guide](#8-deployment-guide)
9. [CDN Access Control & Authentication](#9-cdn-access-control--authentication)
10. [Troubleshooting](#10-troubleshooting)
11. [Cost Breakdown](#11-cost-breakdown)

---

## 1. Overview

The Sims 4 Updater distributes game patches and DLC content through a CDN proxy built on Cloudflare Workers and a backend seedbox. The CDN layer decouples the public-facing download URLs from the backend storage infrastructure, provides global edge caching, and prevents direct exposure of seedbox credentials or internal paths.

> **Seedbox flexibility**: Any seedbox or server that supports **SFTP upload** and **HTTP/HTTPS download** can be used as the storage backend. The CDN Manager connects via SFTP (paramiko) for file uploads, and the Cloudflare Worker proxies HTTP downloads to clients. Compatible providers include Whatbox, RapidSeedbox, Ultraseedbox, Seedbox.io, or any VPS/dedicated server running SSH + a web server. Configure your provider's credentials in `cdn_config.json`.

### Architecture Diagram

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                         User's Machine                              │
 │                                                                     │
 │  Sims4Updater.exe                                                   │
 │  ┌───────────────────────────────────────────────────────────────┐  │
 │  │  PatchClient.fetch_manifest()                                 │  │
 │  │  DLCDownloader.download()                                     │  │
 │  │  Downloader.download_file() ← HTTP resume + MD5 verify       │  │
 │  └───────────────────────────────────────────────────────────────┘  │
 └───────────────────────────────┬─────────────────────────────────────┘
                                 │  HTTPS GET cdn.example.com/dlc/EP01.zip
                                 ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │                    Cloudflare Edge Network                          │
 │                                                                     │
 │  ┌─────────────────────┐       ┌─────────────────────────────────┐  │
 │  │   Cloudflare DNS    │──────▶│      Cloudflare Worker          │  │
 │  │  cdn.example.com │       │      worker.js                  │  │
 │  │  AAAA → 100:: (proxy│       │                                 │  │
 │  │  enabled)           │       │  1. Strip leading slash         │  │
 │  └─────────────────────┘       │  2. KV lookup: CDN_ROUTES[path] │  │
 │                                │  3. Build seedbox URL           │  │
 │  ┌─────────────────────┐       │  4. Basic Auth fetch            │  │
 │  │  KV Namespace       │◀──────│  5. Stream response + headers   │  │
 │  │  CDN_ROUTES         │       └───────────────┬─────────────────┘  │
 │  │                     │                       │                    │
 │  │  "dlc/EP01.zip"     │                       │  HTTPS + Basic Auth│
 │  │  → "files/sims4/    │                       │  (Worker secrets)  │
 │  │    dlc/EP01.zip"    │                       ▼                    │
 │  └─────────────────────┘       ┌─────────────────────────────────┐  │
 │                                │      Backend Seedbox             │  │
 │                                │  your-seedbox.example.com        │  │
 │                                │                                 │  │
 │                                │  files/sims4/                   │  │
 │                                │    dlc/     ← DLC ZIPs          │  │
 │                                │    patches/ ← Binary deltas     │  │
 │                                │    language/← Locale archives   │  │
 │                                └─────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────┘
```

### How the Proxy Works

When a user's app requests `https://cdn.example.com/dlc/EP01.zip`, the following chain executes entirely within the Cloudflare edge before any bytes from the file reach the client:

1. **DNS resolution** routes the request to the nearest Cloudflare PoP (point of presence) via the Anycast network.
2. **The Worker intercepts** the request before any origin fetch occurs.
3. **KV lookup**: the Worker reads `CDN_ROUTES["dlc/EP01.zip"]`, receiving the value `files/sims4/dlc/EP01.zip`.
4. **Seedbox fetch**: the Worker constructs `https://server.whatbox.ca/private/files/sims4/dlc/EP01.zip` and issues an internal request using HTTP Basic Auth credentials stored as Worker secrets (never exposed to clients).
5. **Response streaming**: the seedbox response body is streamed directly back to the client with sanitized headers (Content-Type, Content-Length, Accept-Ranges, Cache-Control, CORS, Content-Disposition). Server-identifying headers such as `Server` and `X-Powered-By` are stripped.

### Why This Architecture

| Concern | How It Is Addressed |
|---|---|
| Seedbox credentials must not leak | Credentials live only in Worker environment secrets; clients never see them |
| Storage paths may change | KV routing table decouples public URLs from backend paths |
| Direct seedbox exposure is undesirable | No public route to the seedbox; Worker is the only authorized caller |
| Global delivery performance | Cloudflare's 300+ PoP network serves cached responses from edge |
| Resumable downloads | `Accept-Ranges` passed through; clients can issue `Range` requests |
| CORS for potential web clients | Worker injects `Access-Control-Allow-Origin: *` |
| Cache freshness | `Cache-Control: public, max-age=86400` (24 h) for stable files |
| Cost | Cloudflare free tier handles 100K requests/day at zero marginal cost |

---

## 2. Component Reference

### 2.1 Cloudflare Worker (worker.js)

**Location**: `cloudflare-worker/worker.js`
**Scope**: Handles every inbound request to `cdn.example.com/*`

#### Request Handling Logic

```
Incoming request
       │
       ▼
  Strip leading "/"
  from request.url.pathname
       │
       ▼
  KV lookup: CDN_ROUTES.get(cleanPath)
       │
       ├─── null ──▶ Return HTTP 404 {"error": "Not found"}
       │
       └─── value ──▶ Build seedboxUrl = SEEDBOX_BASE_URL + "/" + seedboxPath
                            │
                            ▼
                      fetch(seedboxUrl, {
                        headers: {
                          Authorization: "Basic " + btoa(USER:PASS)
                        }
                      })
                            │
                            ├─── non-2xx ──▶ Forward error status
                            │
                            └─── 2xx ──▶ Stream body back with clean headers
```

#### Response Headers Set by the Worker

| Header | Value | Purpose |
|---|---|---|
| `Content-Type` | Forwarded from seedbox | MIME type for client |
| `Content-Length` | Forwarded from seedbox | Download progress reporting |
| `Accept-Ranges` | `bytes` | Enables HTTP resume |
| `Cache-Control` | `public, max-age=86400` | 24-hour edge caching |
| `Access-Control-Allow-Origin` | `*` | CORS for browser clients |
| `Content-Disposition` | `attachment; filename="<basename>"` | Browser save dialog filename |

#### Headers Removed by the Worker

| Header | Reason |
|---|---|
| `Server` | Prevents identification of seedbox software stack |
| `X-Powered-By` | Prevents identification of Apache/PHP version |

#### Worker Pseudocode

```javascript
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Strip leading slash → clean path used as KV key
    const cleanPath = url.pathname.replace(/^\//, "");
    if (!cleanPath) {
      return new Response(JSON.stringify({ error: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    // KV routing: CDN_ROUTES["dlc/EP01.zip"] → "files/sims4/dlc/EP01.zip"
    const seedboxPath = await env.CDN_ROUTES.get(cleanPath);
    if (!seedboxPath) {
      return new Response(JSON.stringify({ error: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Authenticate with seedbox using environment secrets
    const seedboxUrl = `${env.SEEDBOX_BASE_URL}/${seedboxPath}`;
    const credentials = btoa(`${env.SEEDBOX_USER}:${env.SEEDBOX_PASS}`);

    const upstream = await fetch(seedboxUrl, {
      headers: { Authorization: `Basic ${credentials}` },
    });

    if (!upstream.ok) {
      return new Response(upstream.body, { status: upstream.status });
    }

    // Build clean response — strip identifying headers, add CORS + caching
    const filename = seedboxPath.split("/").pop();
    const responseHeaders = new Headers();
    for (const [k, v] of upstream.headers.entries()) {
      if (!["server", "x-powered-by"].includes(k.toLowerCase())) {
        responseHeaders.set(k, v);
      }
    }
    responseHeaders.set("Cache-Control", "public, max-age=86400");
    responseHeaders.set("Access-Control-Allow-Origin", "*");
    responseHeaders.set("Content-Disposition", `attachment; filename="${filename}"`);
    responseHeaders.set("Accept-Ranges", "bytes");

    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  },
};
```

> **Note**: The actual `worker.js` at `cloudflare-worker/worker.js` is the authoritative source. The pseudocode above documents intent and is kept in sync with any structural changes.

---

### 2.2 Cloudflare KV Namespace (CDN_ROUTES)

The KV namespace acts as the routing table between public CDN paths and internal seedbox paths. This indirection means you can reorganize the seedbox directory structure without changing any URLs that clients have cached or hardcoded.

#### Key-Value Schema

| Key (CDN path) | Value (seedbox path) |
|---|---|
| `manifest.json` | `files/sims4/manifest.json` |
| `dlc/EP01.zip` | `files/sims4/dlc/EP01.zip` |
| `dlc/GP05.zip` | `files/sims4/dlc/GP05.zip` |
| `patches/1.121.372.1020_to_1.122.100.1020.zip` | `files/sims4/patches/1.121.372.1020_to_1.122.100.1020.zip` |
| `language/de_DE.zip` | `files/sims4/language/de_DE.zip` |

#### KV Limits (Free Tier)

| Resource | Free Tier Limit |
|---|---|
| KV reads | 100,000 / day |
| KV writes | 1,000 / day |
| KV storage | 1 GB |
| KV value size | 25 MB (text only; paths are well under this) |

For a typical deployment (< 200 DLC entries, read by at most tens of thousands of daily users), the free tier is sufficient.

#### Managing KV Entries

Entries are managed via:

- **CDN Manager GUI** — the KV Routes tab provides add/delete/list operations (see Section 5)
- **Cloudflare dashboard** → Workers & Pages → KV → CDN_ROUTES namespace (manual editing)

---

### 2.3 Backend Seedbox

The backend storage is a seedbox or server that provides both SFTP and HTTPS access to the same file tree. Any provider that supports SFTP upload and HTTP/HTTPS download can be used — Whatbox, RapidSeedbox, Ultraseedbox, Seedbox.io, or a self-hosted VPS with SSH and a web server (e.g., nginx).

#### Access Methods

| Protocol | Purpose | Port | Auth |
|---|---|---|---|
| SFTP | File upload from upload scripts | 22 | Username + password |
| HTTPS | File download by the Worker | 443 | HTTP Basic Auth |

#### Directory Layout on Seedbox

```
files/
└── sims4/
    ├── manifest.json          # Master manifest (managed by CDN Manager)
    ├── dlc/
    │   ├── EP01.zip           # Expansion Pack 01 archive
    │   ├── EP02.zip
    │   │   ...
    │   ├── GP01.zip           # Game Pack 01 archive
    │   │   ...
    │   ├── SP01.zip           # Stuff Pack 01 archive
    │   │   ...
    │   ├── FP01.zip           # Free Pack archive
    │   │   ...
    │   └── KIT01.zip          # Kit archive
    ├── patches/
    │   └── {from}_to_{to}.zip # Binary delta patch archive
    └── language/
        └── {locale_code}.zip  # Language file archive (e.g., de_DE.zip)
```

All upload scripts write into `files/sims4/` on the seedbox. The Worker's `SEEDBOX_BASE_URL` must point to the parent directory that contains this tree (e.g., `https://your-seedbox.example.com/private`), so that the full resolved URL becomes `https://your-seedbox.example.com/private/files/sims4/dlc/EP01.zip`.

---

## 3. URL Structure

All content is served from `https://cdn.example.com/`. The URL space is organized into four top-level paths:

```
cdn.example.com/
│
├── manifest.json
│     The master manifest. Fetched by the app on startup.
│     Contains patch graph, DLC download entries, and fingerprints.
│
├── dlc/
│   ├── EP01.zip  →  EP14.zip      Expansion Packs
│   ├── GP01.zip  →  GP12.zip      Game Packs
│   ├── SP01.zip  →  SP22.zip      Stuff Packs
│   ├── FP01.zip  →  FP03.zip      Free Packs
│   └── KIT01.zip → ...            Kits
│
├── patches/
│   └── {from_version}_to_{to_version}.zip
│         Binary delta patch. The {from_version} and {to_version} strings
│         are full version numbers in the format:
│           major.minor.patch.build  (e.g., 1.121.372.1020)
│         Example: 1.121.372.1020_to_1.122.100.1020.zip
│
└── language/
    └── {locale_code}.zip
          Language-specific game file archive.
          Locale code matches The Sims 4 locale identifiers:
            en_US, de_DE, fr_FR, es_ES, pt_BR, ...
```

### URL Permanence

Once a DLC or patch URL is published in a `manifest.json`, it must remain accessible at that path indefinitely (or until the manifest is updated). Clients may cache the URL from a previously fetched manifest. Removing a KV entry for an active URL will cause 404 errors for users whose manifests have not yet refreshed.

---

## 4. Environment Secrets and Configuration

### 4.1 Worker Environment Secrets

These are set in the Cloudflare dashboard under **Workers & Pages → your-worker → Settings → Variables**. They are encrypted at rest and never visible after being set.

| Secret Name | Example Value | Description |
|---|---|---|
| `SEEDBOX_BASE_URL` | `https://your-seedbox.example.com/private` | Base HTTPS URL of your seedbox file server. No trailing slash. |
| `SEEDBOX_USER` | `myusername` | Seedbox account username for HTTP Basic Auth |
| `SEEDBOX_PASS` | `s3cur3password` | Seedbox account password for HTTP Basic Auth |

Additionally, a **KV namespace binding** must be configured:

| Binding Name | Bound To |
|---|---|
| `CDN_ROUTES` | The KV namespace ID created in Step 2 of the Deployment Guide |

The binding name `CDN_ROUTES` is what `env.CDN_ROUTES.get(key)` references in the Worker code.

---

### 4.2 cdn_config.json

**Location**: `cloudflare-worker/cdn_config.json`
**Tracked by git**: No — this file MUST be in `.gitignore` and never committed.
**Template**: `cloudflare-worker/cdn_config.example.json`

This file provides credentials to the CDN Manager GUI application. It is read at startup and never used by the deployed Worker.

```json
{
  "whatbox_host": "your-seedbox-host.example.com",
  "whatbox_port": 22,
  "whatbox_user": "your-username",
  "whatbox_pass": "your-password",
  "cloudflare_account_id": "abcdef1234567890abcdef1234567890",
  "cloudflare_api_token": "your-cloudflare-api-token-here",
  "cloudflare_kv_namespace_id": "abcdef1234567890abcdef1234567890"
}
```

#### Field Reference

| Field | Description | Where to Find It |
|---|---|---|
| `whatbox_host` | Seedbox SFTP hostname | Your seedbox provider's control panel |
| `whatbox_port` | SFTP port (almost always 22) | Your seedbox provider's control panel |
| `whatbox_user` | Seedbox username | Your seedbox provider's control panel |
| `whatbox_pass` | Seedbox password | Your seedbox provider's control panel |
| `cloudflare_account_id` | Cloudflare account ID | Cloudflare dashboard → right sidebar |
| `cloudflare_api_token` | API token with KV edit permissions | Cloudflare dashboard → My Profile → API Tokens |
| `cloudflare_kv_namespace_id` | KV namespace ID for CDN_ROUTES | Cloudflare dashboard → Workers & Pages → KV |

#### Creating a Cloudflare API Token

The token needs the following permissions:
- **Account** → Cloudflare Workers KV Storage → Edit
- **Zone** → (none required for KV operations)

Do not grant broader permissions than necessary. A token scoped only to KV write is sufficient.

---

### 4.3 CDN Manager Config

**Location**: `cloudflare-worker/cdn_manager_config.json` (created by CDN Manager Settings tab)
**Tracked by git**: No — should be in `.gitignore`

The CDN Manager stores its own configuration (game directory, upload preferences) in this file. It is separate from `cdn_config.json` (which holds credentials).

---

## 5. CDN Manager GUI

**Location**: `cloudflare-worker/cdn_manager/`
**Executable**: `CDNManager.exe` (built via `cdn_manager.spec`)

The CDN Manager is a standalone CustomTkinter GUI application that provides all CDN management operations through a tabbed interface. It replaces the previous standalone Python scripts (`cdn_upload.py`, `cdn_pack_upload.py`, etc.).

### Running the CDN Manager

```bash
# From source
cd cloudflare-worker
python -m cdn_manager

# Build the exe
cd cloudflare-worker
pyinstaller --clean --noconfirm cdn_manager.spec
# Output: dist/CDNManager.exe
```

Requires `cdn_config.json` in the `cloudflare-worker/` directory (copy from `cdn_config.example.json`).

### GUI Tabs

| Tab | Backend Module | Purpose |
|---|---|---|
| Dashboard | — | Connection status, seedbox storage overview |
| DLC Upload | `backend/dlc_ops.py` | Package DLC files into ZIPs and upload to seedbox via SFTP |
| Language Upload | `backend/lang_ops.py` | Package and upload language locale archives |
| Patch Upload | `backend/patch_ops.py` | Create and upload binary delta patches |
| Manifest | `backend/manifest_ops.py` | Edit, merge, and publish `manifest.json` |
| KV Routes | `backend/connection.py` | Add, delete, and list Cloudflare KV route entries |
| Archives | `backend/archive_ops.py` | Manage archived versions and content |
| Settings | `config.py` | Configure credentials and preferences |

### Architecture

```
cloudflare-worker/cdn_manager/
├── __main__.py              # Entry point
├── app.py                   # App(ctk.CTk) — main window, sidebar, threading
├── config.py                # CDN Manager settings
├── theme.py                 # Colors, fonts, sizing
├── components.py            # Shared UI components
├── animations.py            # Animation utilities
├── backend/
│   ├── connection.py        # SFTP + Cloudflare KV connection management
│   ├── dlc_ops.py           # DLC packaging + upload pipeline
│   ├── lang_ops.py          # Language pack upload pipeline
│   ├── patch_ops.py         # Patch creation + upload pipeline
│   ├── manifest_ops.py      # Manifest editing + publishing
│   └── archive_ops.py       # Archive management operations
└── frames/
    ├── dashboard_frame.py   # Overview tab
    ├── dlc_frame.py         # DLC upload tab
    ├── language_frame.py    # Language upload tab
    ├── patch_frame.py       # Patch upload tab
    ├── manifest_frame.py    # Manifest editor tab
    ├── kv_frame.py          # KV route management tab
    ├── archive_frame.py     # Archive management tab
    └── settings_frame.py    # Settings tab
```

### Upload Pipeline

Each upload (DLC, language, or patch) follows this pipeline through the GUI with live progress:

1. Package content into a ZIP archive
2. Compute MD5 hash of the archive
3. Upload ZIP to seedbox via SFTP (with progress bar)
4. Register KV route (CDN path → seedbox path) via Cloudflare API
5. Update `manifest.json` with the new entry

### SFTP Performance

The CDN Manager uses optimized Paramiko settings for full-speed SFTP transfers:

```python
transport.default_window_size = paramiko.common.MAX_WINDOW_SIZE
transport.packetizer.REKEY_BYTES = pow(2, 40)
transport.packetizer.REKEY_PACKETS = pow(2, 40)
```

This ensures 10-50 MB/s throughput instead of the default ~1 MB/s caused by conservative TCP window sizes.

---

## 6. Manifest Format

The manifest is the central configuration document that the app fetches on startup from `https://cdn.example.com/manifest.json`. It tells the app:

- What the latest game version is
- What patch archives exist and how they connect (the patch graph)
- What DLC archives are available for download
- What language archives are available
- Version fingerprints for version detection

### Full Schema

```json
{
  "latest": "1.122.100.1020",
  "game_latest": "1.122.100.1020",
  "patches": [
    {
      "from": "1.121.372.1020",
      "to": "1.122.100.1020",
      "url": "https://cdn.example.com/patches/1.121.372.1020_to_1.122.100.1020.zip",
      "size": 892341234,
      "md5": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
    }
  ],
  "dlc_downloads": {
    "EP01": {
      "url": "https://cdn.example.com/dlc/EP01.zip",
      "size": 1706434567,
      "md5": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
      "filename": "EP01.zip"
    },
    "GP05": {
      "url": "https://cdn.example.com/dlc/GP05.zip",
      "size": 523412345,
      "md5": "B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5",
      "filename": "GP05.zip"
    }
  },
  "language_downloads": {
    "de_DE": {
      "url": "https://cdn.example.com/language/de_DE.zip",
      "size": 134567890,
      "md5": "C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6",
      "filename": "de_DE.zip"
    }
  },
  "fingerprints": {
    "1.122.100.1020": {
      "GameVersion.dll": "A1B2C3D4E5F6..."
    }
  }
}
```

### Field Reference

| Field | Type | Description |
|---|---|---|
| `latest` | `string` | Latest available version string. If empty string, the manifest is treated as DLC-only (no game patches available). |
| `game_latest` | `string` | Same as `latest`; present for backward compatibility. |
| `patches` | `array` | List of available patch archives. Each entry describes a directed edge in the patch graph (BFS planner uses this). |
| `patches[].from` | `string` | Source version for this patch |
| `patches[].to` | `string` | Target version for this patch |
| `patches[].url` | `string` | Full CDN URL of the patch archive |
| `patches[].size` | `int` | Archive size in bytes |
| `patches[].md5` | `string` | MD5 hex digest for integrity verification |
| `dlc_downloads` | `object` | Map of pack ID → `DLCDownloadEntry`. Consumed by the DLC Downloader tab. |
| `dlc_downloads[id].url` | `string` | Full CDN URL of the DLC archive |
| `dlc_downloads[id].size` | `int` | Archive size in bytes |
| `dlc_downloads[id].md5` | `string` | MD5 hex digest |
| `dlc_downloads[id].filename` | `string` | Filename to use when saving (usually `{id}.zip`) |
| `language_downloads` | `object` | Map of locale code → download entry (same schema as `dlc_downloads`) |
| `fingerprints` | `object` | Map of version string → file hash map. Used by `VersionDetector` to identify installed version. |

### DLC-Only Manifest

If `latest` is `""` (empty string), `PatchClient` treats the manifest as DLC-only: no game patch check is performed, and the update button in the home frame is hidden. The `dlc_downloads` section is still parsed and shown in the DLC Downloader tab.

This is useful when the CDN is used purely for DLC distribution without hosting game patches.

---

## 7. App Download Flow

This section traces the code path from user interaction to a downloaded, installed DLC.

### Step-by-Step Flow

```
User opens DLC Downloader tab
         │
         ▼
DownloaderFrame.on_show()
   [gui/frames/downloader_frame.py]
         │
         ▼  run_async()
PatchClient.fetch_manifest(manifest_url)
   [patch/client.py]
   → GET https://cdn.example.com/manifest.json
   → parse_manifest(json_text)  [patch/manifest.py]
   → returns Manifest(dlc_downloads={...}, ...)
         │
         ▼
DownloaderFrame populates DLC list
   For each DLCDownloadEntry:
     → Show pack name, size, MD5
     → Check if already installed (DLCCatalog)
     → Show "Download" or "Installed" button
         │
         ▼  User clicks "Download" for EP01
         │
         ▼  run_async() / dedicated Thread
DLCDownloader.download(entry, game_dir, callbacks)
   [dlc/downloader.py]
         │
         ├──▶ Downloader.download_file(url, dest_path, callbacks)
         │      [patch/downloader.py]
         │      → HTTP GET with Range header (resume support)
         │      → Write chunks to temp file
         │      → Verify MD5 on completion
         │      → Rename temp → final ZIP path
         │
         ├──▶ Extract ZIP to game directory
         │      → ZipFile.extractall(game_dir)
         │
         ├──▶ Delete ZIP archive (cleanup)
         │
         └──▶ Register DLC in crack config
                → DLCManager.enable_dlc(dlc_id)
                  [dlc/manager.py]
                  → detect_format() → appropriate DLCConfigAdapter
                  → adapter.set_dlc_state(dlc_id, enabled=True)
```

### Key Source Files

| File | Role |
|---|---|
| `src/sims4_updater/patch/manifest.py` | `DLCDownloadEntry` dataclass and `parse_manifest()` function |
| `src/sims4_updater/patch/client.py` | `PatchClient.fetch_manifest()` — HTTP fetch + JSON parse |
| `src/sims4_updater/patch/downloader.py` | `Downloader.download_file()` — chunked HTTP download with resume and MD5 verification |
| `src/sims4_updater/dlc/downloader.py` | `DLCDownloader` — orchestrates download → extract → register pipeline |
| `src/sims4_updater/gui/frames/downloader_frame.py` | `DownloaderFrame` — GUI for the DLC Downloader tab |

### HTTP Resume Mechanism

`Downloader.download_file()` supports resuming interrupted downloads using the `Range` HTTP header:

1. If a partial download file exists at the destination, its size is read.
2. The next request includes `Range: bytes=<existing_size>-`.
3. The server (seedbox via the Worker) returns HTTP 206 Partial Content.
4. The downloader appends to the existing file rather than overwriting.
5. After the final byte is received, MD5 is computed over the complete file and compared against `DLCDownloadEntry.md5`. A mismatch causes the download to be deleted and retried from zero.

This mechanism relies on the Worker correctly forwarding the `Accept-Ranges: bytes` header from the seedbox, which it does explicitly.

---

## 8. Deployment Guide

This section covers standing up a new CDN instance from scratch. Follow these steps in order.

### Prerequisites

- A domain name you control (to create a subdomain like `cdn.yourdomain.com`)
- A Cloudflare account (free tier is sufficient)
- A seedbox subscription or server with SFTP + HTTPS access (e.g., Whatbox, RapidSeedbox, Ultraseedbox, or any VPS)
- Python 3.12+ with `paramiko` and `requests` installed
- The DLC files from a licensed game installation

---

### Step 1 — Add Your Domain to Cloudflare

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com).
2. Click **Add a Site** and enter your domain.
3. Follow the nameserver instructions to point your domain's DNS to Cloudflare.
4. Wait for propagation (typically 5–30 minutes).

If you already manage your domain in Cloudflare, skip this step.

---

### Step 2 — Create the KV Namespace

1. In the Cloudflare dashboard, go to **Workers & Pages → KV**.
2. Click **Create a namespace**.
3. Name it `CDN_ROUTES`.
4. Note the **Namespace ID** shown after creation — you will need it in `cdn_config.json`.

---

### Step 3 — Deploy the Worker

1. In the Cloudflare dashboard, go to **Workers & Pages → Create Application → Create Worker**.
2. Give it a name (e.g., `sims4-cdn`).
3. Click **Deploy** to create the worker with placeholder code.
4. Click **Edit code** and paste in the contents of `cloudflare-worker/worker.js`.
5. Click **Deploy** again to push the real code.

---

### Step 4 — Add DNS Record for the CDN Subdomain

1. Go to your domain's **DNS** settings in Cloudflare.
2. Add a new **AAAA** record:
   - **Name**: `cdn` (creates `cdn.yourdomain.com`)
   - **IPv6 address**: `100::` (a reserved, non-routable address — Cloudflare intercepts it)
   - **Proxy status**: Proxied (orange cloud)
3. Save the record.

> The `100::` address is intentionally a dummy. Because the record is proxied, Cloudflare intercepts all requests at the edge and routes them to the Worker before any connection attempt is made to `100::`.

---

### Step 5 — Add the Worker Route

1. Go to **Workers & Pages → your-worker → Settings → Triggers**.
2. Under **Routes**, click **Add route**.
3. Enter: `cdn.yourdomain.com/*`
4. Select your zone (domain).
5. Save.

---

### Step 6 — Configure Worker Environment

#### KV Binding

1. Go to **Workers & Pages → your-worker → Settings → Variables**.
2. Under **KV Namespace Bindings**, click **Add binding**.
3. Variable name: `CDN_ROUTES`
4. KV Namespace: select `CDN_ROUTES` from the dropdown.
5. Save.

#### Environment Secrets

Still under **Variables**, in the **Environment Variables** section:

1. Add `SEEDBOX_BASE_URL` → your seedbox HTTPS base URL (e.g., `https://your-seedbox.example.com/private`)
   - Mark as **Secret**.
2. Add `SEEDBOX_USER` → your seedbox username.
   - Mark as **Secret**.
3. Add `SEEDBOX_PASS` → your seedbox password.
   - Mark as **Secret**.
4. Click **Save and Deploy**.

---

### Step 7 — Create cdn_config.json

Copy the example file and fill in your credentials:

```bash
cp cloudflare-worker/cdn_config.example.json cloudflare-worker/cdn_config.json
```

Edit `cdn_config.json` with your actual values:

```json
{
  "whatbox_host": "your-server.whatbox.ca",
  "whatbox_port": 22,
  "whatbox_user": "your_username",
  "whatbox_pass": "your_password",
  "cloudflare_account_id": "your_account_id",
  "cloudflare_api_token": "your_api_token",
  "cloudflare_kv_namespace_id": "your_kv_namespace_id"
}
```

Verify that `cdn_config.json` is listed in `.gitignore` before proceeding.

---

### Step 8 — Upload All DLCs

Launch the CDN Manager from a machine with the game installed:

```bash
cd cloudflare-worker
python -m cdn_manager
```

Use the DLC Upload tab to:
1. Select the game directory.
2. Package each DLC into a ZIP archive.
3. Upload each archive to the seedbox via SFTP.
4. Register each KV route.
5. Generate and upload `manifest.json` via the Manifest tab.

This process takes 30–120 minutes depending on connection speed and the number of DLCs.

---

### Step 9 — Point the App at Your CDN

Update `manifest_url` in the app's settings to:
```
https://cdn.yourdomain.com/manifest.json
```

Or update the default in `src/sims4_updater/constants.py` if you are maintaining a fork.

---

### Step 10 — Verify the Deployment

```bash
# Check manifest is served
curl -I https://cdn.yourdomain.com/manifest.json

# Check a DLC archive is served
curl -I https://cdn.yourdomain.com/dlc/EP01.zip

# Check a missing path returns 404
curl -I https://cdn.yourdomain.com/nonexistent

# Or verify via the CDN Manager's KV Routes tab
```

Expected output for a successful check:
```
HTTP/2 200
content-type: application/zip
content-length: 1706434567
accept-ranges: bytes
cache-control: public, max-age=86400
access-control-allow-origin: *
```

---

## 9. CDN Access Control & Authentication

The CDN implements server-side access control using JWT session tokens, a ban system, and optional private CDN mode with access request workflows.

### Authentication Flow

```
Client                          API Worker                      CDN Worker
  │                                 │                               │
  ├─ POST /auth/token ─────────────>│                               │
  │  {machine_id, uid, app_version} │                               │
  │                                 ├─ Check bans (IP/machine/UID)  │
  │                                 ├─ Check allowlist (private CDN) │
  │                                 ├─ Generate JWT (1hr, HS256)    │
  │<─────────── {token, expires_in} │                               │
  │                                 │                               │
  ├─ GET /dlc/EP01.zip ──────────────────────────────────────────────>│
  │  Authorization: Bearer {jwt}    │                               ├─ Verify JWT signature
  │  X-Machine-Id: {machine_id}     │                               ├─ Check ban list
  │                                 │                               ├─ Proxy to seedbox
  │<─────────────────── file stream │                               │
```

### JWT Token Format

Tokens use HMAC-SHA256 with a shared secret (`JWT_SECRET` env var on both workers).

**Payload:**

```json
{
  "machine_id": "a1b2c3d4e5f6...",
  "uid": "user-123",
  "ip": "1.2.3.4",
  "iat": 1708700000,
  "exp": 1708703600
}
```

Tokens expire after 1 hour. The client's `CDNTokenAuth` adapter auto-refreshes when < 60 seconds remain before each HTTP request.

### Client-Side Modules

| Module | Purpose |
| --- | --- |
| `core/machine_id.py` | Generates deterministic machine fingerprint: `SHA256("sims4updater-v1:" + MachineGuid)[:32]` from Windows registry |
| `core/identity.py` | Configures `X-Machine-Id` and `X-UID` headers, injected into all CDN HTTP requests |
| `core/cdn_auth.py` | `CDNAuth` manages token lifecycle; `CDNTokenAuth(AuthBase)` auto-refreshes per HTTP request |

### Ban System

Bans can target IP addresses, machine IDs, or UIDs. Both permanent and temporary (with expiry) bans are supported.

**Supabase tables:**

- `bans` — All bans with type, value, reason, permanent flag, expiry
- `active_bans` view — Filters out expired temporary bans
- `bans_summary` view — Aggregated stats (active, permanent, temp, expired, unbanned)

**Ban check order:** IP → Machine ID → UID. First match blocks the request.

### Private CDN Mode

When `cdn_access` is set to `"private"` (via admin dashboard or Supabase `cdn_settings` table):

1. Token requests from unknown machines return `403 access_required`
2. Client shows an access request dialog with a reason field
3. Request stored in `access_requests` table (status: pending)
4. Admin reviews via `/admin/access` dashboard — approve or deny (single or bulk)
5. Approved machines added to `cdn_allowlist` table
6. On next token request, the machine gets a valid JWT

### Admin Dashboards

Four password-protected dashboards (`?pw=ADMIN_PASSWORD`):

| Dashboard | Route | Features |
| --- | --- | --- |
| Analytics | `/admin/stats` | Online users, version stats, crack formats, DLC popularity, download volume |
| Contributions | `/admin` | DLC + GreenLuma contribution review and approval |
| Bans | `/admin/bans` | Create/remove bans, connected clients table, CDN access mode toggle, ban from client list |
| Access | `/admin/access` | Access request review with status filters, search, bulk approve/deny with checkboxes |

All dashboards share a navigation bar and auto-refresh every 30 seconds.

### Token Logging

Every token request is logged to the `token_log` table with an upsert trigger:

- Tracks: machine_id, uid, ip, app_version, request_count, first_seen, last_seen
- Visible in the Bans dashboard "Connected Clients" section
- Admins can ban directly from the client list

### Supabase Schema

| Table | Primary Key | Purpose |
| --- | --- | --- |
| `bans` | `id` (auto) | Ban records (type, value, reason, permanent, expires_at, active) |
| `access_requests` | `id` (auto) | Access request queue (machine_id, uid, reason, status, reviewed_at) |
| `cdn_allowlist` | `machine_id` | Approved machines for private CDNs |
| `cdn_settings` | `key` | Dynamic config key-value store (e.g., cdn_access: public/private) |
| `token_log` | `machine_id` | Client connection tracking with upsert trigger for request counting |

### Worker Environment Variables

**CDN Worker (`worker.js`):**

| Variable | Type | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | Secret | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Secret | Supabase service_role key |
| `JWT_SECRET` | Secret | Shared HMAC-SHA256 signing key |

**API Worker (`api-worker.js`):**

| Variable | Type | Purpose |
| --- | --- | --- |
| `JWT_SECRET` | Secret | Same shared signing key as CDN worker |
| `ADMIN_PASSWORD` | Secret | Password for admin dashboards |
| `DISCORD_WEBHOOK` | Secret | Discord webhook for ban/access notifications |
| `SUPABASE_URL` | Secret | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Secret | Supabase service_role key |
| `CDN_ACCESS` | Var | Default access mode ("public" or "private") |
| `CDN_NAME` | Var | CDN display name |

### API Endpoints

**Public (no auth):**

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/token` | Request JWT session token |
| POST | `/access/request` | Submit access request (private CDNs) |

**Admin (password-protected):**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/admin/bans` | Ban management dashboard |
| GET | `/admin/bans/api` | List all bans + summary |
| POST | `/admin/bans/create` | Create a ban |
| POST | `/admin/bans/remove/:id` | Remove a ban |
| GET | `/admin/access` | Access request dashboard |
| GET | `/admin/access/api` | List all access requests |
| POST | `/admin/access/approve/:id` | Approve single request |
| POST | `/admin/access/deny/:id` | Deny single request |
| POST | `/admin/access/bulk` | Bulk approve/deny `{action, ids}` |
| GET | `/admin/settings/api` | Get CDN settings |
| POST | `/admin/settings/update` | Update a CDN setting |
| GET | `/admin/clients/api` | List connected clients |

---

## 10. Troubleshooting

### 502 Bad Gateway

**Symptom**: CDN returns HTTP 502 for a path that has a KV entry.

**Cause**: The KV value contains an incorrect seedbox path. The Worker builds the full URL as `SEEDBOX_BASE_URL + "/" + kv_value`. If the KV value is `dlc/EP01.zip` instead of `files/sims4/dlc/EP01.zip`, the constructed URL will point to a non-existent path on the seedbox, and the seedbox returns 404 or 403, which the Worker surfaces as 502.

**Fix**: Use the CDN Manager's KV Routes tab to check and correct the entry, or fix via the Cloudflare dashboard (Workers & Pages → KV → CDN_ROUTES).

---

### 404 Not Found from CDN

**Symptom**: CDN returns HTTP 404 for a path you expect to exist.

**Cause**: No KV entry for the requested path.

**Fix**: Use the CDN Manager's KV Routes tab to add the missing route entry.

---

### Upload Stuck at Low Speed (1 MB/s)

**Symptom**: SFTP uploads to the seedbox are capped at approximately 1 MB/s despite a fast local connection.

**Cause**: Paramiko (the Python SSH/SFTP library) uses a conservative TCP window size by default (32 KB), which severely limits throughput on high-latency connections.

**Fix**: Ensure the upload scripts set the window size before opening the SFTP connection:

```python
import paramiko
transport = paramiko.Transport((host, port))
transport.default_window_size = paramiko.common.MAX_WINDOW_SIZE
transport.packetizer.REKEY_BYTES = pow(2, 40)
transport.packetizer.REKEY_PACKETS = pow(2, 40)
transport.connect(username=user, password=password)
sftp = paramiko.SFTPClient.from_transport(transport)
```

This setting is already applied in the CDN Manager's backend (`connection.py`). If you encounter the symptom in a custom script, add the above lines.

---

### Worker Returns 401 / Seedbox Authentication Fails

**Symptom**: Worker returns HTTP 401 or 403, or the file is served but content looks like an HTML login page.

**Cause**: Incorrect `SEEDBOX_USER` or `SEEDBOX_PASS` Worker secrets, or the seedbox HTTPS URL requires a different path prefix.

**Fix**:
1. Verify credentials by testing the seedbox URL directly:
   ```bash
   curl -u "username:password" https://your-seedbox.example.com/private/files/sims4/manifest.json -I
   ```
2. If that fails, log in to your seedbox provider's control panel and confirm the HTTPS path.
3. Update the Worker secrets in the Cloudflare dashboard (**Workers & Pages → your-worker → Settings → Variables**).
4. Re-deploy the Worker (edit any line and save to trigger a re-deploy).

---

### KV Write Limit Exceeded

**Symptom**: CDN Manager reports KV write errors near the end of a large batch upload.

**Cause**: Cloudflare free tier allows 1,000 KV writes per day. A full upload of all packs (~50–100 DLCs) will consume 50–100 writes for DLC routes plus 1 for `manifest.json`.

**Fix**: This is within free tier limits for a normal deployment. If you are re-registering many routes repeatedly (e.g., running `--fresh` multiple times in one day), space out your runs across midnight UTC to reset the daily counter.

---

### App Cannot Fetch Manifest (Connection Refused / SSL Error)

**Symptom**: The app shows "Manifest fetch failed" on startup.

**Steps to diagnose**:
1. Confirm the DNS record is proxied in Cloudflare (orange cloud).
2. Confirm the Worker route is set to `cdn.yourdomain.com/*` (not a more specific path).
3. Test from a browser: `https://cdn.yourdomain.com/manifest.json`
4. Check the Worker's log in the Cloudflare dashboard (**Workers & Pages → your-worker → Logs**) for runtime errors.

---

## 11. Cost Breakdown

The CDN architecture is designed to operate within Cloudflare's free tier for typical usage volumes. The only non-free component is the seedbox.

| Service | Tier | Monthly Cost | Notes |
|---|---|---|---|
| Cloudflare DNS | Free | $0 | Domain routing via Anycast network |
| Cloudflare Worker | Free | $0 | 100,000 requests/day included; $5/mo for 10M req/day if you exceed it |
| Cloudflare KV Reads | Free | $0 | 100,000 reads/day included; $0.50 per million reads above that |
| Cloudflare KV Writes | Free | $0 | 1,000 writes/day included; $5 per million writes above that |
| Seedbox (any provider) | Paid | ~$5-15/mo | File hosting, HTTPS, SFTP; cost varies by provider and plan |
| **Total** | | **~$5-15/mo** | |

### Scaling Considerations

- **Worker requests**: Each file download involves one Worker invocation (the KV lookup is a sub-request, not a separate invocation). A deployment serving 1,000 users/day downloading 10 files each = 10,000 requests/day, well within the free tier.
- **KV reads**: Each Worker invocation does one KV read. Same calculation: 10,000 reads/day on a 100,000 limit.
- **Bandwidth**: Cloudflare does not charge for egress bandwidth from Workers to clients. The only bandwidth cost is the Worker-to-seedbox fetch, which is typically included in the seedbox subscription.
- **Seedbox storage**: A full DLC catalog (all expansion/game/stuff/kit packs) typically totals 40–80 GB. Verify your seedbox plan's storage quota before uploading.

If usage grows significantly beyond these estimates, upgrading to the Cloudflare Workers Paid plan ($5/month for 10M requests) is the first and likely only additional cost.

---

*This document describes the CDN infrastructure for The Sims 4 Updater. For related documentation, see:*

- *`Documentation/Architecture_and_Developer_Guide.md` — overall system architecture and module map*
- *`Documentation/DLC_Management_System.md` — DLC catalog, crack formats, and DLC manager internals*
- *`Documentation/DLC_Packer_and_Distribution.md` — DLC packer, ZIP format, and manifest generation*
- *`Documentation/Update_and_Patching_System.md` — version detection, patch planning, and download pipeline*
