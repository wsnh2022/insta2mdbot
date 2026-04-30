# Setup Guide - INSTA_TO_MD_BOT

This guide documents every step to deploy INSTA_TO_MD_BOT from scratch, including every issue encountered during the original setup and exactly how to fix them.

---

## Prerequisites

| Requirement | Where to get it |
|-------------|----------------|
| GitHub account | github.com |
| Cloudflare account (free) | cloudflare.com |
| OpenRouter API key | openrouter.ai |
| GitHub PAT (`repo` + `workflow` scopes) | GitHub → Settings → Developer settings → Personal access tokens |
| Cloudflare API token ("Edit Cloudflare Workers" template) | See instructions below |
| Node.js installed | nodejs.org (for `npx wrangler`) |

---

### How to create the Cloudflare API token

This token lets wrangler deploy and manage your Worker. You must use the correct template - a generic token will not have the right permissions.

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com) or [API-TOKENS](https://dash.cloudflare.com/profile/api-tokens)
2. Click your profile icon (top right) → **My Profile**
3. Click **API Tokens** in the left sidebar
4. Click **Create Token**
5. Find the **"Edit Cloudflare Workers"** template and click **Use template**
6. Leave all settings as default - do not restrict by zone or IP unless you know what you're doing
7. Click **Continue to summary** → **Create Token**
8. **Copy the token immediately** - it is only shown once. If you lose it, you must delete and recreate it.

> **Gotcha:** Do NOT use "Global API Key" - it has full account access and is a security risk. Always use a scoped API token via the template.

> **Gotcha:** The token is only shown once on screen after creation. If you close the page without copying it, you cannot retrieve it - you must delete the token and create a new one.

---

## Step-by-Step Setup

### 1. Fork / clone the repo

```
https://github.com/wsnh2022/insta2mdbot
```

Enable GitHub Pages: repo **Settings → Pages → Source: Deploy from a branch → Branch: main → Folder: /docs**

> **Gotcha:** GitHub Pages only works on public repos on the free plan. If your repo is private you will get no Pages option. Keep the code repo **public** and use a separate private repo for notes (see Step 3).

---

### 2. Add GitHub Actions secrets

Go to: `https://github.com/YOUR_USERNAME/insta2mdbot/settings/secrets/actions`

Add these secrets:

| Name | Value | Required |
|------|-------|----------|
| `OPENROUTER_API_KEY` | Your OpenRouter API key | Yes |
| `NOTES_REPO_PAT` | Your GitHub PAT (`ghp_...`) | Yes |
| `INSTAGRAM_SESSION_ID` | Your Instagram `sessionid` cookie value | Optional (but recommended) |

> **Gotcha:** All secrets must be added to the **main code repo** (`insta2mdbot`), NOT to the private notes repo. The workflow runs in the code repo and reads secrets from there. Adding secrets to the notes repo has no effect.

---

### How to get your Instagram Session ID (for `INSTAGRAM_SESSION_ID`)

Adding this secret makes instaloader download as your logged-in account instead of anonymously. This significantly reduces Instagram IP blocks and rate limiting on the GitHub Actions runner.

**Step 1 — Open Instagram in a desktop browser and log in**

Use Chrome, Edge, or Firefox. You must be on desktop — mobile browsers don't expose DevTools easily.

**Step 2 — Open DevTools**

Press `F12` (or right-click anywhere → **Inspect**).

**Step 3 — Navigate to the cookie**

- Click the **Application** tab (Chrome/Edge) or **Storage** tab (Firefox)
- In the left sidebar expand **Cookies** → click `https://www.instagram.com`
- Find the row where **Name** is exactly `sessionid`
- Click it and copy the full **Value** (it's a long alphanumeric string like `58901234567%3AaBcDeFgHiJkLmN%3A12%3A...`)

**Step 4 — Add it as a GitHub secret**

1. Go to your repo → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `INSTAGRAM_SESSION_ID`
4. Value: paste the cookie value
5. Click **Add secret**

That's it — every future GitHub Actions run automatically picks it up.

> **Gotcha: Don't log out of Instagram after copying the cookie.** Logging out invalidates the session immediately. The cookie stays valid as long as you remain logged in on that browser.

> **Gotcha: Sessions expire after a few months.** If the bot starts hitting more download errors than usual, your session has likely expired. Repeat Steps 1–4 above to get a fresh cookie and update the secret.

> **Gotcha: Changing your Instagram password invalidates all sessions.** After a password change you must get a new cookie.

> **Note: This is completely optional.** If `INSTAGRAM_SESSION_ID` is not set, the bot falls back to anonymous downloads exactly as before — no errors, just slightly higher risk of IP blocks on heavy use.

---

### 3. Create a private notes repo

Create a new **private** GitHub repository (e.g. `insta2mdbot-notes`).

> **Gotcha:** When creating the repo, tick **"Add a README file"** to initialize it. If you skip this, the repo has no commits and no default branch - `actions/checkout@v4` will fail with a cryptic error when trying to clone it.
>
> If you created it empty by mistake, initialize it via the API:
> ```powershell
> $pat = "YOUR_GITHUB_PAT"
> $content = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("# insta2mdbot-notes`n`nPrivate notes."))
> $body = @{ message = "init: add README"; content = $content } | ConvertTo-Json
> Invoke-RestMethod "https://api.github.com/repos/YOUR_USERNAME/insta2mdbot-notes/contents/README.md" -Method Put -Headers @{Authorization="token $pat"; Accept="application/vnd.github.v3+json"} -Body $body -ContentType "application/json"
> ```

Update `.github/workflows/process_post.yml` line with `repository: YOUR_USERNAME/insta2mdbot-notes`.

---

### 4. Deploy the Cloudflare Worker

Open PowerShell and run all commands **in the same session** (the token does not persist between sessions):

```powershell
$env:CLOUDFLARE_API_TOKEN = "your-cloudflare-api-token"
cd path\to\insta2mdbot\worker
npx wrangler deploy
npx wrangler secret put GITHUB_PAT
npx wrangler secret put ACCESS_KEY
```

- When `secret put GITHUB_PAT` prompts, paste your GitHub PAT
- When `secret put ACCESS_KEY` prompts, type a passphrase you will use in the form

> **Gotcha: Wrangler tries to open a browser for login** - if you see "Wrangler authorization failed" in a browser popup, close it. Wrangler is trying OAuth instead of using the token. The fix: make sure `$env:CLOUDFLARE_API_TOKEN` is set **before** running any wrangler command, in the **same PowerShell window**.

> **Gotcha: Wrong command syntax** - the correct command is:
> ```powershell
> npx wrangler secret put GITHUB_PAT
> ```
> Do NOT pass a URL or value as part of the command. Wrangler will prompt you to enter the value interactively after you run it.

> **Gotcha: Token confusion** - three separate credentials are used:
> - `CLOUDFLARE_API_TOKEN` - authenticates wrangler to Cloudflare (only needed during deployment)
> - `GITHUB_PAT` - stored as a Worker secret; used to trigger GitHub Actions
> - `ACCESS_KEY` - a passphrase you choose; gates access to the form

---

### 5. Update WORKER_URL in docs/app.js

After `wrangler deploy` succeeds, copy the deployed URL from the output:
```
https://instatomdnotes-worker.YOUR_SUBDOMAIN.workers.dev
```

Open `docs/app.js` line 1 and replace the placeholder:
```javascript
const WORKER_URL = "https://instatomdnotes-worker.YOUR_SUBDOMAIN.workers.dev";
```

---

### 6. Update wrangler.toml with your account ID

Run `npx wrangler whoami` (with `$env:CLOUDFLARE_API_TOKEN` set) and copy your Account ID.

Open `worker/wrangler.toml` and set:
```toml
account_id = "YOUR_32_CHAR_ACCOUNT_ID"
```

---

### 7. Commit and push

```powershell
git add worker/wrangler.toml docs/app.js
git commit -m "deploy: set account_id and worker URL"
git push
```

> **Gotcha: git push rejected** - this project's GitHub Actions workflow commits notes back to the repo after every run, which means the remote is often ahead of your local branch. If you see `! [rejected] main -> main (fetch first)`, run:
> ```powershell
> git stash
> git pull --rebase origin main
> git stash pop
> git push
> ```
> You will need to do this regularly. The stash step is required because `git pull --rebase` fails if you have any unstaged local changes.

---

### 8. AHK Hotkey (Optional)

An AutoHotkey v2 script lets you trigger a conversion without opening the browser — select an Instagram URL anywhere on screen and press `Alt+I`.

**Prerequisites:** [AutoHotkey v2](https://www.autohotkey.com/) installed (download and run the installer, default options).

**Setup:**

1. Open `ahk/passphrase.txt` and replace its contents with the same passphrase you set as `ACCESS_KEY` in the Cloudflare Worker (`npx wrangler secret put ACCESS_KEY`).
2. Double-click `ahk/insta_trigger.ahk` to run the script. An AHK icon appears in the system tray.

**Usage:**

1. In any app (browser, notes, anywhere) — select/highlight an Instagram post URL
2. Press `Alt+I`
3. A Windows notification appears within a second:
   - "Triggered — GitHub Actions is processing the post" → success
   - "Wrong passphrase — update passphrase.txt" → passphrase mismatch
   - "Rate limited — wait a minute and try again" → 10 req/min limit hit
4. GitHub Actions runs in the background — the note appears in the private notes repo in ~2 min

**How it works:** the script sends `Ctrl+C` to copy the selected text, extracts the shortcode via regex, and POSTs `{"instagram_url": "..."}` directly to the Cloudflare Worker with `X-Access-Key` set — identical to a form submission, no browser involved.

> **Note:** `ahk/passphrase.txt` is listed in `.gitignore` and will never be committed. The script file itself is safe to commit — it contains no secrets.

> **Tip:** Press `Ctrl+S` while editing the `.ahk` file to reload it instantly (built into the script header).

---

## Common Errors and Fixes

### `ERROR: No matching distribution found for instaloader==1.9.7`
The version `1.9.7` does not exist on PyPI. instaloader versions jump from 1.3 directly to 2.0+. Use `instaloader==4.15.1` in `requirements.txt`.

---

### `error: cannot pull with rebase: You have unstaged changes`
Always stash before pulling:
```powershell
git stash
git pull --rebase origin main
git stash pop
```

---

### Workflow fails: `error: cannot pull with rebase: You have unstaged changes` inside GitHub Actions
This happens when the workflow tries to `git pull --rebase` before committing the new note. The note file sitting in `notes/` is an unstaged change that blocks the rebase.

Fix - in the workflow, always **commit first, then pull, then push**:
```yaml
git add notes/
git diff --cached --quiet && echo "No new notes" && exit 0
git commit -m "note: ..."
git pull --rebase origin main
git push
```

---

### Only the first (or last) carousel image is extracted
Bug in the download loop: the filename counter was based on `len(images)` which never incremented correctly, so every slide overwrote `slide_00.jpg`.

Fix - use a separate counter variable:
```python
count = 0
for node in post.get_sidecar_nodes():
    if not node.is_video:
        loader.download_pic(filename=str(tmp_dir / f"slide_{count:02d}"), ...)
        count += 1
```

---

### CORS error: `x-access-key is not allowed by Access-Control-Allow-Headers`
The Cloudflare Worker was not redeployed after adding `X-Access-Key` to the CORS headers in `index.js`. Any time you change `worker/index.js`, you must redeploy:
```powershell
$env:CLOUDFLARE_API_TOKEN = "your-token"
cd worker
npx wrangler deploy
```

---

### Workflow fails: `Error: Input required and not supplied: token`
The `NOTES_REPO_PAT` secret is missing or added to the wrong repository. It must be in the **code repo** (`insta2mdbot`), not the notes repo. Go to:
`https://github.com/YOUR_USERNAME/insta2mdbot/settings/secrets/actions`
and add `NOTES_REPO_PAT`.

---

### High token usage on OpenRouter (~6,000+ tokens per image)
instaloader downloads images at full Instagram resolution (1080px+). Vision models tokenize large images into many tiles, each costing ~170 tokens.

Fix - resize images to max 768px before encoding with Pillow:
```python
from PIL import Image

def resize_image(path, max_px=768):
    img = Image.open(path)
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    img.save(path, "JPEG", quality=85)
    return path
```

---

### Form shows "Network error. Check your connection."
This usually means a CORS preflight failure, not an actual network issue. Check the browser DevTools Console (F12) for the real error. Most likely cause: the Worker was not redeployed after a code change.

---

### Notes are visible publicly on GitHub
Free GitHub Pages requires a public repo, so the code is public. To keep notes private, push them to a **separate private repo** using a PAT. The workflow checks out the private repo to the `notes/` path before running the processor - no changes needed in the Python script.

---

## Security Hardening

The following security improvements have been applied. Run `redeploy.bat` after any Worker change.

### CORS locked to GitHub Pages only

`worker/index.js` — `Access-Control-Allow-Origin` was changed from `*` (any site) to `https://wsnh2022.github.io` only. No other website's JavaScript can call the Worker, even if they know the URL and passphrase.

Direct API calls (AHK, curl, Postman) are unaffected — CORS is a browser-only restriction.

---

### IP lockout after failed passphrase attempts

`worker/index.js` — After 5 wrong passphrase attempts from the same IP, that IP is blocked for **45 minutes** on both GET and POST endpoints. Applies to brute-force attempts against the form and the AHK hotkey.

---

### Rate limiting extended to GET endpoint

`worker/index.js` — The status-polling GET endpoint was previously unprotected. It now shares the same IP lockout as POST, preventing rapid passphrase probing via the status endpoint.

---

### Passphrase strength

`ACCESS_KEY` (Cloudflare Worker secret) should be at minimum 12 characters with uppercase, lowercase, numbers, and symbols. This gives ~72 bits of entropy — combined with the IP lockout, brute force is not a practical attack.

To update: `npx wrangler secret put ACCESS_KEY` (with `$env:CLOUDFLARE_API_TOKEN` set).

---

### GitHub PATs — use classic tokens only

Generate one classic token and use it for both `GITHUB_PAT` and `NOTES_REPO_PAT`.

**Scopes required:**
- `repo` — full access (required for private repo checkout in Actions)
- `workflow` — required to trigger `workflow_dispatch`

Generate at: **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**

**Where to paste it:**
- `GITHUB_PAT` → Cloudflare dashboard → Workers & Pages → `instatomdnotes-worker` → Settings → Variables and Secrets → Rotate
- `NOTES_REPO_PAT` → github.com/wsnh2022/insta2mdbot → Settings → Secrets and variables → Actions → Update

> **Do not use fine-grained tokens.** `actions/checkout@v4` with a private repo + fine-grained token returns a 403 error regardless of permission configuration. Classic tokens are the only working approach for this stack.

---

### AHK passphrase file

`ahk/passphrase.txt` is listed in `.gitignore` and is never committed. It is read at hotkey-press time from the local filesystem. The AHK script itself contains no secrets and is safe to commit.

---

## Architecture at a Glance

```
[GitHub Pages form]
    │  POST { instagram_url } + X-Access-Key header
    ▼
[Cloudflare Worker]
    │  Validates passphrase (ACCESS_KEY secret)
    │  Rate limits (10 req/min)
    │  Calls GitHub API to trigger workflow_dispatch
    ▼
[GitHub Actions runner]
    │  Checks out code repo
    │  Checks out private notes repo → notes/
    │  pip install instaloader, requests, Pillow
    │  process.py:
    │    1. Check _processed.txt — skip if shortcode already saved
    │    2. Download carousel slides via instaloader
    │       (uses sessionid cookie if INSTAGRAM_SESSION_ID secret is set)
    │    3. Resize each slide to max 768px (Pillow)
    │    4. Send all slides to OpenRouter vision model
    │       (chain: Gemini 2.5 Flash Lite → Qwen 3.5 9B → NVIDIA Nemotron Nano 12B 2 VL)
    │       (if all fail: retry full chain after 1 min, then 3 min)
    │    5. Second API call → get title + tags (JSON)
    │    6. Third API call → generate 2-3 sentence summary
    │    7. Build .md note with YAML frontmatter + summary callout
    │       saved to notes/{primary-tag}/{slug}.md
    │  git commit + push → private notes repo
    ▼
[github.com/YOUR_USERNAME/insta2mdbot-notes] (private)
```
