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
      const runsUrl = `https://api.github.com/repos/${env.GITHUB_REPO_OWNER}/${env.GITHUB_REPO_NAME}/actions/workflows/${env.GITHUB_WORKFLOW_FILE}/runs?per_page=1`;
      const runsResp = await fetch(runsUrl, {
        headers: {
          "Authorization": `token ${env.GITHUB_PAT}`,
          "Accept": "application/vnd.github.v3+json",
          "User-Agent": "instatomdnotes-worker",
        },
      });
      if (!runsResp.ok) {
        return jsonResponse({ error: "Failed to fetch run status" }, 500, corsOrigin);
      }
      const runsData = await runsResp.json();
      const run = runsData.workflow_runs?.[0];
      if (!run) {
        return jsonResponse({ status: "none", message: "No runs found." }, 200, corsOrigin);
      }
      return jsonResponse({
        status: run.status,
        conclusion: run.conclusion,
        run_id: run.id,
      }, 200, corsOrigin);
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

    const { instagram_url, mode, content } = body;

    let workflowInputs;

    if (instagram_url) {
      const shortcodeMatch = instagram_url.match(/instagram\.com\/p\/([A-Za-z0-9_-]+)/);
      if (!shortcodeMatch) {
        return jsonResponse({ error: "Invalid Instagram URL" }, 400, corsOrigin);
      }
      const cleanUrl = `https://www.instagram.com/p/${shortcodeMatch[1]}/`;
      workflowInputs = { mode: "instagram", instagram_url: cleanUrl };

    } else if (mode === "urls" || mode === "text") {
      if (typeof content !== "string" || content.trim().length === 0) {
        return jsonResponse({ error: "content is required and must be a non-empty string" }, 400, corsOrigin);
      }
      if (content.length > 10000) {
        return jsonResponse({ error: "content exceeds 10,000 character limit" }, 400, corsOrigin);
      }
      workflowInputs = { mode, content };

    } else {
      return jsonResponse({ error: "Request must include instagram_url, or mode + content" }, 400, corsOrigin);
    }

    const githubApiUrl = `https://api.github.com/repos/${env.GITHUB_REPO_OWNER}/${env.GITHUB_REPO_NAME}/actions/workflows/${env.GITHUB_WORKFLOW_FILE}/dispatches`;

    const resp = await fetch(githubApiUrl, {
      method: "POST",
      headers: {
        "Authorization": `token ${env.GITHUB_PAT}`,
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "instatomdnotes-worker",
      },
      body: JSON.stringify({
        ref: env.GITHUB_REF,
        inputs: workflowInputs,
      }),
    });

    if (resp.status === 204) {
      return jsonResponse({ status: "triggered", message: "Processing started. Check your notes in ~2 minutes." }, 200, corsOrigin);
    }

    if (resp.status === 401) {
      return jsonResponse({ error: "GitHub token invalid" }, 500, corsOrigin);
    }

    const errText = await resp.text();
    return jsonResponse({ error: `GitHub API error: ${errText}` }, 500, corsOrigin);
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
