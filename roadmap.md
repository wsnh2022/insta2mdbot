# instatomdnotes - Roadmap

---

## Phase 1 - Complete ✅

7 features shipped over 4 days.

| Feature | What it does |
|---------|-------------|
| Obsidian Frontmatter | YAML frontmatter - works natively in Obsidian (dataview, graph, tag autocomplete) |
| Duplicate Detection | `_processed.txt` shortcode log - skips re-processing, saves AI credits |
| AI TLDR Summary | 2-3 sentence callout block (`> [!summary]`) generated after extraction |
| Auto-Folder by Topic | Notes routed to `notes/{primary-tag}/` subfolders automatically |
| Instaloader Session Login | `INSTAGRAM_SESSION_ID` secret reduces anonymous IP blocks |
| Status Polling | GET `/status` Worker route + frontend polls every 10s - shows "Done!" live |
| Batch URL Submission | Textarea input, up to 10 URLs, 30s staggered dispatch |

UI improvements shipped alongside:
- Card layout with cover image banner
- Passphrase auto-collapse (saves to sessionStorage, 🔒 button to reveal)
- iOS zoom bug fix (`font-size: 1rem` on inputs)
- Mobile-safe touch targets and keyboard layout

---

## Phase 2 - Next

### Android One-Click Share

Share any Instagram post directly from the Android Instagram app to the bot - no browser, no copy-pasting.

**How:** Android supports [Web Share Target API](https://web.dev/web-share-target/) - a PWA can register itself as a share destination. When the user hits "Share" in Instagram, the bot appears in the share sheet.

**What needs to be built:**
- `docs/manifest.json` - PWA manifest declaring the app as a share target
- `docs/sw.js` - minimal service worker (required for PWA install)
- Worker handles incoming `share_target` POST (URL passed as query param)
- `docs/index.html` - add PWA meta tags + manifest link
- User installs the PWA to home screen once via Chrome → it registers as a share target

**Files to create/modify:**
| File | Change |
|------|--------|
| `docs/manifest.json` | New - PWA identity + `share_target` declaration |
| `docs/sw.js` | New - minimal service worker for PWA install |
| `docs/index.html` | Add `<link rel="manifest">` + theme meta tags |
| `docs/app.js` | Handle `?url=` query param auto-fill on share |

---

### Source Expansion - "to-md" Bot Family

Same architecture (Worker + GitHub Actions + AI + private notes repo), different sources.

| Source | Input | Key dependency | Notes |
|--------|-------|---------------|-------|
| **YouTube → Notes** | Video URL | `youtube-transcript` Python lib or YouTube Data API | Transcript → clean structured notes, timestamps as headers |
| **Twitter/X Threads → Notes** | Thread URL | `tweepy` or `snscrape` | Whole thread → single note, quoted tweets handled |
| **Reddit Posts → Notes** | Post URL | `praw` (Reddit API) | OP + top comments → summarised note |
| **PDF/Article → Notes** | URL or file upload | `requests` + `pdfplumber` or `trafilatura` | Web article or PDF → extracted + summarised |

**Recommended start: YouTube → Notes**
- Most valuable for learning (lectures, tutorials, talks)
- `youtube-transcript` library works without OAuth for public videos
- Same OpenRouter text pipeline - no vision model needed (cheaper)
- Clean chapter/timestamp structure maps naturally to `###` headers

**Shared architecture across all sources:**
```
[Web form or share sheet]
        ↓
[Cloudflare Worker - same auth + rate limit]
        ↓
[GitHub Actions - source-specific fetcher + AI pipeline]
        ↓
[Private notes repo - same Obsidian frontmatter format]
```

Each new source = a new repo with its own `process.py` + workflow. Worker can stay shared or get a route per source.

---

## Parking Lot (possible later)

- Telegram bot notification on completion
- Per-tag note index (`_index.md`) auto-updated on each commit
- Content-type-aware formatting (recipe → ingredient table, workout → exercise table)

---

### Notion Image Storage — Fix Needed

**Problem:** `notion_push.py` uploads carousel slides directly to Notion via the file upload API (`v1/file_uploads`). These are the only permanent copy of the images — they are NOT saved to the GitHub notes repo (only `.md` files are committed there). At 10-15 posts/day with ~12 slides each (~100KB/image), this accumulates ~540MB/month of Notion storage. The free plan has no storage meter and an unclear total cap — likely becomes a problem within 2-3 months.

**Options to consider:**

| Option | What changes | Tradeoff |
|--------|-------------|----------|
| Commit images to notes repo alongside `.md`, use GitHub raw URLs in Notion image blocks | `process_post.yml` commits images, `notion_push.py` uses external URL blocks instead of uploads | Zero Notion storage. Images permanently owned. GitHub repo grows instead (~18MB/day). |
| Stop uploading images to Notion entirely | Remove image upload loop from `notion_push.py` | Simplest fix. Notion pages have text/summary only — no visual. |
| Periodic cleanup job | GitHub Action that deletes Notion image blocks older than N days | Keeps Notion clean but images are gone after N days. Complex to build. |

**Recommended:** Option 1 (commit to notes repo + external URLs). Images stay permanently accessible in the private repo, Notion pages still show the carousel visually, and Notion storage stays at zero.

**Files to change:** `scripts/notion_push.py`, `.github/workflows/process_post.yml`
