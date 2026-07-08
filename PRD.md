# PRD: Local Processing via Cloudflare KV Queue

> **Status: Abandoned.** This migration was never finished or deployed. The project was archived instead of completing it, see [README.md](README.md) for why. Kept here as a historical record of the plan.

## Problem
GitHub Actions self-hosted runner on Windows has blocking issues (PowerShell execution policy, WSL/bash conflicts) that prevent the Instagram carousel processing workflow from running reliably.

## Goal
Replace GitHub Actions with a local processing script that runs on PC startup. The mobile share funnel (PWA → Cloudflare Worker) stays unchanged.

## New Architecture

```
Mobile Instagram
  → share to PWA (wsnh2022.github.io/insta2mdbot/)
  → POST to Cloudflare Worker (auth, dedup check, validation unchanged)
  → Worker writes job to Cloudflare KV queue
  → [PC powers on]
  → scripts/process_queue.py reads KV queue
  → runs process.py for each item (download + AI extraction)
  → runs notion_push.py (push to Notion)
  → deletes item from KV
  → appends shortcode to local _processed.txt (duplicate guard)
```

No GitHub Actions. No git commits for notes. Notes remain local + Notion only.

## Phases

### Phase 1: Cloudflare KV Namespace
- [x] Run `npx wrangler kv namespace create QUEUE` in `worker/` (ID: `897dcd24fa784dbc90f32d4d6cb0db21`)
- [x] Add KV binding to `worker/wrangler.toml`

### Phase 2: Update Cloudflare Worker
- [x] `worker/index.js`: POST handler writes job to KV instead of triggering workflow_dispatch
- [x] `worker/index.js`: GET handler returns in_progress/completed based on KV queue state
- [x] `worker/index.js`: Duplicate pre-check reads `processed:{shortcode}` from KV
- [ ] Redeploy worker: `redeploy.bat`

### Phase 3: Local Queue Processor
- [x] Created `scripts/process_queue.py`:
  - Reads Cloudflare API token from `.cloudflare-token`
  - Lists all `queue:` keys in KV namespace
  - For each key: reads job JSON, sets env vars, calls `process.py` as subprocess
  - If `push_to_notion` is true: calls `notion_push.py` as subprocess
  - On success: deletes key from KV, marks `processed:{shortcode}` in KV
  - On failure: leaves key in KV (retries next run), logs error

### Phase 4: Local Environment
- [ ] Create `.env.local` in project root (gitignored) with:
  ```
  OPENROUTER_API_KEY=sk-or-...
  NOTION_TOKEN=secret_...
  NOTION_DATABASE_ID=...
  NOTION_READING_LIST_DB_ID=...
  NOTION_TEXT_NOTES_DB_ID=...
  ```
  (Copy values from GitHub Actions secrets: Settings > Secrets and variables > Actions)
- [ ] Run `pip install -r requirements.txt` locally to confirm deps installed

### Phase 5: Windows Task Scheduler
- [ ] Create scheduled task: trigger = "At log on", action = `python D:\...\scripts\process_queue.py`
- [ ] Or: use `gitsync.bat` pattern to create a `.bat` launcher

### Phase 6: End-to-End Test
- [ ] Share a real Instagram carousel from mobile
- [ ] Verify KV queue receives the job (check via Cloudflare dashboard)
- [ ] Run `process_queue.py` manually
- [ ] Verify Notion page created with images and text
- [ ] Verify item removed from KV queue
- [ ] Trigger same URL again, verify duplicate is caught

### Phase 7: Cleanup
- [ ] Update `CLAUDE.md` to reflect new architecture
- [ ] Update `README.md` (if exists) with new setup instructions
- [ ] Disable or remove `.github/workflows/process_post.yml` (keep file, set `on: workflow_dispatch` only, add comment)
- [ ] Remove self-hosted runner from GitHub (optional)
- [ ] Delete this PRD

## Config Values Needed
| Value | Source |
|-------|--------|
| Cloudflare Account ID | `worker/wrangler.toml` (`account_id`) |
| KV Namespace ID | Output of `wrangler kv namespace create QUEUE` |
| Cloudflare API Token | `.cloudflare-token` (already exists, gitignored) |
| OPENROUTER_API_KEY | Already in GitHub Actions secrets, add to local env |
| NOTION_TOKEN | Already in GitHub Actions secrets, add to local env |
| NOTION_DATABASE_ID | Already in GitHub Actions secrets, add to local env |
| NOTION_READING_LIST_DB_ID | Already in GitHub Actions secrets, add to local env |
| NOTION_TEXT_NOTES_DB_ID | Already in GitHub Actions secrets, add to local env |
