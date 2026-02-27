-- Token request log (tracks who authenticates with the CDN)
CREATE TABLE IF NOT EXISTS public.token_log (
  machine_id TEXT NOT NULL,
  uid TEXT DEFAULT '',
  ip TEXT DEFAULT '',
  app_version TEXT DEFAULT '',
  last_seen TIMESTAMPTZ DEFAULT now(),
  request_count INTEGER DEFAULT 1,
  first_seen TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (machine_id)
);

-- Auto-increment request_count on duplicate
CREATE OR REPLACE FUNCTION public.upsert_token_log()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE public.token_log
  SET last_seen = now(),
      request_count = token_log.request_count + 1,
      ip = NEW.ip,
      uid = NEW.uid,
      app_version = NEW.app_version
  WHERE machine_id = NEW.machine_id;
  IF FOUND THEN
    RETURN NULL; -- Skip INSERT
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER tr_upsert_token_log
BEFORE INSERT ON public.token_log
FOR EACH ROW
EXECUTE FUNCTION public.upsert_token_log();

CREATE INDEX IF NOT EXISTS idx_token_log_last_seen ON public.token_log (last_seen DESC);

ALTER TABLE public.token_log ENABLE ROW LEVEL SECURITY;
