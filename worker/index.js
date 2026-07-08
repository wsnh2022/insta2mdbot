// Simple in-memory rate limiter — 10 requests per minute globally
const rateLimiter = new Map();

// Per-IP failed auth tracking — blocks after 5 wrong passphrases for 45 minutes
const failedAttempts = new Map();

function isRateLimited() {
  const minute = Math.floor(Date.now() / 60000);
  const count = (rateLimiter.get(minute) || 0) + 1;
  rateLimiter.set(minute, count);
  for (const key of rateLimiter.keys()) {
    if (key < minute) rateLimiter.delete(key);
  }
  return count > 10;
}

function isLockedOut(ip) {
  const record = failedAttempts.get(ip);
  if (!record) return false;
  if (Date.now() > record.resetAt) {
    failedAttempts.delete(ip);
    return false;
  }
  return record.count >= 5;
}

function recordFailedAttempt(ip) {
  const record = failedAttempts.get(ip) || { count: 0, resetAt: Date.now() + 45 * 60 * 1000 };
  record.count += 1;
  failedAttempts.set(ip, record);
}

function clearFailedAttempts(ip) {
  failedAttempts.delete(ip);
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowedOrigin = "https://wsnh2022.github.io";
    const corsOrigin = origin === allowedOrigin ? allowedOrigin : "null";
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";

    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": corsOrigin,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-Access-Key",
          "Vary": "Origin",
        },
      });
    }

    if (request.method === "GET") {
      if (isLockedOut(ip)) {
        return jsonResponse({ error: "Too many failed attempts. Try again later." }, 429, corsOrigin);
      }
      const accessKey = request.headers.get("X-Access-Key");
      if (!accessKey || accessKey !== env.ACCESS_KEY) {
        recordFailedAttempt(ip);
        return jsonResponse({ error: "Unauthorized" }, 401, corsOrigin);
      }
      clearFailedAttempts(ip);
      if (isRateLimited()) {
        return jsonResponse({ error: "Too many requests. Try again in a minute." }, 429, corsOrigin);
      }
      // Queue status — frontend polls this after submission
      // in_progress while items are pending; completed once local script clears them
      const list = await env.QUEUE.list({ prefix: "queue:" });
      const pending = list.keys.length;
      if (pending > 0) {
        return jsonResponse({ status: "in_progress", pending }, 200, corsOrigin);
      }
      return jsonResponse({ status: "completed", conclusion: "success", duplicate: false }, 200, corsOrigin);
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    if (isLockedOut(ip)) {
      return jsonResponse({ error: "Too many failed attempts. Try again later." }, 429, corsOrigin);
    }

    const accessKey = request.headers.get("X-Access-Key");
    if (!accessKey || accessKey !== env.ACCESS_KEY) {
      recordFailedAttempt(ip);
      return jsonResponse({ error: "Unauthorized" }, 401, corsOrigin);
    }
    clearFailedAttempts(ip);

    if (isRateLimited()) {
      return jsonResponse({ error: "Too many requests. Try again in a minute." }, 429, corsOrigin);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return jsonResponse({ error: "Invalid JSON body" }, 400, corsOrigin);
    }

    const { instagram_url, mode, content, push_to_notion, extract_text, notion_title_override } = body;

    let job;

    if (instagram_url) {
      const shortcodeMatch = instagram_url.match(/instagram\.com\/p\/([A-Za-z0-9_-]+)/);
      if (!shortcodeMatch) {
        return jsonResponse({ error: "Invalid Instagram URL" }, 400, corsOrigin);
      }
      const shortcode = shortcodeMatch[1];
      const cleanUrl = `https://www.instagram.com/p/${shortcode}/`;

      // Duplicate check via KV
      const already = await env.QUEUE.get(`processed:${shortcode}`);
      if (already) {
        return jsonResponse({ status: "duplicate", shortcode }, 200, corsOrigin);
      }

      job = {
        mode: "instagram",
        url: cleanUrl,
        shortcode,
        push_to_notion: push_to_notion !== false,
        extract_text: extract_text !== false,
        queued_at: new Date().toISOString(),
        ...(notion_title_override && typeof notion_title_override === "string"
          ? { notion_title_override: notion_title_override.trim() }
          : {}),
      };

    } else if (mode === "urls" || mode === "text") {
      if (typeof content !== "string" || content.trim().length === 0) {
        return jsonResponse({ error: "content is required and must be a non-empty string" }, 400, corsOrigin);
      }
      if (content.length > 10000) {
        return jsonResponse({ error: "content exceeds 10,000 character limit" }, 400, corsOrigin);
      }
      job = {
        mode,
        content,
        push_to_notion: true,
        queued_at: new Date().toISOString(),
      };

    } else {
      return jsonResponse({ error: "Request must include instagram_url, or mode + content" }, 400, corsOrigin);
    }

    const key = `queue:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await env.QUEUE.put(key, JSON.stringify(job));

    return jsonResponse({ status: "triggered", message: "Queued for local processing." }, 200, corsOrigin);
  },
};

function jsonResponse(data, status = 200, corsOrigin = "null") {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": corsOrigin,
      "Vary": "Origin",
    },
  });
}
