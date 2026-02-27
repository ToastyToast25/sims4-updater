-- Migration: Add session_id column and new analytics views
-- Date: 2026-02-26

-- Add session_id to users table
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS session_id TEXT;

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
