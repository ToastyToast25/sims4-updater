# CDN Infrastructure — Technical Reference

**Project**: The Sims 4 Updater
**CDN Domain**: cdn.hyperabyss.com
**Last Updated**: 2026-02-21

---

## Table of Contents

1. [Overview](#1-overview)
2. [Component Reference](#2-component-reference)
   - [Cloudflare Worker](#21-cloudflare-worker-workerjs)
   - [Cloudflare KV Namespace](#22-cloudflare-kv-namespace-cdn_routes)
   - [Whatbox Seedbox](#23-whatbox-seedbox)
3. [URL Structure](#3-url-structure)
4. [Environment Secrets and Configuration](#4-environment-secrets-and-configuration)
   - [Worker Environment Secrets](#41-worker-environment-secrets)
   - [cdn_config.json](#42-cdn_configjson)
   - [upload_state.json](#43-upload_statejson-auto-generated)
5. [Upload Tools](#5-upload-tools)
   - [cdn_upload.py — Low-Level CLI](#51-cdn_uploadpy--low-level-cli)
   - [cdn_pack_upload.py — Batch DLC Uploader](#52-cdn_pack_uploadpy--batch-dlc-uploader)
   - [upload_all_dlcs.bat — Launcher Script](#53-upload_all_dlcsbat--launcher-script)
6. [Manifest Format](#6-manifest-format)
7. [App Download Flow](#7-app-download-flow)
8. [Deployment Guide](#8-deployment-guide)
9. [Troubleshooting](#9-troubleshooting)
10. [Cost Breakdown](#10-cost-breakdown)

---

## 1. Overview

The Sims 4 Updater distributes game patches and DLC content through a CDN proxy built on Cloudflare Workers and a private Whatbox seedbox. The CDN layer decouples the public-facing download URLs from the backend storage infrastructure, provides global edge caching, and prevents direct exposure of seedbox credentials or internal paths.

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
                                 │  HTTPS GET cdn.hyperabyss.com/dlc/EP01.zip
                                 ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │                    Cloudflare Edge Network                          │
 │                                                                     │
 │  ┌─────────────────────┐       ┌─────────────────────────────────┐  │
 │  │   Cloudflare DNS    │──────▶│      Cloudflare Worker          │  │
 │  │  cdn.hyperabyss.com │       │      worker.js                  │  │
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
 │                                │      Whatbox Seedbox             │  │
 │                                │  server.whatbox.ca               │  │
 │                                │                                 │  │
 │                                │  files/sims4/                   │  │
 │                                │    dlc/     ← DLC ZIPs          │  │
 │                                │    patches/ ← Binary deltas     │  │
 │                                │    language/← Locale archives   │  │
 │                                └─────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────┘
```

### How the Proxy Works

When a user's app requests `https://cdn.hyperabyss.com/dlc/EP01.zip`, the following chain executes entirely within the Cloudflare edge before any bytes from the file reach the client:

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
**Scope**: Handles every inbound request to `cdn.hyperabyss.com/*`

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

- **`cdn_upload.py add-kv`** and **`cdn_upload.py delete-kv`** (command-line, see Section 5.1)
- **`cdn_pack_upload.py`** automatically registers entries during batch uploads (see Section 5.2)
- **Cloudflare dashboard** → Workers & Pages → KV → CDN_ROUTES namespace (manual editing)

---

### 2.3 Whatbox Seedbox

The seedbox is a managed private server at Whatbox (whatbox.ca). It provides both SFTP and HTTPS access to the same file tree.

#### Access Methods

| Protocol | Purpose | Port | Auth |
|---|---|---|---|
| SFTP | File upload from upload scripts | 22 | Username + password |
| HTTPS | File download by the Worker | 443 | HTTP Basic Auth |

#### Directory Layout on Seedbox

```
files/
└── sims4/
    ├── manifest.json          # Master manifest (generated by cdn_pack_upload.py)
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

All upload scripts write into `files/sims4/` on the seedbox. The Worker's `SEEDBOX_BASE_URL` must point to the parent directory that contains this tree (e.g., `https://server.whatbox.ca/private`), so that the full resolved URL becomes `https://server.whatbox.ca/private/files/sims4/dlc/EP01.zip`.

---

## 3. URL Structure

All content is served from `https://cdn.hyperabyss.com/`. The URL space is organized into four top-level paths:

```
cdn.hyperabyss.com/
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
| `SEEDBOX_BASE_URL` | `https://server.whatbox.ca/private` | Base HTTPS URL of the Whatbox file server. No trailing slash. |
| `SEEDBOX_USER` | `myusername` | Whatbox account username for HTTP Basic Auth |
| `SEEDBOX_PASS` | `s3cur3password` | Whatbox account password for HTTP Basic Auth |

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

This file provides credentials to the upload scripts (`cdn_upload.py` and `cdn_pack_upload.py`). It is read-only at runtime by those scripts and never used by the deployed Worker.

```json
{
  "whatbox_host": "server.whatbox.ca",
  "whatbox_port": 22,
  "whatbox_user": "username",
  "whatbox_pass": "password",
  "cloudflare_account_id": "abcdef1234567890abcdef1234567890",
  "cloudflare_api_token": "your-cloudflare-api-token-here",
  "cloudflare_kv_namespace_id": "abcdef1234567890abcdef1234567890"
}
```

#### Field Reference

| Field | Description | Where to Find It |
|---|---|---|
| `whatbox_host` | Seedbox SFTP hostname | Whatbox control panel |
| `whatbox_port` | SFTP port (almost always 22) | Whatbox control panel |
| `whatbox_user` | Seedbox username | Whatbox control panel |
| `whatbox_pass` | Seedbox password | Whatbox control panel |
| `cloudflare_account_id` | Cloudflare account ID | Cloudflare dashboard → right sidebar |
| `cloudflare_api_token` | API token with KV edit permissions | Cloudflare dashboard → My Profile → API Tokens |
| `cloudflare_kv_namespace_id` | KV namespace ID for CDN_ROUTES | Cloudflare dashboard → Workers & Pages → KV |

#### Creating a Cloudflare API Token

The token needs the following permissions:
- **Account** → Cloudflare Workers KV Storage → Edit
- **Zone** → (none required for KV operations)

Do not grant broader permissions than necessary. A token scoped only to KV write is sufficient.

---

### 4.3 upload_state.json (Auto-Generated)

**Location**: `cloudflare-worker/upload_state.json` (created on first run of `cdn_pack_upload.py`)
**Tracked by git**: No — auto-generated; should be in `.gitignore`

This file is the resume state for the batch uploader. It is written after each successful upload and read at startup to skip already-completed items. If the process is interrupted (crash, Ctrl+C, reboot), re-running the script will read this file and resume from where it left off.

```json
{
  "completed": {
    "EP01": {
      "url": "https://cdn.hyperabyss.com/dlc/EP01.zip",
      "size": 1706434567,
      "md5": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
      "filename": "EP01.zip"
    },
    "EP02": {
      "url": "https://cdn.hyperabyss.com/dlc/EP02.zip",
      "size": 892341234,
      "md5": "F6E5D4C3B2A1F6E5D4C3B2A1F6E5D4C3",
      "filename": "EP02.zip"
    }
  },
  "failed": []
}
```

#### State File Fields

| Field | Type | Description |
|---|---|---|
| `completed` | `object` | Map of pack ID → upload result. Keys are pack IDs from `dlc_catalog.json` (e.g., `EP01`). |
| `completed[id].url` | `string` | Final public CDN URL |
| `completed[id].size` | `int` | Archive size in bytes |
| `completed[id].md5` | `string` | MD5 hex digest of the archive |
| `completed[id].filename` | `string` | Bare filename (e.g., `EP01.zip`) |
| `failed` | `array` | Pack IDs that exhausted all retry attempts |

To force a full re-upload of everything (ignoring resume state), use the `--fresh` flag or delete this file manually.

---

## 5. Upload Tools

All upload tools live in the `cloudflare-worker/` directory.

### 5.1 cdn_upload.py — Low-Level CLI

**Location**: `cloudflare-worker/cdn_upload.py`

This script provides low-level, interactive control over individual files and KV entries. It is intended for manual operations: uploading a single replacement file, registering a hand-crafted URL, or auditing the current KV table.

#### Commands

```
python cdn_upload.py <command> [args]
```

| Command | Syntax | Description |
|---|---|---|
| `upload` | `upload <local_path> <remote_path>` | Upload a single file via SFTP to the seedbox at `files/sims4/<remote_path>` |
| `add-kv` | `add-kv <cdn_path> <seedbox_path>` | Write a KV entry mapping `cdn_path` to `seedbox_path` |
| `delete-kv` | `delete-kv <cdn_path>` | Remove a KV entry |
| `list-kv` | `list-kv [prefix]` | List all KV entries, optionally filtered by prefix |
| `verify` | `verify <cdn_path>` | Fetch `https://cdn.hyperabyss.com/<cdn_path>` and print HTTP status + headers |

#### Example: Uploading a Replacement manifest.json

```bash
# 1. Upload the file to the seedbox
python cdn_upload.py upload ./manifest.json files/sims4/manifest.json

# 2. Register the KV route (if not already registered)
python cdn_upload.py add-kv manifest.json files/sims4/manifest.json

# 3. Verify the CDN serves it correctly
python cdn_upload.py verify manifest.json
```

#### Example: Auditing All DLC Routes

```bash
python cdn_upload.py list-kv dlc/
```

Output:
```
dlc/EP01.zip  →  files/sims4/dlc/EP01.zip
dlc/EP02.zip  →  files/sims4/dlc/EP02.zip
dlc/GP01.zip  →  files/sims4/dlc/GP01.zip
...
```

---

### 5.2 cdn_pack_upload.py — Batch DLC Uploader

**Location**: `cloudflare-worker/cdn_pack_upload.py`

This is the primary tool for a full CDN deployment. It automates the complete pipeline:

```
Game directory
     │
     ▼
Package DLC files into ZIP archive
     │
     ▼
Compute MD5 hash of archive
     │
     ▼
Upload ZIP to seedbox via SFTP
     │
     ▼
Register KV route (CDN path → seedbox path)
     │
     ▼
Record completion in upload_state.json
     │
     ▼ (after all DLCs complete)
Generate manifest.json with dlc_downloads entries
     │
     ▼
Upload manifest.json to seedbox
     │
     ▼
Register manifest.json KV route
```

#### Usage

```bash
# Default: upload all DLCs, auto-detect game dir from registry
python cdn_pack_upload.py

# Explicit game directory
python cdn_pack_upload.py --game-dir "C:\Program Files (x86)\Steam\steamapps\common\The Sims 4"

# Control parallelism (default: auto-detected via speedtest)
python cdn_pack_upload.py --workers 4

# Upload only specific packs
python cdn_pack_upload.py --only EP01 EP02 GP05

# Skip SFTP upload (only register KV entries for already-uploaded files)
python cdn_pack_upload.py --skip-upload

# Only regenerate and upload manifest.json (no DLC uploads)
python cdn_pack_upload.py --manifest-only

# Ignore resume state and start fresh
python cdn_pack_upload.py --fresh
```

Or via the launcher:
```batch
upload_all_dlcs.bat
```

#### Command-Line Flags

| Flag | Default | Description |
|---|---|---|
| `--workers N` | Auto (speedtest) | Number of parallel upload threads |
| `--only ID [ID ...]` | All | Restrict to specific pack IDs |
| `--skip-upload` | False | Skip SFTP upload; only update KV entries |
| `--manifest-only` | False | Skip all DLC processing; only generate+upload manifest |
| `--fresh` | False | Delete `upload_state.json` and re-upload everything |
| `--game-dir PATH` | Registry detection | Override game installation path |

#### Automatic Worker Count (Speedtest)

At startup, before any uploads begin, the script measures upload throughput to the seedbox by transferring a small probe file. It then selects the number of parallel workers that maximizes throughput without saturating the connection:

```
measured_mbps < 10   →  1 worker
measured_mbps < 30   →  2 workers
measured_mbps < 80   →  4 workers
measured_mbps >= 80  →  8 workers
```

The `--workers N` flag overrides this detection entirely.

#### Resume and Fault Tolerance

The script is designed to survive interruptions. On every successful upload:
1. The result is appended to `upload_state.json`.
2. On next run, the state file is read and all completed pack IDs are skipped.

**Retry policy**: Each upload attempt follows exponential backoff:

| Attempt | Delay Before Retry |
|---|---|
| 1 (initial) | None |
| 2 | 5 seconds |
| 3 | 10 seconds |
| 4 | 20 seconds |
| 5 | 40 seconds |
| 6 (final) | 80 seconds, then record as failed |

A pack ID recorded in `failed` in the state file will be retried on the next run unless `--fresh` is used.

#### Graceful Shutdown

- **First Ctrl+C**: Sets a stop flag. Active uploads are allowed to finish. No new uploads are started. State is saved.
- **Second Ctrl+C**: Immediate force quit. Partially written files on the seedbox should be cleaned up manually.

#### Progress Output

Progress is printed at most once every 2 seconds per worker to avoid flooding the terminal. The format is:

```
[EP05] 45.3% — 812.4 MB / 1.8 GB — 12.3 MB/s — ETA 1m 23s
```

---

### 5.3 upload_all_dlcs.bat — Launcher Script

**Location**: `cloudflare-worker/upload_all_dlcs.bat`

A thin wrapper for environments where double-clicking a batch file is more convenient than opening a terminal:

```batch
@echo off
python cdn_pack_upload.py %*
pause
```

The `%*` passes all arguments through to `cdn_pack_upload.py`. The `pause` at the end keeps the console window open after completion so you can read the final output.

---

## 6. Manifest Format

The manifest is the central configuration document that the app fetches on startup from `https://cdn.hyperabyss.com/manifest.json`. It tells the app:

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
      "url": "https://cdn.hyperabyss.com/patches/1.121.372.1020_to_1.122.100.1020.zip",
      "size": 892341234,
      "md5": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
    }
  ],
  "dlc_downloads": {
    "EP01": {
      "url": "https://cdn.hyperabyss.com/dlc/EP01.zip",
      "size": 1706434567,
      "md5": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
      "filename": "EP01.zip"
    },
    "GP05": {
      "url": "https://cdn.hyperabyss.com/dlc/GP05.zip",
      "size": 523412345,
      "md5": "B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5",
      "filename": "GP05.zip"
    }
  },
  "language_downloads": {
    "de_DE": {
      "url": "https://cdn.hyperabyss.com/language/de_DE.zip",
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
   → GET https://cdn.hyperabyss.com/manifest.json
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
3. The server (Whatbox via the Worker) returns HTTP 206 Partial Content.
4. The downloader appends to the existing file rather than overwriting.
5. After the final byte is received, MD5 is computed over the complete file and compared against `DLCDownloadEntry.md5`. A mismatch causes the download to be deleted and retried from zero.

This mechanism relies on the Worker correctly forwarding the `Accept-Ranges: bytes` header from the seedbox, which it does explicitly.

---

## 8. Deployment Guide

This section covers standing up a new CDN instance from scratch. Follow these steps in order.

### Prerequisites

- A domain name you control (to create a subdomain like `cdn.yourdomain.com`)
- A Cloudflare account (free tier is sufficient)
- A Whatbox seedbox subscription (or equivalent SFTP + HTTPS file host)
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

1. Add `SEEDBOX_BASE_URL` → your Whatbox HTTPS base URL (e.g., `https://server.whatbox.ca/private`)
   - Mark as **Secret**.
2. Add `SEEDBOX_USER` → your Whatbox username.
   - Mark as **Secret**.
3. Add `SEEDBOX_PASS` → your Whatbox password.
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

Run the batch uploader from a machine with the game installed:

```bash
cd cloudflare-worker
python cdn_pack_upload.py
```

The script will:
1. Detect the game directory from the Windows registry.
2. Run a speedtest to select optimal parallel workers.
3. Package each DLC into a ZIP archive.
4. Upload each archive to the seedbox via SFTP.
5. Register each KV route.
6. Generate and upload `manifest.json`.

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

# Low-level verification via upload tool
cd cloudflare-worker
python cdn_upload.py verify manifest.json
python cdn_upload.py verify dlc/EP01.zip
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

## 9. Troubleshooting

### 502 Bad Gateway

**Symptom**: CDN returns HTTP 502 for a path that has a KV entry.

**Cause**: The KV value contains an incorrect seedbox path. The Worker builds the full URL as `SEEDBOX_BASE_URL + "/" + kv_value`. If the KV value is `dlc/EP01.zip` instead of `files/sims4/dlc/EP01.zip`, the constructed URL will point to a non-existent path on the seedbox, and the seedbox returns 404 or 403, which the Worker surfaces as 502.

**Fix**:
```bash
# Check what the KV entry says
python cdn_upload.py list-kv dlc/EP01.zip

# If wrong, delete and re-add with the correct full path
python cdn_upload.py delete-kv dlc/EP01.zip
python cdn_upload.py add-kv dlc/EP01.zip files/sims4/dlc/EP01.zip

# Verify
python cdn_upload.py verify dlc/EP01.zip
```

---

### 404 Not Found from CDN

**Symptom**: CDN returns HTTP 404 for a path you expect to exist.

**Cause**: No KV entry for the requested path.

**Fix**:
```bash
# Confirm the file exists on the seedbox (will succeed if credentials work)
# Then register the missing KV route
python cdn_upload.py add-kv dlc/EP02.zip files/sims4/dlc/EP02.zip
```

---

### Upload Stuck at Low Speed (1 MB/s)

**Symptom**: SFTP uploads to Whatbox are capped at approximately 1 MB/s despite a fast local connection.

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

This setting is already applied in `cdn_pack_upload.py`. If you encounter the symptom in a custom script, add the above lines.

---

### State File Corrupted / Unexpected Resume Behavior

**Symptom**: The uploader skips packs that need re-uploading, or crashes on startup while reading state.

**Fix**: Delete the state file and start fresh:
```bash
rm cloudflare-worker/upload_state.json
python cdn_pack_upload.py --fresh
```

`--fresh` also deletes the state file programmatically, so either approach works.

---

### Worker Returns 401 / Seedbox Authentication Fails

**Symptom**: Worker returns HTTP 401 or 403, or the file is served but content looks like an HTML login page.

**Cause**: Incorrect `SEEDBOX_USER` or `SEEDBOX_PASS` Worker secrets, or the Whatbox HTTPS URL requires a different path prefix.

**Fix**:
1. Verify credentials by testing the seedbox URL directly:
   ```bash
   curl -u "username:password" https://server.whatbox.ca/private/files/sims4/manifest.json -I
   ```
2. If that fails, log in to the Whatbox control panel and confirm the HTTPS path.
3. Update the Worker secrets in the Cloudflare dashboard (**Workers & Pages → your-worker → Settings → Variables**).
4. Re-deploy the Worker (edit any line and save to trigger a re-deploy).

---

### KV Write Limit Exceeded

**Symptom**: `cdn_pack_upload.py` reports KV write errors near the end of a large batch.

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

## 10. Cost Breakdown

The CDN architecture is designed to operate within Cloudflare's free tier for typical usage volumes. The only non-free component is the Whatbox seedbox.

| Service | Tier | Monthly Cost | Notes |
|---|---|---|---|
| Cloudflare DNS | Free | $0 | Domain routing via Anycast network |
| Cloudflare Worker | Free | $0 | 100,000 requests/day included; $5/mo for 10M req/day if you exceed it |
| Cloudflare KV Reads | Free | $0 | 100,000 reads/day included; $0.50 per million reads above that |
| Cloudflare KV Writes | Free | $0 | 1,000 writes/day included; $5 per million writes above that |
| Whatbox Seedbox | Paid | ~$15/mo | File hosting, HTTPS, SFTP, unlimited egress |
| **Total** | | **~$15/mo** | |

### Scaling Considerations

- **Worker requests**: Each file download involves one Worker invocation (the KV lookup is a sub-request, not a separate invocation). A deployment serving 1,000 users/day downloading 10 files each = 10,000 requests/day, well within the free tier.
- **KV reads**: Each Worker invocation does one KV read. Same calculation: 10,000 reads/day on a 100,000 limit.
- **Bandwidth**: Cloudflare does not charge for egress bandwidth from Workers to clients. The only bandwidth cost is the Worker-to-seedbox fetch, which is included in the Whatbox subscription.
- **Whatbox storage**: Storage on Whatbox is quota-based. A full DLC catalog (all expansion/game/stuff/kit packs) typically totals 40–80 GB. Verify your Whatbox plan's storage quota before uploading.

If usage grows significantly beyond these estimates, upgrading to the Cloudflare Workers Paid plan ($5/month for 10M requests) is the first and likely only additional cost.

---

*This document describes the CDN infrastructure for The Sims 4 Updater. For related documentation, see:*

- *`Documentation/Architecture_and_Developer_Guide.md` — overall system architecture and module map*
- *`Documentation/DLC_Management_System.md` — DLC catalog, crack formats, and DLC manager internals*
- *`Documentation/DLC_Packer_and_Distribution.md` — DLC packer, ZIP format, and manifest generation*
- *`Documentation/Update_and_Patching_System.md` — version detection, patch planning, and download pipeline*
