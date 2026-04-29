import os
import sys
import re
import time
import base64
import json
import requests
import instaloader
from pathlib import Path
from datetime import datetime
from PIL import Image

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
INSTAGRAM_URL = os.environ["INSTAGRAM_URL"]
NOTES_DIR = Path("notes")
PRIMARY_MODEL = "google/gemini-2.5-flash-lite"
FALLBACK_MODEL = "qwen/qwen3.5-9b"
FALLBACK_MODEL_2 = "nvidia/nemotron-nano-12b-v1"
MODELS = [PRIMARY_MODEL, FALLBACK_MODEL, FALLBACK_MODEL_2]
CHAIN_RETRY_DELAYS = [60, 180]

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
- Do NOT summarize. Extract and clean only.
- Output plain markdown only — no commentary, no preamble"""

METADATA_PROMPT = """Given this extracted Instagram carousel content, return a JSON object with exactly two keys:
- "title": a concise 5-8 word title describing the core topic (title case, no hashtags)
- "tags": an array of 3-5 relevant lowercase topic hashtags without the # symbol

Return only valid JSON. No explanation, no markdown code block.

Content:
{content}"""

SUMMARY_PROMPT = """Summarise this Instagram carousel content in 2-3 plain sentences. \
Capture the core idea and single most useful takeaway. No bullet points, no formatting — plain prose only.

Content:
{content}"""


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
    img = Image.open(path)
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    img.save(path, "JPEG", quality=85)
    return path


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

    retry_delays = [10, 30, 60]
    for attempt, delay in enumerate(retry_delays + [None]):
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=60,
        )

        if resp.status_code == 401:
            raise RuntimeError("OpenRouter API key invalid or missing.")

        if resp.status_code == 429:
            if delay is not None:
                print(f"      Rate limited (429). Retrying in {delay}s... (attempt {attempt + 1}/{len(retry_delays)})")
                time.sleep(delay)
                continue
            raise RuntimeError(f"Rate limited after {len(retry_delays)} retries.")

        resp.raise_for_status()

        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"OpenRouter error: {data['error'].get('message', data['error'])}")

        return data["choices"][0]["message"]["content"]


def get_metadata(content: str) -> dict:
    prompt = METADATA_PROMPT.format(content=content[:3000])
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/instatomdnotes",
    }
    body = {
        "model": PRIMARY_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
    }
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"OpenRouter error: {data['error'].get('message', data['error'])}")
    raw = data["choices"][0]["message"]["content"].strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def get_summary(content: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/instatomdnotes",
    }
    body = {
        "model": PRIMARY_MODEL,
        "messages": [{"role": "user", "content": SUMMARY_PROMPT.format(content=content[:3000])}],
        "max_tokens": 150,
    }
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"OpenRouter error: {data['error'].get('message', data['error'])}")
    return data["choices"][0]["message"]["content"].strip()


def title_to_filename(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    return re.sub(r'-+', '-', slug).strip('-')


def build_markdown(url: str, extracted: str, title: str, tags: list, summary: str = "") -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    frontmatter = f'---\ntitle: "{title}"\nsource: "{url}"\ntags:\n{tag_lines}\ndate: {date_str}\n---'
    summary_block = f"\n> [!summary]\n> {summary}\n" if summary else ""
    return f"{frontmatter}{summary_block}\n{extracted.strip()}\n"


def main():
    tmp_dir = Path("/tmp/insta_download")
    shortcode = INSTAGRAM_URL.rstrip("/").split("/")[-1]
    processed_log = NOTES_DIR / "_processed.txt"

    if processed_log.exists():
        if shortcode in processed_log.read_text(encoding="utf-8").splitlines():
            print(f"[SKIP] Already processed: {shortcode}")
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
    extracted = None
    for attempt, delay in enumerate([None] + CHAIN_RETRY_DELAYS):
        if delay is not None:
            print(f"      All models failed. Retrying full chain in {delay}s... (attempt {attempt}/{len(CHAIN_RETRY_DELAYS)})")
            time.sleep(delay)
        for model in MODELS:
            try:
                extracted = call_openrouter(images, model)
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


if __name__ == "__main__":
    main()
