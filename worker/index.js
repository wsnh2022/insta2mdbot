// Simple in-memory rate limiter — 10 requests per minute globally
const rateLimiter = new Map();

function isRateLimited() {
  const minute = Math.floor(Date.now() / 60000);
  const count = (rateLimiter.get(minute) || 0) + 1;
  rateLimiter.set(minute, count);
  for (const key of rateLimiter.keys()) {
    if (key < minute) rateLimiter.delete(key);
  }
  return count > 10;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-Access-Key",
        },
      });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const accessKey = request.headers.get("X-Access-Key");
    if (!accessKey || accessKey !== env.ACCESS_KEY) {
      return jsonResponse({ error: "Unauthorized" }, 401);
    }

    if (isRateLimited()) {
      return jsonResponse({ error: "Too many requests. Try again in a minute." }, 429);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return jsonResponse({ error: "Invalid JSON body" }, 400);
    }

    const { instagram_url } = body;

    if (!instagram_url || !instagram_url.includes("instagram.com/p/")) {
      return jsonResponse({ error: "Invalid Instagram URL" }, 400);
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
        inputs: { instagram_url },
      }),
    });

    if (resp.status === 204) {
      return jsonResponse({ status: "triggered", message: "Processing started. Check your notes in ~2 minutes." });
    }

    if (resp.status === 401) {
      return jsonResponse({ error: "GitHub token invalid" }, 500);
    }

    const errText = await resp.text();
    return jsonResponse({ error: `GitHub API error: ${errText}` }, 500);
  },
};

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
