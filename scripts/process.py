import os
import sys
import re
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
PRIMARY_MODEL = "google/gemini-2.0-flash-lite-001"
FALLBACK_MODEL = "meta-llama/llama-3.2-11b-vision-instruct"

EXTRACTION_PROMPT = """You are extracting content from an Instagram carousel.

Rules:
- Extract ALL meaningful text verbatim from each slide
- Format named sections (e.g. "Rule #1", "Step 1", "Tip 1") as ### markdown headers
- Remove EVERYTHING promotional: @handles, slide counters like (01/09), "Presented by", "Follow for more", "Save this", calls to action, branding watermarks
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

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=body,
        timeout=60,
    )

    if resp.status_code == 401:
        raise RuntimeError("OpenRouter API key invalid or missing.")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


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
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def build_markdown(url: str, extracted: str, title: str, tags: list) -> str:
    shortcode = url.rstrip("/").split("/")[-1]
    date_str = datetime.now().strftime("%Y-%m-%d")
    tag_str = " ".join(f"#{t}" for t in tags)
    return f"""# {title}

**Source:** {url}
**Date:** {date_str}

---

{extracted.strip()}

---

**Tags:** {tag_str}
**Search Terms:** {shortcode}
"""


def main():
    tmp_dir = Path("/tmp/insta_download")
    shortcode = INSTAGRAM_URL.rstrip("/").split("/")[-1]

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
    try:
        extracted = call_openrouter(images, PRIMARY_MODEL)
        print("      Primary model succeeded.")
    except Exception as primary_err:
        print(f"      Primary model failed: {primary_err}")
        print(f"[2/5] Falling back to {FALLBACK_MODEL}...")
        try:
            extracted = call_openrouter(images, FALLBACK_MODEL)
            print("      Fallback model succeeded.")
        except Exception as fallback_err:
            print(f"[ERROR] Fallback model also failed: {fallback_err}")
            sys.exit(1)

    extracted = re.sub(r'\[image-only slide\]\s*\n?', '', extracted).strip()

    print(f"[3/5] Getting title and tags...")
    try:
        metadata = get_metadata(extracted)
        title = metadata.get("title", shortcode)
        tags = metadata.get("tags", ["instagram", "notes"])
    except Exception as e:
        print(f"      Metadata call failed: {e} — using defaults")
        title = shortcode
        tags = ["instagram", "notes"]

    print("[4/5] Building markdown note...")
    note_md = build_markdown(INSTAGRAM_URL, extracted, title, tags)

    note_path = NOTES_DIR / f"{shortcode}.md"
    NOTES_DIR.mkdir(exist_ok=True)
    note_path.write_text(note_md, encoding="utf-8")
    print(f"[5/5] Saved: {note_path}")


if __name__ == "__main__":
    main()
