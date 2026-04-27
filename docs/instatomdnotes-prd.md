# instatomdnotes — Development Plan
> Personal Instagram carousel → clean Markdown knowledge base. Stack locked. Build vertically.

---

## LOCKED STACK

| Layer | Tool | Version | Notes |
|---|---|---|---|
| Frontend | Plain HTML/CSS/JS | ES2022 (no bundler) | Vanilla only — no frameworks, no build step |
| Hosting | GitHub Pages | Latest | Serve from `/docs` folder or root of repo |
| Secure API Layer | Cloudflare Worker | Workers Runtime (2024) | Free tier: 100k req/day — plenty for personal use |
| Backend Runner | GitHub Actions | `ubuntu-22.04` runner | `workflow_dispatch` trigger — on-demand only |
| Python Runtime | Python | `3.11` | Do NOT use 3.12 — instaloader + requests may break silently |
| Instagram Downloader | instaloader | `1.9.7` | Pin exactly — API surface changes between minor versions |
| HTTP Client | requests | `2.31.0` | For OpenRouter API calls |
| Vision Model Primary | google/gemini-2.0-flash-lite-001 | via OpenRouter | Multi-image per request supported |
| Vision Model Fallback | meta-llama/llama-3.2-11b-vision-instruct | via OpenRouter | Single-image calls only — batch if needed |
| Output Storage | GitHub Repo `/notes` folder | GITHUB_TOKEN | Actions commits back to repo via `git push` |
| Token Security | Cloudflare Worker env secrets | Wrangler CLI | GitHub PAT stored in Worker secrets, never in frontend |

---

## PROJECT STRUCTURE

```
instatomdnotes/
├── docs/                          # GitHub Pages root
│   ├── index.html                 # Submission form (URL input + submit button)
│   ├── style.css                  # Minimal styling
│   └── app.js                     # POST to Cloudflare Worker, show confirmation
│
├── worker/                        # Cloudflare Worker source
│   ├── index.js                   # Receives URL, validates, triggers GitHub Actions
│   └── wrangler.toml              # Worker config (name, account_id, route)
│
├── .github/
│   └── workflows/
│       └── process_post.yml       # workflow_dispatch YAML — Instagram → markdown pipeline
│
├── scripts/
│   └── process.py                 # Python processor: download → base64 → OpenRouter → save .md
│
├── notes/                         # Output folder — generated .md files land here
│   └── .gitkeep
│
├── requirements.txt               # Pinned Python deps for Actions runner
├── .gitignore
└── README.md
```

**.gitignore must include:**
```
.env
*.session          # instaloader session files — contain credentials
__pycache__/
*.pyc
.wrangler/
node_modules/
```

---

## PHASE 0 — Environment Setup (Day 0)

### System Prerequisites

**Local machine (for setup only):**
```bash
# Node.js (for Wrangler CLI)
node --version  # must be >= 18
npm --version

# Python 3.11
python3.11 --version

# Wrangler (Cloudflare Worker CLI)
npm install -g wrangler@3
wrangler --version

# Git
git --version
```

### Repo Initialization
```bash
git init instatomdnotes
cd instatomdnotes
mkdir -p docs .github/workflows scripts notes worker
touch notes/.gitkeep
touch docs/index.html docs/style.css docs/app.js
touch scripts/process.py requirements.txt
touch worker/index.js worker/wrangler.toml
touch .gitignore README.md
```

### Requirements File
```
# requirements.txt — pin exact versions
instaloader==1.9.7
requests==2.31.0
```

### GitHub Repo + Secrets Setup
```bash
# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/instatomdnotes.git

# In GitHub repo settings → Actions → Secrets:
# OPENROUTER_API_KEY  ← your OpenRouter key
# These are accessed in workflow YAML as ${{ secrets.OPENROUTER_API_KEY }}
```

### GitHub Pages Setup
- Go to repo Settings → Pages
- Source: `Deploy from a branch`
- Branch: `main`, folder: `/docs`
- Note the URL: `https://YOUR_USERNAME.github.io/instatomdnotes`

### Cloudflare Account Setup
```bash
wrangler login
# This opens browser — authenticate with your Cloudflare account
```

> ⚠️ **Security rule from Day 0:** Your GitHub Personal Access Token (PAT) with `workflow:dispatch` scope lives ONLY in Cloudflare Worker secrets. It never touches the frontend JS or the repo source. If it's ever in the repo, rotate it immediately.

### Git First Commit
```bash
git add .
git commit -m "phase-0: project scaffold"
git push origin main
```

**Success Criteria:**
- [ ] `wrangler --version` returns a version number
- [ ] `python3.11 --version` returns `3.11.x`
- [ ] GitHub repo exists and has the folder structure above
- [ ] GitHub Pages URL is accessible (returns 404 or blank page — that's fine at this stage)
- [ ] GitHub Actions secret `OPENROUTER_API_KEY` is set in repo settings

---

## PHASE 1 — GitHub Actions Workflow Skeleton (Day 1 AM)

Build the workflow YAML first. It must accept an Instagram URL as input and run successfully end-to-end — even with a stub Python script — before wiring the frontend.

**`.github/workflows/process_post.yml`:**
```yaml
name: Process Instagram Post

on:
  workflow_dispatch:
    inputs:
      instagram_url:
        description: 'Instagram post URL'
        required: true
        type: string

jobs:
  process:
    runs-on: ubuntu-22.04
    permissions:
      contents: write   # Required to commit notes back to repo

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run processor
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          INSTAGRAM_URL: ${{ inputs.instagram_url }}
        run: python scripts/process.py

      - name: Commit notes to repo
        run: |
          git config user.name "instatomdnotes-bot"
          git config user.email "bot@instatomdnotes"
          git add notes/
          git diff --cached --quiet || git commit -m "note: ${{ inputs.instagram_url }}"
          git push
```

**Stub `scripts/process.py` for Phase 1 test:**
```python
import os

url = os.environ.get("INSTAGRAM_URL", "")
print(f"[stub] Received URL: {url}")

# Write a test note so the commit step has something to push
os.makedirs("notes", exist_ok=True)
with open("notes/stub-test.md", "w") as f:
    f.write(f"# Stub Note\nURL: {url}\n")

print("[stub] Done. Phase 1 skeleton complete.")
```

**Test command:**
```bash
# Trigger manually from GitHub UI:
# Actions tab → "Process Instagram Post" → Run workflow → paste any URL
# OR via API:
curl -X POST \
  -H "Authorization: token YOUR_PAT" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/YOUR_USERNAME/instatomdnotes/actions/workflows/process_post.yml/dispatches \
  -d '{"ref":"main","inputs":{"instagram_url":"https://www.instagram.com/p/TEST123/"}}'
```

**Success Criteria:**
- [ ] Workflow appears in GitHub Actions tab
- [ ] Manual trigger completes without errors (green checkmark)
- [ ] `notes/stub-test.md` appears committed to the repo after the run
- [ ] `git log` shows the bot commit

---

## PHASE 2 — Python Processor: Download + Extract (Day 1 PM)

Replace the stub with real logic: instaloader downloads the carousel, images are read and base64-encoded, sent to OpenRouter, markdown is returned and saved.

> ⚠️ **instaloader note:** For public posts, no login is required. If you need to access your own private account posts, instaloader supports session files — but store them as GitHub secrets (base64-encoded), never commit them to the repo.

**`scripts/process.py` (full implementation):**
```python
import os
import sys
import base64
import json
import requests
import instaloader
from pathlib import Path
from datetime import datetime

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
INSTAGRAM_URL = os.environ["INSTAGRAM_URL"]
NOTES_DIR = Path("notes")
PRIMARY_MODEL = "google/gemini-2.0-flash-lite-001"
FALLBACK_MODEL = "meta-llama/llama-3.2-11b-vision-instruct"

EXTRACTION_PROMPT = """You are extracting content from an Instagram carousel slide.

Your task:
- Extract ALL text verbatim from the slide
- Preserve lists, steps, frameworks, and examples exactly
- Remove: calls to action ("save this", "follow me", "like this"), promotional lines, repetitive filler
- Do NOT summarize. Extract and clean only.
- Output plain text only — no commentary, no "here is the extracted text" preamble.

If the slide has no meaningful text (pure image/graphic), output: [image-only slide]"""


def download_carousel(url: str, tmp_dir: Path) -> list[Path]:
    """Download carousel images to tmp_dir. Returns sorted list of image paths."""
    loader = instaloader.Instaloader(
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        filename_pattern="{shortcode}_{mediaid}",
    )
    shortcode = url.rstrip("/").split("/")[-1]
    post = instaloader.Post.from_shortcode(loader.context, shortcode)

    tmp_dir.mkdir(parents=True, exist_ok=True)

    images = []
    if post.typename == "GraphSidecar":
        for node in post.get_sidecar_nodes():
            if not node.is_video:
                loader.download_pic(
                    filename=str(tmp_dir / f"slide_{len(images):02d}"),
                    url=node.display_url,
                    mtime=post.date_local,
                )
                images.extend(sorted(tmp_dir.glob(f"slide_{len(images)-1:02d}*.jpg")))
    else:
        loader.download_pic(
            filename=str(tmp_dir / "slide_00"),
            url=post.url,
            mtime=post.date_local,
        )

    return sorted(tmp_dir.glob("*.jpg"))


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_openrouter(images: list[Path], model: str) -> str:
    """Send all images to OpenRouter in a single request. Returns extracted text."""
    content = []
    for img_path in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encode_image(img_path)}"}
        })
    content.append({"type": "text", "text": EXTRACTION_PROMPT})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/instatomdnotes",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4096,
    }

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=body,
        timeout=60,
    )

    if resp.status_code == 401:
        raise RuntimeError("OpenRouter API key invalid or missing.")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def build_markdown(url: str, extracted: str) -> str:
    shortcode = url.rstrip("/").split("/")[-1]
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"""# {shortcode} — {date_str}

**Source:** {url}

---

## Extracted Content

{extracted.strip()}

---

**Tags:** #instagram #extracted  
**Search Terms:** {shortcode}
"""


def main():
    tmp_dir = Path("/tmp/insta_download")

    print(f"[1/4] Downloading: {INSTAGRAM_URL}")
    images = download_carousel(INSTAGRAM_URL, tmp_dir)
    print(f"      Found {len(images)} image(s)")

    if not images:
        print("[ERROR] No images found. Exiting.")
        sys.exit(1)

    print(f"[2/4] Sending to {PRIMARY_MODEL}...")
    try:
        extracted = call_openrouter(images, PRIMARY_MODEL)
        print("      Primary model succeeded.")
    except Exception as e:
        print(f"      Primary model failed: {e}")
        print(f"[2/4] Falling back to {FALLBACK_MODEL}...")
        extracted = call_openrouter(images, FALLBACK_MODEL)
        print("      Fallback model succeeded.")

    print("[3/4] Building markdown note...")
    note_md = build_markdown(INSTAGRAM_URL, extracted)

    shortcode = INSTAGRAM_URL.rstrip("/").split("/")[-1]
    note_path = NOTES_DIR / f"{shortcode}.md"
    NOTES_DIR.mkdir(exist_ok=True)
    note_path.write_text(note_md, encoding="utf-8")
    print(f"[4/4] Saved: {note_path}")


if __name__ == "__main__":
    main()
```

**Test command:**
```bash
# Trigger workflow with a real public Instagram post URL
# Check Actions tab for logs — look for [1/4] through [4/4]
# Verify the .md file appears in /notes after run
```

**Success Criteria:**
- [ ] Workflow downloads carousel images (log shows image count > 0)
- [ ] OpenRouter call succeeds (primary or fallback)
- [ ] `.md` note is committed to `/notes/{shortcode}.md`
- [ ] Note file contains source URL, extracted content, and tags

---

## PHASE 3 — Cloudflare Worker (Day 2 AM)

The Worker sits between your frontend and GitHub API. It holds your GitHub PAT as a secret. It receives a POST from the browser, validates the Instagram URL, and fires the workflow dispatch.

> ⚠️ **CORS must be configured in the Worker — browser requests will fail silently without it.**

**`worker/wrangler.toml`:**
```toml
name = "instatomdnotes-worker"
main = "index.js"
compatibility_date = "2024-01-01"

[vars]
GITHUB_REPO_OWNER = "YOUR_USERNAME"
GITHUB_REPO_NAME = "instatomdnotes"
GITHUB_WORKFLOW_FILE = "process_post.yml"
GITHUB_REF = "main"
```

**`worker/index.js`:**
```javascript
export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
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
      return jsonResponse({ status: "triggered", message: "Processing started. Check your notes folder in ~2 minutes." });
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
```

**Deploy Worker + Set Secrets:**
```bash
cd worker

# Deploy first (creates the worker)
wrangler deploy

# Set the GitHub PAT as a secret (never in wrangler.toml)
wrangler secret put GITHUB_PAT
# Paste your PAT when prompted

# Note your Worker URL from deploy output:
# e.g. https://instatomdnotes-worker.YOUR_ACCOUNT.workers.dev
```

**Test command:**
```bash
curl -X POST https://instatomdnotes-worker.YOUR_ACCOUNT.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"instagram_url": "https://www.instagram.com/p/REAL_SHORTCODE/"}'
# Expected: {"status":"triggered","message":"Processing started..."}
```

**Success Criteria:**
- [ ] `wrangler deploy` succeeds and outputs a Worker URL
- [ ] `wrangler secret put GITHUB_PAT` completes without error
- [ ] curl test returns `{"status":"triggered"}`
- [ ] GitHub Actions workflow appears in Actions tab after the curl test
- [ ] CORS preflight (OPTIONS) returns 200

---

## PHASE 4 — Frontend Form (Day 2 PM)

Static HTML form on GitHub Pages. Posts to the Cloudflare Worker. Shows confirmation message on success.

**`docs/index.html`:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>instatomdnotes</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main>
    <h1>instatomdnotes</h1>
    <p class="tagline">Instagram carousel → clean Markdown note</p>

    <form id="submit-form">
      <label for="url">Instagram Post URL</label>
      <input
        type="url"
        id="url"
        name="url"
        placeholder="https://www.instagram.com/p/..."
        required
        autocomplete="off"
      />

      <div class="options">
        <label><input type="checkbox" name="extract_text" checked> Extract text</label>
        <label><input type="checkbox" name="remove_clutter" checked> Remove promotional clutter</label>
        <label><input type="checkbox" name="add_tags" checked> Add tags</label>
      </div>

      <button type="submit" id="submit-btn">Convert</button>
    </form>

    <div id="status" class="status hidden"></div>
  </main>
  <script src="app.js"></script>
</body>
</html>
```

**`docs/style.css`:**
```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #0d1117;
  color: #e6edf3;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
main { width: 100%; max-width: 480px; padding: 2rem; }
h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
.tagline { color: #8b949e; font-size: 0.875rem; margin-bottom: 2rem; }
label[for="url"] { display: block; font-size: 0.875rem; margin-bottom: 0.5rem; color: #8b949e; }
input[type="url"] {
  width: 100%;
  padding: 0.75rem 1rem;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #e6edf3;
  font-size: 1rem;
  margin-bottom: 1rem;
}
input[type="url"]:focus { outline: none; border-color: #58a6ff; }
.options { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.5rem; }
.options label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: #8b949e; cursor: pointer; }
button {
  width: 100%;
  padding: 0.75rem;
  background: #238636;
  border: none;
  border-radius: 6px;
  color: #fff;
  font-size: 1rem;
  cursor: pointer;
}
button:disabled { background: #30363d; cursor: not-allowed; }
.status { margin-top: 1.5rem; padding: 1rem; border-radius: 6px; font-size: 0.875rem; }
.status.success { background: #0d2a1a; border: 1px solid #238636; color: #3fb950; }
.status.error { background: #2a0d0d; border: 1px solid #f85149; color: #f85149; }
.hidden { display: none; }
```

**`docs/app.js`:**
```javascript
const WORKER_URL = "https://instatomdnotes-worker.YOUR_ACCOUNT.workers.dev";

const form = document.getElementById("submit-form");
const btn = document.getElementById("submit-btn");
const status = document.getElementById("status");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = document.getElementById("url").value.trim();

  if (!url.includes("instagram.com/p/")) {
    showStatus("Please enter a valid Instagram post URL.", "error");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Submitting...";
  status.className = "status hidden";

  try {
    const resp = await fetch(WORKER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instagram_url: url }),
    });

    const data = await resp.json();

    if (resp.ok && data.status === "triggered") {
      showStatus("✓ Submitted. Your markdown note will be ready in ~2 minutes.\nCheck your /notes folder on GitHub.", "success");
      form.reset();
    } else {
      showStatus(data.error || "Something went wrong. Try again.", "error");
    }
  } catch (err) {
    showStatus("Network error. Check your connection.", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Convert";
  }
});

function showStatus(msg, type) {
  status.textContent = msg;
  status.className = `status ${type}`;
}
```

**Deploy:**
```bash
git add docs/
git commit -m "phase-4: frontend form"
git push
# GitHub Pages auto-deploys within ~60 seconds
```

**Test command:**
- Open `https://YOUR_USERNAME.github.io/instatomdnotes`
- Paste a real Instagram post URL
- Click Convert
- Watch GitHub Actions tab — job should appear within 5 seconds

**Success Criteria:**
- [ ] GitHub Pages URL loads the form (no 404)
- [ ] Submit triggers the Cloudflare Worker (check Worker logs with `wrangler tail`)
- [ ] GitHub Actions job appears and completes
- [ ] `/notes/{shortcode}.md` is committed to repo after ~2 minutes
- [ ] Confirmation message displays on page after submit

---

## PHASE 5 — Error Handling + Stability (Day 3 AM)

**Python processor error cases:**

| Scenario | Handler |
|---|---|
| Invalid/expired Instagram URL | `try/except` around `Post.from_shortcode` — print error, `sys.exit(1)`, workflow fails cleanly |
| Private post (not followed) | instaloader raises `QueryReturnedNotFoundException` — catch and exit with message |
| No images returned | Check `len(images) == 0` after download — exit with descriptive message |
| OpenRouter 401 (bad key) | Raise `RuntimeError("API key invalid")` explicitly — don't rely on generic `raise_for_status` |
| OpenRouter timeout (>60s) | `requests.post(timeout=60)` — catch `requests.Timeout`, retry once with fallback model |
| Primary model fails (any error) | Log error, immediately retry with fallback model — if fallback also fails, exit with error |
| Fallback model also fails | Print both errors, `sys.exit(1)` — workflow fails, no partial note written |
| Notes folder doesn't exist | `NOTES_DIR.mkdir(exist_ok=True)` — always safe to call |
| File already exists for shortcode | Overwrite — same shortcode = same post, idempotent |
| Git push fails (conflict) | `git pull --rebase` before push in YAML, or use `git push --force-with-lease` |

**Add to workflow YAML after the run step:**
```yaml
      - name: Pull latest before commit (avoid push conflicts)
        run: git pull --rebase origin main

      - name: Commit notes to repo
        run: |
          git config user.name "instatomdnotes-bot"
          git config user.email "bot@instatomdnotes"
          git add notes/
          git diff --cached --quiet && echo "No new notes to commit" || git commit -m "note: ${{ inputs.instagram_url }}"
          git push
```

**Worker error handling (already in Phase 3 — verify these are present):**
- [ ] Invalid URL → 400 with clear message
- [ ] GitHub API 401 → 500 with message (don't expose PAT)
- [ ] CORS headers on all responses including errors

**Frontend error handling (already in Phase 4 — verify):**
- [ ] Network errors caught and displayed
- [ ] Button re-enabled after any outcome
- [ ] Clear messaging for invalid URL format

**Success Criteria:**
- [ ] Submitting an invalid URL returns a clear error (not a 500)
- [ ] Submitting a private/inaccessible post fails the workflow gracefully (no partial file)
- [ ] Primary model failure triggers fallback automatically (check logs)
- [ ] Double-submitting the same URL produces one clean `.md` (no corruption)
- [ ] `git log` shows clean commit history with no merge conflicts

---

## PHASE 6 — End-to-End Validation + Deployment (Day 3 PM)

**Full end-to-end test on a clean state:**

```bash
# 1. Clear notes folder
rm notes/*.md
git add notes/ && git commit -m "clear: reset notes for e2e test" && git push

# 2. Submit 3 different Instagram posts via the live form
# (use real posts from @datacraft.yogi or any public account)

# 3. After each, verify in GitHub:
# - Actions tab: workflow ran, green checkmark
# - notes/ folder: .md file exists with correct shortcode name
# - .md content: source URL present, extracted text present, no blank file

# 4. Test error case: submit a garbage URL
# - Expected: form shows error, no workflow triggered

# 5. Test Worker directly with curl (no browser)
# - Expected: same trigger behavior
```

**Deployment final checklist:**
```bash
# Verify GitHub Pages
curl -I https://YOUR_USERNAME.github.io/instatomdnotes
# Expected: HTTP/2 200

# Verify Worker is live
curl -X OPTIONS https://instatomdnotes-worker.YOUR_ACCOUNT.workers.dev
# Expected: 200 with CORS headers

# Check Worker URL in app.js matches deployed worker
grep WORKER_URL docs/app.js
```

**Success Criteria:**
- [ ] Three real posts processed successfully end-to-end
- [ ] Each `.md` file contains source URL, extracted text, tags
- [ ] Error URL handled gracefully by frontend (no broken state)
- [ ] `wrangler tail` shows Worker logs for each submission
- [ ] GitHub Pages form loads in under 2 seconds on mobile browser

---

## TIMELINE

| Day | Phase | Key Output |
|---|---|---|
| Day 0 | Environment Setup | Repo, Python, Wrangler installed; secrets set; GitHub Pages enabled |
| Day 1 AM | Phase 1 — GitHub Actions skeleton | Workflow runs with stub script; bot commits to `/notes` |
| Day 1 PM | Phase 2 — Python processor | Real download + OpenRouter call; actual `.md` saved to repo |
| Day 2 AM | Phase 3 — Cloudflare Worker | Worker deployed; GitHub Actions triggerable via curl |
| Day 2 PM | Phase 4 — Frontend form | Live GitHub Pages form submits real posts end-to-end |
| Day 3 AM | Phase 5 — Error handling | Graceful failures on bad URLs, model errors, git conflicts |
| Day 3 PM | Phase 6 — E2E validation | 3 real posts processed; system confirmed stable |

---

## DEBUGGING MATRIX

| Symptom | Check First | Check Second |
|---|---|---|
| Workflow never triggers after form submit | Check browser network tab — is the Worker returning 204 or an error? | Check Worker logs: `wrangler tail` — is the GitHub API call succeeding? |
| `401 Unauthorized` from GitHub API | `GITHUB_PAT` secret in Cloudflare Worker is wrong or expired | PAT was created with wrong scope — needs `repo` + `workflow` permissions |
| `403 Forbidden` from GitHub API | PAT is correct but the workflow file name in wrangler.toml doesn't match | Branch name (`main` vs `master`) mismatch in Worker vars |
| instaloader raises `QueryReturnedNotFoundException` | Post is private — instaloader can't access it without login | URL is malformed — shortcode is incorrect |
| instaloader download hangs | Instagram rate limiting the runner IP | Try again in 5 minutes — or add `time.sleep(2)` between image downloads |
| OpenRouter returns empty content | Model doesn't support the image format — check base64 encoding | Prompt too long with many slides — split into individual image calls |
| `KeyError: choices` in OpenRouter response | Rate limit or quota exceeded — check OpenRouter dashboard | Model name typo — verify exact model string |
| `.md` file not appearing in `/notes` after successful run | Git push step in YAML failed silently — check Actions logs for push output | `git diff --cached --quiet` exited 0 (nothing to commit) — check if file was actually written |
| GitHub Pages showing old version of form | Browser cache — hard refresh (Ctrl+Shift+R) | Pages deploy took >5min — check Pages deployment status in repo settings |
| CORS error in browser console | Worker not returning `Access-Control-Allow-Origin: *` on error responses | Preflight OPTIONS request failing — Worker doesn't handle OPTIONS correctly |
| Python `ModuleNotFoundError: instaloader` | `requirements.txt` not installed in workflow — check `pip install -r requirements.txt` step | Version mismatch — pin to `instaloader==1.9.7` exactly |
| Extracted markdown is blank or `[image-only slide]` for all slides | Post is a video carousel (no still images) | OpenRouter model returned empty response — check raw API response in logs |

---

## MVP LOCK — Do Not Build in Week 1

- **Job completion polling** — form saying "it's done" automatically. A static confirmation message is sufficient for personal use. Add later if needed.
- **Notes history/index page** — browsable list of processed notes in the UI. GitHub's repo file browser already does this.
- **Duplicate detection** — checking if a shortcode was already processed. Overwriting is fine for now.
- **Tag generation via second LLM call** — the single extraction prompt handles this. Don't add complexity.
- **Email/Telegram notification when done** — you know where your notes live. Not needed for personal tool.
- **Markdown format options** (e.g. Obsidian vs Notion format) — one clean format is enough for MVP.
- **Authentication on the form** — it's a personal tool on a GitHub account. No external auth needed.
- **Local dev environment for testing** — the GitHub Actions runner IS the environment. Test there.

---

## FINAL CHECKLIST

- [ ] `requirements.txt` has exact pinned versions for all packages (`instaloader==1.9.7`, `requests==2.31.0`)
- [ ] `OPENROUTER_API_KEY` stored only in GitHub Actions secrets — never in source code or workflow YAML
- [ ] `GITHUB_PAT` stored only in Cloudflare Worker secrets — never in frontend JS or repo
- [ ] `.gitignore` includes `*.session` — instaloader session files must never be committed
- [ ] Cloudflare Worker returns CORS headers on ALL responses, including error responses
- [ ] Python processor catches both primary model failure AND fallback failure — `sys.exit(1)` on both fail
- [ ] GitHub Actions workflow has `permissions: contents: write` for the bot commit step
- [ ] `git pull --rebase` before bot commit to prevent push conflicts on concurrent runs
- [ ] Worker validates Instagram URL format before calling GitHub API (prevents garbage data in workflow)
- [ ] Frontend button is disabled during submission — prevents double-triggers
- [ ] Python uses `timeout=60` on all OpenRouter requests — default has no timeout
- [ ] `NOTES_DIR.mkdir(exist_ok=True)` called before writing — never assume the folder exists on the runner
- [ ] Workflow file name in `wrangler.toml` exactly matches `.github/workflows/process_post.yml`
- [ ] Tested end-to-end with at least 3 real public Instagram post URLs before calling it done
- [ ] `wrangler tail` verified showing live Worker logs during form submissions
