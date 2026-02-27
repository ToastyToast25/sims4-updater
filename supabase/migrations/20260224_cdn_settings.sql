-- CDN Settings table (dynamic config)
CREATE TABLE IF NOT EXISTS public.cdn_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.cdn_settings ENABLE ROW LEVEL SECURITY;

-- Default: public access
INSERT INTO public.cdn_settings (key, value) VALUES ('cdn_access', 'public')
ON CONFLICT (key) DO NOTHING;
