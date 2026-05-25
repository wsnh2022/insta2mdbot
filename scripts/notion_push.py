import os
import sys
import json
import re
import time
import requests
from pathlib import Path
from datetime import datetime

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
NOTION_TITLE_OVERRIDE = os.environ.get("NOTION_TITLE_OVERRIDE", "").strip()
METADATA_PATH = Path("/tmp/metadata.json")
IMAGES_DIR = Path("/tmp/insta_download")
GITHUB_STEP_SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY", "")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

RETRY_DELAYS = [5, 15, 30]


def notion_post(url, **kwargs):
    for attempt, delay in enumerate(RETRY_DELAYS + [None]):
        resp = requests.post(url, headers=HEADERS, timeout=30, **kwargs)
        if resp.status_code == 429:
            if delay is not None:
                print(f"      Rate limited. Retrying in {delay}s... (attempt {attempt + 1}/{len(RETRY_DELAYS)})")
                time.sleep(delay)
                continue
            raise RuntimeError(f"Notion rate limit hit after {len(RETRY_DELAYS)} retries.")
        resp.raise_for_status()
        return resp
    raise RuntimeError("notion_post: exhausted retries")


def notion_patch(url, **kwargs):
    for attempt, delay in enumerate(RETRY_DELAYS + [None]):
        resp = requests.patch(url, headers=HEADERS, timeout=30, **kwargs)
        if resp.status_code == 429:
            if delay is not None:
                print(f"      Rate limited. Retrying in {delay}s... (attempt {attempt + 1}/{len(RETRY_DELAYS)})")
                time.sleep(delay)
                continue
            raise RuntimeError(f"Notion rate limit hit after {len(RETRY_DELAYS)} retries.")
        resp.raise_for_status()
        return resp
    raise RuntimeError("notion_patch: exhausted retries")


NOTION_LANGUAGES = {
    "python", "javascript", "typescript", "java", "c", "c++", "c#", "go", "rust",
    "bash", "shell", "sql", "html", "css", "json", "yaml", "markdown", "php",
    "ruby", "swift", "kotlin", "scala", "r", "matlab", "powershell", "docker",
    "graphql", "xml", "scss", "sass", "less",
}


def markdown_to_blocks(text: str) -> list:
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Fenced code block — collect until closing ```
        if line.startswith("```"):
            lang = line[3:].strip().lower() or "plain text"
            if lang not in NOTION_LANGUAGES:
                lang = "plain text"
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].rstrip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append({
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)[:2000]}}],
                    "language": lang,
                },
            })
            i += 1
            continue

        if not line or line.startswith("---"):
            i += 1
            continue

        # Strip bold/italic markers
        line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
        line = re.sub(r'\*(.+?)\*', r'\1', line)

        if line.startswith("### "):
            blocks.append({"type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]}})
        elif line.startswith("## "):
            blocks.append({"type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]}})
        elif re.match(r'^\d+\. ', line):
            blocks.append({"type": "numbered_list_item", "numbered_list_item": {"rich_text": [{"type": "text", "text": {"content": re.sub(r'^\d+\. ', '', line)}}]}})
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        else:
            blocks.append({"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:2000]}}]}})

        i += 1
    return blocks


def append_blocks_batched(page_id: str, blocks: list):
    for i in range(0, len(blocks), 100):
        notion_patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            json={"children": blocks[i:i+100]},
        )


def load_metadata():
    if not METADATA_PATH.exists():
        print("[SKIP] /tmp/metadata.json not found. Skipping Notion push.")
        sys.exit(0)
    with open(METADATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def create_page(title, tags, summary, source_url, date_str):
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            "Source": {"url": source_url or None},
            "Tags": {"multi_select": [{"name": t} for t in tags]},
            "Date": {"date": {"start": date_str}},
            "Summary": {"rich_text": [{"text": {"content": summary[:2000]}}]},
        },
    }
    resp = notion_post("https://api.notion.com/v1/pages", json=payload)
    return resp.json()["id"]


def upload_image(image_path: Path) -> str:
    create_resp = notion_post(
        "https://api.notion.com/v1/file_uploads",
        json={"filename": image_path.name, "content_type": "image/jpeg"},
    )
    data = create_resp.json()
    upload_id = data["id"]
    upload_url = data["upload_url"]

    for attempt, delay in enumerate(RETRY_DELAYS + [None]):
        with open(image_path, "rb") as f:
            upload_resp = requests.post(
                upload_url,
                headers={
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                },
                files={"file": (image_path.name, f, "image/jpeg")},
                timeout=60,
            )
        if upload_resp.status_code == 429:
            if delay is not None:
                print(f"      Rate limited on upload. Retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise RuntimeError("Upload rate limited after retries.")
        upload_resp.raise_for_status()
        break

    return upload_id


def append_image_block(page_id: str, upload_id: str):
    notion_patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        json={
            "children": [
                {
                    "type": "image",
                    "image": {"type": "file_upload", "file_upload": {"id": upload_id}},
                }
            ]
        },
    )


def append_footer(page_id: str, source_url: str, date_str: str):
    notion_patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        json={
            "children": [
                {"type": "divider", "divider": {}},
                {
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": f"Source: {source_url}  |  Processed: {date_str}"},
                            }
                        ]
                    },
                },
            ]
        },
    )


def write_summary(title, page_url, image_count):
    if not GITHUB_STEP_SUMMARY:
        return
    with open(GITHUB_STEP_SUMMARY, "a", encoding="utf-8") as f:
        f.write(f"### Notion push\n")
        f.write(f"- **Page:** [{title}]({page_url})\n")
        f.write(f"- **Images uploaded:** {image_count}\n")


def main():
    metadata = load_metadata()
    title = NOTION_TITLE_OVERRIDE or metadata.get("title", "Untitled")
    tags = metadata.get("tags", [])
    summary = metadata.get("summary", "")
    source_url = metadata.get("url", "")
    extracted = metadata.get("extracted", "")
    date_str = datetime.now().strftime("%Y-%m-%d")

    images = sorted(IMAGES_DIR.glob("*.jpg")) if IMAGES_DIR.exists() else []

    print(f"[1/4] Creating Notion page: {title}")
    page_id = create_page(title, tags, summary, source_url, date_str)
    print(f"      Page created: {page_id}")

    if extracted:
        print(f"[2/4] Appending extracted text...")
        try:
            blocks = markdown_to_blocks(extracted)
            blocks.append({"type": "divider", "divider": {}})
            append_blocks_batched(page_id, blocks)
            print(f"      {len(blocks) - 1} text blocks appended")
        except Exception as e:
            print(f"      Text blocks failed (non-fatal): {e}")

    print(f"[3/4] Uploading {len(images)} image(s)...")
    uploaded = 0
    for i, img_path in enumerate(images):
        try:
            upload_id = upload_image(img_path)
            append_image_block(page_id, upload_id)
            uploaded += 1
            print(f"      [{i+1}/{len(images)}] {img_path.name} uploaded")
            if i < len(images) - 1:
                time.sleep(0.7)
        except Exception as e:
            print(f"      [{i+1}/{len(images)}] FAILED: {img_path.name} — {e}")

    print(f"[4/4] Appending footer...")
    try:
        append_footer(page_id, source_url, date_str)
    except Exception as e:
        print(f"      Footer failed (non-fatal): {e}")

    page_url = f"https://notion.so/{page_id.replace('-', '')}"
    write_summary(title, page_url, uploaded)
    print(f"[DONE] {page_url}")


if __name__ == "__main__":
    main()
