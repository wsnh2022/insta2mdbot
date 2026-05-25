import os
import requests

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

payload = {
    "parent": {"database_id": NOTION_DATABASE_ID},
    "properties": {
        "Name": {"title": [{"text": {"content": "Connection Test - Safe to Delete"}}]},
    },
}

response = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
print(response.status_code, response.json().get("url", response.text))
