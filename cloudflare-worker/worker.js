/**
 * Sims 4 Updater CDN Worker — cdn.hyperabyss.com
 *
 * Proxies clean URLs to Whatbox seedbox via HTTPS with basic auth.
 * Enforces JWT session tokens + ban checks on download paths.
 *
 * Users see: https://cdn.hyperabyss.com/patches/1.121.372_to_1.122.100.zip
 * Worker authenticates with Whatbox and streams the file back.
 *
 * REQUEST FLOW:
 *   1. CORS preflight → allow
 *   2. Method check → only GET/HEAD/OPTIONS
 *   3. Public paths (manifest.json, root) → no auth required
 *   4. Ban check (IP + machine_id) → 403 if banned
 *   5. JWT validation + machine_id binding → 401 if missing/invalid/expired
 *   6. KV lookup → seedbox proxy (with path validation)
 *
 * SETUP:
 *   1. Create a KV namespace called "CDN_ROUTES" in Cloudflare dashboard
 *   2. Deploy this worker and bind CDN_ROUTES to it
 *   3. Add route: cdn.hyperabyss.com/* → this worker
 *   4. Add environment secrets (Worker Settings → Variables and Secrets):
 *      SEEDBOX_BASE_URL, SEEDBOX_USER, SEEDBOX_PASS,
 *      SUPABASE_URL, SUPABASE_SERVICE_KEY, JWT_SECRET
 *
 * KV ENTRIES (key = clean path, value = path on seedbox):
 *   "manifest.json"                        → "files/sims4/manifest.json"
 *   "patches/1.121.372_to_1.122.100.zip"  → "files/sims4/patches/..."
 *   "dlc/EP01.zip"                         → "files/sims4/dlc/EP01.zip"
 *   "language/de_DE.zip"                   → "files/sims4/language/de_DE.zip"
 */

// Paths that don't require JWT authentication
const PUBLIC_PATHS = new Set(["manifest.json"]);

// Expected seedbox path prefix (prevents KV route traversal)
const SEEDBOX_PATH_PREFIX = "files/";

export default {
  async fetch(request, env) {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(),
      });
    }

    // Only allow GET and HEAD
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD, OPTIONS", ...corsHeaders() },
      });
    }

    const url = new URL(request.url);
    const path = url.pathname.slice(1); // strip leading slash

    // Handle root / empty path
    if (!path) {
      return new Response("Sims 4 Updater CDN", {
        status: 200,
        headers: { "Content-Type": "text/plain", ...corsHeaders() },
      });
    }

    const isPublic = PUBLIC_PATHS.has(path);

    // ── Ban check (runs on ALL paths, including public) ──
    if (env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
      const banResult = await checkBan(request, env);
      if (banResult) return banResult;
    }

    // ── JWT validation (protected paths only) ──
    if (!isPublic) {
      // Fail closed: refuse to serve without auth capability
      if (!env.JWT_SECRET) {
        return jsonResponse({ error: "service_unavailable" }, 503);
      }

      // Require X-Machine-Id header on protected paths
      const machineId = request.headers.get("X-Machine-Id");
      if (!machineId) {
        return jsonResponse({ error: "machine_id_required" }, 400);
      }

      const authResult = await validateToken(request, env);
      if (authResult) return authResult;
    }

    // ── KV lookup → seedbox proxy ──
    const seedboxPath = await env.CDN_ROUTES.get(path);

    if (!seedboxPath) {
      return jsonResponse({ error: "not_found" }, 404);
    }

    // Validate seedbox path: prevent traversal attacks via KV manipulation
    const normalizedPath = seedboxPath.replace(/\\/g, "/");
    if (normalizedPath.includes("..") || !normalizedPath.startsWith(SEEDBOX_PATH_PREFIX)) {
      return jsonResponse({ error: "invalid_route" }, 403);
    }

    // Build the full seedbox URL
    const baseUrl = env.SEEDBOX_BASE_URL.replace(/\/+$/, "");
    const seedboxUrl = `${baseUrl}/${seedboxPath}`;

    // Create basic auth header from secrets
    const credentials = btoa(`${env.SEEDBOX_USER}:${env.SEEDBOX_PASS}`);

    // Forward Range header for resume support
    const fetchHeaders = {
      "User-Agent": "HyperabyssCDN/1.0",
      Authorization: `Basic ${credentials}`,
    };
    const rangeHeader = request.headers.get("Range");
    if (rangeHeader) {
      fetchHeaders["Range"] = rangeHeader;
    }

    // Fetch from seedbox with authentication (no redirect following)
    const seedboxResponse = await fetch(seedboxUrl, {
      headers: fetchHeaders,
      redirect: "error",
    });

    if (!seedboxResponse.ok && seedboxResponse.status !== 206) {
      return new Response("Upstream error", { status: 502 });
    }

    // Stream the response back to the user with clean headers (allowlist)
    const headers = new Headers();
    headers.set(
      "Content-Type",
      seedboxResponse.headers.get("Content-Type") || "application/octet-stream"
    );
    const contentLength = seedboxResponse.headers.get("Content-Length");
    if (contentLength) headers.set("Content-Length", contentLength);
    headers.set("Accept-Ranges", "bytes");

    // Public paths can be cached; authenticated responses must not
    if (isPublic) {
      headers.set("Cache-Control", "public, max-age=86400");
    } else {
      headers.set("Cache-Control", "private, no-store");
    }

    // CORS
    for (const [k, v] of Object.entries(corsHeaders())) {
      headers.set(k, v);
    }

    // Content-Range for resumed downloads
    const contentRange = seedboxResponse.headers.get("Content-Range");
    if (contentRange) headers.set("Content-Range", contentRange);

    // Content-Disposition: sanitize filename to prevent header injection
    const disposition = seedboxResponse.headers.get("Content-Disposition");
    if (disposition && !disposition.includes("\r") && !disposition.includes("\n")) {
      headers.set("Content-Disposition", disposition);
    } else {
      const rawFilename = path.split("/").pop() || "download";
      const filename = rawFilename.replace(/["\\\r\n;]/g, "_");
      headers.set("Content-Disposition", `attachment; filename="${filename}"`);
    }

    return new Response(seedboxResponse.body, {
      status: seedboxResponse.status,
      headers,
    });
  },
};

// ── JWT Validation ────────────────────────────────────────────

async function validateToken(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) {
    return jsonResponse({ error: "token_required" }, 401);
  }

  const token = auth.slice(7);
  const payload = await verifyJWT(token, env.JWT_SECRET);

  if (!payload) {
    return jsonResponse({ error: "invalid_token" }, 401);
  }

  if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
    return jsonResponse({ error: "token_expired" }, 401);
  }

  // Bind token to requesting client's machine_id
  const requestMachineId = request.headers.get("X-Machine-Id") || "";
  if (payload.machine_id && requestMachineId && payload.machine_id !== requestMachineId) {
    return jsonResponse({ error: "token_mismatch" }, 401);
  }

  return null; // Valid — proceed
}

async function verifyJWT(token, secret) {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    const [headerB64, payloadB64, sigB64] = parts;

    // Validate JWT algorithm claim
    try {
      const headerJson = atob(headerB64.replace(/-/g, "+").replace(/_/g, "/"));
      const header = JSON.parse(headerJson);
      if (header.alg !== "HS256") return null;
    } catch {
      return null;
    }

    // Import HMAC key
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    );

    // Verify signature
    const sig = base64urlDecode(sigB64);
    const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
    const valid = await crypto.subtle.verify("HMAC", key, sig, data);
    if (!valid) return null;

    // Decode payload
    const json = atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function base64urlDecode(str) {
  // Pad and convert base64url to standard base64
  str = str.replace(/-/g, "+").replace(/_/g, "/");
  while (str.length % 4) str += "=";
  const binary = atob(str);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

// ── Ban Check ─────────────────────────────────────────────────

function sanitizeFilterValue(val) {
  if (!val || typeof val !== "string") return "";
  return val.replace(/[^a-zA-Z0-9._:\-]/g, "").substring(0, 200);
}

async function checkBan(request, env) {
  const ip = sanitizeFilterValue(request.headers.get("CF-Connecting-IP") || "");
  const machineId = sanitizeFilterValue(request.headers.get("X-Machine-Id") || "");
  const uid = sanitizeFilterValue(request.headers.get("X-UID") || "");

  // Build OR conditions for matching bans
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
      // Fail open — don't block users if Supabase is down
      return null;
    }

    const bans = await resp.json();
    if (bans.length === 0) return null;

    const ban = bans[0];
    return jsonResponse(
      {
        error: "banned",
        reason: ban.reason || "",
        ban_type: ban.ban_type || "",
        expires_at: ban.expires_at || "",
      },
      403
    );
  } catch {
    // Fail open
    return null;
  }
}

// ── Helpers ───────────────────────────────────────────────────

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(),
    },
  });
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers":
      "Content-Type, Authorization, X-Machine-Id, X-UID",
  };
}
