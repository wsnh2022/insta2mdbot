import os
import sys
import re
import time
import base64
import json
import urllib.request
import requests
import instaloader
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from PIL import Image

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
INSTAGRAM_URL = os.environ.get("INSTAGRAM_URL", "")
MODE = os.environ.get("MODE", "instagram").strip().lower()
CONTENT = os.environ.get("CONTENT", "")
NOTES_DIR = Path("notes")
EXTRACT_TEXT = os.environ.get("EXTRACT_TEXT", "true").strip().lower() != "false"
PRIMARY_MODEL = "google/gemini-2.5-flash-lite"
FALLBACK_MODEL = "qwen/qwen3.5-9b"
FALLBACK_MODEL_2 = "nvidia/nemotron-nano-12b-v1"
MODELS = [PRIMARY_MODEL, FALLBACK_MODEL, FALLBACK_MODEL_2]
CHAIN_RETRY_DELAYS = [60, 180]
OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/instatomdnotes",
}

EXTRACTION_PROMPT = """You are extracting content from an Instagram carousel.

Rules:
- Extract ALL meaningful text verbatim from each slide
- Format named sections with a descriptive title (e.g. "Rule #1: Understand Your Why", "Step 1: Do X") as ### markdown headers including the title
- For numbered tips or points that have NO descriptive title (just a number + body text), format as a plain numbered markdown list (1. 2. 3.) — do NOT create ### headers for bare numbers
- For any slide with multiple columns of items arranged side by side (e.g. BASIC/ADVANCED, WRONG/RIGHT, BEFORE/AFTER, OLD/NEW, DO/DON'T): these items are PAIRED by row position — item 1 in the left column pairs with item 1 in the right column, item 2 pairs with item 2, and so on. You MUST reconstruct this as a Markdown table. Use the column headers as table headers. Read ACROSS each row, not down each column. NEVER output the columns as two separate lists — that destroys the pairing and is always wrong for this layout type
- Remove decorative icon artifacts that appear before list or table items — these include numbered circles like (1) (2), single symbols like ! ? → ✓ ✗, and any emoji used purely as visual decoration
- Remove EVERYTHING promotional: @handles, slide counters like (01/09), "Presented by", "Follow for more", "Save this", (save for later), calls to action, branding watermarks
- Remove repetitive recap slides that only restate what was already covered
- If a slide has no meaningful text (pure graphic/image), output nothing for it
- If a slide contains code (any programming language, terminal commands, config snippets), wrap it in a fenced code block with the correct language tag (e.g. ```python, ```bash, ```sql). Preserve indentation exactly.
- Do NOT summarize. Extract and clean only.
- Output plain markdown only — no commentary, no preamble"""

METADATA_PROMPT = """Given this content, return a JSON object with exactly two keys:
- "title": a concise 5-8 word title describing the core topic (title case, no hashtags)
- "tags": an array of 3-5 relevant lowercase topic tags without the # symbol

Return only valid JSON. No explanation, no markdown code block.

Content:
{content}"""

SUMMARY_PROMPT = """Summarise the following content in 2-3 plain sentences. \
Capture the core idea and single most useful takeaway. No bullet points, no formatting — plain prose only.

Content:
{content}"""


IMAGE_ONLY_PROMPT = """Look at these carousel slides and return a JSON object with exactly three keys:
- "title": a concise 5-8 word title describing the core topic (title case, no hashtags)
- "tags": an array of 3-5 relevant lowercase topic tags without the # symbol
- "summary": a 2-3 sentence plain prose summary of the core idea and most useful takeaway

Return only valid JSON. No explanation, no markdown code block."""


def _repair_and_parse_json(raw: str) -> dict:
    """Try progressively more aggressive repairs before giving up."""
    start = raw.find('{')
    end = raw.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    chunk = raw[start:end + 1]
    # Fix trailing commas
    clean = re.sub(r',(\s*[}\]])', r'\1', chunk)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # Regex field extraction as last resort
    result = {}
    title_m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', clean)
    tags_m = re.search(r'"tags"\s*:\s*\[([^\]]+)\]', clean)
    summary_m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', clean)
    if title_m:
        result["title"] = title_m.group(1)
    if tags_m:
        try:
            result["tags"] = json.loads(f"[{tags_m.group(1)}]")
        except Exception:
            result["tags"] = [t.strip().strip('"') for t in tags_m.group(1).split(',')]
    if summary_m:
        result["summary"] = summary_m.group(1)
    if result:
        return result
    raise ValueError("Could not extract any fields from response")


def get_metadata_and_summary_from_images(images: list[Path]) -> dict:
    """Single vision AI call across fallback models: returns title, tags, and summary from images."""
    content = []
    for img_path in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encode_image(img_path)}"}
        })
    content.append({"type": "text", "text": IMAGE_ONLY_PROMPT})
    for model in MODELS:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 1200,
        }
        # Disable built-in reasoning/thinking to avoid wasting token budget on thinking output
        if any(x in model for x in ("qwen", "deepseek")):
            body["reasoning"] = {"exclude": True}
        retry_delays = [10, 30]
        for _, delay in enumerate(retry_delays + [None]):
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=OPENROUTER_HEADERS, json=body, timeout=60,
                )
                if resp.status_code == 429:
                    if delay is not None:
                        print(f"      {model} rate limited. Retrying in {delay}s...")
                        time.sleep(delay)
                        continue
                    print(f"      {model} rate limited after retries. Trying next model...")
                    break
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    print(f"      {model} error: {data['error'].get('message', data['error'])}. Trying next model...")
                    break
                raw = data["choices"][0]["message"].get("content") or ""
                if not raw.strip():
                    print(f"      {model} returned empty content. Trying next model...")
                    break
                try:
                    result = _repair_and_parse_json(raw.strip())
                    print(f"      {model} succeeded.")
                    return result
                except Exception as err:
                    print(f"      {model} failed: {err}. Trying next model...")
                    break
            except Exception as err:
                print(f"      {model} failed: {err}. Trying next model...")
                break
    raise RuntimeError("All models failed for image metadata extraction.")


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
    session_id = os.environ.get("INSTAGRAM_SESSION_ID", "")
    if session_id:
        loader.context._session.cookies.set(
            "sessionid", session_id, domain=".instagram.com"
        )
    shortcode = url.rstrip("/").split("/")[-1]
    post = instaloader.Post.from_shortcode(loader.context, shortcode)

    tmp_dir.mkdir(parents=True, exist_ok=True)

    if post.typename == "GraphSidecar":
        count = 0
        for node in post.get_sidecar_nodes():
            if not node.is_video:
                loader.download_pic(
                    filename=str(tmp_dir / f"slide_{count:02d}"),
                    url=node.display_url,
                    mtime=post.date_local,
                )
                count += 1
    else:
        loader.download_pic(
            filename=str(tmp_dir / "slide_00"),
            url=post.url,
            mtime=post.date_local,
        )

    return sorted(tmp_dir.glob("*.jpg"))


def resize_image(path: Path, max_px: int = 768) -> Path:
    resized_dir = Path("/tmp/insta_resized")
    resized_dir.mkdir(exist_ok=True)
    out = resized_dir / path.name
    img = Image.open(path)
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    img.save(out, "JPEG", quality=85)
    return out


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_image_content(images: list[Path]) -> list:
    """Encode all images to base64 once. Returns the OpenRouter content list."""
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image(p)}"}}
        for p in images
    ]
    return content


def call_openrouter(encoded_content: list, model: str) -> str:
    """Send pre-encoded image content to OpenRouter. Returns extracted text."""
    content = encoded_content + [{"type": "text", "text": EXTRACTION_PROMPT}]

    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4096,
    }
    if any(x in model for x in ("qwen", "deepseek")):
        body["reasoning"] = {"exclude": True}

    retry_delays = [10, 30, 60]
    for _, delay in enumerate(retry_delays + [None]):
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=OPENROUTER_HEADERS,
            json=body,
            timeout=60,
        )

        if resp.status_code == 401:
            raise RuntimeError("OpenRouter API key invalid or missing.")

        if resp.status_code == 429:
            if delay is not None:
                print(f"      Rate limited (429). Retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise RuntimeError(f"Rate limited after {len(retry_delays)} retries.")

        resp.raise_for_status()

        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"OpenRouter error: {data['error'].get('message', data['error'])}")

        raw = data["choices"][0]["message"].get("content") or ""
        if not raw.strip():
            raise RuntimeError(f"{model} returned empty content.")
        return raw


def _text_call(prompt: str, max_tokens: int) -> str:
    """Single OpenRouter text call with fallback models. Returns raw response string."""
    for model in MODELS:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if any(x in model for x in ("qwen", "deepseek")):
            body["reasoning"] = {"exclude": True}
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=OPENROUTER_HEADERS,
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data['error'].get('message', data['error']))
            raw = data["choices"][0]["message"].get("content") or ""
            if not raw.strip():
                raise RuntimeError("empty content")
            return raw.strip()
        except Exception as err:
            print(f"      {model} failed: {err}. Trying next model...")
    raise RuntimeError("All models failed.")


def get_metadata(content: str) -> dict:
    raw = _text_call(METADATA_PROMPT.format(content=content[:3000]), max_tokens=200)
    return _repair_and_parse_json(raw)


def get_summary(content: str) -> str:
    return _text_call(SUMMARY_PROMPT.format(content=content[:3000]), max_tokens=150)


def title_to_filename(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug if slug else "untitled"


def build_markdown(url: str, extracted: str, title: str, tags: list, summary: str = "") -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    source_line = f'\nsource: "{url}"' if url else ""
    frontmatter = f'---\ntitle: "{title}"{source_line}\ntags:\n{tag_lines}\ndate: {date_str}\n---'
    summary_block = f"\n> [!summary]\n> {summary}\n" if summary else ""
    return f"{frontmatter}{summary_block}\n{extracted.strip()}\n"


def process_instagram():
    tmp_dir = Path("/tmp/insta_download")
    shortcode = INSTAGRAM_URL.rstrip("/").split("/")[-1]
    processed_log = NOTES_DIR / "_processed.txt"

    if not EXTRACT_TEXT:
        if processed_log.exists() and shortcode in processed_log.read_text(encoding="utf-8").splitlines():
            Path("/tmp/is_duplicate").write_text("1", encoding="utf-8")
            print(f"[SKIP] Already processed: {shortcode}")
            sys.exit(0)
        print(f"[MODE] images only — skipping text extraction")
        print(f"[1/3] Downloading: {INSTAGRAM_URL}")
        try:
            images = download_carousel(INSTAGRAM_URL, tmp_dir)
        except Exception as e:
            print(f"[ERROR] Download failed: {e}")
            sys.exit(1)
        images = [resize_image(p) for p in images]
        print(f"      Found {len(images)} image(s), resized to max 768px")
        if not images:
            print("[ERROR] No images found. Exiting.")
            sys.exit(1)
        print(f"[2/3] Getting title, tags and summary from images (1 AI call)...")
        title, tags, summary = shortcode, [], ""
        try:
            result = get_metadata_and_summary_from_images(images)
            title = result.get("title", shortcode)
            tags = result.get("tags", [])
            summary = result.get("summary", "")
            print(f"      Done: {title}")
        except Exception as e:
            print(f"      AI call failed: {e} — using shortcode as title")
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        with open(processed_log, "a", encoding="utf-8") as f:
            f.write(shortcode + "\n")
        print(f"[3/3] Writing metadata for Notion...")
        Path("/tmp/metadata.json").write_text(
            json.dumps({"mode": "instagram", "title": title, "tags": tags, "summary": summary, "url": INSTAGRAM_URL, "extracted": ""}),
            encoding="utf-8",
        )
        return

    if processed_log.exists():
        if shortcode in processed_log.read_text(encoding="utf-8").splitlines():
            Path("/tmp/is_duplicate").write_text("1", encoding="utf-8")
            print(f"[NOTION] Already processed: {shortcode} — re-downloading for Notion push only")
            try:
                images = download_carousel(INSTAGRAM_URL, tmp_dir)
                images = [resize_image(p) for p in images]
                print(f"      Found {len(images)} image(s), resized to max 768px")
            except Exception as e:
                print(f"      Re-download failed: {e} — skipping Notion push")
                sys.exit(0)
            existing_md = None
            for md_path in NOTES_DIR.glob("**/*.md"):
                text = md_path.read_text(encoding="utf-8")
                if shortcode in text or INSTAGRAM_URL in text:
                    existing_md = text
                    break
            title, tags, summary, extracted = shortcode, [], "", ""
            if existing_md:
                existing_md = existing_md.replace('\r\n', '\n')
                parts = existing_md.split("---", 2)
                if len(parts) >= 3:
                    fm = parts[1]
                    tm = re.search(r'title:\s*"?(.+?)"?\s*$', fm, re.MULTILINE)
                    title = tm.group(1).strip('"') if tm else shortcode
                    tags = re.findall(r'^\s+- (.+)$', fm, re.MULTILINE)
                    body = parts[2].strip()
                    sm = re.search(r'>\s*\[!summary\]\n((?:>.*\n?)+)', body)
                    if sm:
                        summary = " ".join(re.findall(r'^>\s*(.+)$', sm.group(1), re.MULTILINE)).strip()
                    extracted = re.sub(r'>\s*\[!summary\]\n(?:>.*\n?)+', '', body).strip()
            Path("/tmp/metadata.json").write_text(
                json.dumps({"mode": "instagram", "title": title, "tags": tags, "summary": summary, "url": INSTAGRAM_URL, "extracted": extracted}),
                encoding="utf-8",
            )
            sys.exit(0)

    print(f"[1/5] Downloading: {INSTAGRAM_URL}")
    try:
        images = download_carousel(INSTAGRAM_URL, tmp_dir)
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        sys.exit(1)
    print(f"      Found {len(images)} image(s)")
    images = [resize_image(p) for p in images]
    print(f"      Resized to max 768px")

    if not images:
        print("[ERROR] No images found. Exiting.")
        sys.exit(1)

    print(f"[2/5] Extracting text via {PRIMARY_MODEL}...")
    encoded_content = build_image_content(images)
    extracted = None
    for attempt, delay in enumerate([None] + CHAIN_RETRY_DELAYS):
        if delay is not None:
            print(f"      All models failed. Retrying full chain in {delay}s... (attempt {attempt}/{len(CHAIN_RETRY_DELAYS)})")
            time.sleep(delay)
        for model in MODELS:
            try:
                extracted = call_openrouter(encoded_content, model)
                print(f"      {model} succeeded.")
                break
            except Exception as err:
                print(f"      {model} failed: {err}")
                if model != MODELS[-1]:
                    print(f"      Trying next model...")
        if extracted is not None:
            break

    if extracted is None:
        print("[ERROR] All models failed after all retries. Exiting.")
        sys.exit(1)

    extracted = re.sub(r'\[image-only slide\]\s*\n?', '', extracted).strip()

    print(f"[3/5] Getting title, tags and summary...")
    try:
        metadata = get_metadata(extracted)
        title = metadata.get("title", shortcode)
        tags = metadata.get("tags", ["instagram", "notes"])
    except Exception as e:
        print(f"      Metadata call failed: {e} — using defaults")
        title = shortcode
        tags = ["instagram", "notes"]

    summary = ""
    try:
        summary = get_summary(extracted)
        print(f"      Summary generated.")
    except Exception as e:
        print(f"      Summary call failed: {e} — skipping")

    print("[4/5] Building markdown note...")
    note_md = build_markdown(INSTAGRAM_URL, extracted, title, tags, summary)

    folder = title_to_filename(tags[0]) if tags else "misc"
    note_path = NOTES_DIR / folder / f"{title_to_filename(title)}.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(note_md, encoding="utf-8")
    with open(processed_log, "a", encoding="utf-8") as f:
        f.write(shortcode + "\n")
    print(f"[5/5] Saved: {note_path}")

    Path("/tmp/metadata.json").write_text(
        json.dumps({"mode": "instagram", "title": title, "tags": tags, "summary": summary, "url": INSTAGRAM_URL, "extracted": extracted}),
        encoding="utf-8",
    )


def extract_urls_from_text(text: str) -> list[str]:
    found = re.findall(r'https?://[^\s\)"\'<>]+', text)
    seen = set()
    result = []
    for u in found:
        u = u.rstrip('.,;:!?')
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def fetch_title(url: str) -> str:
    """Fetch the <title> tag from a URL. Falls back to the raw URL on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read(8192).decode("utf-8", errors="ignore")
        m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        return m.group(1).strip() if m else url
    except Exception:
        return url


def process_urls():
    lines = [l.strip() for l in CONTENT.splitlines() if l.strip()]
    urls = [l for l in lines if re.match(r'^https?://', l)]
    if not urls:
        print("[SKIP] No valid URLs found in content.")
        sys.exit(0)
    date_str = datetime.now().strftime("%Y-%m-%d")
    pending_path = NOTES_DIR / "pending-to-read.md"
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    new_items = "\n".join(f"- [{date_str}] {u}" for u in urls)
    if pending_path.exists():
        existing = pending_path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        pending_path.write_text(existing + new_items + "\n", encoding="utf-8")
    else:
        pending_path.write_text("# Pending to Read\n\n" + new_items + "\n", encoding="utf-8")
    print(f"[DONE] Appended {len(urls)} URL(s) to {pending_path}")
    print(f"      Fetching page titles for Notion...")
    url_entries = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fetch_title, u): i for i, u in enumerate(urls)}
        for future in as_completed(futures):
            i = futures[future]
            url_entries[i] = {"url": urls[i], "title": future.result()}
    Path("/tmp/metadata.json").write_text(
        json.dumps({"mode": "urls", "urls": url_entries}),
        encoding="utf-8",
    )


def process_text():
    if not CONTENT.strip():
        print("[ERROR] CONTENT is empty for mode=text.")
        sys.exit(1)
    print("[1/4] Extracting embedded URLs from content...")
    embedded_urls = extract_urls_from_text(CONTENT)
    print(f"      Found {len(embedded_urls)} embedded URL(s)")
    print("[2/4] Getting title, tags and summary via AI...")
    title = "Untitled Note"
    tags = ["notes"]
    try:
        metadata = get_metadata(CONTENT)
        title = metadata.get("title", "Untitled Note")
        tags = metadata.get("tags", ["notes"])
    except Exception as e:
        print(f"      Metadata call failed: {e} — using defaults")
    summary = ""
    try:
        summary = get_summary(CONTENT)
        print("      Summary generated.")
    except Exception as e:
        print(f"      Summary call failed: {e} — skipping")
    print("[3/4] Building markdown note...")
    further_reading = ""
    if embedded_urls:
        links = "\n".join(f"- {u}" for u in embedded_urls)
        further_reading = f"\n\n## Further Reading\n\n{links}\n"
    note_body = CONTENT.strip() + further_reading
    note_md = build_markdown("", note_body, title, tags, summary)
    folder = title_to_filename(tags[0]) if tags else "misc"
    note_path = NOTES_DIR / folder / f"{title_to_filename(title)}.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(note_md, encoding="utf-8")
    print(f"[4/4] Saved: {note_path}")
    Path("/tmp/metadata.json").write_text(
        json.dumps({"mode": "text", "title": title, "tags": tags, "summary": summary, "extracted": note_body}),
        encoding="utf-8",
    )


def main():
    if MODE == "urls":
        print("[MODE] urls — appending to reading list")
        process_urls()
    elif MODE == "text":
        print("[MODE] text — generating AI note from raw content")
        process_text()
    else:
        if not INSTAGRAM_URL:
            print("[ERROR] MODE=instagram but INSTAGRAM_URL is not set.")
            sys.exit(1)
        print(f"[MODE] instagram — processing carousel: {INSTAGRAM_URL}")
        process_instagram()


if __name__ == "__main__":
    main()
