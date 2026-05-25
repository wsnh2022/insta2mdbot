import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
NOTION_TITLE_OVERRIDE = os.environ.get("NOTION_TITLE_OVERRIDE", "").strip()
METADATA_PATH = Path("/tmp/metadata.json")
IMAGES_DIR = Path("/tmp/insta_download")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


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
            "Summary": {"rich_text": [{"text": {"content": summary}}]},
        },
    }
    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def upload_image(image_path: Path) -> str:
    """Upload image to Notion file upload endpoint. Returns file upload ID."""
    create_resp = requests.post(
        "https://api.notion.com/v1/file_uploads",
        headers=HEADERS,
        json={"filename": image_path.name, "content_type": "image/jpeg"},
        timeout=30,
    )
    create_resp.raise_for_status()
    data = create_resp.json()
    upload_id = data["id"]
    upload_url = data["upload_url"]

    with open(image_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            files={"file": (image_path.name, f, "image/jpeg")},
            timeout=60,
        )
    upload_resp.raise_for_status()
    return upload_id


def append_image_block(page_id: str, upload_id: str):
    payload = {
        "children": [
            {
                "type": "image",
                "image": {
                    "type": "file_upload",
                    "file_upload": {"id": upload_id},
                },
            }
        ]
    }
    resp = requests.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


def append_footer(page_id: str, source_url: str, date_str: str):
    payload = {
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
    }
    resp = requests.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


def main():
    metadata = load_metadata()
    title = NOTION_TITLE_OVERRIDE or metadata.get("title", "Untitled")
    tags = metadata.get("tags", [])
    summary = metadata.get("summary", "")
    source_url = metadata.get("url", "")
    date_str = datetime.now().strftime("%Y-%m-%d")

    images = sorted(IMAGES_DIR.glob("*.jpg")) if IMAGES_DIR.exists() else []

    print(f"[1/3] Creating Notion page: {title}")
    page_id = create_page(title, tags, summary, source_url, date_str)
    print(f"      Page created: {page_id}")

    print(f"[2/3] Uploading {len(images)} image(s)...")
    for i, img_path in enumerate(images):
        try:
            upload_id = upload_image(img_path)
            append_image_block(page_id, upload_id)
            print(f"      [{i+1}/{len(images)}] {img_path.name} uploaded")
            if i < len(images) - 1:
                time.sleep(0.4)
        except Exception as e:
            print(f"      [{i+1}/{len(images)}] FAILED: {img_path.name} — {e}")

    print(f"[3/3] Appending footer...")
    try:
        append_footer(page_id, source_url, date_str)
    except Exception as e:
        print(f"      Footer failed (non-fatal): {e}")

    print(f"[DONE] https://notion.so/{page_id.replace('-', '')}")


if __name__ == "__main__":
    main()
