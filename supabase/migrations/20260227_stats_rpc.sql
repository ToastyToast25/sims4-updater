-- RPC function: get_stats(p_days INTEGER)
-- Returns all analytics data for the given time window.
-- Pass 0 for all-time stats.

CREATE OR REPLACE FUNCTION public.get_stats(p_days INTEGER DEFAULT 30)
RETURNS JSONB AS $$
DECLARE
  cutoff TIMESTAMPTZ;
  result JSONB := '{}'::JSONB;
  tmp JSONB;
BEGIN
  IF p_days <= 0 THEN
    cutoff := '1970-01-01'::TIMESTAMPTZ;
  ELSE
    cutoff := now() - (p_days || ' days')::INTERVAL;
  END IF;

  -- online_users (always last 6 min, not affected by range)
  SELECT jsonb_build_object('count', count(*))
  INTO tmp
  FROM public.users WHERE last_seen > now() - interval '6 minutes';
  result := result || jsonb_build_object('online_users', jsonb_build_array(tmp));

  -- active_users
  SELECT jsonb_build_object(
    'dau', count(*) FILTER (WHERE last_seen > now() - interval '1 day'),
    'wau', count(*) FILTER (WHERE last_seen > now() - interval '7 days'),
    'mau', count(*) FILTER (WHERE last_seen > now() - interval '30 days'),
    'total', count(*)
  )
  INTO tmp
  FROM public.users;
  result := result || jsonb_build_object('active_users', jsonb_build_array(tmp));

  -- version_stats
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT app_version, count(*) AS count FROM public.users
    WHERE last_seen > cutoff
    GROUP BY app_version ORDER BY count DESC
  ) t;
  result := result || jsonb_build_object('version_stats', tmp);

  -- game_version_stats
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT coalesce(game_version, 'unknown') AS game_version, count(*) AS count
    FROM public.users WHERE last_seen > cutoff AND game_detected = TRUE
    GROUP BY game_version ORDER BY count DESC
  ) t;
  result := result || jsonb_build_object('game_version_stats', tmp);

  -- crack_format_stats
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT coalesce(crack_format, 'unknown') AS crack_format, count(*) AS count
    FROM public.users WHERE last_seen > cutoff
    GROUP BY crack_format ORDER BY count DESC
  ) t;
  result := result || jsonb_build_object('crack_format_stats', tmp);

  -- locale_stats
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT coalesce(locale, 'unknown') AS locale, count(*) AS count
    FROM public.users WHERE last_seen > cutoff
    GROUP BY locale ORDER BY count DESC
  ) t;
  result := result || jsonb_build_object('locale_stats', tmp);

  -- event_stats
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT event_type, count(*) AS count FROM public.events
    WHERE created_at > cutoff
    GROUP BY event_type ORDER BY count DESC
  ) t;
  result := result || jsonb_build_object('event_stats', tmp);

  -- popular_dlcs
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT metadata->>'dlc_id' AS dlc_id, count(*) AS downloads,
      coalesce(sum(public.safe_bigint(metadata->>'size_bytes')), 0) AS total_bytes
    FROM public.events
    WHERE event_type = 'dlc_download_complete' AND created_at > cutoff
    GROUP BY metadata->>'dlc_id' ORDER BY downloads DESC LIMIT 20
  ) t;
  result := result || jsonb_build_object('popular_dlcs', tmp);

  -- update_stats
  SELECT jsonb_build_object(
    'started', count(*) FILTER (WHERE event_type = 'update_started'),
    'completed', count(*) FILTER (WHERE event_type = 'update_completed'),
    'failed', count(*) FILTER (WHERE event_type = 'update_failed')
  )
  INTO tmp
  FROM public.events
  WHERE event_type IN ('update_started', 'update_completed', 'update_failed')
    AND created_at > cutoff;
  result := result || jsonb_build_object('update_stats', jsonb_build_array(tmp));

  -- download_volume
  SELECT jsonb_build_object(
    'total_downloads', count(*),
    'total_bytes', coalesce(sum(public.safe_bigint(metadata->>'size_bytes')), 0),
    'avg_duration', coalesce(avg(public.safe_float(metadata->>'duration_seconds')), 0),
    'avg_speed_bps', coalesce(avg(public.safe_float(metadata->>'speed_bps')), 0)
  )
  INTO tmp
  FROM public.events
  WHERE event_type = 'dlc_download_complete' AND created_at > cutoff;
  result := result || jsonb_build_object('download_volume', jsonb_build_array(tmp));

  -- session_stats
  SELECT jsonb_build_object(
    'total_sessions', count(*),
    'avg_duration', coalesce(avg(public.safe_float(metadata->>'duration_seconds')), 0),
    'max_duration', coalesce(max(public.safe_float(metadata->>'duration_seconds')), 0)
  )
  INTO tmp
  FROM public.events
  WHERE event_type = 'session_end' AND created_at > cutoff;
  result := result || jsonb_build_object('session_stats', jsonb_build_array(tmp));

  -- feature_usage
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT metadata->>'to_frame' AS feature, count(*) AS visits
    FROM public.events
    WHERE event_type = 'frame_navigation' AND created_at > cutoff
    GROUP BY metadata->>'to_frame' ORDER BY visits DESC
  ) t;
  result := result || jsonb_build_object('feature_usage', tmp);

  -- error_summary
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT event_type, count(*) AS count, count(DISTINCT uid) AS affected_users
    FROM public.events
    WHERE event_type IN ('update_failed', 'dlc_download_failed', 'update_cancelled', 'dlc_download_cancelled')
      AND created_at > cutoff
    GROUP BY event_type ORDER BY count DESC
  ) t;
  result := result || jsonb_build_object('error_summary', tmp);

  -- dlc_count_distribution
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB ORDER BY t.sort_order), '[]'::JSONB)
  INTO tmp
  FROM (
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
    WHERE last_seen > cutoff
    GROUP BY 1, 2
  ) t;
  result := result || jsonb_build_object('dlc_count_distribution', tmp);

  -- daily_active_trend (last N days as time series)
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT d::date AS day, count(DISTINCT e.uid) AS active_users
    FROM generate_series(
      GREATEST(cutoff::date, (now() - interval '90 days')::date),
      now()::date, '1 day'::interval
    ) AS d
    LEFT JOIN public.events e
      ON e.created_at::date = d::date
      AND e.created_at >= GREATEST(cutoff, now() - interval '90 days')
    GROUP BY d::date ORDER BY d::date
  ) t;
  result := result || jsonb_build_object('daily_active_trend', tmp);

  -- new_users_daily
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT created_at::date AS day, count(*) AS new_users
    FROM public.users WHERE created_at > cutoff
    GROUP BY created_at::date ORDER BY created_at::date
  ) t;
  result := result || jsonb_build_object('new_users_daily', tmp);

  -- daily_events_trend
  SELECT coalesce(jsonb_agg(row_to_json(t)::JSONB), '[]'::JSONB)
  INTO tmp
  FROM (
    SELECT d::date AS day, count(e.id) AS event_count
    FROM generate_series(
      GREATEST(cutoff::date, (now() - interval '90 days')::date),
      now()::date, '1 day'::interval
    ) AS d
    LEFT JOIN public.events e
      ON e.created_at::date = d::date
      AND e.created_at >= GREATEST(cutoff, now() - interval '90 days')
    GROUP BY d::date ORDER BY d::date
  ) t;
  result := result || jsonb_build_object('daily_events_trend', tmp);

  RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;
