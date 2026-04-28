# instatomdnotes

Convert Instagram carousels into clean, structured Markdown notes — automatically.

**Live app:** https://wsnh2022.github.io/insta2mdbot/

---

## What it does

Paste an Instagram post URL → the app downloads every slide of the carousel, extracts all meaningful text using a vision AI model, and saves a formatted `.md` note to a private GitHub repository. Takes about 2 minutes per post.

**Output example:**

```
# Eight Rules for Mastering Self-Discipline

**Source:** https://www.instagram.com/p/DXaZDwgDJ6I
**Tags:** #self-discipline #productivity #mindset
**Date:** 2026-04-28

---

### Rule #1: Understand Your Why
Self-discipline starts with clarity...

### Rule #2: Train Your Mind to Delay Gratification
...
```

---

## How it works

```
GitHub Pages form
      ↓  POST (passphrase protected)
Cloudflare Worker
      ↓  triggers via GitHub API
GitHub Actions (ubuntu runner)
      ↓  downloads carousel with instaloader
      ↓  resizes images to 768px
      ↓  extracts text via OpenRouter vision model
      ↓  generates title + tags via second AI call
      ↓  builds .md note
Private GitHub repo (insta2mdbot-notes)
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | GitHub Pages — vanilla HTML/CSS/JS |
| API gateway | Cloudflare Worker |
| Backend | GitHub Actions + Python 3.11 |
| Image download | instaloader 4.15.1 |
| AI extraction | OpenRouter (Gemini 2.0 Flash Lite, Llama 3.2 11B fallback) |
| Note storage | Private GitHub repo |

---

## Security

- **Passphrase protected** — the form requires a secret passphrase; the Cloudflare Worker rejects all requests without it
- **Rate limited** — max 10 requests per minute on the Worker
- **Notes are private** — generated notes are committed to a separate private repository, not this one
- **Secrets never in code** — GitHub PAT stored as Cloudflare Worker secret, OpenRouter key stored as GitHub Actions secret

---

## Repository structure

```
insta2mdbot/
├── docs/               # GitHub Pages frontend
│   ├── index.html      # Form UI
│   ├── app.js          # Submits URL + passphrase to Worker
│   └── style.css       # Styling
├── worker/
│   ├── index.js        # Cloudflare Worker — auth, rate limit, triggers Actions
│   └── wrangler.toml   # Worker config
├── scripts/
│   └── process.py      # Downloads carousel, resizes, extracts, builds note
├── .github/workflows/
│   └── process_post.yml  # GitHub Actions workflow
└── requirements.txt    # Python dependencies
```

---

## Setup (self-hosting)

### Prerequisites
- Cloudflare account (free tier)
- GitHub account
- OpenRouter API key
- GitHub PAT with `repo` + `workflow` scopes

### Steps

1. **Fork this repo** and enable GitHub Pages from the `docs/` folder

2. **Create a private notes repo** (e.g. `insta2mdbot-notes`) with a README

3. **Add GitHub Actions secrets** to this repo:
   - `OPENROUTER_API_KEY` — your OpenRouter key
   - `NOTES_REPO_PAT` — your GitHub PAT

4. **Deploy the Cloudflare Worker:**
   ```powershell
   $env:CLOUDFLARE_API_TOKEN = "your-cloudflare-token"
   cd worker
   npx wrangler deploy
   npx wrangler secret put GITHUB_PAT   # paste your GitHub PAT
   npx wrangler secret put ACCESS_KEY   # choose a passphrase for the form
   ```

5. **Update `docs/app.js` line 1** with your deployed Worker URL

6. Commit and push — done

---

## Dependencies

```
instaloader==4.15.1
requests==2.31.0
Pillow==10.4.0
```
