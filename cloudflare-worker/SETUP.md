# CDN Setup Guide — cdn.hyperabyss.com

## Overview

```
User's app → cdn.hyperabyss.com/dlc/EP01.zip → Cloudflare Worker → RapidSeedbox → file streamed back
```

Users never see the seedbox URL. All they see is your domain.

## Step 1: Create KV Namespace

1. Go to Cloudflare dashboard → **Workers & Pages** → **KV**
2. Click **Create a namespace**
3. Name it: `CDN_ROUTES`
4. Copy the **Namespace ID**
5. Paste it into `wrangler.toml` replacing `YOUR_KV_NAMESPACE_ID_HERE`

## Step 2: Deploy the Worker

### Option A: Wrangler CLI (recommended)

```bash
npm install -g wrangler
wrangler login
cd cloudflare-worker
wrangler deploy
```

### Option B: Dashboard (no CLI needed)

1. Go to **Workers & Pages** → **Create** → **Create Worker**
2. Name it: `sims4-cdn`
3. Paste the contents of `worker.js` into the editor
4. Click **Deploy**
5. Go to the worker's **Settings** → **Variables** → **KV Namespace Bindings**
6. Add binding: Variable name = `CDN_ROUTES`, KV namespace = the one you created

## Step 3: Add DNS Record

1. Go to Cloudflare dashboard → **hyperabyss.com** → **DNS**
2. Add record:
   - Type: `AAAA`
   - Name: `cdn`
   - Content: `100::` (placeholder — Worker handles the actual routing)
   - Proxy: **ON** (orange cloud)
3. This creates `cdn.hyperabyss.com`

## Step 4: Add Worker Route

1. Go to **hyperabyss.com** → **Workers Routes**
2. Add route:
   - Route: `cdn.hyperabyss.com/*`
   - Worker: `sims4-cdn`

## Step 5: Add File Mappings

For each file you host on the seedbox, add a KV entry mapping the clean path to the Secure Link.

### Via Wrangler CLI:

```bash
# Manifest
wrangler kv:key put --namespace-id YOUR_KV_ID "manifest.json" "https://rapidseedbox123.swift-nl.seedbox.vip/path/to/manifest.json"

# Patches
wrangler kv:key put --namespace-id YOUR_KV_ID "patches/1.121.372_to_1.122.100.zip" "https://rapidseedbox123.swift-nl.seedbox.vip/path/to/patch1.zip"

# DLCs
wrangler kv:key put --namespace-id YOUR_KV_ID "dlc/EP01.zip" "https://rapidseedbox123.swift-nl.seedbox.vip/path/to/EP01.zip"
wrangler kv:key put --namespace-id YOUR_KV_ID "dlc/GP01.zip" "https://rapidseedbox123.swift-nl.seedbox.vip/path/to/GP01.zip"

# Language files
wrangler kv:key put --namespace-id YOUR_KV_ID "language/de_DE.zip" "https://rapidseedbox123.swift-nl.seedbox.vip/path/to/de_DE.zip"
```

### Via Dashboard:

1. Go to **Workers & Pages** → **KV** → **CDN_ROUTES**
2. Click **Add entry**
3. Key: `dlc/EP01.zip`
4. Value: `https://rapidseedbox123.swift-nl.seedbox.vip/your-secure-link-path/EP01.zip`

## Step 6: Test

```bash
# Should download the file
curl -I https://cdn.hyperabyss.com/manifest.json

# Should return 404
curl -I https://cdn.hyperabyss.com/doesnt-exist.zip
```

## Adding New Files

When you upload a new file to the seedbox:

1. Upload file to seedbox via FTP/SFTP
2. Generate a Secure Link in File Commander
3. Add a KV entry: `wrangler kv:key put --namespace-id YOUR_KV_ID "path/filename" "SECURE_LINK_URL"`
4. File is now available at `https://cdn.hyperabyss.com/path/filename`

## URL Structure

```
cdn.hyperabyss.com/
├── manifest.json                          # Master manifest
├── patches/
│   ├── 1.121.372_to_1.122.100.zip        # Patch files
│   └── ...
├── dlc/
│   ├── EP01.zip                           # DLC archives
│   ├── GP01.zip
│   └── ...
└── language/
    ├── de_DE.zip                          # Language files
    └── ...
```

## Costs

| Service              | Cost        |
|----------------------|-------------|
| hyperabyss.com       | Already own |
| Cloudflare DNS       | Free        |
| Cloudflare Worker    | Free (100k req/day) |
| Cloudflare KV        | Free (100k reads/day, 1k writes/day) |
| RapidSeedbox Swift   | $8/mo       |
| **Total**            | **$8/mo**   |
