# instatomdnotes — Feature Roadmap

7 features implemented iteratively, 2 per day over 4 days.
Each pair is chosen to touch the same layer of the stack so changes stay cohesive.

---

## Day 1 — Note Foundation
*Both features touch only `scripts/process.py` — zero infra changes.*

- [x] **Obsidian-Compatible Frontmatter** — Replace ad-hoc header block with proper YAML frontmatter so notes work natively in Obsidian (dataview, graph view, tag autocomplete).
- [x] **Duplicate Detection** — Track processed shortcodes in `notes/_processed.txt`. Skip re-processing if already done — saves AI credits and prevents duplicate commits.

---

## Day 2 — Note Enrichment
*Both features extend the AI pipeline and note content in `scripts/process.py`.*

- [ ] **AI-Generated TLDR / Summary** — Third OpenRouter call generates a 2-3 sentence summary, inserted as an Obsidian callout (`> [!summary]`) right after frontmatter.
- [ ] **Auto-Folder by Topic** — Notes routed into subfolders by primary tag (e.g. `notes/productivity/`, `notes/fitness/`) instead of all flat.

---

## Day 3 — Infrastructure
*Session reliability (Python + workflow) and processing feedback (Worker + frontend).*

- [ ] **Instaloader Session Login** — Use saved Instagram `sessionid` cookie (stored as GitHub secret) to reduce anonymous IP blocks significantly.
- [ ] **Status Polling Endpoint** — New GET `/status` route on the Worker queries GitHub Actions API for latest run status. Frontend polls every 10s and updates the UI from "Processing..." → "Done! Note saved."

---

## Day 4 — Power User
*Frontend + Worker changes. Session login should be stable before this.*

- [ ] **Batch URL Submission** — Textarea replaces single URL input. Submit up to 10 URLs at once; frontend dispatches them sequentially with 6s delays to stay under the rate limit.

---

## Feature Summary

| Feature | File(s) | Status |
|---------|---------|--------|
| Obsidian Frontmatter | `scripts/process.py` | Done |
| Duplicate Detection | `scripts/process.py` | Done |
| TLDR Summary | `scripts/process.py` | Pending |
| Auto-Folder | `scripts/process.py` | Pending |
| Session Login | `scripts/process.py`, `process_post.yml` | Pending |
| Status Polling | `worker/index.js`, `docs/app.js` | Pending |
| Batch Submission | `docs/index.html`, `docs/app.js` | Pending |
