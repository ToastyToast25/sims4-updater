# Supabase Setup Guide

**Project**: The Sims 4 Updater
**Last Updated**: 2026-02-23

---

## Table of Contents

1. [Overview](#1-overview)
2. [Create a Supabase Project](#2-create-a-supabase-project)
3. [Run the Database Schema](#3-run-the-database-schema)
4. [Get Your Credentials](#4-get-your-credentials)
5. [Configure Cloudflare Workers](#5-configure-cloudflare-workers)
6. [Generate a JWT Secret](#6-generate-a-jwt-secret)
7. [Deploy Workers](#7-deploy-workers)
8. [Verify the Setup](#8-verify-the-setup)
9. [Database Schema Reference](#9-database-schema-reference)
10. [Admin Dashboards](#10-admin-dashboards)
11. [Maintenance](#11-maintenance)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Overview

The Sims 4 Updater uses [Supabase](https://supabase.com) (hosted PostgreSQL + REST API) as the backend database for:

- **Telemetry & Analytics** — user heartbeats, events, download stats, session tracking
- **CDN Access Control** — bans (IP/machine/UID), access requests, allowlists
- **Connected Clients** — token request log showing who's connected to the CDN
- **CDN Settings** — dynamic configuration (public/private mode)

Supabase provides a free tier that's sufficient for most CDN deployments. Each CDN provider runs their own Supabase project, so data is isolated per-CDN.

### What You'll Set Up

| Component | Purpose |
|-----------|---------|
| Supabase project | PostgreSQL database + REST API |
| Database tables | `users`, `events`, `bans`, `access_requests`, `cdn_allowlist`, `cdn_settings`, `token_log` |
| Analytics views | Pre-computed stats for the admin dashboards |
| Worker secrets | Connect both Cloudflare Workers to Supabase |
| JWT secret | Shared signing key for CDN session tokens |

---

## 2. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up or log in
2. Click **New Project**
3. Fill in:
   - **Name**: e.g. `sims4-cdn` (or any name you prefer)
   - **Database Password**: generate a strong password (you won't need this for the app — the service_role key handles auth)
   - **Region**: pick the region closest to your seedbox or majority of users
4. Click **Create new project** and wait for provisioning (~1 minute)

> **Free tier limits**: 500 MB database, 2 GB bandwidth, 50k monthly active users. This is more than enough for typical CDN usage.

---

## 3. Run the Database Schema

1. In the Supabase dashboard, go to **SQL Editor** (left sidebar)
2. Click **New Query**
3. Open the file `cloudflare-worker/supabase_setup.sql` from this repository
4. Copy the **entire contents** and paste into the SQL editor
5. Click **Run** (or press Ctrl+Enter)

You should see `Success. No rows returned` — this means all tables, views, indexes, triggers, and seed data were created.

### What Gets Created

**Tables (7)**:

| Table | Purpose |
|-------|---------|
| `users` | Telemetry user records (one per UID) |
| `events` | Telemetry event log (updates, downloads, sessions) |
| `bans` | IP/machine/UID bans with permanent and temporary support |
| `access_requests` | Access requests for private CDN mode |
| `cdn_allowlist` | Approved machines for private CDN mode |
| `cdn_settings` | Dynamic key-value configuration |
| `token_log` | Connected client tracking (one row per machine) |

**Views (10)**: `online_users`, `active_users`, `version_stats`, `crack_format_stats`, `locale_stats`, `event_stats`, `popular_dlcs`, `update_stats`, `download_volume`, `session_stats`, `active_bans`, `bans_summary`

**Triggers (1)**: `token_log_upsert_trigger` — auto-updates `last_seen` and increments `request_count` when a client reconnects

**Seed data**: `cdn_settings` gets a default `cdn_access = public` entry

### Verify Tables Were Created

Go to **Table Editor** in the Supabase dashboard. You should see all 7 tables listed. Click on each to confirm they exist (they'll be empty, which is expected).

---

## 4. Get Your Credentials

You need two values from Supabase:

### 4a. Project URL

1. Go to **Settings** (gear icon) > **API**
2. Copy the **Project URL** — looks like:
   ```
   https://abcdefghijklmnop.supabase.co
   ```

### 4b. Service Role Key

1. On the same **Settings > API** page
2. Under **Project API keys**, find the `service_role` key
3. Click **Reveal** and copy it — looks like:
   ```
   eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIs...
   ```

> **Security**: The `service_role` key bypasses Row Level Security and has full database access. Never expose it in client-side code. It's only used by the Cloudflare Workers (server-side).

> **Do NOT use the `anon` key** — it doesn't have permission to write to tables with RLS enabled and no public policies.

---

## 5. Configure Cloudflare Workers

Both the CDN Worker (`worker.js`) and the API Worker (`api-worker.js`) need Supabase credentials. Set them as secrets using `wrangler`:

### 5a. API Worker Secrets

```bash
cd cloudflare-worker

# Supabase credentials
npx wrangler secret put SUPABASE_URL -c wrangler-api.toml
# Paste: https://your-project-id.supabase.co

npx wrangler secret put SUPABASE_SERVICE_KEY -c wrangler-api.toml
# Paste: your service_role key

# JWT secret (see Step 6)
npx wrangler secret put JWT_SECRET -c wrangler-api.toml
# Paste: your generated JWT secret

# Admin dashboard password
npx wrangler secret put ADMIN_PASSWORD -c wrangler-api.toml
# Paste: choose a strong password for /admin/* routes

# Discord webhook (optional — for ban/access notifications)
npx wrangler secret put DISCORD_WEBHOOK -c wrangler-api.toml
# Paste: https://discord.com/api/webhooks/...
```

### 5b. CDN Worker Secrets

```bash
cd cloudflare-worker

# Supabase credentials (same as API worker)
npx wrangler secret put SUPABASE_URL -c wrangler.toml
# Paste: https://your-project-id.supabase.co

npx wrangler secret put SUPABASE_SERVICE_KEY -c wrangler.toml
# Paste: your service_role key

# JWT secret (MUST be the same as API worker)
npx wrangler secret put JWT_SECRET -c wrangler.toml
# Paste: same JWT secret as API worker
```

### 5c. Plain-Text Variables

These are already set in the wrangler TOML files but can be overridden:

| Variable | File | Default | Description |
|----------|------|---------|-------------|
| `CDN_ACCESS` | `wrangler-api.toml` | `"public"` | `"public"` or `"private"` — can also be changed at runtime via the admin dashboard |
| `CDN_NAME` | `wrangler-api.toml` | `"HyperAbyss CDN"` | Display name shown in access-required errors |

To change:

```bash
npx wrangler vars put CDN_ACCESS -c wrangler-api.toml
# Enter: public (or private)

npx wrangler vars put CDN_NAME -c wrangler-api.toml
# Enter: Your CDN Name
```

---

## 6. Generate a JWT Secret

The JWT secret is a shared key used by both workers — the API Worker signs tokens with it, and the CDN Worker verifies them. Generate a random 64-character hex string:

**Option A — OpenSSL (Linux/macOS/Git Bash)**:
```bash
openssl rand -hex 32
```

**Option B — Python**:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Option C — PowerShell (Windows)**:
```powershell
-join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
```

Copy the output and use it for the `JWT_SECRET` secret on **both** workers (Step 5a and 5b). They must match — if they don't, the CDN Worker will reject every token the API Worker issues.

---

## 7. Deploy Workers

After setting all secrets, deploy both workers:

```bash
cd cloudflare-worker

# Deploy API Worker
npx wrangler deploy -c wrangler-api.toml

# Deploy CDN Worker
npx wrangler deploy -c wrangler.toml
```

Verify the deployments in the Cloudflare dashboard under **Workers & Pages**.

---

## 8. Verify the Setup

### 8a. Test the API Worker

```bash
# Health check — should return JSON with stats
curl https://api.hyperabyss.com/stats/health

# Request a token (simulates a client connecting)
curl -X POST https://api.hyperabyss.com/auth/token \
  -H "Content-Type: application/json" \
  -d '{"machine_id":"test123","uid":"testuser","app_version":"2.4.0"}'
# Should return: {"token":"eyJ...","expires_in":3600}
```

### 8b. Verify Token Log

After the test token request above:

1. Go to Supabase **Table Editor** > `token_log`
2. You should see one row with `machine_id = test123`
3. The admin dashboard at `https://api.hyperabyss.com/admin/bans?pw=YOUR_PASSWORD` should show the client in the "Connected Clients" table

### 8c. Test the Admin Dashboards

Open these URLs in your browser (replace `YOUR_PASSWORD` with your `ADMIN_PASSWORD`):

| Dashboard | URL |
|-----------|-----|
| Analytics | `https://api.hyperabyss.com/admin/analytics?pw=YOUR_PASSWORD` |
| Contributions | `https://api.hyperabyss.com/admin/contributions?pw=YOUR_PASSWORD` |
| Bans & Clients | `https://api.hyperabyss.com/admin/bans?pw=YOUR_PASSWORD` |
| Access Requests | `https://api.hyperabyss.com/admin/access?pw=YOUR_PASSWORD` |

### 8d. Clean Up Test Data

After verifying, remove the test entry:

```sql
DELETE FROM public.token_log WHERE machine_id = 'test123';
```

---

## 9. Database Schema Reference

### Tables

#### `users` — Telemetry user records

| Column | Type | Description |
|--------|------|-------------|
| `uid` | `TEXT` (PK) | Anonymous user identifier |
| `app_version` | `TEXT` | Sims 4 Updater version |
| `game_version` | `TEXT` | Detected game version |
| `game_detected` | `BOOLEAN` | Whether a game install was found |
| `crack_format` | `TEXT` | Detected crack config format |
| `dlc_count` | `INTEGER` | Number of installed DLCs |
| `locale` | `TEXT` | Game language/locale |
| `os_version` | `TEXT` | Windows version |
| `last_seen` | `TIMESTAMPTZ` | Last heartbeat timestamp |
| `created_at` | `TIMESTAMPTZ` | First seen timestamp |

#### `events` — Telemetry event log

| Column | Type | Description |
|--------|------|-------------|
| `id` | `BIGINT` (PK) | Auto-incrementing ID |
| `uid` | `TEXT` | User who triggered the event |
| `event_type` | `TEXT` | Event category (e.g. `update_started`, `dlc_download_complete`) |
| `metadata` | `JSONB` | Event-specific data (size, duration, DLC ID, etc.) |
| `created_at` | `TIMESTAMPTZ` | Event timestamp |

#### `bans` — CDN access bans

| Column | Type | Description |
|--------|------|-------------|
| `id` | `BIGINT` (PK) | Auto-incrementing ID |
| `ban_type` | `TEXT` | `ip`, `machine`, or `uid` |
| `value` | `TEXT` | The banned IP, machine ID, or UID |
| `reason` | `TEXT` | Admin-provided reason |
| `permanent` | `BOOLEAN` | `true` for permanent, `false` for temporary |
| `expires_at` | `TIMESTAMPTZ` | Expiry time (temp bans only) |
| `created_at` | `TIMESTAMPTZ` | When the ban was created |
| `active` | `BOOLEAN` | `true` = enforced, `false` = unbanned |

#### `access_requests` — Private CDN access requests

| Column | Type | Description |
|--------|------|-------------|
| `id` | `BIGINT` (PK) | Auto-incrementing ID |
| `machine_id` | `TEXT` (unique) | Requesting machine's fingerprint |
| `uid` | `TEXT` | User identifier |
| `app_version` | `TEXT` | Client version |
| `reason` | `TEXT` | User-provided reason for access |
| `ip` | `TEXT` | Requesting IP address |
| `status` | `TEXT` | `pending`, `approved`, or `denied` |
| `reviewed_at` | `TIMESTAMPTZ` | When the request was reviewed |
| `created_at` | `TIMESTAMPTZ` | When the request was submitted |

#### `cdn_allowlist` — Approved machines (private CDN)

| Column | Type | Description |
|--------|------|-------------|
| `machine_id` | `TEXT` (PK) | Approved machine fingerprint |
| `uid` | `TEXT` | Associated user identifier |
| `approved_at` | `TIMESTAMPTZ` | Approval timestamp |
| `approved_by` | `TEXT` | Who approved (`admin` by default) |

#### `cdn_settings` — Dynamic CDN configuration

| Column | Type | Description |
|--------|------|-------------|
| `key` | `TEXT` (PK) | Setting name |
| `value` | `TEXT` | Setting value |
| `updated_at` | `TIMESTAMPTZ` | Last modified timestamp |

Default settings:

| Key | Default | Description |
|-----|---------|-------------|
| `cdn_access` | `public` | `public` = anyone can download, `private` = allowlist-only |

#### `token_log` — Connected client tracking

| Column | Type | Description |
|--------|------|-------------|
| `machine_id` | `TEXT` (PK) | Client machine fingerprint |
| `uid` | `TEXT` | User identifier |
| `ip` | `TEXT` | Client IP address |
| `app_version` | `TEXT` | Client app version |
| `last_seen` | `TIMESTAMPTZ` | Last token request time (auto-updated by trigger) |
| `request_count` | `INTEGER` | Total token requests (auto-incremented by trigger) |

### Views

| View | Purpose | Used by |
|------|---------|---------|
| `online_users` | Count of users seen in last 6 minutes | Analytics dashboard |
| `active_users` | DAU, WAU, MAU, total user counts | Analytics dashboard |
| `version_stats` | App version distribution (30 days) | Analytics dashboard |
| `crack_format_stats` | Crack format distribution (30 days) | Analytics dashboard |
| `locale_stats` | Locale/language distribution (30 days) | Analytics dashboard |
| `event_stats` | Event type totals (30 days) | Analytics dashboard |
| `popular_dlcs` | Top 20 downloaded DLCs (30 days) | Analytics dashboard |
| `update_stats` | Update started/completed/failed (30 days) | Analytics dashboard |
| `download_volume` | Total downloads, bytes, speed (30 days) | Analytics dashboard |
| `session_stats` | Session count and duration (30 days) | Analytics dashboard |
| `active_bans` | Currently enforced bans (excludes expired) | CDN/API Workers |
| `bans_summary` | Ban count breakdown by status | Bans dashboard |

### Triggers

| Trigger | Table | Fires on | Action |
|---------|-------|----------|--------|
| `token_log_upsert_trigger` | `token_log` | `BEFORE UPDATE` | Sets `last_seen = now()` and increments `request_count` |

---

## 10. Admin Dashboards

Four admin dashboards are served by the API Worker, all password-protected:

| Dashboard | URL | Features |
|-----------|-----|----------|
| **Analytics** | `/admin/analytics?pw=...` | Online users, DAU/WAU/MAU, version/crack/locale charts, events, popular DLCs, download volume |
| **Contributions** | `/admin/contributions?pw=...` | User-submitted DLC metadata and depot keys |
| **Bans** | `/admin/bans?pw=...` | Create/remove bans, connected clients list, CDN access mode toggle |
| **Access** | `/admin/access?pw=...` | Review/approve/deny access requests, bulk actions (private CDN only) |

All dashboards auto-refresh every 30 seconds.

---

## 11. Maintenance

### Cleaning Up Old Data

Telemetry events can grow over time. To prune events older than 90 days:

```sql
DELETE FROM public.events WHERE created_at < now() - interval '90 days';
```

To prune stale token_log entries (clients not seen in 30 days):

```sql
DELETE FROM public.token_log WHERE last_seen < now() - interval '30 days';
```

### Rotating the JWT Secret

If you need to rotate the JWT secret:

1. Generate a new secret (see [Step 6](#6-generate-a-jwt-secret))
2. Update both workers:
   ```bash
   npx wrangler secret put JWT_SECRET -c wrangler-api.toml
   npx wrangler secret put JWT_SECRET -c wrangler.toml
   ```
3. Redeploy both workers:
   ```bash
   npx wrangler deploy -c wrangler-api.toml
   npx wrangler deploy -c wrangler.toml
   ```
4. All existing client tokens will be invalidated — clients auto-refresh within 60 seconds

### Rotating the Supabase Service Key

1. In Supabase dashboard, go to **Settings > API**
2. Rotate the `service_role` key
3. Update both workers with the new key:
   ```bash
   npx wrangler secret put SUPABASE_SERVICE_KEY -c wrangler-api.toml
   npx wrangler secret put SUPABASE_SERVICE_KEY -c wrangler.toml
   ```
4. Redeploy both workers

### Backing Up the Database

Supabase provides daily automatic backups on paid plans. For free tier, export manually:

1. Go to **Settings > Database**
2. Under **Database Backups**, download the latest backup
3. Or use `pg_dump` via the connection string (found in **Settings > Database > Connection string**)

---

## 12. Troubleshooting

### "Connected Clients" table is empty

The `token_log` table is only populated when clients request tokens via `POST /auth/token`. If no clients are using the app with CDN auth enabled (v2.4.0+), the table will be empty. Test manually:

```bash
curl -X POST https://api.hyperabyss.com/auth/token \
  -H "Content-Type: application/json" \
  -d '{"machine_id":"test123","uid":"testuser","app_version":"2.4.0"}'
```

Then check the dashboard — the test client should appear.

### "JWT not configured" error

The `JWT_SECRET` environment variable is not set on the API Worker. Run:

```bash
npx wrangler secret put JWT_SECRET -c wrangler-api.toml
```

### Token requests return 500

Check that `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are set correctly on the API Worker. The URL must not have a trailing slash.

### Bans not taking effect

The CDN Worker checks bans on every download request. Verify that:
1. `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are set on the **CDN Worker** (not just the API Worker)
2. The ban is in the `bans` table with `active = TRUE`
3. For temp bans, `expires_at` is in the future

### Analytics dashboard shows no data

Telemetry data is only collected when:
1. The user has telemetry enabled in app settings (opt-in)
2. The `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are set on the API Worker
3. The app's telemetry URL points to your API Worker

### "relation does not exist" errors in worker logs

The SQL schema hasn't been run. Go to Supabase SQL Editor and run the full `cloudflare-worker/supabase_setup.sql` file.

### CDN settings toggle not saving

Ensure the `cdn_settings` table exists and has the seed row:

```sql
SELECT * FROM public.cdn_settings;
```

If empty, re-run the seed:

```sql
INSERT INTO public.cdn_settings (key, value) VALUES ('cdn_access', 'public')
ON CONFLICT (key) DO NOTHING;
```
