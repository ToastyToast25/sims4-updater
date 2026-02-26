-- =============================================================
-- Sims 4 Updater — Telemetry Database Setup
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- =============================================================

-- Step 1: Tables
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.users (
  uid TEXT PRIMARY KEY,
  app_version TEXT,
  game_version TEXT,
  game_detected BOOLEAN DEFAULT FALSE,
  crack_format TEXT,
  dlc_count INTEGER,
  locale TEXT,
  os_version TEXT,
  last_seen TIMESTAMPTZ DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  uid TEXT NOT NULL,
  event_type TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_type ON public.events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON public.events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_uid ON public.events (uid);

-- Step 2: Analytics Views
-- -------------------------------------------------------------

-- Online users (seen in last 6 min, slightly > 5-min ping interval)
CREATE OR REPLACE VIEW public.online_users AS
SELECT count(*) AS count FROM public.users
WHERE last_seen > now() - interval '6 minutes';

-- Active user counts (DAU, WAU, MAU, total)
CREATE OR REPLACE VIEW public.active_users AS
SELECT
  count(*) FILTER (WHERE last_seen > now() - interval '1 day') AS dau,
  count(*) FILTER (WHERE last_seen > now() - interval '7 days') AS wau,
  count(*) FILTER (WHERE last_seen > now() - interval '30 days') AS mau,
  count(*) AS total
FROM public.users;

-- App version distribution (last 30 days)
CREATE OR REPLACE VIEW public.version_stats AS
SELECT app_version, count(*) AS count FROM public.users
WHERE last_seen > now() - interval '30 days'
GROUP BY app_version ORDER BY count DESC;

-- Crack format distribution (last 30 days)
CREATE OR REPLACE VIEW public.crack_format_stats AS
SELECT coalesce(crack_format, 'unknown') AS crack_format, count(*) AS count
FROM public.users WHERE last_seen > now() - interval '30 days'
GROUP BY crack_format ORDER BY count DESC;

-- Locale distribution (last 30 days)
CREATE OR REPLACE VIEW public.locale_stats AS
SELECT coalesce(locale, 'unknown') AS locale, count(*) AS count
FROM public.users WHERE last_seen > now() - interval '30 days'
GROUP BY locale ORDER BY count DESC;

-- Event totals by type (last 30 days)
CREATE OR REPLACE VIEW public.event_stats AS
SELECT event_type, count(*) AS count FROM public.events
WHERE created_at > now() - interval '30 days'
GROUP BY event_type ORDER BY count DESC;

-- Safe casting helpers (prevent view errors on malformed JSONB metadata)
CREATE OR REPLACE FUNCTION public.safe_bigint(val TEXT) RETURNS BIGINT AS $$
BEGIN RETURN val::BIGINT; EXCEPTION WHEN OTHERS THEN RETURN 0; END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION public.safe_float(val TEXT) RETURNS DOUBLE PRECISION AS $$
BEGIN RETURN val::DOUBLE PRECISION; EXCEPTION WHEN OTHERS THEN RETURN 0; END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Popular DLCs by download count (last 30 days)
CREATE OR REPLACE VIEW public.popular_dlcs AS
SELECT metadata->>'dlc_id' AS dlc_id, count(*) AS downloads,
  coalesce(sum(public.safe_bigint(metadata->>'size_bytes')), 0) AS total_bytes
FROM public.events
WHERE event_type = 'dlc_download_complete' AND created_at > now() - interval '30 days'
GROUP BY metadata->>'dlc_id' ORDER BY downloads DESC LIMIT 20;

-- Update success/failure rate (last 30 days)
CREATE OR REPLACE VIEW public.update_stats AS
SELECT
  count(*) FILTER (WHERE event_type = 'update_started') AS started,
  count(*) FILTER (WHERE event_type = 'update_completed') AS completed,
  count(*) FILTER (WHERE event_type = 'update_failed') AS failed
FROM public.events
WHERE event_type IN ('update_started', 'update_completed', 'update_failed')
  AND created_at > now() - interval '30 days';

-- Download volume (last 30 days)
CREATE OR REPLACE VIEW public.download_volume AS
SELECT
  count(*) AS total_downloads,
  coalesce(sum(public.safe_bigint(metadata->>'size_bytes')), 0) AS total_bytes,
  coalesce(avg(public.safe_float(metadata->>'duration_seconds')), 0) AS avg_duration,
  coalesce(avg(public.safe_float(metadata->>'speed_bps')), 0) AS avg_speed_bps
FROM public.events
WHERE event_type = 'dlc_download_complete' AND created_at > now() - interval '30 days';

-- Session stats (last 30 days)
CREATE OR REPLACE VIEW public.session_stats AS
SELECT
  count(*) AS total_sessions,
  coalesce(avg(public.safe_float(metadata->>'duration_seconds')), 0) AS avg_duration,
  coalesce(max(public.safe_float(metadata->>'duration_seconds')), 0) AS max_duration
FROM public.events
WHERE event_type = 'session_end' AND created_at > now() - interval '30 days';

-- Step 3: Enable Row Level Security (allow service_role full access)
-- -------------------------------------------------------------

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS by default.
-- Explicit deny-all policies for anon role to prevent accidental exposure.
CREATE POLICY deny_anon_users ON public.users FOR ALL TO anon USING (false);
CREATE POLICY deny_anon_events ON public.events FOR ALL TO anon USING (false);

-- =============================================================
-- Step 4: CDN Access Control — Bans, Access Requests, Allowlist
-- =============================================================

-- Bans table (IP, machine, UID bans with permanent/temp support)
CREATE TABLE IF NOT EXISTS public.bans (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ban_type TEXT NOT NULL CHECK (ban_type IN ('ip', 'machine', 'uid')),
  value TEXT NOT NULL,
  reason TEXT DEFAULT '',
  permanent BOOLEAN DEFAULT TRUE,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  active BOOLEAN DEFAULT TRUE,
  UNIQUE(ban_type, value)
);

CREATE INDEX IF NOT EXISTS idx_bans_active ON public.bans (ban_type, value) WHERE active = TRUE;

ALTER TABLE public.bans ENABLE ROW LEVEL SECURITY;
CREATE POLICY deny_anon_bans ON public.bans FOR ALL TO anon USING (false);

-- Active bans view (excludes expired temp bans — used by worker ban checks)
CREATE OR REPLACE VIEW public.active_bans AS
SELECT * FROM public.bans
WHERE active = TRUE
  AND (permanent = TRUE OR expires_at > now());

-- Ban summary view (for admin dashboard stats)
CREATE OR REPLACE VIEW public.bans_summary AS
SELECT
  count(*) FILTER (WHERE active AND (permanent OR expires_at > now())) AS active_count,
  count(*) FILTER (WHERE active AND permanent) AS permanent_count,
  count(*) FILTER (WHERE active AND NOT permanent AND expires_at > now()) AS temp_count,
  count(*) FILTER (WHERE active AND NOT permanent AND expires_at <= now()) AS expired_count,
  count(*) FILTER (WHERE NOT active) AS unbanned_count,
  count(*) AS total
FROM public.bans;

-- Access requests table (for private CDNs — in-app access request flow)
CREATE TABLE IF NOT EXISTS public.access_requests (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  machine_id TEXT NOT NULL,
  uid TEXT NOT NULL,
  app_version TEXT,
  reason TEXT DEFAULT '',
  ip TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(machine_id)
);

ALTER TABLE public.access_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY deny_anon_access_requests ON public.access_requests FOR ALL TO anon USING (false);

-- CDN allowlist (approved machines for private CDNs)
CREATE TABLE IF NOT EXISTS public.cdn_allowlist (
  machine_id TEXT PRIMARY KEY,
  uid TEXT,
  approved_at TIMESTAMPTZ DEFAULT now(),
  approved_by TEXT DEFAULT 'admin'
);

ALTER TABLE public.cdn_allowlist ENABLE ROW LEVEL SECURITY;
CREATE POLICY deny_anon_allowlist ON public.cdn_allowlist FOR ALL TO anon USING (false);

-- CDN settings (dynamic key-value config, e.g. public/private mode)
CREATE TABLE IF NOT EXISTS public.cdn_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.cdn_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY deny_anon_cdn_settings ON public.cdn_settings FOR ALL TO anon USING (false);

-- Seed default settings
INSERT INTO public.cdn_settings (key, value) VALUES
  ('cdn_access', 'public')
ON CONFLICT (key) DO NOTHING;

-- Token log (connected clients — populated on each /auth/token request)
CREATE TABLE IF NOT EXISTS public.token_log (
  machine_id TEXT PRIMARY KEY,
  uid TEXT DEFAULT '',
  ip TEXT DEFAULT '',
  app_version TEXT DEFAULT '',
  last_seen TIMESTAMPTZ DEFAULT now(),
  request_count INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_token_log_last_seen ON public.token_log (last_seen DESC);

ALTER TABLE public.token_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY deny_anon_token_log ON public.token_log FOR ALL TO anon USING (false);

-- Auto-update last_seen and increment request_count on upsert
CREATE OR REPLACE FUNCTION update_token_log_on_conflict()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    NEW.last_seen = now();
    NEW.request_count = OLD.request_count + 1;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER token_log_upsert_trigger
BEFORE UPDATE ON public.token_log
FOR EACH ROW EXECUTE FUNCTION update_token_log_on_conflict();
