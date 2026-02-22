/**
 * Sims 4 Updater Contribution API — api.hyperabyss.com
 *
 * Endpoints:
 *   POST /contribute          — Submit DLC metadata (from user apps)
 *   GET  /admin               — Dashboard to review contributions (password protected)
 *   GET|POST /admin/approve/:id — Approve a contribution
 *   GET|POST /admin/reject/:id  — Reject a contribution
 *   GET  /admin/list           — JSON list of all contributions
 *   GET  /health              — Health check
 *
 * Environment:
 *   CONTRIBUTIONS   — KV namespace for storing contributions
 *   ADMIN_PASSWORD  — Password for admin dashboard
 *   DISCORD_WEBHOOK — Discord webhook URL for notifications
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS headers for app requests
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
      });
    }

    // Health check
    if (path === "/health") {
      return json({ status: "ok" });
    }

    // Contribution submission (from user apps)
    if (path === "/contribute" && request.method === "POST") {
      return handleContribution(request, env);
    }

    // GreenLuma key + manifest contribution
    if (path === "/contribute/greenluma" && request.method === "POST") {
      return handleGLContribution(request, env);
    }

    // Admin routes
    if (path.startsWith("/admin")) {
      // Check admin auth
      const authErr = checkAdminAuth(request, env);
      if (authErr) return authErr;

      if (path === "/admin" && request.method === "GET") {
        return serveDashboard(env);
      }
      if (path === "/admin/list" && request.method === "GET") {
        return listContributions(env);
      }
      if (path === "/admin/gl/list" && request.method === "GET") {
        return listGLContributions(env);
      }
      if (path.startsWith("/admin/approve/") && (request.method === "POST" || request.method === "GET")) {
        const id = path.replace("/admin/approve/", "");
        return updateStatus(env, id, "approved");
      }
      if (path.startsWith("/admin/reject/") && (request.method === "POST" || request.method === "GET")) {
        const id = path.replace("/admin/reject/", "");
        return updateStatus(env, id, "rejected");
      }
      if (path.startsWith("/admin/gl/approve/") && (request.method === "POST" || request.method === "GET")) {
        const depotId = path.replace("/admin/gl/approve/", "");
        return updateGLStatus(env, depotId, "approved");
      }
      if (path.startsWith("/admin/gl/reject/") && (request.method === "POST" || request.method === "GET")) {
        const depotId = path.replace("/admin/gl/reject/", "");
        return updateGLStatus(env, depotId, "rejected");
      }
    }

    return new Response("Not Found", { status: 404 });
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

function checkAdminAuth(request, env) {
  const url = new URL(request.url);
  const pw = url.searchParams.get("pw") ||
    request.headers.get("X-Admin-Password");

  if (!pw || pw !== env.ADMIN_PASSWORD) {
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
    const pw = encodeURIComponent(env.ADMIN_PASSWORD);
    const fields = validEntries
      .filter((e) => stored.includes(e.depot_id))
      .map((e) => ({
        name: `${e.dlc_id || e.depot_id}`,
        value: `Depot: ${e.depot_id}\nKey: \`${e.key.slice(0, 8)}...${e.key.slice(-8)}\`\nManifest: ${e.manifest_id} (${e.manifest_size} bytes)`,
        inline: true,
      }));

    // Add approve/reject links for each entry
    const actionLines = stored.map((d) =>
      `[Approve ${d}](https://api.hyperabyss.com/admin/gl/approve/${d}?pw=${pw}) | [Reject](https://api.hyperabyss.com/admin/gl/reject/${d}?pw=${pw})`
    );

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
  const pw = encodeURIComponent(env.ADMIN_PASSWORD);
  const approveUrl = `https://api.hyperabyss.com/admin/approve/${contribution.dlc_id}?pw=${pw}`;
  const rejectUrl = `https://api.hyperabyss.com/admin/reject/${contribution.dlc_id}?pw=${pw}`;

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
// Admin: Dashboard HTML
// ---------------------------------------------------------------------------

async function serveDashboard(env) {
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

function api(path, method) {
  method = method || "GET";
  var sep = path.indexOf("?") >= 0 ? "&" : "?";
  return fetch(BASE + path + sep + "pw=" + PW, { method: method }).then(function(r) { return r.json(); });
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
    html += '<div class="card-title"><span class="dlc-id">' + c.dlc_id + "</span>" + (c.dlc_name ? '<span class="dlc-name">' + c.dlc_name + "</span>" : "") + "</div>";
    html += '<div class="card-meta">';
    html += '<span class="meta-item"><svg viewBox="0 0 16 16"><path d="M3.75 1.5a.25.25 0 00-.25.25v11.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V6H9.75A1.75 1.75 0 018 4.25V1.5H3.75zm5.75.56v2.19c0 .138.112.25.25.25h2.19L9.5 2.06zM2 1.75C2 .784 2.784 0 3.75 0h5.086c.464 0 .909.184 1.237.513l3.414 3.414c.329.328.513.773.513 1.237v8.086A1.75 1.75 0 0112.25 15h-8.5A1.75 1.75 0 012 13.25V1.75z"/></svg>' + c.file_count + " files</span>";
    html += '<span class="meta-item"><svg viewBox="0 0 16 16"><path d="M3.5 3.75a.25.25 0 01.25-.25h8.5a.25.25 0 01.25.25v8.5a.25.25 0 01-.25.25h-8.5a.25.25 0 01-.25-.25v-8.5zM3.75 2A1.75 1.75 0 002 3.75v8.5c0 .966.784 1.75 1.75 1.75h8.5A1.75 1.75 0 0014 12.25v-8.5A1.75 1.75 0 0012.25 2h-8.5z"/></svg>' + formatSize(c.total_size) + "</span>";
    html += '<span class="meta-item"><svg viewBox="0 0 16 16"><path d="M1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0zM8 0a8 8 0 100 16A8 8 0 008 0zm.5 4.75a.75.75 0 00-1.5 0v3.5a.75.75 0 00.37.65l2.5 1.5a.75.75 0 00.76-1.3L8.5 7.94V4.75z"/></svg>' + timeAgo(c.submitted_at) + "</span>";
    html += '<span class="meta-item">v' + (c.app_version || "?") + "</span>";
    if (c.ip) html += '<span class="meta-item" style="color:#484f58">' + c.ip + "</span>";
    html += "</div></div>";
    html += '<span class="badge ' + c.status + '">' + c.status + "</span></div>";

    html += '<button class="files-toggle" id="toggle-' + uid + '" data-toggle="' + uid + '">';
    html += '<svg viewBox="0 0 16 16"><path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z"/></svg>';
    html += "View " + c.file_count + " files (" + formatSize(c.total_size) + ")</button>";
    html += '<div class="files-body" id="files-' + uid + '">';
    html += '<table class="files-table"><thead><tr><th>File</th><th style="text-align:right">Size</th><th>MD5</th></tr></thead><tbody>';
    for (var j = 0; j < c.files.length; j++) {
      var f = c.files[j];
      html += '<tr><td class="file-name">' + f.name + '</td><td class="file-size">' + formatSize(f.size) + '</td><td class="file-hash">' + f.md5 + "</td></tr>";
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
    headers: { "Content-Type": "text/html" },
  });
}
