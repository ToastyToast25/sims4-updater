-- Migration: Add performance indexes for get_stats RPC function
-- Date: 2026-02-28
--
-- These indexes optimize the 15+ queries inside get_stats():
-- 1. Composite index for time-ranged event type queries
-- 2. Expression index for generate_series date JOINs
-- 3. Partial expression indexes for JSONB metadata GROUP BY
-- 4. Users last_seen index for time-ranged user queries

-- Composite: covers event_stats, popular_dlcs, update_stats, download_volume,
-- session_stats, feature_usage, error_summary queries
CREATE INDEX IF NOT EXISTS idx_events_type_created
ON public.events (event_type, created_at DESC);

-- Note: An expression index on (created_at::date) is not possible because
-- timestamptz::date is timezone-dependent (not immutable). Instead, we rely on
-- the sargable predicate (e.created_at >= ...) in the RPC's generate_series JOINs
-- which uses the existing idx_events_created index effectively.

-- Partial expression: covers popular_dlcs GROUP BY metadata->>'dlc_id'
CREATE INDEX IF NOT EXISTS idx_events_metadata_dlc_id
ON public.events ((metadata->>'dlc_id'))
WHERE event_type = 'dlc_download_complete';

-- Partial expression: covers feature_usage GROUP BY metadata->>'to'
CREATE INDEX IF NOT EXISTS idx_events_metadata_to
ON public.events ((metadata->>'to'))
WHERE event_type = 'frame_navigation';

-- Users last_seen: helps time-ranged user queries (version_stats, locale_stats, etc.)
CREATE INDEX IF NOT EXISTS idx_users_last_seen
ON public.users (last_seen DESC);
