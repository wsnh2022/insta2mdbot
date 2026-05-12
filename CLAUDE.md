# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A personal tool that converts Instagram carousels into structured Obsidian notes. Paste an Instagram URL in the GitHub Pages form, a Cloudflare Worker triggers a GitHub Actions workflow, Python downloads the carousel, sends slides to OpenRouter vision AI, and saves a formatted `.md` note to a separate private GitHub repo (`wsnh2022/insta2mdbot-notes`).

The form also accepts plain URLs (saved to `notes/pending-to-read.md`) and raw text (AI-converted to a note). Mode is auto-detected by `docs/app.js` and `worker/index.js`.

## Architecture

```
GitHub Pages (docs/)          ← Vanilla HTML/CSS/JS, hosted at wsnh2022.github.io/insta2mdbot/
      │ POST + X-Access-Key
      ▼
Cloudflare Worker (worker/)   ← Auth, rate limit, URL sanitisation, triggers workflow_dispatch
      │ GitHub API
      ▼
GitHub Actions (.github/workflows/process_post.yml)
      │ runs scripts/process.py
      ▼
Private notes repo (wsnh2022/insta2mdbot-notes)   ← YAML frontmatter .md files, never in this repo
```

**Three processing modes** (set by `MODE` env var, dispatched by the Worker):
- `instagram`: downloads carousel via instaloader, vision AI converts to structured note
- `urls`: appends plain URLs to `notes/pending-to-read.md`
- `text`: AI-generates title, tags, and summary from raw text, saves as note

**AI chain** (`scripts/process.py`): Gemini 2.5 Flash Lite → Qwen 3.5 9B → NVIDIA Nemotron Nano 12B 2 VL. If all three fail, retries the full chain after 60s then 180s before giving up.

## Deploy

Run `gitsync.bat` from the project root. It handles git add, commit, and push (with pull --rebase if needed).

## Redeploying the Cloudflare Worker

Any change to `worker/index.js` must be redeployed to take effect:

```powershell
# Option 1: double-click redeploy.bat (reads .cloudflare-token from project root)

# Option 2: manual
$env:CLOUDFLARE_API_TOKEN = "your-token"   # must be set BEFORE wrangler commands in the same session
cd worker
npx wrangler deploy
```

To update Worker secrets:
```powershell
npx wrangler secret put GITHUB_PAT
npx wrangler secret put ACCESS_KEY
```

## Running the Python script locally

```powershell
pip install -r requirements.txt

# instagram mode
$env:OPENROUTER_API_KEY = "sk-..."
$env:INSTAGRAM_URL = "https://www.instagram.com/p/SHORTCODE/"
python scripts/process.py

# text mode
$env:MODE = "text"
$env:CONTENT = "your raw text here"
python scripts/process.py
```

The script writes to a `notes/` directory relative to where it runs. On GitHub Actions, that directory is the checked-out private notes repo.

## Key files

| File | Purpose |
|------|---------|
| `scripts/process.py` | All processing logic: download, resize, AI extraction, metadata, note building |
| `worker/index.js` | Cloudflare Worker: auth, rate limiting, URL validation, GitHub dispatch |
| `worker/wrangler.toml` | Worker config: `account_id` is set, secrets (`GITHUB_PAT`, `ACCESS_KEY`) stored in Cloudflare dashboard |
| `docs/app.js` | Frontend: mode detection, batch submission, status polling |
| `.github/workflows/process_post.yml` | Workflow: checks out both repos, installs deps, runs process.py, commits note |
| `ahk/insta_trigger.ahk` | AHK v2 hotkey (`Alt+I`): copies selected URL, POSTs to Worker directly |
| `ahk/passphrase.txt` | Passphrase for AHK script, gitignored, create manually |
| `.cloudflare-token` | Cloudflare API token for redeploy.bat, gitignored, create manually |

## Worker secrets vs GitHub secrets

| Secret | Stored in | Used by |
|--------|-----------|---------|
| `ACCESS_KEY` | Cloudflare Worker secrets | Worker: gates all requests |
| `GITHUB_PAT` | Cloudflare Worker secrets | Worker: triggers `workflow_dispatch` |
| `OPENROUTER_API_KEY` | GitHub Actions secrets (code repo) | `process.py` |
| `NOTES_REPO_PAT` | GitHub Actions secrets (code repo) | Workflow: checks out private notes repo |

All GitHub Actions secrets must be in the **code repo** (`insta2mdbot`), not the notes repo.

## Important constraints

- **Do not set `INSTAGRAM_SESSION_ID`.** Using a real account session from GitHub Actions datacenter IPs causes Instagram to lock the account. Anonymous mode is the safe default.
- **Use classic GitHub PATs only** (not fine-grained). `actions/checkout@v4` returns 403 with fine-grained tokens on private repos.
- **Notes repo must be initialized** (have at least one commit). An empty repo causes `actions/checkout@v4` to fail.
- **CORS is locked** to `https://wsnh2022.github.io` only. Direct API calls (AHK, curl) bypass CORS, this is expected.
- Images are resized to max 768px before encoding to keep vision model token costs low.

## Note output format

```markdown
---
title: "Title Here"
source: "https://www.instagram.com/p/SHORTCODE/"
tags:
  - tag1
  - tag2
date: 2026-05-12
---

> [!summary]
> 2-3 sentence plain prose summary.

### Section Header
Content...
```

Notes are saved to `notes/{primary-tag}/{slug}.md` in the private repo. Processed shortcodes are logged in `notes/_processed.txt` for duplicate detection.

## Commits
Never add `Co-Authored-By: Claude` or any Anthropic co-author line to commit messages.

## Agents
Never use `isolation: "worktree"` on agents. It creates stale branches and folders that need manual cleanup.

## Writing Style
Never use em dashes. Use a comma, period, colon, or rewrite the sentence instead.

## General
Do not create new files unless explicitly asked. All frontend content lives in the existing `docs/` files.
