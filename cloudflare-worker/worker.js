/**
 * Sims 4 Updater CDN Worker — cdn.hyperabyss.com
 *
 * Proxies clean URLs to Whatbox seedbox via HTTPS with basic auth.
 * Users see: https://cdn.hyperabyss.com/patches/1.121.372_to_1.122.100.zip
 * Worker authenticates with Whatbox and streams the file back.
 *
 * SETUP:
 *   1. Create a KV namespace called "CDN_ROUTES" in Cloudflare dashboard
 *   2. Deploy this worker and bind CDN_ROUTES to it
 *   3. Add route: cdn.hyperabyss.com/* → this worker
 *   4. Add environment secrets: SEEDBOX_BASE_URL, SEEDBOX_USER, SEEDBOX_PASS
 *   5. Populate KV with path mappings (clean path → seedbox file path)
 *
 * ENVIRONMENT SECRETS (set in Worker Settings → Variables and Secrets):
 *   SEEDBOX_BASE_URL = "https://server.whatbox.ca/private"  (your Whatbox HTTPS URL)
 *   SEEDBOX_USER     = "your_whatbox_username"
 *   SEEDBOX_PASS     = "your_whatbox_password"
 *
 * KV ENTRIES (key = clean path, value = path on seedbox):
 *   "manifest.json"                        → "files/sims4/manifest.json"
 *   "patches/1.121.372_to_1.122.100.zip"  → "files/sims4/patches/1.121.372_to_1.122.100.zip"
 *   "dlc/EP01.zip"                         → "files/sims4/dlc/EP01.zip"
 *   "language/de_DE.zip"                   → "files/sims4/language/de_DE.zip"
 *
 *   OR if your seedbox paths match the clean paths, just use the same value:
 *   "dlc/EP01.zip"                         → "dlc/EP01.zip"
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Strip leading slash to get the clean path
    const path = url.pathname.slice(1);

    // Handle root / empty path
    if (!path) {
      return new Response("Sims 4 Updater CDN", {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      });
    }

    // Look up the seedbox path from KV
    const seedboxPath = await env.CDN_ROUTES.get(path);

    if (!seedboxPath) {
      return new Response("Not Found", { status: 404 });
    }

    // Build the full seedbox URL
    const baseUrl = env.SEEDBOX_BASE_URL.replace(/\/+$/, "");
    const seedboxUrl = `${baseUrl}/${seedboxPath}`;

    // Create basic auth header from secrets
    const credentials = btoa(`${env.SEEDBOX_USER}:${env.SEEDBOX_PASS}`);

    // Fetch from seedbox with authentication
    const seedboxResponse = await fetch(seedboxUrl, {
      headers: {
        "User-Agent": "HyperabyssCDN/1.0",
        "Authorization": `Basic ${credentials}`,
      },
      redirect: "follow",
    });

    if (!seedboxResponse.ok) {
      return new Response("Upstream error", { status: 502 });
    }

    // Stream the response back to the user with clean headers
    const headers = new Headers();
    headers.set("Content-Type", seedboxResponse.headers.get("Content-Type") || "application/octet-stream");
    headers.set("Content-Length", seedboxResponse.headers.get("Content-Length") || "");
    headers.set("Accept-Ranges", "bytes");
    headers.set("Cache-Control", "public, max-age=86400"); // Cache 24h at edge
    headers.set("Access-Control-Allow-Origin", "*");

    // Preserve content disposition for downloads
    const disposition = seedboxResponse.headers.get("Content-Disposition");
    if (disposition) {
      headers.set("Content-Disposition", disposition);
    } else {
      // Set filename from the clean path
      const filename = path.split("/").pop();
      headers.set("Content-Disposition", `attachment; filename="${filename}"`);
    }

    // Remove any headers that leak seedbox info
    headers.delete("Server");
    headers.delete("X-Powered-By");

    return new Response(seedboxResponse.body, {
      status: seedboxResponse.status,
      headers,
    });
  },
};
