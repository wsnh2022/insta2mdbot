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
