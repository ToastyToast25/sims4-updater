-- =============================================================
-- Sims 4 Updater — Telemetry Database Setup
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- =============================================================

-- Step 1: Tables
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.users (
  uid TEXT PRIMARY KEY,
  session_id TEXT,
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

-- Migration: add session_id column if upgrading from older schema
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS session_id TEXT;

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

-- Game version distribution (last 30 days, from heartbeat data)
CREATE OR REPLACE VIEW public.game_version_stats AS
SELECT coalesce(game_version, 'unknown') AS game_version, count(*) AS count
FROM public.users WHERE last_seen > now() - interval '30 days'
  AND game_detected = TRUE
GROUP BY game_version ORDER BY count DESC;

-- Daily active users trend (last 30 days — one row per day, based on events)
CREATE OR REPLACE VIEW public.daily_active_trend AS
SELECT d::date AS day,
  count(DISTINCT e.uid) AS active_users
FROM generate_series(
  (now() - interval '30 days')::date,
  now()::date,
  '1 day'::interval
) AS d
LEFT JOIN public.events e ON e.created_at::date = d::date
GROUP BY d::date ORDER BY d::date;

-- New users per day (last 30 days)
CREATE OR REPLACE VIEW public.new_users_daily AS
SELECT created_at::date AS day, count(*) AS new_users
FROM public.users
WHERE created_at > now() - interval '30 days'
GROUP BY created_at::date ORDER BY created_at::date;

-- Feature usage from frame_navigation events (last 30 days)
CREATE OR REPLACE VIEW public.feature_usage AS
SELECT metadata->>'to' AS feature, count(*) AS visits
FROM public.events
WHERE event_type = 'frame_navigation'
  AND created_at > now() - interval '30 days'
GROUP BY metadata->>'to' ORDER BY visits DESC;

-- Error/failure summary (last 30 days)
CREATE OR REPLACE VIEW public.error_summary AS
SELECT event_type, count(*) AS count,
  count(DISTINCT uid) AS affected_users
FROM public.events
WHERE event_type IN (
  'update_failed', 'dlc_download_failed', 'update_cancelled',
  'dlc_download_cancelled'
) AND created_at > now() - interval '30 days'
GROUP BY event_type ORDER BY count DESC;

-- DLC count distribution (how many DLCs users have, last 30 days)
CREATE OR REPLACE VIEW public.dlc_count_distribution AS
SELECT bucket, count FROM (
  SELECT
    CASE
      WHEN dlc_count IS NULL THEN 'unknown'
      WHEN dlc_count = 0 THEN '0'
      WHEN dlc_count BETWEEN 1 AND 10 THEN '1-10'
      WHEN dlc_count BETWEEN 11 AND 30 THEN '11-30'
      WHEN dlc_count BETWEEN 31 AND 60 THEN '31-60'
      WHEN dlc_count BETWEEN 61 AND 90 THEN '61-90'
      WHEN dlc_count > 90 THEN '90+'
    END AS bucket,
    CASE
      WHEN dlc_count IS NULL THEN 7
      WHEN dlc_count = 0 THEN 1
      WHEN dlc_count BETWEEN 1 AND 10 THEN 2
      WHEN dlc_count BETWEEN 11 AND 30 THEN 3
      WHEN dlc_count BETWEEN 31 AND 60 THEN 4
      WHEN dlc_count BETWEEN 61 AND 90 THEN 5
      WHEN dlc_count > 90 THEN 6
    END AS sort_order,
    count(*) AS count
  FROM public.users
  WHERE last_seen > now() - interval '30 days'
  GROUP BY 1, 2
) sub
ORDER BY sort_order;

-- Daily events trend (last 30 days — events per day)
CREATE OR REPLACE VIEW public.daily_events_trend AS
SELECT d::date AS day,
  count(e.id) AS event_count
FROM generate_series(
  (now() - interval '30 days')::date,
  now()::date,
  '1 day'::interval
) AS d
LEFT JOIN public.events e ON e.created_at::date = d::date
GROUP BY d::date ORDER BY d::date;

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
