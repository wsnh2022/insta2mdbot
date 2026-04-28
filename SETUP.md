# Setup Guide — instatomdnotes

This guide documents every step to deploy instatomdnotes from scratch, including every issue encountered during the original setup and exactly how to fix them.

---

## Prerequisites

| Requirement | Where to get it |
|-------------|----------------|
| GitHub account | github.com |
| Cloudflare account (free) | cloudflare.com |
| OpenRouter API key | openrouter.ai |
| GitHub PAT (`repo` + `workflow` scopes) | GitHub → Settings → Developer settings → Personal access tokens |
| Cloudflare API token ("Edit Cloudflare Workers" template) | Cloudflare → My Profile → API Tokens |
| Node.js installed | nodejs.org (for `npx wrangler`) |

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

Add these two secrets:

| Name | Value |
|------|-------|
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `NOTES_REPO_PAT` | Your GitHub PAT (`ghp_...`) |

> **Gotcha:** Both secrets must be added to the **main code repo** (`insta2mdbot`), NOT to the private notes repo. The workflow runs in the code repo and reads secrets from there. Adding secrets to the notes repo has no effect.

---

### 3. Create a private notes repo

Create a new **private** GitHub repository (e.g. `insta2mdbot-notes`).

> **Gotcha:** When creating the repo, tick **"Add a README file"** to initialize it. If you skip this, the repo has no commits and no default branch — `actions/checkout@v4` will fail with a cryptic error when trying to clone it.
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

> **Gotcha: Wrangler tries to open a browser for login** — if you see "Wrangler authorization failed" in a browser popup, close it. Wrangler is trying OAuth instead of using the token. The fix: make sure `$env:CLOUDFLARE_API_TOKEN` is set **before** running any wrangler command, in the **same PowerShell window**.

> **Gotcha: Wrong command syntax** — the correct command is:
> ```powershell
> npx wrangler secret put GITHUB_PAT
> ```
> Do NOT pass a URL or value as part of the command. Wrangler will prompt you to enter the value interactively after you run it.

> **Gotcha: Token confusion** — three separate credentials are used:
> - `CLOUDFLARE_API_TOKEN` — authenticates wrangler to Cloudflare (only needed during deployment)
> - `GITHUB_PAT` — stored as a Worker secret; used to trigger GitHub Actions
> - `ACCESS_KEY` — a passphrase you choose; gates access to the form

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

> **Gotcha: git push rejected** — this project's GitHub Actions workflow commits notes back to the repo after every run, which means the remote is often ahead of your local branch. If you see `! [rejected] main -> main (fetch first)`, run:
> ```powershell
> git stash
> git pull --rebase origin main
> git stash pop
> git push
> ```
> You will need to do this regularly. The stash step is required because `git pull --rebase` fails if you have any unstaged local changes.

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

Fix — in the workflow, always **commit first, then pull, then push**:
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

Fix — use a separate counter variable:
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

Fix — resize images to max 768px before encoding with Pillow:
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
Free GitHub Pages requires a public repo, so the code is public. To keep notes private, push them to a **separate private repo** using a PAT. The workflow checks out the private repo to the `notes/` path before running the processor — no changes needed in the Python script.

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
    │    1. Download carousel slides via instaloader
    │    2. Resize each slide to max 768px (Pillow)
    │    3. Send all slides to OpenRouter vision model
    │    4. Second API call → get title + tags (JSON)
    │    5. Build .md note
    │  git commit + push → private notes repo
    ▼
[github.com/YOUR_USERNAME/insta2mdbot-notes] (private)
```
