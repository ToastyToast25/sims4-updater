/**
 * Sims 4 Updater Contribution API — api.hyperabyss.com
 *
 * Endpoints:
 *   POST /contribute            — Submit DLC metadata (from user apps)
 *   POST /contribute/greenluma  — Submit GreenLuma depot keys + manifests
 *   POST /stats/heartbeat       — Telemetry heartbeat (upsert user)
 *   POST /stats/event           — Telemetry event (append)
 *   GET  /admin                 — Dashboard to review contributions (password protected)
 *   GET  /admin/stats           — Analytics dashboard (password protected)
 *   GET  /admin/stats/api       — JSON: all Supabase view data
 *   GET  /admin/stats/recent    — JSON: last 50 events
 *   GET|POST /admin/approve/:id — Approve a contribution
 *   GET|POST /admin/reject/:id  — Reject a contribution
 *   GET  /admin/list            — JSON list of all contributions
 *   GET  /health                — Health check
 *
 * Environment:
 *   CONTRIBUTIONS    — KV namespace for storing contributions
 *   ADMIN_PASSWORD   — Password for admin dashboard
 *   DISCORD_WEBHOOK  — Discord webhook URL for notifications
 *   SUPABASE_URL     — Supabase project URL (e.g. https://xxx.supabase.co)
 *   SUPABASE_SERVICE_KEY — Supabase service_role key (server-side only)
 */

export default {
  async fetch(request, env) {
    try {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS headers for app requests
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Machine-Id, X-UID",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    // Health check
    if (path === "/health") {
      return json({ status: "ok" });
    }

    // Reject oversized request bodies globally (512KB max)
    if (request.method === "POST") {
      const contentLength = parseInt(request.headers.get("Content-Length") || "0");
      if (contentLength > 524288) {
        return json({ error: "Request too large" }, 413);
      }
    }

    // ── Ban check for user-facing routes ──
    const userPaths = ["/contribute", "/stats/", "/auth/", "/access/"];
    const isUserRoute = userPaths.some((p) => path.startsWith(p));
    if (isUserRoute && env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
      const banResult = await checkBanApi(request, env);
      if (banResult) return banResult;
    }

    // Token issuance (CDN auth)
    if (path === "/auth/token" && request.method === "POST") {
      return handleTokenRequest(request, env);
    }

    // Access request (private CDN)
    if (path === "/access/request" && request.method === "POST") {
      return handleAccessRequest(request, env);
    }

    // Contribution submission (from user apps)
    if (path === "/contribute" && request.method === "POST") {
      return handleContribution(request, env);
    }

    // GreenLuma key + manifest contribution
    if (path === "/contribute/greenluma" && request.method === "POST") {
      return handleGLContribution(request, env);
    }

    // Telemetry
    if (path === "/stats/heartbeat" && request.method === "POST") {
      return handleStatsHeartbeat(request, env);
    }
    if (path === "/stats/event" && request.method === "POST") {
      return handleStatsEvent(request, env);
    }

    // Admin routes
    if (path.startsWith("/admin")) {
      // Check admin auth
      const authErr = await checkAdminAuth(request, env);
      if (authErr) return authErr;

      const pw = url.searchParams.get("pw") || request.headers.get("X-Admin-Password") || "";

      if (path === "/admin" && request.method === "GET") {
        return serveDashboard(env, pw);
      }
      // Ban management
      if (path === "/admin/bans" && request.method === "GET") {
        return serveBansDashboard(env, pw);
      }
      if (path === "/admin/bans/api" && request.method === "GET") {
        return getBansData(env);
      }
      if (path === "/admin/bans/create" && request.method === "POST") {
        return createBan(request, env);
      }
      if (path.startsWith("/admin/bans/remove/") && request.method === "POST") {
        const id = path.replace("/admin/bans/remove/", "");
        return removeBan(env, id);
      }
      // Access management (private CDNs)
      if (path === "/admin/access" && request.method === "GET") {
        return serveAccessDashboard(env, pw);
      }
      if (path === "/admin/access/api" && request.method === "GET") {
        return getAccessData(env);
      }
      if (path.startsWith("/admin/access/approve/") && request.method === "POST") {
        const id = path.replace("/admin/access/approve/", "");
        return approveAccess(env, id);
      }
      if (path.startsWith("/admin/access/deny/") && request.method === "POST") {
        const id = path.replace("/admin/access/deny/", "");
        return denyAccess(env, id);
      }
      if (path === "/admin/access/bulk" && request.method === "POST") {
        return bulkAccessAction(request, env);
      }
      if (path === "/admin/stats" && request.method === "GET") {
        return serveStatsDashboard(env, pw);
      }
      if (path === "/admin/stats/api" && request.method === "GET") {
        const days = url.searchParams.get("days") || "30";
        return getStatsData(env, days);
      }
      if (path === "/admin/stats/recent" && request.method === "GET") {
        return getRecentEvents(env);
      }
      if (path === "/admin/list" && request.method === "GET") {
        return listContributions(env);
      }
      if (path === "/admin/gl/list" && request.method === "GET") {
        return listGLContributions(env);
      }
      if (path.startsWith("/admin/approve/") && request.method === "POST") {
        const id = path.replace("/admin/approve/", "");
        if (!/^(EP|GP|SP|FP|KP)\d{2}$/.test(id)) return json({ error: "Invalid DLC ID format" }, 400);
        return updateStatus(env, id, "approved");
      }
      if (path.startsWith("/admin/reject/") && request.method === "POST") {
        const id = path.replace("/admin/reject/", "");
        if (!/^(EP|GP|SP|FP|KP)\d{2}$/.test(id)) return json({ error: "Invalid DLC ID format" }, 400);
        return updateStatus(env, id, "rejected");
      }
      if (path.startsWith("/admin/gl/approve/") && request.method === "POST") {
        const depotId = path.replace("/admin/gl/approve/", "");
        if (!/^\d+$/.test(depotId)) return json({ error: "Invalid depot ID" }, 400);
        return updateGLStatus(env, depotId, "approved");
      }
      if (path.startsWith("/admin/gl/reject/") && request.method === "POST") {
        const depotId = path.replace("/admin/gl/reject/", "");
        if (!/^\d+$/.test(depotId)) return json({ error: "Invalid depot ID" }, 400);
        return updateGLStatus(env, depotId, "rejected");
      }
      // CDN Settings
      if (path === "/admin/settings/api" && request.method === "GET") {
        return getCDNSettingsData(env);
      }
      if (path === "/admin/settings/update" && request.method === "POST") {
        return updateCDNSetting(request, env);
      }
      // Connected clients (token log)
      if (path === "/admin/clients/api" && request.method === "GET") {
        return getClientsData(env);
      }
    }

    return new Response("Not Found", { status: 404 });
    } catch (err) {
      console.error("API worker unhandled error:", err.message, err.stack);
      return json({ error: "internal_error" }, 500);
    }
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Shared navigation bar for admin dashboards.
 * @param {string} active - Current page key
 * @param {string} pw - Admin password for nav links
 * @returns {{ css: string, html: string }}
 */
function adminNav(active, pw) {
  const pages = [
    { id: "stats", path: "/admin/stats", label: "Analytics", icon: "\u{1F4CA}" },
    { id: "contributions", path: "/admin", label: "Contributions", icon: "\u{1F4E6}" },
    { id: "bans", path: "/admin/bans", label: "Bans", icon: "\u{1F6AB}" },
    { id: "access", path: "/admin/access", label: "Access", icon: "\u{1F511}" },
  ];
  const css = `
  .admin-nav { background: #0d1117; border-bottom: 1px solid #21262d; padding: 8px 24px; display: flex; gap: 4px; position: sticky; top: 53px; z-index: 99; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .admin-nav a { padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; color: #8b949e; text-decoration: none; transition: all 0.15s; white-space: nowrap; flex-shrink: 0; }
  .admin-nav a:hover { color: #e1e4e8; background: #161b22; }
  .admin-nav a.active { color: #e1e4e8; background: #21262d; font-weight: 600; }
  .admin-nav .nav-icon { margin-right: 5px; }
  @media (max-width: 768px) { .admin-nav { padding: 6px 12px; top: 0; } .admin-nav a { padding: 6px 10px; font-size: 12px; } }`;
  const epw = encodeURIComponent(pw || "");
  const links = pages
    .map(
      (p) =>
        `<a href="${p.path}?pw=${epw}" class="${p.id === active ? "active" : ""}">`+
        `<span class="nav-icon">${p.icon}</span>${p.label}</a>`
    )
    .join("");
  const html = `<nav class="admin-nav">${links}</nav>`;
  return { css, html };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Content-Type-Options": "nosniff",
      "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Machine-Id, X-UID",
    },
  });
}

/**
 * Escape HTML entities to prevent XSS in rendered dashboard pages.
 */
function escapeHtml(str) {
  if (typeof str !== "string") return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

/**
 * Sanitize a value for use in Supabase PostgREST filter expressions.
 * Strips characters that could inject additional filter operators.
 */
function sanitizeFilterValue(val) {
  if (!val || typeof val !== "string") return "";
  // Only allow alphanumeric, dots, colons, hyphens (covers IPs, hex IDs, UIDs)
  return val.replace(/[^a-zA-Z0-9._:\-]/g, "").substring(0, 200);
}

function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const enc = new TextEncoder();
  const aBuf = enc.encode(a);
  const bBuf = enc.encode(b);
  // Pad to equal length to prevent length-based timing leaks
  const maxLen = Math.max(aBuf.length, bBuf.length);
  const paddedA = new Uint8Array(maxLen);
  const paddedB = new Uint8Array(maxLen);
  paddedA.set(aBuf);
  paddedB.set(bBuf);
  let result = aBuf.length ^ bBuf.length; // Non-zero if lengths differ
  for (let i = 0; i < maxLen; i++) {
    result |= paddedA[i] ^ paddedB[i];
  }
  return result === 0;
}

async function checkAdminAuth(request, env) {
  const url = new URL(request.url);
  const pw = url.searchParams.get("pw") ||
    request.headers.get("X-Admin-Password");

  if (!pw || !timingSafeEqual(pw, env.ADMIN_PASSWORD || "")) {
    // Brute-force protection: rate limit failed admin auth by IP
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const rlKey = `admin_rl:${ip}`;
    const now = Math.floor(Date.now() / 1000);
    const data = await env.CONTRIBUTIONS.get(rlKey);
    if (data) {
      const parsed = JSON.parse(data);
      if (parsed.failures >= 10 && (now - parsed.first) < 900) {
        return new Response("Too many attempts. Try again later.", {
          status: 429,
          headers: { "Content-Type": "text/plain" },
        });
      }
      if ((now - parsed.first) >= 900) {
        await env.CONTRIBUTIONS.put(rlKey, JSON.stringify({ failures: 1, first: now }), { expirationTtl: 900 });
      } else {
        parsed.failures++;
        await env.CONTRIBUTIONS.put(rlKey, JSON.stringify(parsed), { expirationTtl: 900 });
      }
    } else {
      await env.CONTRIBUTIONS.put(rlKey, JSON.stringify({ failures: 1, first: now }), { expirationTtl: 900 });
    }
    return new Response("Unauthorized. Add ?pw=YOUR_PASSWORD to the URL.", {
      status: 401,
      headers: { "Content-Type": "text/plain" },
    });
  }
  return null;
}

// ---------------------------------------------------------------------------
// Rate limiting (simple IP-based, stored in KV)
// ---------------------------------------------------------------------------

async function checkRateLimit(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const key = `ratelimit:${ip}`;
  const now = Math.floor(Date.now() / 1000);

  const data = await env.CONTRIBUTIONS.get(key);
  if (data) {
    const parsed = JSON.parse(data);
    // Max 5 submissions per hour per IP
    if (parsed.count >= 5 && (now - parsed.first) < 3600) {
      return true; // rate limited
    }
    if ((now - parsed.first) >= 3600) {
      // Reset window
      await env.CONTRIBUTIONS.put(key, JSON.stringify({ count: 1, first: now }), { expirationTtl: 3600 });
      return false;
    }
    parsed.count++;
    await env.CONTRIBUTIONS.put(key, JSON.stringify(parsed), { expirationTtl: 3600 });
    return false;
  }

  await env.CONTRIBUTIONS.put(key, JSON.stringify({ count: 1, first: now }), { expirationTtl: 3600 });
  return false;
}

// ---------------------------------------------------------------------------
// Telemetry rate limiting (per-UID, stored in KV)
// ---------------------------------------------------------------------------

async function checkStatsRateLimit(env, uid, type) {
  // type: "heartbeat" (15/hour for 5-min pings) or "event" (50/hour)
  const maxCount = type === "heartbeat" ? 15 : 50;
  const key = `stats_rl:${type}:${uid}`;
  const now = Math.floor(Date.now() / 1000);

  const data = await env.CONTRIBUTIONS.get(key);
  if (data) {
    const parsed = JSON.parse(data);
    if (parsed.count >= maxCount && (now - parsed.first) < 3600) {
      return true; // rate limited
    }
    if ((now - parsed.first) >= 3600) {
      await env.CONTRIBUTIONS.put(key, JSON.stringify({ count: 1, first: now }), { expirationTtl: 3600 });
      return false;
    }
    parsed.count++;
    await env.CONTRIBUTIONS.put(key, JSON.stringify(parsed), { expirationTtl: 3600 });
    return false;
  }

  await env.CONTRIBUTIONS.put(key, JSON.stringify({ count: 1, first: now }), { expirationTtl: 3600 });
  return false;
}

// ---------------------------------------------------------------------------
// Telemetry handlers — proxy to Supabase
// ---------------------------------------------------------------------------

async function handleStatsHeartbeat(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  // Validate required fields
  if (!body.uid || typeof body.uid !== "string" || body.uid.length < 16) {
    return json({ error: "Missing or invalid uid" }, 400);
  }
  if (!body.app_version || typeof body.app_version !== "string") {
    return json({ error: "Missing app_version" }, 400);
  }

  // Rate limit: 15 heartbeats per hour per UID (5-min periodic pings)
  if (await checkStatsRateLimit(env, body.uid, "heartbeat")) {
    return json({ status: "rate_limited", message: "15 heartbeats per hour" }, 429);
  }

  // Truncate helper for string fields
  function trunc(val, maxLen) {
    if (typeof val !== "string") return val;
    return val.substring(0, maxLen);
  }

  // Forward upsert to Supabase (server-side timestamp, truncated fields)
  const payload = {
    uid: trunc(body.uid, 128),
    session_id: trunc(body.session_id || "", 64) || null,
    app_version: trunc(body.app_version, 32),
    game_version: trunc(body.game_version || "", 32) || null,
    os_version: trunc(body.os_version || "", 64) || null,
    locale: trunc(body.locale || "", 10) || null,
    crack_format: trunc(body.crack_format || "", 32) || null,
    dlc_count: typeof body.dlc_count === "number" ? Math.min(Math.max(body.dlc_count, 0), 9999) : null,
    game_detected: !!body.game_detected,
    last_seen: new Date().toISOString(),
  };

  const resp = await supabasePost(env, "/rest/v1/users", payload, true);
  if (!resp.ok) {
    const text = await resp.text();
    return json({ status: "error", message: `Supabase error: ${resp.status}` }, 502);
  }

  return json({ status: "ok", message: "Heartbeat recorded" });
}

async function handleStatsEvent(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  // Validate required fields
  if (!body.uid || typeof body.uid !== "string" || body.uid.length < 16) {
    return json({ error: "Missing or invalid uid" }, 400);
  }
  if (!body.event_type || typeof body.event_type !== "string") {
    return json({ error: "Missing event_type" }, 400);
  }

  // Rate limit: 50 events per hour per UID
  if (await checkStatsRateLimit(env, body.uid, "event")) {
    return json({ status: "rate_limited", message: "50 events per hour" }, 429);
  }

  // Validate metadata size
  let metadata = body.metadata || null;
  if (metadata) {
    const metaStr = JSON.stringify(metadata);
    if (metaStr.length > 4096) {
      return json({ error: "metadata too large (max 4KB)" }, 400);
    }
  }

  const payload = {
    uid: typeof body.uid === "string" ? body.uid.substring(0, 128) : body.uid,
    event_type: typeof body.event_type === "string" ? body.event_type.substring(0, 64) : body.event_type,
    metadata,
  };

  const resp = await supabasePost(env, "/rest/v1/events", payload, false);
  if (!resp.ok) {
    const text = await resp.text();
    return json({ status: "error", message: `Supabase error: ${resp.status}` }, 502);
  }

  return json({ status: "ok", message: "Event recorded" });
}

async function supabasePost(env, path, data, upsert = false) {
  const headers = {
    "apikey": env.SUPABASE_SERVICE_KEY,
    "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
  };
  if (upsert) {
    headers["Prefer"] = "resolution=merge-duplicates";
  }
  return fetch(`${env.SUPABASE_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  });
}

async function supabaseRpc(env, funcName, params = {}) {
  return fetch(`${env.SUPABASE_URL}/rest/v1/rpc/${funcName}`, {
    method: "POST",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(params),
  });
}

// ---------------------------------------------------------------------------
// Contribution handling
// ---------------------------------------------------------------------------

async function handleContribution(request, env) {
  // Rate limit
  if (await checkRateLimit(request, env)) {
    return json({ error: "Rate limited. Max 5 submissions per hour." }, 429);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  // Validate required fields
  if (!body.dlc_id || !body.files || !Array.isArray(body.files)) {
    return json({ error: "Missing required fields: dlc_id, files[]" }, 400);
  }

  // Validate DLC ID format (e.g., EP01, GP05, SP18, FP01)
  if (!/^(EP|GP|SP|FP)\d{2}$/.test(body.dlc_id)) {
    return json({ error: "Invalid DLC ID format. Expected: EP01, GP05, etc." }, 400);
  }

  // Validate files array
  for (const f of body.files) {
    if (!f.name || !f.size || !f.md5) {
      return json({ error: "Each file must have: name, size, md5" }, 400);
    }
    // Validate MD5 format
    if (!/^[a-f0-9]{32}$/i.test(f.md5)) {
      return json({ error: `Invalid MD5 hash for ${f.name}` }, 400);
    }
    // Reject suspiciously named files
    if (f.name.includes("..") || f.name.includes("\\") || f.name.startsWith("/")) {
      return json({ error: `Invalid file name: ${f.name}` }, 400);
    }
  }

  // Build contribution record
  const id = `${Date.now()}-${body.dlc_id}`;
  const contribution = {
    id,
    dlc_id: body.dlc_id,
    dlc_name: body.dlc_name || "",
    files: body.files.map((f) => ({
      name: f.name,
      size: f.size,
      md5: f.md5,
    })),
    total_size: body.files.reduce((sum, f) => sum + (f.size || 0), 0),
    file_count: body.files.length,
    status: "pending",
    submitted_at: new Date().toISOString(),
    ip: request.headers.get("CF-Connecting-IP") || "unknown",
    app_version: body.app_version || "unknown",
  };

  // Check for duplicate (same DLC ID already pending)
  const existing = await env.CONTRIBUTIONS.get(`contrib:${body.dlc_id}`);
  if (existing) {
    const parsed = JSON.parse(existing);
    if (parsed.status === "pending") {
      return json({
        status: "duplicate",
        message: `${body.dlc_id} already has a pending contribution.`,
      });
    }
  }

  // Store in KV
  await env.CONTRIBUTIONS.put(`contrib:${body.dlc_id}`, JSON.stringify(contribution));

  // Also store in index for listing
  const indexData = await env.CONTRIBUTIONS.get("index");
  const index = indexData ? JSON.parse(indexData) : [];
  if (!index.includes(body.dlc_id)) {
    index.push(body.dlc_id);
    await env.CONTRIBUTIONS.put("index", JSON.stringify(index));
  }

  // Send Discord notification
  await notifyDiscord(env, contribution);

  return json({
    status: "accepted",
    message: `Contribution for ${body.dlc_id} submitted for review.`,
    id,
  });
}

// ---------------------------------------------------------------------------
// GreenLuma contribution handling
// ---------------------------------------------------------------------------

async function handleGLContribution(request, env) {
  // Rate limit (shared with file contributions)
  if (await checkRateLimit(request, env)) {
    return json({ error: "Rate limited. Max 5 submissions per hour." }, 429);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  if (!body.entries || !Array.isArray(body.entries) || body.entries.length === 0) {
    return json({ error: "Missing required field: entries[] (non-empty array)" }, 400);
  }

  if (body.entries.length > 50) {
    return json({ error: "Too many entries (max 50 per submission)" }, 400);
  }

  // Validate each entry
  const validEntries = [];
  for (const e of body.entries) {
    if (!e.depot_id || !e.key || !e.manifest_id || !e.manifest_b64) {
      return json({
        error: `Entry ${e.depot_id || "?"}: missing required fields (depot_id, key, manifest_id, manifest_b64)`,
      }, 400);
    }
    if (!/^\d+$/.test(e.depot_id)) {
      return json({ error: `Invalid depot_id: ${e.depot_id} (must be numeric)` }, 400);
    }
    if (!/^[0-9a-fA-F]{64}$/.test(e.key)) {
      return json({ error: `Invalid key for depot ${e.depot_id} (must be 64-char hex)` }, 400);
    }
    if (!/^\d+$/.test(e.manifest_id)) {
      return json({ error: `Invalid manifest_id for depot ${e.depot_id} (must be numeric)` }, 400);
    }

    // Validate base64 and size
    let decoded;
    try {
      decoded = atob(e.manifest_b64);
    } catch {
      return json({ error: `Invalid base64 for depot ${e.depot_id}` }, 400);
    }
    if (decoded.length > 500000) {
      return json({ error: `Manifest too large for depot ${e.depot_id} (${decoded.length} bytes, max 500KB)` }, 400);
    }
    if (decoded.length < 10) {
      return json({ error: `Manifest too small for depot ${e.depot_id} (${decoded.length} bytes)` }, 400);
    }

    validEntries.push({
      depot_id: e.depot_id,
      dlc_id: e.dlc_id || "",
      dlc_name: e.dlc_name || "",
      key: e.key.toLowerCase(),
      manifest_id: e.manifest_id,
      manifest_size: decoded.length,
    });
  }

  // Store each entry
  const stored = [];
  const skipped = [];
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const now = new Date().toISOString();

  for (const entry of validEntries) {
    // Check for duplicate
    const existing = await env.CONTRIBUTIONS.get(`gl:${entry.depot_id}`);
    if (existing) {
      const parsed = JSON.parse(existing);
      if (parsed.status === "pending") {
        skipped.push(entry.depot_id);
        continue;
      }
    }

    const record = {
      id: `${Date.now()}-gl-${entry.depot_id}`,
      ...entry,
      status: "pending",
      submitted_at: now,
      ip,
      app_version: body.app_version || "unknown",
    };

    // Store record (without manifest binary to keep it lean)
    await env.CONTRIBUTIONS.put(`gl:${entry.depot_id}`, JSON.stringify(record));

    // Store manifest binary separately
    const matchingEntry = body.entries.find((e) => e.depot_id === entry.depot_id);
    if (matchingEntry) {
      await env.CONTRIBUTIONS.put(`gl_manifest:${entry.depot_id}`, matchingEntry.manifest_b64);
    }

    stored.push(entry.depot_id);
  }

  // Update GL index
  const indexData = await env.CONTRIBUTIONS.get("gl_index");
  const index = indexData ? JSON.parse(indexData) : [];
  for (const depotId of stored) {
    if (!index.includes(depotId)) {
      index.push(depotId);
    }
  }
  await env.CONTRIBUTIONS.put("gl_index", JSON.stringify(index));

  // Discord notification
  if (env.DISCORD_WEBHOOK && stored.length > 0) {
    const fields = validEntries
      .filter((e) => stored.includes(e.depot_id))
      .map((e) => ({
        name: `${e.dlc_id || e.depot_id}`,
        value: `Depot: ${e.depot_id}\nKey: \`${e.key.slice(0, 8)}...${e.key.slice(-8)}\`\nManifest: ${e.manifest_id} (${e.manifest_size} bytes)`,
        inline: true,
      }));

    // Link to dashboard (no password in URLs)
    const actionLines = [`Review in [Admin Dashboard](https://api.hyperabyss.com/admin)`];

    const embed = {
      title: `GreenLuma Keys: ${stored.length} depot(s)`,
      color: 0x9b59b6,
      fields: [
        ...fields.slice(0, 20),
        { name: "Actions", value: actionLines.join("\n") },
        { name: "App Version", value: body.app_version || "unknown", inline: true },
      ],
      footer: { text: `IP: ${ip}` },
      timestamp: now,
    };

    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "CDN Contributions", embeds: [embed] }),
      });
    } catch {
      // Best effort
    }
  }

  return json({
    status: "accepted",
    message: `${stored.length} depot(s) submitted, ${skipped.length} skipped (already pending).`,
    stored,
    skipped,
  });
}

async function listGLContributions(env) {
  const indexData = await env.CONTRIBUTIONS.get("gl_index");
  const index = indexData ? JSON.parse(indexData) : [];

  const contributions = [];
  for (const depotId of index) {
    const data = await env.CONTRIBUTIONS.get(`gl:${depotId}`);
    if (data) {
      contributions.push(JSON.parse(data));
    }
  }

  contributions.sort((a, b) => {
    if (a.status === "pending" && b.status !== "pending") return -1;
    if (a.status !== "pending" && b.status === "pending") return 1;
    return new Date(b.submitted_at) - new Date(a.submitted_at);
  });

  return json(contributions);
}

async function updateGLStatus(env, depotId, newStatus) {
  const data = await env.CONTRIBUTIONS.get(`gl:${depotId}`);
  if (!data) {
    return json({ error: "GL contribution not found" }, 404);
  }

  const contribution = JSON.parse(data);
  contribution.status = newStatus;
  contribution.reviewed_at = new Date().toISOString();

  await env.CONTRIBUTIONS.put(`gl:${depotId}`, JSON.stringify(contribution));

  // Discord notification
  if (env.DISCORD_WEBHOOK) {
    const color = newStatus === "approved" ? 0x2ecc71 : 0xe74c3c;
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Contributions",
          embeds: [{
            title: `GL ${depotId} ${newStatus.toUpperCase()}`,
            color,
            description: `GreenLuma depot ${depotId} (${contribution.dlc_id}) has been ${newStatus}.`,
            timestamp: contribution.reviewed_at,
          }],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: newStatus, depot_id: depotId });
}

// ---------------------------------------------------------------------------
// Discord notification
// ---------------------------------------------------------------------------

async function notifyDiscord(env, contribution) {
  if (!env.DISCORD_WEBHOOK) return;

  const sizeMB = (contribution.total_size / 1024 / 1024).toFixed(1);
  const approveUrl = `https://api.hyperabyss.com/admin`;
  const rejectUrl = `https://api.hyperabyss.com/admin`;

  const embed = {
    title: `New DLC Contribution: ${contribution.dlc_id}`,
    color: 0x3498db,
    fields: [
      { name: "DLC", value: `${contribution.dlc_id} ${contribution.dlc_name ? `(${contribution.dlc_name})` : ""}`, inline: true },
      { name: "Files", value: `${contribution.file_count} files`, inline: true },
      { name: "Total Size", value: `${sizeMB} MB`, inline: true },
      { name: "App Version", value: contribution.app_version, inline: true },
      { name: "Status", value: "Pending Review", inline: true },
      { name: "Actions", value: `[Approve](${approveUrl}) | [Reject](${rejectUrl})` },
    ],
    footer: { text: `ID: ${contribution.id}` },
    timestamp: contribution.submitted_at,
  };

  // Build the JSON file content for the contribution
  const fileJson = JSON.stringify(contribution, null, 2);
  const fileBlob = new Blob([fileJson], { type: "application/json" });

  // Use multipart/form-data to attach the file
  const formData = new FormData();
  formData.append("payload_json", JSON.stringify({
    username: "CDN Contributions",
    embeds: [embed],
  }));
  formData.append("files[0]", fileBlob, `${contribution.dlc_id}_contribution.json`);

  try {
    await fetch(env.DISCORD_WEBHOOK, {
      method: "POST",
      body: formData,
    });
  } catch {
    // Best effort — don't fail the contribution if Discord is down
  }
}

// ---------------------------------------------------------------------------
// Admin: List contributions
// ---------------------------------------------------------------------------

async function listContributions(env) {
  const indexData = await env.CONTRIBUTIONS.get("index");
  const index = indexData ? JSON.parse(indexData) : [];

  const contributions = [];
  for (const dlcId of index) {
    const data = await env.CONTRIBUTIONS.get(`contrib:${dlcId}`);
    if (data) {
      contributions.push(JSON.parse(data));
    }
  }

  // Sort: pending first, then by date
  contributions.sort((a, b) => {
    if (a.status === "pending" && b.status !== "pending") return -1;
    if (a.status !== "pending" && b.status === "pending") return 1;
    return new Date(b.submitted_at) - new Date(a.submitted_at);
  });

  return json(contributions);
}

// ---------------------------------------------------------------------------
// Admin: Update status
// ---------------------------------------------------------------------------

async function updateStatus(env, dlcId, newStatus) {
  const data = await env.CONTRIBUTIONS.get(`contrib:${dlcId}`);
  if (!data) {
    return json({ error: "Contribution not found" }, 404);
  }

  const contribution = JSON.parse(data);
  contribution.status = newStatus;
  contribution.reviewed_at = new Date().toISOString();

  await env.CONTRIBUTIONS.put(`contrib:${dlcId}`, JSON.stringify(contribution));

  // Discord notification for status change
  if (env.DISCORD_WEBHOOK) {
    const color = newStatus === "approved" ? 0x2ecc71 : 0xe74c3c;
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Contributions",
          embeds: [{
            title: `${contribution.dlc_id} ${newStatus.toUpperCase()}`,
            color,
            description: `Contribution for ${contribution.dlc_id} has been ${newStatus}.`,
            timestamp: contribution.reviewed_at,
          }],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: newStatus, dlc_id: dlcId });
}

// ---------------------------------------------------------------------------
// Stats: API + Dashboard
// ---------------------------------------------------------------------------

async function supabaseGet(env, path) {
  return fetch(`${env.SUPABASE_URL}${path}`, {
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
    },
  });
}

async function getStatsData(env, days) {
  // Use the get_stats RPC function with a configurable time range
  const d = parseInt(days) || 30;
  // Clamp: 0 (all-time) or 1–3650
  const clampedDays = d <= 0 ? 0 : Math.min(Math.max(d, 1), 3650);

  const resp = await supabaseRpc(env, "get_stats", { p_days: clampedDays });
  if (resp.ok) {
    const data = await resp.json();
    return json(data);
  }

  // Fallback: query views directly if RPC fails (e.g., function not deployed yet)
  const views = [
    "online_users", "active_users", "version_stats", "crack_format_stats",
    "locale_stats", "event_stats", "popular_dlcs", "update_stats",
    "download_volume", "session_stats", "game_version_stats",
    "daily_active_trend", "new_users_daily", "feature_usage",
    "error_summary", "dlc_count_distribution", "daily_events_trend",
  ];
  const results = {};
  const settled = await Promise.allSettled(
    views.map(async (v) => {
      const r = await supabaseGet(env, `/rest/v1/${v}?select=*`);
      if (r.ok) return { name: v, data: await r.json() };
      return { name: v, data: [] };
    })
  );
  for (const s of settled) {
    if (s.status === "fulfilled") results[s.value.name] = s.value.data;
    else results[s.reason?.name || "unknown"] = [];
  }
  results._fallback = true;
  return json(results);
}

async function getRecentEvents(env) {
  const resp = await supabaseGet(
    env,
    "/rest/v1/events?select=*&order=created_at.desc&limit=50"
  );
  if (!resp.ok) {
    return json({ error: `Supabase error: ${resp.status}` }, 502);
  }
  return json(await resp.json());
}

async function serveStatsDashboard(env, pw) {
  const nav = adminNav("stats", pw);
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sims 4 Updater — Analytics</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0d12; color: #e1e4e8; min-height: 100vh; }
  .header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .logo { width: 32px; height: 32px; background: linear-gradient(135deg, #58a6ff, #3b82f6); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; }
  .header h1 { font-size: 18px; color: #e1e4e8; font-weight: 600; }
  .header-right { display: flex; align-items: center; gap: 10px; }
  .auto-refresh-toggle { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #8b949e; cursor: pointer; }
  .auto-refresh-toggle input { accent-color: #58a6ff; }
  .last-updated { font-size: 11px; color: #484f58; }
  ${nav.css}
  .container { max-width: 1280px; margin: 0 auto; padding: 24px; }
  .section-title { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin: 24px 0 12px; font-weight: 600; }
  .section-title:first-child { margin-top: 0; }

  /* Metric cards */
  .metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 12px; }
  .metrics.three { grid-template-columns: repeat(3, 1fr); }
  .metric { background: #161b22; padding: 18px; border-radius: 10px; border: 1px solid #30363d; }
  .metric-value { font-size: 28px; font-weight: 700; line-height: 1; }
  .metric-label { font-size: 11px; color: #8b949e; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.4px; }
  .metric-value.green { color: #2ecc71; }
  .metric-value.blue { color: #58a6ff; }
  .metric-value.orange { color: #f0ad4e; }
  .metric-value.red { color: #e74c3c; }
  .online-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #2ecc71; margin-right: 6px; animation: pulse-dot 2s infinite; }
  @keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

  /* Bar charts */
  .charts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 12px; }
  .chart-card { background: #161b22; border-radius: 10px; border: 1px solid #30363d; padding: 18px; }
  .chart-title { font-size: 13px; color: #e1e4e8; font-weight: 600; margin-bottom: 14px; }
  .bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .bar-label { font-size: 12px; color: #8b949e; min-width: 100px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar-track { flex: 1; height: 18px; background: #0d1117; border-radius: 4px; overflow: hidden; position: relative; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; min-width: 2px; }
  .bar-fill.blue { background: linear-gradient(90deg, #1f6feb, #58a6ff); }
  .bar-fill.green { background: linear-gradient(90deg, #238636, #2ecc71); }
  .bar-fill.orange { background: linear-gradient(90deg, #d29922, #f0ad4e); }
  .bar-fill.purple { background: linear-gradient(90deg, #8b5cf6, #a78bfa); }
  .bar-count { font-size: 11px; color: #58a6ff; min-width: 40px; font-weight: 600; }

  /* Activity feed */
  .feed-card { background: #161b22; border-radius: 10px; border: 1px solid #30363d; overflow: hidden; }
  .feed-header { padding: 14px 18px; border-bottom: 1px solid #30363d; font-size: 13px; font-weight: 600; }
  .feed-scroll { max-height: 400px; overflow-y: auto; }
  .feed-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .feed-table th { text-align: left; padding: 8px 16px; color: #484f58; font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #21262d; position: sticky; top: 0; background: #161b22; }
  .feed-table td { padding: 7px 16px; border-bottom: 1px solid #1c2128; }
  .feed-table tr:hover td { background: rgba(88,166,255,0.03); }
  .event-type { color: #58a6ff; font-weight: 500; }
  .uid-short { color: #484f58; font-family: monospace; font-size: 11px; }
  .meta-preview { color: #8b949e; font-size: 11px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .time-col { color: #484f58; white-space: nowrap; }

  .loading { text-align: center; padding: 40px; color: #484f58; }

  /* Sparkline SVG charts */
  .sparkline-card { background: #161b22; border-radius: 10px; border: 1px solid #30363d; padding: 18px; }
  .sparkline-title { font-size: 13px; color: #e1e4e8; font-weight: 600; margin-bottom: 8px; }
  .sparkline-card svg { width: 100%; height: 80px; }
  .sparkline-card .spark-line { fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .sparkline-card .spark-area { opacity: 0.15; }
  .sparkline-card .spark-label { font-size: 10px; fill: #484f58; }
  .sparkline-card .spark-val { font-size: 10px; fill: #8b949e; text-anchor: end; }
  .sparklines { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 12px; }

  /* Error/warning metric */
  .metric-value.red { color: #e74c3c; }
  .metric-subtext { font-size: 10px; color: #484f58; margin-top: 2px; }

  @media (max-width: 1100px) {
    .metrics { grid-template-columns: repeat(3, 1fr) !important; }
    .charts { grid-template-columns: 1fr; }
    .sparklines { grid-template-columns: 1fr; }
  }
  @media (max-width: 768px) {
    .header { padding: 12px 16px; flex-wrap: wrap; gap: 8px; }
    .header h1 { font-size: 15px; }
    .header-right { width: 100%; justify-content: space-between; }
    .container { padding: 12px; }
    .metrics { grid-template-columns: repeat(2, 1fr) !important; gap: 8px; }
    .metric { padding: 12px; }
    .metric-value { font-size: 22px; }
    .charts { grid-template-columns: 1fr; gap: 8px; }
    .sparklines { grid-template-columns: 1fr; gap: 8px; }
    .section-title { font-size: 12px; margin: 16px 0 8px; }
    .feed-table th, .feed-table td { padding: 6px 8px; font-size: 11px; }
    .meta-preview { max-width: 120px; }
  }
  @media (max-width: 480px) {
    .metrics { grid-template-columns: 1fr 1fr !important; gap: 6px; }
    .metric-value { font-size: 18px; }
    .metric-label { font-size: 9px; }
    .bar-label { min-width: 60px; font-size: 10px; }
    .bar-count { font-size: 10px; min-width: 30px; }
  }
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div class="logo">S4</div>
    <h1>Sims 4 Updater &mdash; Analytics</h1>
  </div>
  <div class="header-right">
    <select id="timeRange" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:6px 10px;color:#e1e4e8;font-size:12px;outline:none;cursor:pointer">
      <option value="7">7 days</option>
      <option value="30" selected>30 days</option>
      <option value="60">60 days</option>
      <option value="90">90 days</option>
      <option value="365">1 year</option>
      <option value="0">All time</option>
    </select>
    <label class="auto-refresh-toggle">
      <input type="checkbox" id="autoRefresh" checked> Auto-refresh
    </label>
    <span class="last-updated" id="lastUpdated"></span>
  </div>
</div>
${nav.html}
<div class="container">
  <div id="content"><div class="loading">Loading analytics...</div></div>
</div>
<script>
var PW = new URLSearchParams(window.location.search).get("pw");
var BASE = window.location.origin;
var refreshTimer = null;
var currentDays = 30;

function getRangeLabel() {
  if (currentDays <= 0) return "All Time";
  if (currentDays === 365) return "1 Year";
  return currentDays + "d";
}

function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function api(path) {
  var sep = path.indexOf("?") >= 0 ? "&" : "?";
  return fetch(BASE + path + sep + "pw=" + PW).then(function(r) {
    if (!r.ok) return r.text().then(function(t) { try { return JSON.parse(t); } catch(e) { throw new Error("Server error " + r.status); } });
    return r.json();
  });
}

function fmtSize(b) {
  if (!b || b === 0) return "0 B";
  if (b >= 1073741824) return (b/1073741824).toFixed(1) + " GB";
  if (b >= 1048576) return (b/1048576).toFixed(1) + " MB";
  if (b >= 1024) return (b/1024).toFixed(0) + " KB";
  return b + " B";
}
function fmtSpeed(bps) {
  if (!bps || bps === 0) return "0 B/s";
  if (bps >= 1048576) return (bps/1048576).toFixed(1) + " MB/s";
  if (bps >= 1024) return (bps/1024).toFixed(0) + " KB/s";
  return Math.round(bps) + " B/s";
}
function fmtDuration(s) {
  if (!s || s <= 0) return "0s";
  if (s < 60) return Math.round(s) + "s";
  if (s < 3600) return Math.round(s/60) + "m";
  return (s/3600).toFixed(1) + "h";
}
function fmtPct(n, d) { return d > 0 ? Math.round(100 * n / d) + "%" : "N/A"; }
function timeAgo(iso) {
  if (!iso) return "";
  var diff = Date.now() - new Date(iso).getTime();
  var mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  var hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + "h ago";
  return Math.floor(hrs/24) + "d ago";
}
function row(a) { return a && a[0] ? a[0] : {}; }
function barChart(title, items, colorClass) {
  if (!items || items.length === 0) return '<div class="chart-card"><div class="chart-title">' + title + '</div><div style="color:#484f58;font-size:12px">No data</div></div>';
  var max = Math.max.apply(null, items.map(function(i) { return i.count; }));
  var html = '<div class="chart-card"><div class="chart-title">' + title + '</div>';
  items.slice(0, 10).forEach(function(item) {
    var pct = max > 0 ? Math.max(2, (item.count / max) * 100) : 2;
    html += '<div class="bar-row"><span class="bar-label">' + esc(item.label) + '</span>';
    html += '<div class="bar-track"><div class="bar-fill ' + colorClass + '" style="width:' + pct + '%"></div></div>';
    html += '<span class="bar-count">' + item.count + '</span></div>';
  });
  html += '</div>';
  return html;
}

function sparkline(title, data, valueKey, color) {
  if (!data || data.length === 0) return '<div class="sparkline-card"><div class="sparkline-title">' + title + '</div><div style="color:#484f58;font-size:12px">No data</div></div>';
  var vals = data.map(function(d) { return d[valueKey] || 0; });
  var max = Math.max.apply(null, vals);
  if (max === 0) max = 1;
  var w = 400, ht = 80, pad = 2;
  var step = vals.length > 1 ? (w - pad * 2) / (vals.length - 1) : 0;
  var pts = vals.map(function(v, i) { return (pad + i * step).toFixed(1) + "," + (ht - pad - ((v / max) * (ht - pad * 2 - 10))).toFixed(1); });
  var line = pts.join(" ");
  var area = pts.join(" ") + " " + (pad + (vals.length - 1) * step).toFixed(1) + "," + (ht - pad) + " " + pad + "," + (ht - pad);
  var first = data[0].day ? data[0].day.substring(5) : "";
  var last = data[data.length - 1].day ? data[data.length - 1].day.substring(5) : "";
  var total = vals.reduce(function(a, b) { return a + b; }, 0);
  var latest = vals[vals.length - 1];
  var html = '<div class="sparkline-card"><div class="sparkline-title">' + title;
  html += ' <span style="color:' + color + ';font-size:14px;font-weight:700;float:right">' + latest + ' today</span></div>';
  html += '<svg viewBox="0 0 ' + w + ' ' + ht + '" preserveAspectRatio="none">';
  html += '<polygon class="spark-area" points="' + area + '" fill="' + color + '"/>';
  html += '<polyline class="spark-line" points="' + line + '" stroke="' + color + '"/>';
  html += '<text x="' + pad + '" y="' + (ht - 1) + '" class="spark-label">' + first + '</text>';
  html += '<text x="' + (w - pad) + '" y="' + (ht - 1) + '" class="spark-val">' + last + '</text>';
  html += '</svg></div>';
  return html;
}

function render(stats, events) {
  var au = row(stats.active_users || []);
  var on = row(stats.online_users || []);
  var us = row(stats.update_stats || []);
  var dv = row(stats.download_volume || []);
  var ss = row(stats.session_stats || []);
  var errs = stats.error_summary || [];

  // Calculate new users today from daily trend (only if last entry is actually today)
  var nud = stats.new_users_daily || [];
  var todayStr = new Date().toISOString().substring(0, 10);
  var lastEntry = nud.length > 0 ? nud[nud.length - 1] : null;
  var newToday = (lastEntry && lastEntry.day && lastEntry.day.substring(0, 10) === todayStr) ? (lastEntry.new_users || 0) : 0;

  // Total errors (' + getRangeLabel() + ')
  var totalErrors = errs.reduce(function(s, e) { return s + (e.count || 0); }, 0);
  var errorUsers = errs.reduce(function(s, e) { return s + (e.affected_users || 0); }, 0);

  var h = '';
  if (stats._fallback) {
    h += '<div style="background:#5c3d00;border:1px solid #d29922;color:#e3b341;padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:13px">';
    h += 'RPC function unavailable — showing default 30-day data. Time range selection is disabled.</div>';
  }

  // Top metrics
  h += '<div class="section-title">Users</div>';
  h += '<div class="metrics" style="grid-template-columns:repeat(6,1fr)">';
  h += '<div class="metric"><div class="metric-value green"><span class="online-dot"></span>' + (on.count || 0) + '</div><div class="metric-label">Online Now</div></div>';
  h += '<div class="metric"><div class="metric-value blue">' + (au.dau || 0) + '</div><div class="metric-label">Daily Active</div></div>';
  h += '<div class="metric"><div class="metric-value blue">' + (au.wau || 0) + '</div><div class="metric-label">Weekly Active</div></div>';
  h += '<div class="metric"><div class="metric-value blue">' + (au.mau || 0) + '</div><div class="metric-label">Monthly Active</div></div>';
  h += '<div class="metric"><div class="metric-value blue">' + (au.total || 0) + '</div><div class="metric-label">Total Users</div></div>';
  h += '<div class="metric"><div class="metric-value green">' + newToday + '</div><div class="metric-label">New Today</div></div>';
  h += '</div>';

  // Daily trends (sparklines)
  var trendNote = (currentDays > 90 || currentDays <= 0) ? ' <span style="color:#484f58;font-size:12px">(charts show last 90 days)</span>' : '';
  h += '<div class="section-title">Activity Trends (' + getRangeLabel() + ')' + trendNote + '</div>';
  h += '<div class="sparklines">';
  h += sparkline("Daily Active Users", stats.daily_active_trend || [], "active_users", "#58a6ff");
  h += sparkline("New Users", stats.new_users_daily || [], "new_users", "#2ecc71");
  h += sparkline("Daily Events", stats.daily_events_trend || [], "event_count", "#f0ad4e");
  // DLC count distribution as a bar chart in the 4th sparkline slot
  var dc = (stats.dlc_count_distribution || []).map(function(r) { return {label: r.bucket || "?", count: r.count}; });
  h += barChart("DLC Count Distribution", dc, "purple");
  h += '</div>';

  // Downloads + updates + errors
  h += '<div class="section-title">Downloads &amp; Updates</div>';
  h += '<div class="metrics" style="grid-template-columns:repeat(5,1fr)">';
  h += '<div class="metric"><div class="metric-value orange">' + (dv.total_downloads || 0) + '</div><div class="metric-label">DLC Downloads (' + getRangeLabel() + ')</div></div>';
  h += '<div class="metric"><div class="metric-value orange">' + fmtSize(dv.total_bytes || 0) + '</div><div class="metric-label">Download Volume (' + getRangeLabel() + ')</div></div>';
  h += '<div class="metric"><div class="metric-value green">' + fmtPct(us.completed || 0, us.started || 0) + '</div><div class="metric-label">Update Success Rate</div></div>';
  h += '<div class="metric"><div class="metric-value blue">' + (us.started || 0) + '</div><div class="metric-label">Updates Started (' + getRangeLabel() + ')</div></div>';
  h += '<div class="metric"><div class="metric-value red">' + totalErrors + '</div><div class="metric-label">Errors (' + getRangeLabel() + ')</div><div class="metric-subtext">' + errorUsers + ' users affected</div></div>';
  h += '</div>';

  // Charts
  h += '<div class="section-title">Distributions (' + getRangeLabel() + ')</div>';
  h += '<div class="charts">';
  var vs = (stats.version_stats || []).map(function(r) { return {label: r.app_version || "?", count: r.count}; });
  var gv = (stats.game_version_stats || []).map(function(r) { return {label: r.game_version || "unknown", count: r.count}; });
  var cs = (stats.crack_format_stats || []).map(function(r) { return {label: r.crack_format || "unknown", count: r.count}; });
  var ls = (stats.locale_stats || []).map(function(r) { return {label: r.locale || "unknown", count: r.count}; });
  var fu = (stats.feature_usage || []).map(function(r) { return {label: r.feature || "?", count: r.visits}; });
  var pd = (stats.popular_dlcs || []).map(function(r) { return {label: r.dlc_id || "?", count: r.downloads, extra: fmtSize(r.total_bytes)}; });
  h += barChart("App Version", vs, "blue");
  h += barChart("Game Version", gv, "green");
  h += barChart("Crack Format", cs, "green");
  h += barChart("Locale", ls, "orange");
  h += barChart("Feature Usage (Tab Visits)", fu, "blue");

  // Popular DLCs — custom to show size
  if (pd.length > 0) {
    var maxDl = Math.max.apply(null, pd.map(function(i) { return i.count; }));
    h += '<div class="chart-card"><div class="chart-title">Popular DLCs</div>';
    pd.slice(0, 10).forEach(function(item) {
      var pct = maxDl > 0 ? Math.max(2, (item.count / maxDl) * 100) : 2;
      h += '<div class="bar-row"><span class="bar-label">' + esc(item.label) + '</span>';
      h += '<div class="bar-track"><div class="bar-fill purple" style="width:' + pct + '%"></div></div>';
      h += '<span class="bar-count">' + item.count + ' (' + item.extra + ')</span></div>';
    });
    h += '</div>';
  } else {
    h += barChart("Popular DLCs", [], "purple");
  }
  h += '</div>';

  // Error breakdown (if any errors)
  if (errs.length > 0) {
    h += '<div class="section-title">Errors &amp; Failures (' + getRangeLabel() + ')</div>';
    h += '<div class="charts"><div style="grid-column:1/-1">';
    var errItems = errs.map(function(r) { return {label: r.event_type + " (" + r.affected_users + " users)", count: r.count}; });
    h += barChart("Error Breakdown", errItems, "orange").replace('<div class="chart-card">', '<div class="chart-card" style="grid-column:1/-1">');
    h += '</div></div>';
  }

  // Session & download stats
  h += '<div class="section-title">Sessions &amp; Performance</div>';
  h += '<div class="metrics">';
  h += '<div class="metric"><div class="metric-value blue">' + (ss.total_sessions || 0) + '</div><div class="metric-label">Sessions (' + getRangeLabel() + ')</div></div>';
  h += '<div class="metric"><div class="metric-value blue">' + fmtDuration(ss.avg_duration || 0) + '</div><div class="metric-label">Avg Session</div></div>';
  h += '<div class="metric"><div class="metric-value blue">' + fmtDuration(ss.max_duration || 0) + '</div><div class="metric-label">Max Session</div></div>';
  h += '<div class="metric"><div class="metric-value orange">' + fmtSpeed(dv.avg_speed_bps || 0) + '</div><div class="metric-label">Avg DL Speed</div></div>';
  h += '<div class="metric"><div class="metric-value orange">' + fmtDuration(dv.avg_duration || 0) + '</div><div class="metric-label">Avg DL Duration</div></div>';
  h += '</div>';

  // Download reliability
  var dr = row(stats.download_reliability || []);
  if (dr.total_downloads > 0) {
    h += '<div class="section-title">Download Reliability (' + getRangeLabel() + ')</div>';
    h += '<div class="metrics" style="grid-template-columns:repeat(4,1fr)">';
    h += '<div class="metric"><div class="metric-value green">' + fmtPct(dr.total_downloads - (dr.with_retries || 0), dr.total_downloads) + '</div><div class="metric-label">First-Try Success</div></div>';
    h += '<div class="metric"><div class="metric-value orange">' + (dr.with_retries || 0) + '</div><div class="metric-label">Needed Retries</div></div>';
    h += '<div class="metric"><div class="metric-value blue">' + (dr.with_resume || 0) + '</div><div class="metric-label">Resumed Downloads</div></div>';
    h += '<div class="metric"><div class="metric-value red">' + (dr.registration_failures || 0) + '</div><div class="metric-label">Registration Failures</div></div>';
    h += '</div>';
  }

  // Patch performance
  var pds = row(stats.patch_download_stats || []);
  var pas = row(stats.patch_apply_stats || []);
  if ((pds.total_downloads || 0) > 0 || (pas.total_applies || 0) > 0) {
    h += '<div class="section-title">Patch Performance (' + getRangeLabel() + ')</div>';
    h += '<div class="metrics" style="grid-template-columns:repeat(5,1fr)">';
    h += '<div class="metric"><div class="metric-value blue">' + (pds.total_downloads || 0) + '</div><div class="metric-label">Patch Downloads</div></div>';
    h += '<div class="metric"><div class="metric-value blue">' + fmtSize(pds.total_bytes || 0) + '</div><div class="metric-label">Patch Volume</div></div>';
    h += '<div class="metric"><div class="metric-value orange">' + fmtSpeed(pds.avg_speed_bps || 0) + '</div><div class="metric-label">Avg Patch DL Speed</div></div>';
    h += '<div class="metric"><div class="metric-value orange">' + fmtDuration(pds.avg_download_seconds || 0) + '</div><div class="metric-label">Avg DL Time</div></div>';
    h += '<div class="metric"><div class="metric-value green">' + fmtDuration(pas.avg_apply_seconds || 0) + '</div><div class="metric-label">Avg Apply Time</div></div>';
    h += '</div>';
  }

  // DLC by pack type
  var dpt = (stats.dlc_by_pack_type || []).map(function(r) {
    return {label: r.pack_type || "?", count: r.downloads, extra: fmtSize(r.total_bytes || 0)};
  });
  if (dpt.length > 0) {
    h += '<div class="section-title">DLC Downloads by Pack Type (' + getRangeLabel() + ')</div>';
    h += '<div class="charts">';
    var maxPt = Math.max.apply(null, dpt.map(function(i) { return i.count; }));
    h += '<div class="chart-card"><div class="chart-title">Pack Type</div>';
    dpt.forEach(function(item) {
      var pct = maxPt > 0 ? Math.max(2, (item.count / maxPt) * 100) : 2;
      h += '<div class="bar-row"><span class="bar-label">' + esc(item.label) + '</span>';
      h += '<div class="bar-track"><div class="bar-fill green" style="width:' + pct + '%"></div></div>';
      h += '<span class="bar-count">' + item.count + ' (' + item.extra + ')</span></div>';
    });
    h += '</div>';
    // DLC toggle stats
    var dts = row(stats.dlc_toggle_stats || []);
    h += '<div class="chart-card"><div class="chart-title">DLC Toggles</div>';
    h += '<div style="padding:16px;font-size:14px;color:#8b949e">';
    h += '<div style="margin-bottom:8px">\u{1F504} <strong>' + (dts.total_applies || 0) + '</strong> config applies</div>';
    h += '<div style="margin-bottom:8px">\u2705 <strong>' + (dts.total_enabled || 0) + '</strong> DLCs enabled</div>';
    h += '<div>\u274C <strong>' + (dts.total_disabled || 0) + '</strong> DLCs disabled</div>';
    h += '</div></div>';
    h += '</div>';
  }

  // Event type breakdown
  var es = (stats.event_stats || []).map(function(r) { return {label: r.event_type, count: r.count}; });
  h += '<div class="section-title">Event Types (' + getRangeLabel() + ')</div>';
  h += '<div class="charts"><div style="grid-column:1/-1">';
  h += barChart("Events by Type", es, "blue").replace('<div class="chart-card">', '<div class="chart-card" style="grid-column:1/-1">');
  h += '</div></div>';

  // Recent events feed
  h += '<div class="section-title">Recent Events</div>';
  h += '<div class="feed-card"><div class="feed-header">Last 50 Events</div>';
  h += '<div class="feed-scroll"><table class="feed-table"><thead><tr>';
  h += '<th>Time</th><th>UID</th><th>Event</th><th>Metadata</th>';
  h += '</tr></thead><tbody>';
  if (events && events.length > 0) {
    events.forEach(function(ev) {
      var uid = ev.uid ? ev.uid.substring(0, 8) + "..." : "";
      var meta = ev.metadata ? JSON.stringify(ev.metadata) : "";
      if (meta.length > 80) meta = meta.substring(0, 80) + "...";
      h += '<tr><td class="time-col">' + timeAgo(ev.created_at) + '</td>';
      h += '<td class="uid-short">' + esc(uid) + '</td>';
      h += '<td class="event-type">' + esc(ev.event_type || "") + '</td>';
      h += '<td class="meta-preview">' + esc(meta) + '</td></tr>';
    });
  } else {
    h += '<tr><td colspan="4" style="color:#484f58;text-align:center;padding:20px">No events yet</td></tr>';
  }
  h += '</tbody></table></div></div>';

  document.getElementById("content").innerHTML = h;
}

function loadStats() {
  var daysParam = currentDays <= 0 ? "0" : String(currentDays);
  Promise.all([
    api("/admin/stats/api?days=" + daysParam),
    api("/admin/stats/recent"),
  ]).then(function(results) {
    render(results[0], results[1]);
    document.getElementById("lastUpdated").textContent = "Updated " + new Date().toLocaleTimeString();
  }).catch(function(e) {
    document.getElementById("content").innerHTML = '<div class="loading" style="color:#e74c3c">Failed to load: ' + esc(e.message) + '</div>';
  });
}

document.getElementById("timeRange").addEventListener("change", function(e) {
  currentDays = parseInt(e.target.value);
  document.getElementById("content").innerHTML = '<div class="loading">Loading analytics...</div>';
  loadStats();
});

document.getElementById("autoRefresh").addEventListener("change", function(e) {
  if (e.target.checked) startAutoRefresh();
  else if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
});
function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(function() {
    if (document.getElementById("autoRefresh").checked) loadStats();
  }, 60000);
}

loadStats();
startAutoRefresh();
</script>
</body>
</html>`;
  return new Response(html, { headers: { "Content-Type": "text/html", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Strict-Transport-Security": "max-age=31536000; includeSubDomains", "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'" } });
}

// ---------------------------------------------------------------------------
// Admin: Contributions Dashboard HTML
// ---------------------------------------------------------------------------

async function serveDashboard(env, pw) {
  const nav = adminNav("contributions", pw);
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CDN Contributions - Admin</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0d12; color: #e1e4e8; min-height: 100vh; }

  /* Header */
  .header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; backdrop-filter: blur(12px); }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .logo { width: 32px; height: 32px; background: linear-gradient(135deg, #58a6ff, #3b82f6); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; }
  .header h1 { font-size: 18px; color: #e1e4e8; font-weight: 600; }
  .header-right { display: flex; align-items: center; gap: 10px; }
  .auto-refresh-toggle { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #8b949e; cursor: pointer; }
  .auto-refresh-toggle input { accent-color: #58a6ff; }
  .last-updated { font-size: 11px; color: #484f58; }

  /* Container */
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }

  /* Stats row */
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
  .stat { background: #161b22; padding: 20px; border-radius: 12px; border: 1px solid #30363d; transition: border-color 0.2s; cursor: pointer; }
  .stat:hover { border-color: #484f58; }
  .stat.active { border-color: #58a6ff; background: #161b2a; }
  .stat-num { font-size: 28px; font-weight: 700; line-height: 1; }
  .stat-num.pending-color { color: #f0ad4e; }
  .stat-num.approved-color { color: #2ecc71; }
  .stat-num.rejected-color { color: #e74c3c; }
  .stat-num.total-color { color: #58a6ff; }
  .stat-label { font-size: 12px; color: #8b949e; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px; }

  /* Toolbar */
  .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .search-box { flex: 1; min-width: 200px; background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 8px 12px; color: #e1e4e8; font-size: 14px; outline: none; transition: border-color 0.2s; }
  .search-box:focus { border-color: #58a6ff; }
  .search-box::placeholder { color: #484f58; }
  .sort-select { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 8px 12px; color: #e1e4e8; font-size: 13px; outline: none; cursor: pointer; }
  .btn-refresh { background: #21262d; border: 1px solid #30363d; border-radius: 8px; padding: 8px 14px; color: #e1e4e8; font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background 0.2s; }
  .btn-refresh:hover { background: #30363d; }
  .btn-refresh.spinning svg { animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Cards */
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 12px; overflow: hidden; transition: border-color 0.2s, transform 0.15s; }
  .card:hover { border-color: #484f58; }
  .card.pending { border-left: 4px solid #f0ad4e; }
  .card.approved { border-left: 4px solid #2ecc71; }
  .card.rejected { border-left: 4px solid #e74c3c; }

  .card-top { padding: 16px 20px; display: flex; justify-content: space-between; align-items: flex-start; }
  .card-info { flex: 1; }
  .card-title { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
  .dlc-id { font-size: 18px; font-weight: 700; color: #58a6ff; }
  .dlc-name { font-size: 14px; color: #8b949e; font-weight: 400; }
  .badge { padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
  .badge.pending { background: rgba(240,173,78,0.15); color: #f0ad4e; }
  .badge.approved { background: rgba(46,204,113,0.15); color: #2ecc71; }
  .badge.rejected { background: rgba(231,76,60,0.15); color: #e74c3c; }

  .card-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: 12px; color: #8b949e; }
  .meta-item { display: flex; align-items: center; gap: 4px; }
  .meta-item svg { width: 14px; height: 14px; fill: currentColor; opacity: 0.7; }

  /* Collapsible files */
  .files-toggle { width: 100%; background: #0d1117; border: none; border-top: 1px solid #21262d; padding: 8px 20px; color: #8b949e; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background 0.2s; }
  .files-toggle:hover { background: #161b22; color: #e1e4e8; }
  .files-toggle svg { width: 12px; height: 12px; fill: currentColor; transition: transform 0.2s; }
  .files-toggle.open svg { transform: rotate(90deg); }
  .files-body { background: #0d1117; max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
  .files-body.open { max-height: 500px; overflow-y: auto; }
  .files-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
  .files-table th { text-align: left; padding: 6px 20px; color: #484f58; font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #21262d; position: sticky; top: 0; background: #0d1117; }
  .files-table td { padding: 5px 20px; border-bottom: 1px solid #161b2208; }
  .files-table tr:hover td { background: rgba(88,166,255,0.03); }
  .file-name { color: #e1e4e8; }
  .file-size { color: #58a6ff; text-align: right; }
  .file-hash { color: #484f58; font-size: 11px; }

  /* Actions bar */
  .card-actions { padding: 12px 20px; background: #0d1117; border-top: 1px solid #21262d; display: flex; gap: 8px; align-items: center; }
  .btn { padding: 7px 16px; border: none; border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 600; transition: all 0.15s; display: inline-flex; align-items: center; gap: 6px; }
  .btn:active { transform: scale(0.97); }
  .btn-approve { background: #238636; color: #fff; }
  .btn-approve:hover { background: #2ea043; }
  .btn-reject { background: #da3633; color: #fff; }
  .btn-reject:hover { background: #e5534b; }
  .btn-secondary { background: #21262d; color: #e1e4e8; border: 1px solid #30363d; }
  .btn-secondary:hover { background: #30363d; border-color: #484f58; }
  .btn-sm { padding: 5px 10px; font-size: 11px; }
  .actions-spacer { flex: 1; }
  .reviewed-info { font-size: 11px; color: #484f58; }

  /* Toast */
  .toast-container { position: fixed; bottom: 24px; right: 24px; z-index: 1000; display: flex; flex-direction: column; gap: 8px; }
  .toast { padding: 12px 20px; border-radius: 10px; font-size: 13px; font-weight: 500; color: #fff; transform: translateX(120%); opacity: 0; transition: all 0.3s ease; display: flex; align-items: center; gap: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
  .toast.show { transform: translateX(0); opacity: 1; }
  .toast.success { background: #238636; }
  .toast.error { background: #da3633; }
  .toast.info { background: #1f6feb; }

  /* Empty state */
  .empty { text-align: center; padding: 60px 20px; color: #484f58; }
  .empty-icon { font-size: 48px; margin-bottom: 12px; opacity: 0.4; }
  .empty-text { font-size: 16px; color: #8b949e; }
  .empty-sub { font-size: 13px; margin-top: 6px; }

  /* Loading skeleton */
  .skeleton { background: linear-gradient(90deg, #161b22 25%, #21262d 50%, #161b22 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 8px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  /* Responsive */
  @media (max-width: 768px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .toolbar { flex-direction: column; }
    .search-box { width: 100%; }
    .card-meta { gap: 8px; }
    .files-table th, .files-table td { padding: 5px 12px; }
    .file-hash { display: none; }
  }
  ${nav.css}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo">H</div>
    <h1>CDN Contributions</h1>
  </div>
  <div class="header-right">
    <label class="auto-refresh-toggle">
      <input type="checkbox" id="autoRefresh" checked>
      Auto-refresh (30s)
    </label>
    <span class="last-updated" id="lastUpdated"></span>
  </div>
</div>
${nav.html}

<div class="container">
  <div class="stats" id="stats">
    <div class="stat skeleton" style="height:80px"></div>
    <div class="stat skeleton" style="height:80px"></div>
    <div class="stat skeleton" style="height:80px"></div>
    <div class="stat skeleton" style="height:80px"></div>
  </div>

  <div class="toolbar">
    <input type="text" class="search-box" id="searchBox" placeholder="Search by DLC ID or name...">
    <select class="sort-select" id="sortSelect">
      <option value="status">Sort: Status (Pending first)</option>
      <option value="newest">Sort: Newest first</option>
      <option value="oldest">Sort: Oldest first</option>
      <option value="size-desc">Sort: Largest first</option>
      <option value="dlc-id">Sort: DLC ID</option>
    </select>
    <button class="btn-refresh" id="refreshBtn" onclick="loadData()">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 3a5 5 0 104.546 2.914.5.5 0 01.908-.418A6 6 0 118 2v1z"/><path d="M8 4.466V.534a.25.25 0 01.41-.192l2.36 1.966a.25.25 0 010 .384L8.41 4.658A.25.25 0 018 4.466z"/></svg>
      Refresh
    </button>
  </div>

  <div id="contributions"></div>
</div>

<div class="toast-container" id="toasts"></div>

<script>
var PW = new URLSearchParams(window.location.search).get("pw");
var BASE = window.location.origin;
var allData = [];
var filteredData = [];
var activeFilter = "all";
var refreshTimer = null;

function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function api(path, method) {
  method = method || "GET";
  var sep = path.indexOf("?") >= 0 ? "&" : "?";
  return fetch(BASE + path + sep + "pw=" + PW, { method: method }).then(function(r) {
    if (!r.ok) return r.text().then(function(t) { try { return JSON.parse(t); } catch(e) { throw new Error("Server error " + r.status); } });
    return r.json();
  });
}

function formatSize(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  if (bytes >= 1073741824) return (bytes/1073741824).toFixed(1) + " GB";
  if (bytes >= 1048576) return (bytes/1048576).toFixed(1) + " MB";
  if (bytes >= 1024) return (bytes/1024).toFixed(1) + " KB";
  return bytes + " B";
}

function timeAgo(iso) {
  var diff = Date.now() - new Date(iso).getTime();
  var mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  var hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + "h ago";
  var days = Math.floor(hrs / 24);
  if (days < 30) return days + "d ago";
  return new Date(iso).toLocaleDateString();
}

function showToast(msg, type) {
  type = type || "info";
  var container = document.getElementById("toasts");
  var toast = document.createElement("div");
  toast.className = "toast " + type;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(function() { toast.classList.add("show"); });
  setTimeout(function() {
    toast.classList.remove("show");
    setTimeout(function() { toast.remove(); }, 300);
  }, 3000);
}

function doAction(action, dlcId, label) {
  api("/admin/" + action + "/" + dlcId, "POST").then(function() {
    showToast(dlcId + " " + label, "success");
    loadData();
  }).catch(function(e) {
    showToast("Failed: " + e.message, "error");
  });
}

function copyManifest(idx) {
  var c = filteredData[idx];
  if (!c) return;
  var entry = {
    dlc_id: c.dlc_id,
    dlc_name: c.dlc_name,
    files: c.files.map(function(f) { return { name: f.name, size: f.size, md5: f.md5 }; }),
    total_size: c.total_size,
    download_url: "https://cdn.hyperabyss.com/dlc/" + c.dlc_id + ".zip"
  };
  navigator.clipboard.writeText(JSON.stringify(entry, null, 2));
  showToast("Manifest entry copied!", "success");
}

function downloadJson(idx) {
  var c = filteredData[idx];
  if (!c) return;
  var blob = new Blob([JSON.stringify(c, null, 2)], { type: "application/json" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url; a.download = c.dlc_id + "_contribution.json"; a.click();
  URL.revokeObjectURL(url);
  showToast("Downloaded " + c.dlc_id + ".json", "info");
}

function toggleFiles(id) {
  var toggle = document.getElementById("toggle-" + id);
  var body = document.getElementById("files-" + id);
  if (toggle) toggle.classList.toggle("open");
  if (body) body.classList.toggle("open");
}

function setFilter(status) {
  activeFilter = status;
  document.querySelectorAll(".stat").forEach(function(s) { s.classList.remove("active"); });
  var el = document.querySelector("[data-filter=" + JSON.stringify(status) + "]");
  if (el) el.classList.add("active");
  renderCards();
}

function getFiltered() {
  var data = allData.slice();
  if (activeFilter !== "all") data = data.filter(function(c) { return c.status === activeFilter; });
  var q = document.getElementById("searchBox").value.toLowerCase().trim();
  if (q) data = data.filter(function(c) { return c.dlc_id.toLowerCase().indexOf(q) >= 0 || (c.dlc_name || "").toLowerCase().indexOf(q) >= 0; });
  var sort = document.getElementById("sortSelect").value;
  data.sort(function(a, b) {
    if (sort === "status") {
      var order = { pending: 0, approved: 1, rejected: 2 };
      if (order[a.status] !== order[b.status]) return order[a.status] - order[b.status];
      return new Date(b.submitted_at) - new Date(a.submitted_at);
    }
    if (sort === "newest") return new Date(b.submitted_at) - new Date(a.submitted_at);
    if (sort === "oldest") return new Date(a.submitted_at) - new Date(b.submitted_at);
    if (sort === "size-desc") return (b.total_size || 0) - (a.total_size || 0);
    if (sort === "dlc-id") return a.dlc_id.localeCompare(b.dlc_id);
    return 0;
  });
  return data;
}

function renderCards() {
  filteredData = getFiltered();
  var data = filteredData;
  var el = document.getElementById("contributions");

  if (data.length === 0) {
    el.innerHTML = '<div class="empty"><div class="empty-icon">&#128230;</div><div class="empty-text">No contributions found</div><div class="empty-sub">' + (activeFilter !== "all" ? "Try a different filter" : "Waiting for user submissions") + "</div></div>";
    return;
  }

  var html = "";
  for (var i = 0; i < data.length; i++) {
    var c = data[i];
    var uid = c.dlc_id + "-" + i;
    html += '<div class="card ' + c.status + '">';
    html += '<div class="card-top"><div class="card-info">';
    html += '<div class="card-title"><span class="dlc-id">' + esc(c.dlc_id) + "</span>" + (c.dlc_name ? '<span class="dlc-name">' + esc(c.dlc_name) + "</span>" : "") + "</div>";
    html += '<div class="card-meta">';
    html += '<span class="meta-item"><svg viewBox="0 0 16 16"><path d="M3.75 1.5a.25.25 0 00-.25.25v11.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V6H9.75A1.75 1.75 0 018 4.25V1.5H3.75zm5.75.56v2.19c0 .138.112.25.25.25h2.19L9.5 2.06zM2 1.75C2 .784 2.784 0 3.75 0h5.086c.464 0 .909.184 1.237.513l3.414 3.414c.329.328.513.773.513 1.237v8.086A1.75 1.75 0 0112.25 15h-8.5A1.75 1.75 0 012 13.25V1.75z"/></svg>' + c.file_count + " files</span>";
    html += '<span class="meta-item"><svg viewBox="0 0 16 16"><path d="M3.5 3.75a.25.25 0 01.25-.25h8.5a.25.25 0 01.25.25v8.5a.25.25 0 01-.25.25h-8.5a.25.25 0 01-.25-.25v-8.5zM3.75 2A1.75 1.75 0 002 3.75v8.5c0 .966.784 1.75 1.75 1.75h8.5A1.75 1.75 0 0014 12.25v-8.5A1.75 1.75 0 0012.25 2h-8.5z"/></svg>' + formatSize(c.total_size) + "</span>";
    html += '<span class="meta-item"><svg viewBox="0 0 16 16"><path d="M1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0zM8 0a8 8 0 100 16A8 8 0 008 0zm.5 4.75a.75.75 0 00-1.5 0v3.5a.75.75 0 00.37.65l2.5 1.5a.75.75 0 00.76-1.3L8.5 7.94V4.75z"/></svg>' + timeAgo(c.submitted_at) + "</span>";
    html += '<span class="meta-item">v' + esc(c.app_version || "?") + "</span>";
    if (c.ip) html += '<span class="meta-item" style="color:#484f58">' + esc(c.ip) + "</span>";
    html += "</div></div>";
    html += '<span class="badge ' + c.status + '">' + c.status + "</span></div>";

    html += '<button class="files-toggle" id="toggle-' + uid + '" data-toggle="' + uid + '">';
    html += '<svg viewBox="0 0 16 16"><path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z"/></svg>';
    html += "View " + c.file_count + " files (" + formatSize(c.total_size) + ")</button>";
    html += '<div class="files-body" id="files-' + uid + '">';
    html += '<table class="files-table"><thead><tr><th>File</th><th style="text-align:right">Size</th><th>MD5</th></tr></thead><tbody>';
    for (var j = 0; j < c.files.length; j++) {
      var f = c.files[j];
      html += '<tr><td class="file-name">' + esc(f.name) + '</td><td class="file-size">' + formatSize(f.size) + '</td><td class="file-hash">' + esc(f.md5) + "</td></tr>";
    }
    html += "</tbody></table></div>";

    html += '<div class="card-actions">';
    if (c.status === "pending") {
      html += '<button class="btn btn-approve" data-approve="' + c.dlc_id + '"><svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>Approve</button>';
      html += '<button class="btn btn-reject" data-reject="' + c.dlc_id + '"><svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z"/></svg>Reject</button>';
    }
    html += '<button class="btn btn-secondary btn-sm" data-copy="' + i + '">Copy Manifest</button>';
    html += '<button class="btn btn-secondary btn-sm" data-download="' + i + '">Download JSON</button>';
    html += '<span class="actions-spacer"></span>';
    if (c.reviewed_at) html += '<span class="reviewed-info">Reviewed ' + timeAgo(c.reviewed_at) + "</span>";
    html += "</div></div>";
  }
  el.innerHTML = html;
}

function loadData() {
  var btn = document.getElementById("refreshBtn");
  btn.classList.add("spinning");

  api("/admin/list").then(function(data) {
    allData = data;
    var pending = 0, approved = 0, rejected = 0;
    for (var i = 0; i < data.length; i++) {
      if (data[i].status === "pending") pending++;
      else if (data[i].status === "approved") approved++;
      else if (data[i].status === "rejected") rejected++;
    }

    var sh = "";
    sh += '<div class="stat' + (activeFilter === "pending" ? " active" : "") + '" data-filter="pending"><div class="stat-num pending-color">' + pending + '</div><div class="stat-label">Pending</div></div>';
    sh += '<div class="stat' + (activeFilter === "approved" ? " active" : "") + '" data-filter="approved"><div class="stat-num approved-color">' + approved + '</div><div class="stat-label">Approved</div></div>';
    sh += '<div class="stat' + (activeFilter === "rejected" ? " active" : "") + '" data-filter="rejected"><div class="stat-num rejected-color">' + rejected + '</div><div class="stat-label">Rejected</div></div>';
    sh += '<div class="stat' + (activeFilter === "all" ? " active" : "") + '" data-filter="all"><div class="stat-num total-color">' + data.length + '</div><div class="stat-label">Total</div></div>';
    document.getElementById("stats").innerHTML = sh;

    renderCards();
    btn.classList.remove("spinning");
    document.getElementById("lastUpdated").textContent = "Updated " + new Date().toLocaleTimeString();
  }).catch(function(e) {
    showToast("Failed to load: " + e.message, "error");
    btn.classList.remove("spinning");
  });
}

// Event delegation — all clicks handled here, no inline handlers
document.addEventListener("click", function(e) {
  var btn = e.target.closest("button, .stat");
  if (!btn) return;

  if (btn.dataset.filter) { setFilter(btn.dataset.filter); return; }
  if (btn.dataset.toggle) { toggleFiles(btn.dataset.toggle); return; }
  if (btn.dataset.approve) { doAction("approve", btn.dataset.approve, "approved"); return; }
  if (btn.dataset.reject) { doAction("reject", btn.dataset.reject, "rejected"); return; }
  if (btn.dataset.copy) { copyManifest(parseInt(btn.dataset.copy)); return; }
  if (btn.dataset.download) { downloadJson(parseInt(btn.dataset.download)); return; }
});

document.getElementById("searchBox").addEventListener("input", renderCards);
document.getElementById("sortSelect").addEventListener("change", renderCards);

var refreshTimer = null;
function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(function() {
    if (document.getElementById("autoRefresh").checked) loadData();
  }, 30000);
}
document.getElementById("autoRefresh").addEventListener("change", function(e) {
  if (e.target.checked) startAutoRefresh();
  else if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
});

loadData();
startAutoRefresh();
</script>
</body>
</html>`;

  return new Response(html, {
    headers: { "Content-Type": "text/html", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Strict-Transport-Security": "max-age=31536000; includeSubDomains", "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'" },
  });
}

// ---------------------------------------------------------------------------
// Ban check for API routes (user-facing)
// ---------------------------------------------------------------------------

async function checkBanApi(request, env) {
  const ip = sanitizeFilterValue(request.headers.get("CF-Connecting-IP") || "");
  const machineId = sanitizeFilterValue(request.headers.get("X-Machine-Id") || "");
  const uid = sanitizeFilterValue(request.headers.get("X-UID") || "");

  const conditions = [];
  if (ip) conditions.push(`and(ban_type.eq.ip,value.eq.${ip})`);
  if (machineId) conditions.push(`and(ban_type.eq.machine,value.eq.${machineId})`);
  if (uid) conditions.push(`and(ban_type.eq.uid,value.eq.${uid})`);

  if (conditions.length === 0) return null;

  try {
    const filter = `or(${conditions.join(",")})`;
    const resp = await fetch(
      `${env.SUPABASE_URL}/rest/v1/active_bans?${filter}&select=ban_type,reason,permanent,expires_at&limit=1`,
      {
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }
    );

    if (!resp.ok) {
      // Fail closed — deny access when ban check is unavailable
      return json({ error: "service_unavailable" }, 503);
    }

    const bans = await resp.json();
    if (bans.length === 0) return null;

    const ban = bans[0];
    return json(
      {
        error: "banned",
        reason: ban.reason || "",
        ban_type: ban.ban_type || "",
        expires_at: ban.expires_at || "",
      },
      403
    );
  } catch {
    // Fail closed
    return json({ error: "service_unavailable" }, 503);
  }
}

// ---------------------------------------------------------------------------
// JWT Token Issuance — POST /auth/token
// ---------------------------------------------------------------------------

async function checkTokenRateLimit(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const key = `rl:token:${ip}`;
  const now = Math.floor(Date.now() / 1000);
  const data = await env.CONTRIBUTIONS.get(key);
  if (data) {
    const parsed = JSON.parse(data);
    if (parsed.count >= 30 && (now - parsed.first) < 3600) return true;
    if ((now - parsed.first) >= 3600) {
      await env.CONTRIBUTIONS.put(key, JSON.stringify({ count: 1, first: now }), { expirationTtl: 3600 });
      return false;
    }
    parsed.count++;
    await env.CONTRIBUTIONS.put(key, JSON.stringify(parsed), { expirationTtl: 3600 });
    return false;
  }
  await env.CONTRIBUTIONS.put(key, JSON.stringify({ count: 1, first: now }), { expirationTtl: 3600 });
  return false;
}

async function handleTokenRequest(request, env) {
  if (!env.JWT_SECRET) {
    return json({ error: "JWT not configured" }, 500);
  }

  // Rate limit: 30 token requests per hour per IP
  if (await checkTokenRateLimit(request, env)) {
    return json({ error: "Rate limited. Try again later." }, 429);
  }

  // Reject oversized request bodies
  const contentLength = parseInt(request.headers.get("Content-Length") || "0");
  if (contentLength > 65536) {
    return json({ error: "Request too large" }, 413);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  const machineId = (body.machine_id || "").substring(0, 64);
  const uid = (body.uid || "").substring(0, 128);
  const appVersion = (body.app_version || "").substring(0, 32);
  const ip = (request.headers.get("CF-Connecting-IP") || "").substring(0, 45);

  if (!machineId || machineId === "unknown") {
    return json({ error: "Missing or invalid machine_id" }, 400);
  }

  // Log the token request FIRST (for admin visibility — even denied requests)
  await logTokenRequest(env, { machine_id: machineId, uid, ip, app_version: appVersion });

  // Ban check — use body data (more reliable than headers for token requests)
  // Fail closed: if Supabase is unreachable, deny token issuance
  if (env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
    const sIp = sanitizeFilterValue(ip);
    const sMid = sanitizeFilterValue(machineId);
    const sUid = sanitizeFilterValue(uid);
    const conditions = [];
    if (sIp) conditions.push(`and(ban_type.eq.ip,value.eq.${sIp})`);
    if (sMid) conditions.push(`and(ban_type.eq.machine,value.eq.${sMid})`);
    if (sUid) conditions.push(`and(ban_type.eq.uid,value.eq.${sUid})`);
    if (conditions.length > 0) {
      try {
        const filter = `or(${conditions.join(",")})`;
        const banResp = await fetch(
          `${env.SUPABASE_URL}/rest/v1/active_bans?${filter}&select=ban_type,reason,permanent,expires_at&limit=1`,
          {
            headers: {
              apikey: env.SUPABASE_SERVICE_KEY,
              Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
            },
          }
        );
        if (!banResp.ok) {
          return json({ error: "service_unavailable" }, 503);
        }
        const bans = await banResp.json();
        if (bans.length > 0) {
          const ban = bans[0];
          return json({ error: "banned", reason: ban.reason || "", ban_type: ban.ban_type || "", expires_at: ban.expires_at || "" }, 403);
        }
      } catch {
        return json({ error: "service_unavailable" }, 503);
      }
    }
  }

  // Check access mode (dynamic from Supabase, fallback to env var)
  const cdnAccess = await getCDNSetting(env, "cdn_access") || env.CDN_ACCESS || "public";
  if (cdnAccess === "private") {
    const allowed = await checkAllowlist(env, machineId);
    if (!allowed) {
      return json(
        {
          error: "access_required",
          cdn_name: env.CDN_NAME || "This CDN",
          request_url: "/access/request",
        },
        403
      );
    }
  }

  // Generate JWT (1-hour expiry)
  const now = Math.floor(Date.now() / 1000);
  const payload = { machine_id: machineId, uid, ip, iat: now, exp: now + 3600 };
  const token = await signJWT(payload, env.JWT_SECRET);

  return json({ token, expires_in: 3600 });
}

async function checkAllowlist(env, machineId) {
  const safeMachineId = sanitizeFilterValue(machineId);
  if (!safeMachineId) return false;
  try {
    const resp = await fetch(
      `${env.SUPABASE_URL}/rest/v1/cdn_allowlist?machine_id=eq.${safeMachineId}&select=machine_id&limit=1`,
      {
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }
    );
    if (!resp.ok) return false; // Fail closed — deny when Supabase is unreachable
    const data = await resp.json();
    return data.length > 0;
  } catch {
    return false; // Fail closed
  }
}

async function getCDNSetting(env, key) {
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_KEY) return null;
  const safeKey = sanitizeFilterValue(key);
  if (!safeKey) return null;
  try {
    const resp = await fetch(
      `${env.SUPABASE_URL}/rest/v1/cdn_settings?key=eq.${safeKey}&select=value&limit=1`,
      {
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }
    );
    if (!resp.ok) return null;
    const data = await resp.json();
    return data.length > 0 ? data[0].value : null;
  } catch {
    return null;
  }
}

async function setCDNSetting(env, key, value) {
  const safeKey = sanitizeFilterValue(key);
  if (!safeKey) return false;
  const resp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/cdn_settings?key=eq.${safeKey}`,
    {
      method: "PATCH",
      headers: {
        apikey: env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({ value, updated_at: new Date().toISOString() }),
    }
  );
  return resp.ok;
}

async function logTokenRequest(env, info) {
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_KEY) return;
  try {
    // Truncate fields to prevent oversized writes
    const safeInfo = {
      machine_id: typeof info.machine_id === "string" ? info.machine_id.substring(0, 64) : "",
      uid: typeof info.uid === "string" ? info.uid.substring(0, 128) : "",
      ip: typeof info.ip === "string" ? info.ip.substring(0, 45) : "",
      app_version: typeof info.app_version === "string" ? info.app_version.substring(0, 32) : "",
    };
    await fetch(`${env.SUPABASE_URL}/rest/v1/token_log`, {
      method: "POST",
      headers: {
        apikey: env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "resolution=merge-duplicates",
      },
      body: JSON.stringify(safeInfo),
    });
  } catch {
    // Non-critical — don't block token issuance
  }
}

async function signJWT(payload, secret) {
  const header = { alg: "HS256", typ: "JWT" };
  const headerB64 = base64urlEncode(JSON.stringify(header));
  const payloadB64 = base64urlEncode(JSON.stringify(payload));

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const sig = await crypto.subtle.sign("HMAC", key, data);
  const sigB64 = base64urlEncodeBuffer(sig);

  return `${headerB64}.${payloadB64}.${sigB64}`;
}

function base64urlEncode(str) {
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlEncodeBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// ---------------------------------------------------------------------------
// Access Request — POST /access/request
// ---------------------------------------------------------------------------

async function handleAccessRequest(request, env) {
  // Rate limit: reuse contribution rate limiter (5 per hour per IP)
  if (await checkRateLimit(request, env)) {
    return json({ error: "Rate limited. Max 5 requests per hour." }, 429);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  const machineId = body.machine_id || "";
  const uid = body.uid || "";
  const appVersion = body.app_version || "";
  const reason = (body.reason || "").substring(0, 500);
  const ip = request.headers.get("CF-Connecting-IP") || "";

  if (!machineId) {
    return json({ error: "Missing machine_id" }, 400);
  }

  // Upsert into access_requests (ON CONFLICT machine_id) — truncate fields
  const payload = {
    machine_id: machineId.substring(0, 64),
    uid: uid.substring(0, 128),
    app_version: appVersion.substring(0, 32),
    reason: reason.substring(0, 500),
    ip: ip.substring(0, 45),
    status: "pending",
  };

  try {
    const resp = await fetch(
      `${env.SUPABASE_URL}/rest/v1/access_requests`,
      {
        method: "POST",
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          "Content-Type": "application/json",
          Prefer: "resolution=merge-duplicates",
        },
        body: JSON.stringify(payload),
      }
    );

    if (!resp.ok) {
      return json({ error: "Failed to submit request" }, 502);
    }
  } catch {
    return json({ error: "Failed to submit request" }, 502);
  }

  // Discord notification (no password in URLs)
  if (env.DISCORD_WEBHOOK) {
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Access Control",
          embeds: [
            {
              title: "New Access Request",
              color: 0x3498db,
              fields: [
                { name: "Machine ID", value: `\`${machineId.slice(0, 8)}...${machineId.slice(-8)}\``, inline: true },
                { name: "UID", value: uid ? `\`${uid.slice(0, 8)}...\`` : "N/A", inline: true },
                { name: "IP", value: ip || "unknown", inline: true },
                { name: "Reason", value: reason || "(none)" },
                { name: "App Version", value: appVersion || "unknown", inline: true },
                { name: "Review", value: "[Access Dashboard](https://api.hyperabyss.com/admin/access)" },
              ],
              timestamp: new Date().toISOString(),
            },
          ],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: "ok", message: "Access request submitted." });
}

// ---------------------------------------------------------------------------
// Admin: Ban Management
// ---------------------------------------------------------------------------

async function getBansData(env) {
  try {
    const [bansResp, summaryResp] = await Promise.all([
      fetch(`${env.SUPABASE_URL}/rest/v1/bans?select=*&order=created_at.desc&limit=200`, {
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }),
      fetch(`${env.SUPABASE_URL}/rest/v1/bans_summary?select=*`, {
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }),
    ]);

    const bans = bansResp.ok ? await bansResp.json() : [];
    const summaryArr = summaryResp.ok ? await summaryResp.json() : [];
    const summary = summaryArr[0] || {};

    return json({ bans, summary });
  } catch (e) {
    return json({ error: "Failed to fetch bans" }, 502);
  }
}

async function createBan(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  const banType = body.ban_type; // "ip", "machine", "uid"
  const value = body.value;
  const reason = body.reason || "";
  const permanent = body.permanent !== false;
  const durationHours = body.duration_hours || 0;

  if (!["ip", "machine", "uid"].includes(banType)) {
    return json({ error: "Invalid ban_type (ip, machine, uid)" }, 400);
  }
  if (!value || typeof value !== "string") {
    return json({ error: "Missing value" }, 400);
  }
  if (value.length > 200) {
    return json({ error: "Value too long (max 200 chars)" }, 400);
  }
  if (reason.length > 500) {
    return json({ error: "Reason too long (max 500 chars)" }, 400);
  }

  const payload = {
    ban_type: banType,
    value,
    reason,
    permanent,
    active: true,
  };

  if (!permanent && durationHours > 0) {
    payload.expires_at = new Date(Date.now() + durationHours * 3600000).toISOString();
  }

  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/bans`, {
    method: "POST",
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    console.error("createBan Supabase error:", resp.status, await resp.text());
    return json({ error: `Failed to create ban (status ${resp.status})` }, 502);
  }

  // Discord notification
  if (env.DISCORD_WEBHOOK) {
    const expiry = permanent ? "Permanent" : `${durationHours}h`;
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Access Control",
          embeds: [
            {
              title: `Ban Created: ${banType}`,
              color: 0xe74c3c,
              fields: [
                { name: "Type", value: banType, inline: true },
                { name: "Value", value: `\`${value}\``, inline: true },
                { name: "Duration", value: expiry, inline: true },
                { name: "Reason", value: reason || "(none)" },
              ],
              timestamp: new Date().toISOString(),
            },
          ],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: "ok", message: `Ban created: ${banType} = ${value}` });
}

async function removeBan(env, id) {
  // Validate id is numeric to prevent query injection
  if (!id || !/^\d+$/.test(id)) {
    return json({ error: "Invalid ban ID" }, 400);
  }
  // Set active = false
  const resp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/bans?id=eq.${id}`,
    {
      method: "PATCH",
      headers: {
        apikey: env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=representation",
      },
      body: JSON.stringify({ active: false }),
    }
  );

  if (!resp.ok) {
    return json({ error: `Supabase error: ${resp.status}` }, 502);
  }

  const rows = await resp.json();
  const ban = rows[0] || {};

  // Discord notification
  if (env.DISCORD_WEBHOOK) {
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Access Control",
          embeds: [
            {
              title: "Ban Removed",
              color: 0x2ecc71,
              description: `${ban.ban_type || "?"}: \`${ban.value || "?"}\` has been unbanned.`,
              timestamp: new Date().toISOString(),
            },
          ],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: "ok", message: `Ban ${id} removed` });
}

// ---------------------------------------------------------------------------
// Admin: Access Management (private CDNs)
// ---------------------------------------------------------------------------

async function getAccessData(env) {
  try {
    const resp = await fetch(
      `${env.SUPABASE_URL}/rest/v1/access_requests?select=*&order=created_at.desc&limit=200`,
      {
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }
    );
    if (!resp.ok) return json({ error: "Failed to fetch" }, 502);
    return json(await resp.json());
  } catch {
    return json({ error: "Failed to fetch" }, 502);
  }
}

async function approveAccess(env, id) {
  if (!id || !/^\d+$/.test(id)) {
    return json({ error: "Invalid request ID" }, 400);
  }
  // Get the request
  const getResp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/access_requests?id=eq.${id}&select=*&limit=1`,
    {
      headers: {
        apikey: env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      },
    }
  );
  if (!getResp.ok) return json({ error: "Not found" }, 404);
  const rows = await getResp.json();
  if (rows.length === 0) return json({ error: "Not found" }, 404);
  const req = rows[0];

  // Update status
  await fetch(`${env.SUPABASE_URL}/rest/v1/access_requests?id=eq.${id}`, {
    method: "PATCH",
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ status: "approved", reviewed_at: new Date().toISOString() }),
  });

  // Add to allowlist
  await fetch(`${env.SUPABASE_URL}/rest/v1/cdn_allowlist`, {
    method: "POST",
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify({
      machine_id: req.machine_id,
      uid: req.uid || "",
      approved_by: "admin",
    }),
  });

  // Discord notification
  if (env.DISCORD_WEBHOOK) {
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Access Control",
          embeds: [
            {
              title: "Access Approved",
              color: 0x2ecc71,
              description: `Machine \`${req.machine_id.slice(0, 8)}...\` has been approved.`,
              timestamp: new Date().toISOString(),
            },
          ],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: "ok", message: "Access approved" });
}

async function denyAccess(env, id) {
  if (!id || !/^\d+$/.test(id)) {
    return json({ error: "Invalid request ID" }, 400);
  }
  await fetch(`${env.SUPABASE_URL}/rest/v1/access_requests?id=eq.${id}`, {
    method: "PATCH",
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ status: "denied", reviewed_at: new Date().toISOString() }),
  });

  // Discord notification
  if (env.DISCORD_WEBHOOK) {
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Access Control",
          embeds: [
            {
              title: "Access Denied",
              color: 0xe74c3c,
              description: `Access request #${id} has been denied.`,
              timestamp: new Date().toISOString(),
            },
          ],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: "ok", message: "Access denied" });
}

async function bulkAccessAction(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }
  const { action, ids } = body;
  if (!action || !ids || !Array.isArray(ids) || ids.length === 0) {
    return json({ error: "Missing action or ids" }, 400);
  }
  if (action !== "approve" && action !== "deny") {
    return json({ error: "Invalid action" }, 400);
  }
  if (ids.length > 50) {
    return json({ error: "Too many IDs (max 50 per request)" }, 400);
  }
  if (!ids.every(id => /^\d+$/.test(String(id)))) {
    return json({ error: "Invalid ID format" }, 400);
  }

  let count = 0;
  for (const id of ids) {
    if (action === "approve") {
      // Get the request data first for allowlist insertion
      const reqResp = await fetch(
        `${env.SUPABASE_URL}/rest/v1/access_requests?id=eq.${id}&select=machine_id,uid`,
        {
          headers: {
            apikey: env.SUPABASE_SERVICE_KEY,
            Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          },
        }
      );
      const reqData = await reqResp.json();
      if (reqData && reqData.length > 0) {
        const { machine_id, uid } = reqData[0];
        // Add to allowlist
        await fetch(`${env.SUPABASE_URL}/rest/v1/cdn_allowlist`, {
          method: "POST",
          headers: {
            apikey: env.SUPABASE_SERVICE_KEY,
            Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
            "Content-Type": "application/json",
            Prefer: "resolution=merge-duplicates",
          },
          body: JSON.stringify({ machine_id, uid, approved_by: "admin" }),
        });
      }
      // Mark approved
      await fetch(`${env.SUPABASE_URL}/rest/v1/access_requests?id=eq.${id}`, {
        method: "PATCH",
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "approved", reviewed_at: new Date().toISOString() }),
      });
    } else {
      // Mark denied
      await fetch(`${env.SUPABASE_URL}/rest/v1/access_requests?id=eq.${id}`, {
        method: "PATCH",
        headers: {
          apikey: env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "denied", reviewed_at: new Date().toISOString() }),
      });
    }
    count++;
  }

  // Discord notification
  if (env.DISCORD_WEBHOOK) {
    try {
      await fetch(env.DISCORD_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: "CDN Access Control",
          embeds: [
            {
              title: `Bulk ${action === "approve" ? "Approved" : "Denied"}`,
              color: action === "approve" ? 0x2ecc71 : 0xe74c3c,
              description: `${count} access request(s) ${action === "approve" ? "approved" : "denied"} in bulk.`,
              timestamp: new Date().toISOString(),
            },
          ],
        }),
      });
    } catch {
      // Best effort
    }
  }

  return json({ status: "ok", action, count });
}

// ---------------------------------------------------------------------------
// Admin: Ban Management Dashboard HTML
// ---------------------------------------------------------------------------

async function serveBansDashboard(env, pw) {
  const nav = adminNav("bans", pw);
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ban Management - CDN Admin</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0d12; color: #e1e4e8; min-height: 100vh; }
  .header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
  .header h1 { font-size: 18px; font-weight: 600; }
  ${nav.css}
  .container { max-width: 1100px; margin: 0 auto; padding: 24px; }
  .metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }
  .metric { background: #161b22; padding: 18px; border-radius: 10px; border: 1px solid #30363d; }
  .metric-value { font-size: 28px; font-weight: 700; }
  .metric-value.red { color: #e74c3c; }
  .metric-value.orange { color: #f0ad4e; }
  .metric-value.green { color: #2ecc71; }
  .metric-value.blue { color: #58a6ff; }
  .metric-value.dim { color: #484f58; }
  .metric-label { font-size: 11px; color: #8b949e; margin-top: 6px; text-transform: uppercase; }

  .form-card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
  .form-title { font-size: 14px; font-weight: 600; margin-bottom: 14px; }
  .form-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
  .form-group { display: flex; flex-direction: column; gap: 4px; }
  .form-group label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
  .form-group select, .form-group input { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px 10px; color: #e1e4e8; font-size: 13px; outline: none; }
  .form-group select:focus, .form-group input:focus { border-color: #58a6ff; }
  .form-group input { min-width: 200px; }
  .form-group.reason input { min-width: 250px; }
  .toggle-row { display: flex; align-items: center; gap: 8px; margin-top: 18px; }
  .toggle-row input { accent-color: #58a6ff; }
  .toggle-row label { font-size: 12px; color: #8b949e; }
  .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; color: #fff; }
  .btn-create { background: #e74c3c; margin-top: 18px; }
  .btn-create:hover { background: #c0392b; }
  .btn-unban { background: #238636; font-size: 11px; padding: 5px 10px; }
  .btn-unban:hover { background: #2ea043; }

  .table-card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; overflow: hidden; }
  .table-header { padding: 14px 18px; border-bottom: 1px solid #30363d; display: flex; align-items: center; justify-content: space-between; }
  .table-header h2 { font-size: 14px; font-weight: 600; }
  .table-scroll { max-height: 500px; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; padding: 8px 16px; color: #484f58; font-weight: 600; font-size: 10px; text-transform: uppercase; border-bottom: 1px solid #21262d; position: sticky; top: 0; background: #161b22; }
  td { padding: 8px 16px; border-bottom: 1px solid #1c2128; }
  tr:hover td { background: rgba(88,166,255,0.03); }
  .badge { padding: 3px 8px; border-radius: 12px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
  .badge.active { background: rgba(231,76,60,0.15); color: #e74c3c; }
  .badge.expired { background: rgba(240,173,78,0.15); color: #f0ad4e; }
  .badge.removed { background: rgba(72,79,88,0.2); color: #484f58; }
  .mono { font-family: monospace; font-size: 11px; color: #8b949e; }
  .copy-btn:hover { opacity: 0.9 !important; color: #58a6ff; }
  .search { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 6px 10px; color: #e1e4e8; font-size: 12px; outline: none; width: 200px; }
  .search:focus { border-color: #58a6ff; }

  .toast-container { position: fixed; bottom: 24px; right: 24px; z-index: 1000; display: flex; flex-direction: column; gap: 8px; }
  .toast { padding: 12px 20px; border-radius: 10px; font-size: 13px; font-weight: 500; color: #fff; transform: translateX(120%); opacity: 0; transition: all 0.3s ease; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
  .toast.show { transform: translateX(0); opacity: 1; }
  .toast.success { background: #238636; }
  .toast.error { background: #da3633; }

  @media (max-width: 900px) {
    .metrics { grid-template-columns: repeat(3, 1fr); }
    .form-row { flex-direction: column; }
    .form-group input { min-width: 0; width: 100%; }
    .form-group.reason input { min-width: 0; width: 100%; }
    .container { padding: 12px; }
    .table-scroll { overflow-x: auto; }
    table { min-width: 600px; }
  }
  @media (max-width: 600px) {
    .metrics { grid-template-columns: repeat(2, 1fr); }
    .header h1 { font-size: 15px; }
    div[style*="grid-template-columns:1fr 1fr"] { display: flex !important; flex-direction: column !important; }
  }
</style>
</head>
<body>
<div class="header"><h1>Ban Management</h1><span style="font-size:11px;color:#484f58" id="lastUpdated"></span></div>
${nav.html}
<div class="container">
  <div class="metrics" id="stats"></div>

  <div class="form-card">
    <div class="form-title">Create Ban</div>
    <div class="form-row">
      <div class="form-group"><label>Type</label><select id="banType"><option value="ip">IP</option><option value="machine">Machine ID</option><option value="uid">UID</option></select></div>
      <div class="form-group"><label>Value</label><input id="banValue" placeholder="IP address, machine ID, or UID"></div>
      <div class="form-group reason"><label>Reason</label><input id="banReason" placeholder="Reason for ban (optional)"></div>
      <div class="form-group"><label>Permanent</label><select id="banPerm"><option value="true">Yes</option><option value="false">No (temp)</option></select></div>
      <div class="form-group" id="durationGroup" style="display:none"><label>Hours</label><input id="banDuration" type="number" value="24" min="1" style="width:80px"></div>
      <button class="btn btn-create" id="createBtn">Create Ban</button>
    </div>
  </div>

  <div style="margin-bottom:24px">
    <div class="form-card" style="margin-bottom:0">
      <div class="form-title">CDN Info</div>
      <div style="font-size:12px;color:#8b949e">
        <div>Name: <span style="color:#e1e4e8">${escapeHtml(env.CDN_NAME || "HyperAbyss CDN")}</span></div>
        <div style="margin-top:4px">Connected Clients: <span style="color:#58a6ff" id="clientCount">...</span></div>
      </div>
    </div>
  </div>

  <div class="table-card" style="margin-bottom:24px">
    <div class="table-header"><h2>Connected Clients</h2><input class="search" id="clientSearch" placeholder="Filter clients..."></div>
    <div class="table-scroll" style="max-height:300px"><table><thead><tr><th>Machine ID</th><th>UID</th><th>IP</th><th>App Version</th><th>Last Seen</th><th>Requests</th><th></th></tr></thead><tbody id="clientRows"></tbody></table></div>
  </div>

  <div class="table-card">
    <div class="table-header"><h2>All Bans</h2><input class="search" id="search" placeholder="Filter bans..."></div>
    <div class="table-scroll"><table><thead><tr><th>Type</th><th>Value</th><th>Reason</th><th>Created</th><th>Expires</th><th>Status</th><th></th></tr></thead><tbody id="banRows"></tbody></table></div>
  </div>
</div>
<div class="toast-container" id="toasts"></div>
<script>
var PW = new URLSearchParams(window.location.search).get("pw");
var BASE = window.location.origin;
var allBans = [];

function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function api(path, method, body) {
  var sep = path.indexOf("?") >= 0 ? "&" : "?";
  var opts = { method: method || "GET" };
  if (body) { opts.headers = {"Content-Type":"application/json"}; opts.body = JSON.stringify(body); }
  return fetch(BASE + path + sep + "pw=" + PW, opts).then(function(r) {
    if (!r.ok) return r.text().then(function(t) { try { return JSON.parse(t); } catch(e) { throw new Error("Server error " + r.status); } });
    return r.json();
  });
}

function toast(msg, type) {
  var c = document.getElementById("toasts");
  var t = document.createElement("div");
  t.className = "toast " + (type||"success");
  t.textContent = msg;
  c.appendChild(t);
  requestAnimationFrame(function() { t.classList.add("show"); });
  setTimeout(function() { t.classList.remove("show"); setTimeout(function() { t.remove(); }, 300); }, 3000);
}

function timeAgo(iso) {
  if (!iso) return "N/A";
  var d = Date.now() - new Date(iso).getTime();
  var m = Math.floor(d/60000);
  if (m < 1) return "just now";
  if (m < 60) return m + "m ago";
  var h = Math.floor(m/60);
  if (h < 24) return h + "h ago";
  return Math.floor(h/24) + "d ago";
}

function getBanStatus(ban) {
  if (!ban.active) return "removed";
  if (!ban.permanent && ban.expires_at && new Date(ban.expires_at) <= new Date()) return "expired";
  return "active";
}

document.getElementById("banPerm").addEventListener("change", function(e) {
  document.getElementById("durationGroup").style.display = e.target.value === "false" ? "" : "none";
});

document.getElementById("createBtn").addEventListener("click", function() {
  var type = document.getElementById("banType").value;
  var value = document.getElementById("banValue").value.trim();
  var reason = document.getElementById("banReason").value.trim();
  var perm = document.getElementById("banPerm").value === "true";
  var hours = parseInt(document.getElementById("banDuration").value) || 24;
  if (!value) { toast("Value required", "error"); return; }
  if (value.length > 200) { toast("Value too long (max 200 chars)", "error"); return; }
  if (reason.length > 500) { toast("Reason too long (max 500 chars)", "error"); return; }
  var body = { ban_type: type, value: value, reason: reason, permanent: perm };
  if (!perm) body.duration_hours = hours;
  api("/admin/bans/create", "POST", body).then(function(r) {
    if (r.status === "ok") { toast("Ban created"); loadBans(); document.getElementById("banValue").value = ""; document.getElementById("banReason").value = ""; }
    else toast(r.error || "Failed", "error");
  }).catch(function(e) { toast("Error: " + e.message, "error"); });
});

document.getElementById("search").addEventListener("input", renderBans);

function renderBans() {
  var q = document.getElementById("search").value.toLowerCase();
  var rows = allBans.filter(function(b) {
    if (!q) return true;
    return b.ban_type.indexOf(q) >= 0 || b.value.toLowerCase().indexOf(q) >= 0 || (b.reason||"").toLowerCase().indexOf(q) >= 0;
  });
  var html = "";
  rows.forEach(function(b) {
    var st = getBanStatus(b);
    html += "<tr>";
    html += "<td>" + esc(b.ban_type) + "</td>";
    html += '<td class="mono">' + esc(b.value) + "</td>";
    html += "<td>" + esc(b.reason || "-") + "</td>";
    html += "<td>" + timeAgo(b.created_at) + "</td>";
    html += "<td>" + (b.permanent ? "Never" : (b.expires_at ? timeAgo(b.expires_at) : "N/A")) + "</td>";
    html += '<td><span class="badge ' + st + '">' + st + "</span></td>";
    html += "<td>" + (st === "active" ? '<button class="btn-unban" data-unban="' + b.id + '">Unban</button>' : "") + "</td>";
    html += "</tr>";
  });
  document.getElementById("banRows").innerHTML = html || '<tr><td colspan="7" style="text-align:center;color:#484f58;padding:20px">No bans</td></tr>';
}

document.addEventListener("click", function(e) {
  var btn = e.target.closest("[data-unban]");
  if (btn) {
    if (!confirm("Are you sure you want to remove this ban?")) return;
    api("/admin/bans/remove/" + btn.dataset.unban, "POST").then(function() { toast("Ban removed"); loadBans(); }).catch(function(e) { toast("Error: " + e.message, "error"); });
  }
});

function loadBans() {
  api("/admin/bans/api").then(function(data) {
    allBans = data.bans || [];
    var s = data.summary || {};
    var h = "";
    h += '<div class="metric"><div class="metric-value red">' + (s.active_count||0) + '</div><div class="metric-label">Active Bans</div></div>';
    h += '<div class="metric"><div class="metric-value red">' + (s.permanent_count||0) + '</div><div class="metric-label">Permanent</div></div>';
    h += '<div class="metric"><div class="metric-value orange">' + (s.temp_count||0) + '</div><div class="metric-label">Temporary</div></div>';
    h += '<div class="metric"><div class="metric-value dim">' + (s.expired_count||0) + '</div><div class="metric-label">Expired</div></div>';
    h += '<div class="metric"><div class="metric-value green">' + (s.unbanned_count||0) + '</div><div class="metric-label">Unbanned</div></div>';
    document.getElementById("stats").innerHTML = h;
    renderBans();
    document.getElementById("lastUpdated").textContent = "Updated " + new Date().toLocaleTimeString();
  });
}

// --- Connected Clients ---
var allClients = [];

function loadClients() {
  api("/admin/clients/api").then(function(data) {
    allClients = data.clients || [];
    var online = allClients.filter(function(c) {
      return c.last_seen && (Date.now() - new Date(c.last_seen).getTime()) < 6 * 60 * 1000;
    }).length;
    document.getElementById("clientCount").textContent = online + " online / " + allClients.length + " recent";
    renderClients();
  });
}

document.getElementById("clientSearch").addEventListener("input", renderClients);

function renderClients() {
  var q = (document.getElementById("clientSearch").value || "").toLowerCase();
  var rows = allClients.filter(function(c) {
    if (!q) return true;
    return (c.machine_id||"").toLowerCase().indexOf(q) >= 0 || (c.uid||"").toLowerCase().indexOf(q) >= 0 || (c.ip||"").indexOf(q) >= 0 || (c.app_version||"").indexOf(q) >= 0;
  });
  var html = "";
  function copyCell(val) {
    return val && val !== "-" ? ' <span class="copy-btn" data-copy-val="' + esc(val) + '" title="Copy" style="cursor:pointer;opacity:0.4;font-size:10px">&#x2398;</span>' : "";
  }
  rows.forEach(function(c) {
    var isOnline = c.last_seen && (Date.now() - new Date(c.last_seen).getTime()) < 6 * 60 * 1000;
    var dot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:' + (isOnline ? "#2ecc71" : "#484f58") + '" title="' + (isOnline ? "Online" : "Offline") + '"></span>';
    html += "<tr>";
    html += '<td class="mono" title="' + esc(c.machine_id) + '">' + dot + esc((c.machine_id||"").substring(0,16)) + "..." + copyCell(c.machine_id) + "</td>";
    html += '<td class="mono">' + esc(c.uid || "-") + copyCell(c.uid) + "</td>";
    html += "<td>" + esc(c.ip || "-") + copyCell(c.ip) + "</td>";
    html += "<td>" + esc(c.app_version || "-") + copyCell(c.app_version) + "</td>";
    html += "<td>" + timeAgo(c.last_seen) + "</td>";
    html += "<td>" + (c.request_count || 0) + "</td>";
    html += '<td><button class="btn btn-create" style="padding:4px 8px;font-size:10px;margin:0" data-ban-ip="' + esc(c.ip||"") + '" data-ban-mid="' + esc(c.machine_id||"") + '">Ban</button></td>';
    html += "</tr>";
  });
  document.getElementById("clientRows").innerHTML = rows.length ? html : '<tr><td colspan="7" style="text-align:center;color:#484f58;padding:20px">No clients</td></tr>';
}

document.addEventListener("click", function(e) {
  var copyBtn = e.target.closest(".copy-btn");
  if (copyBtn && copyBtn.dataset.copyVal) {
    navigator.clipboard.writeText(copyBtn.dataset.copyVal).then(function() {
      toast("Copied!");
    });
    return;
  }
  var btn = e.target.closest("[data-ban-mid]");
  if (btn && !btn.dataset.unban) {
    var mid = btn.dataset.banMid;
    var ip = btn.dataset.banIp;
    if (!mid && !ip) return;
    var which = mid ? "machine" : "ip";
    var val = mid || ip;
    var reason = prompt("Ban " + which + ": " + val + "\\n\\nReason (optional):", "");
    if (reason === null) return;
    var permChoice = confirm("Make this ban permanent?\\n\\nOK = Permanent\\nCancel = Temporary (24h)");
    var body = { ban_type: which, value: val, reason: reason || "Banned from client list", permanent: permChoice };
    if (!permChoice) body.duration_hours = 24;
    api("/admin/bans/create", "POST", body).then(function(r) {
      if (r.status === "ok") { toast("Banned " + val + (permChoice ? " (permanent)" : " (24h)")); loadBans(); }
      else toast(r.error || "Failed", "error");
    });
  }
});

loadBans();
loadClients();
setInterval(loadBans, 30000);
setInterval(loadClients, 30000);
</script>
</body>
</html>`;
  return new Response(html, { headers: { "Content-Type": "text/html", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Strict-Transport-Security": "max-age=31536000; includeSubDomains", "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'" } });
}

// ---------------------------------------------------------------------------
// Admin: Access Dashboard HTML (for private CDNs)
// ---------------------------------------------------------------------------

async function serveAccessDashboard(env, pw) {
  const nav = adminNav("access", pw);
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Access Requests - CDN Admin</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0d12; color: #e1e4e8; min-height: 100vh; }
  .header { background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
  .header h1 { font-size: 18px; font-weight: 600; }
  ${nav.css}
  .container { max-width: 1100px; margin: 0 auto; padding: 24px; }
  .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }
  .metric { background: #161b22; padding: 18px; border-radius: 10px; border: 1px solid #30363d; }
  .metric-value { font-size: 28px; font-weight: 700; }
  .metric-value.orange { color: #f0ad4e; }
  .metric-value.green { color: #2ecc71; }
  .metric-value.red { color: #e74c3c; }
  .metric-label { font-size: 11px; color: #8b949e; margin-top: 6px; text-transform: uppercase; }

  .table-card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; overflow: hidden; }
  .table-scroll { max-height: 600px; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; padding: 8px 16px; color: #484f58; font-weight: 600; font-size: 10px; text-transform: uppercase; border-bottom: 1px solid #21262d; position: sticky; top: 0; background: #161b22; }
  td { padding: 8px 16px; border-bottom: 1px solid #1c2128; }
  tr:hover td { background: rgba(88,166,255,0.03); }
  .mono { font-family: monospace; font-size: 11px; color: #8b949e; }
  .badge { padding: 3px 8px; border-radius: 12px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
  .badge.pending { background: rgba(240,173,78,0.15); color: #f0ad4e; }
  .badge.approved { background: rgba(46,204,113,0.15); color: #2ecc71; }
  .badge.denied { background: rgba(231,76,60,0.15); color: #e74c3c; }
  .btn { padding: 5px 10px; border: none; border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: 600; color: #fff; }
  .btn-approve { background: #238636; }
  .btn-approve:hover { background: #2ea043; }
  .btn-deny { background: #da3633; }
  .btn-deny:hover { background: #c0392b; }
  .btn-bulk { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; color: #fff; }
  .btn-bulk:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-bulk.approve { background: #238636; }
  .btn-bulk.approve:hover:not(:disabled) { background: #2ea043; }
  .btn-bulk.deny { background: #da3633; }
  .btn-bulk.deny:hover:not(:disabled) { background: #c0392b; }
  .bulk-bar { display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-bottom: 1px solid #30363d; background: #0d1117; }
  .bulk-bar .selected-count { font-size: 12px; color: #8b949e; min-width: 100px; }
  .check-col { width: 32px; text-align: center; }
  .check-col input { accent-color: #58a6ff; cursor: pointer; }
  .filter-bar { display: flex; gap: 8px; align-items: center; padding: 12px 18px; border-bottom: 1px solid #30363d; }
  .filter-btn { background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 5px 12px; color: #8b949e; cursor: pointer; font-size: 11px; font-weight: 600; }
  .filter-btn.active { background: #58a6ff22; border-color: #58a6ff; color: #58a6ff; }
  .search-input { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 5px 10px; color: #e1e4e8; font-size: 12px; outline: none; width: 200px; margin-left: auto; }
  .search-input:focus { border-color: #58a6ff; }
  .toast-container { position: fixed; bottom: 24px; right: 24px; z-index: 1000; display: flex; flex-direction: column; gap: 8px; }
  .toast { padding: 12px 20px; border-radius: 10px; font-size: 13px; font-weight: 500; color: #fff; transform: translateX(120%); opacity: 0; transition: all 0.3s ease; box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
  .toast.show { transform: translateX(0); opacity: 1; }
  .toast.success { background: #238636; }
  .toast.error { background: #da3633; }
</style>
</head>
<body>
<div class="header"><h1>Access Requests</h1><span style="font-size:11px;color:#484f58" id="lastUpdated"></span></div>
${nav.html}
<div class="container">
  <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px;margin-bottom:16px;display:flex;align-items:center;gap:16px;flex-wrap:wrap">
    <div style="font-size:13px;font-weight:600">CDN Access Mode</div>
    <select id="accessMode" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 12px;color:#e1e4e8;font-size:13px;outline:none">
      <option value="public">Public (anyone can download)</option>
      <option value="private">Private (allowlist only)</option>
    </select>
    <button class="btn btn-approve" style="padding:6px 14px;font-size:12px" onclick="saveAccessMode()">Save</button>
    <span id="accessStatus" style="font-size:11px;color:#8b949e"></span>
  </div>
  <div class="metrics" id="stats"></div>
  <div class="table-card">
    <div class="filter-bar">
      <button class="filter-btn active" data-filter="all">All</button>
      <button class="filter-btn" data-filter="pending">Pending</button>
      <button class="filter-btn" data-filter="approved">Approved</button>
      <button class="filter-btn" data-filter="denied">Denied</button>
      <input class="search-input" id="accessSearch" placeholder="Search requests...">
    </div>
    <div class="bulk-bar" id="bulkBar">
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="selectAll"><span style="font-size:11px;color:#8b949e">Select all</span></label>
      <span class="selected-count" id="selectedCount">0 selected</span>
      <button class="btn-bulk approve" id="bulkApprove" disabled>Approve Selected</button>
      <button class="btn-bulk deny" id="bulkDeny" disabled>Deny Selected</button>
    </div>
    <div class="table-scroll"><table><thead><tr><th class="check-col"></th><th>Machine ID</th><th>UID</th><th>IP</th><th>App Version</th><th>Reason</th><th>Status</th><th>Submitted</th><th></th></tr></thead><tbody id="rows"></tbody></table></div>
  </div>
</div>
<div class="toast-container" id="toasts"></div>
<script>
var PW = new URLSearchParams(window.location.search).get("pw");
var BASE = window.location.origin;
var allRequests = [];
var activeFilter = "all";
var selectedIds = new Set();

function esc(s) {
  if (!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function api(path, method, body) {
  var sep = path.indexOf("?") >= 0 ? "&" : "?";
  var opts = { method: method || "GET" };
  if (body) { opts.headers = {"Content-Type":"application/json"}; opts.body = JSON.stringify(body); }
  return fetch(BASE + path + sep + "pw=" + PW, opts).then(function(r) {
    if (!r.ok) return r.text().then(function(t) { try { return JSON.parse(t); } catch(e) { throw new Error("Server error " + r.status); } });
    return r.json();
  });
}

function toast(msg, type) {
  var c = document.getElementById("toasts");
  var t = document.createElement("div");
  t.className = "toast " + (type||"success");
  t.textContent = msg;
  c.appendChild(t);
  requestAnimationFrame(function() { t.classList.add("show"); });
  setTimeout(function() { t.classList.remove("show"); setTimeout(function() { t.remove(); }, 300); }, 3000);
}

function timeAgo(iso) {
  if (!iso) return "";
  var d = Date.now() - new Date(iso).getTime();
  var m = Math.floor(d/60000);
  if (m < 1) return "just now";
  if (m < 60) return m + "m ago";
  var h = Math.floor(m/60);
  if (h < 24) return h + "h ago";
  return Math.floor(h/24) + "d ago";
}

function getFiltered() {
  var q = (document.getElementById("accessSearch").value || "").toLowerCase();
  return allRequests.filter(function(r) {
    if (activeFilter !== "all" && r.status !== activeFilter) return false;
    if (!q) return true;
    return (r.machine_id||"").toLowerCase().indexOf(q) >= 0 || (r.uid||"").toLowerCase().indexOf(q) >= 0 || (r.ip||"").indexOf(q) >= 0 || (r.reason||"").toLowerCase().indexOf(q) >= 0;
  });
}

function updateBulkUI() {
  var count = selectedIds.size;
  document.getElementById("selectedCount").textContent = count + " selected";
  document.getElementById("bulkApprove").disabled = count === 0;
  document.getElementById("bulkDeny").disabled = count === 0;
  var visible = getFiltered().filter(function(r) { return r.status === "pending"; });
  var allChecked = visible.length > 0 && visible.every(function(r) { return selectedIds.has(r.id); });
  document.getElementById("selectAll").checked = allChecked;
}

function renderRequests() {
  var filtered = getFiltered();
  var pending = 0, approved = 0, denied = 0;
  allRequests.forEach(function(r) {
    if (r.status === "pending") pending++;
    else if (r.status === "approved") approved++;
    else denied++;
  });
  var h = '<div class="metric"><div class="metric-value orange">' + pending + '</div><div class="metric-label">Pending</div></div>';
  h += '<div class="metric"><div class="metric-value green">' + approved + '</div><div class="metric-label">Approved</div></div>';
  h += '<div class="metric"><div class="metric-value red">' + denied + '</div><div class="metric-label">Denied</div></div>';
  document.getElementById("stats").innerHTML = h;

  var rows = "";
  filtered.forEach(function(r) {
    var isPending = r.status === "pending";
    rows += "<tr>";
    rows += '<td class="check-col">' + (isPending ? '<input type="checkbox" class="row-check" data-id="' + r.id + '"' + (selectedIds.has(r.id) ? " checked" : "") + ">" : "") + "</td>";
    rows += '<td class="mono" title="' + esc(r.machine_id||"") + '">' + esc((r.machine_id||"").substring(0,12)) + "...</td>";
    rows += '<td class="mono">' + esc((r.uid||"").substring(0,8)) + "...</td>";
    rows += "<td>" + esc(r.ip||"") + "</td>";
    rows += "<td>" + esc(r.app_version||"") + "</td>";
    rows += "<td>" + esc(r.reason||"-") + "</td>";
    rows += '<td><span class="badge ' + esc(r.status) + '">' + esc(r.status) + "</span></td>";
    rows += "<td>" + timeAgo(r.created_at) + "</td>";
    rows += "<td>" + (isPending ? '<button class="btn btn-approve" data-approve="' + r.id + '">Approve</button> <button class="btn btn-deny" data-deny="' + r.id + '">Deny</button>' : "") + "</td>";
    rows += "</tr>";
  });
  document.getElementById("rows").innerHTML = rows || '<tr><td colspan="9" style="text-align:center;color:#484f58;padding:20px">No requests</td></tr>';
  document.getElementById("lastUpdated").textContent = "Updated " + new Date().toLocaleTimeString();
  updateBulkUI();
}

function load() {
  api("/admin/access/api").then(function(data) {
    allRequests = data || [];
    renderRequests();
  });
}

// --- Filter buttons ---
document.querySelectorAll("[data-filter]").forEach(function(btn) {
  btn.addEventListener("click", function() {
    document.querySelectorAll("[data-filter]").forEach(function(b) { b.classList.remove("active"); });
    btn.classList.add("active");
    activeFilter = btn.dataset.filter;
    selectedIds.clear();
    renderRequests();
  });
});

document.getElementById("accessSearch").addEventListener("input", renderRequests);

// --- Select all ---
document.getElementById("selectAll").addEventListener("change", function(e) {
  var checked = e.target.checked;
  var visible = getFiltered().filter(function(r) { return r.status === "pending"; });
  visible.forEach(function(r) {
    if (checked) selectedIds.add(r.id);
    else selectedIds.delete(r.id);
  });
  renderRequests();
});

// --- Row checkboxes ---
document.addEventListener("change", function(e) {
  if (e.target.classList.contains("row-check")) {
    var id = parseInt(e.target.dataset.id);
    if (e.target.checked) selectedIds.add(id);
    else selectedIds.delete(id);
    updateBulkUI();
  }
});

// --- Single approve/deny ---
document.addEventListener("click", function(e) {
  var btn = e.target.closest("[data-approve]");
  if (btn) { api("/admin/access/approve/" + btn.dataset.approve, "POST").then(function() { toast("Approved"); load(); }); return; }
  btn = e.target.closest("[data-deny]");
  if (btn) { api("/admin/access/deny/" + btn.dataset.deny, "POST").then(function() { toast("Denied"); load(); }); }
});

// --- Bulk approve ---
document.getElementById("bulkApprove").addEventListener("click", function() {
  var ids = Array.from(selectedIds);
  if (ids.length === 0) return;
  if (!confirm("Approve " + ids.length + " request(s)?")) return;
  document.getElementById("bulkApprove").disabled = true;
  api("/admin/access/bulk", "POST", { action: "approve", ids: ids }).then(function(r) {
    toast("Approved " + (r.count || ids.length) + " request(s)");
    selectedIds.clear();
    load();
  }).catch(function() { toast("Bulk approve failed", "error"); });
});

// --- Bulk deny ---
document.getElementById("bulkDeny").addEventListener("click", function() {
  var ids = Array.from(selectedIds);
  if (ids.length === 0) return;
  if (!confirm("Deny " + ids.length + " request(s)?")) return;
  document.getElementById("bulkDeny").disabled = true;
  api("/admin/access/bulk", "POST", { action: "deny", ids: ids }).then(function(r) {
    toast("Denied " + (r.count || ids.length) + " request(s)");
    selectedIds.clear();
    load();
  }).catch(function() { toast("Bulk deny failed", "error"); });
});

// --- CDN Access Mode ---
function loadSettings() {
  api("/admin/settings/api").then(function(data) {
    var settings = data.settings || [];
    settings.forEach(function(s) {
      if (s.key === "cdn_access") {
        document.getElementById("accessMode").value = s.value;
      }
    });
  });
}
function saveAccessMode() {
  var val = document.getElementById("accessMode").value;
  var status = document.getElementById("accessStatus");
  status.textContent = "Saving...";
  api("/admin/settings/update", "POST", { key: "cdn_access", value: val }).then(function(r) {
    if (r.status === "ok") { toast("Access mode set to " + val); status.textContent = "Saved"; setTimeout(function() { status.textContent = ""; }, 2000); }
    else { toast(r.error || "Failed", "error"); status.textContent = ""; }
  }).catch(function() { toast("Error saving", "error"); status.textContent = ""; });
}

load();
loadSettings();
setInterval(load, 30000);
</script>
</body>
</html>`;
  return new Response(html, { headers: { "Content-Type": "text/html", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Strict-Transport-Security": "max-age=31536000; includeSubDomains", "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'" } });
}

// ---------------------------------------------------------------------------
// Admin: CDN Settings API
// ---------------------------------------------------------------------------

async function getCDNSettingsData(env) {
  const resp = await supabaseGet(env, "/rest/v1/cdn_settings?select=*");
  const settings = await resp.json();
  return json({ settings: settings || [] });
}

async function updateCDNSetting(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }
  const { key, value } = body;
  if (!key || !value || typeof value !== "string") return json({ error: "Missing key or value" }, 400);
  const allowedSettings = { cdn_access: ["public", "private"] };
  if (!allowedSettings[key]) return json({ error: "Invalid setting key" }, 400);
  if (!allowedSettings[key].includes(value)) {
    return json({ error: `Invalid value for ${key}. Allowed: ${allowedSettings[key].join(", ")}` }, 400);
  }
  const ok = await setCDNSetting(env, key, value);
  if (!ok) return json({ error: "Failed to update setting" }, 500);
  return json({ status: "ok", key, value });
}

// ---------------------------------------------------------------------------
// Admin: Connected Clients API (token_log)
// ---------------------------------------------------------------------------

async function getClientsData(env) {
  // Only return clients seen in the last 24 hours
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const resp = await supabaseGet(
    env,
    `/rest/v1/token_log?select=*&order=last_seen.desc&limit=200&last_seen=gte.${since}`
  );
  const clients = await resp.json();
  return json({ clients: clients || [] });
}
