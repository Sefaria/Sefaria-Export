#!/usr/bin/env python3
"""
Generates books.json by listing the public GCS bucket.
Uses the unauthenticated GCS JSON API — no credentials needed.

Run manually:  python scripts/generate_books_json.py
Run via CI:    GitHub Action triggers monthly after GCS export completes.
"""
import json
import os
import requests
from collections import defaultdict
from datetime import datetime, timezone

BUCKET = os.environ.get("BUCKET", "sefaria-export")
FORMATS = {"json", "txt", "cltk-full", "cltk-flat"}
GCS_API = "https://storage.googleapis.com/storage/v1/b/{bucket}/o"
GCS_PUBLIC = "https://storage.googleapis.com/{bucket}/{name}"


def list_bucket_objects(bucket, prefix=""):
    """List all objects in a public GCS bucket (no auth needed)."""
    url = GCS_API.format(bucket=bucket)
    objects = []
    page_token = None

    while True:
        params = {"maxResults": 1000}
        if prefix:
            params["prefix"] = prefix
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        objects.extend(data.get("items", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return objects


def parse_text_path(rel_path):
    """Parse: {format}/{cat1}/{cat2}/.../{title}/{language}/{version}.{ext}"""
    parts = rel_path.split("/")
    if len(parts) < 4:
        return None
    fmt = parts[0]
    if fmt not in FORMATS:
        return None
    return {
        "format": fmt,
        "categories": parts[1:-3],
        "title": parts[-3],
        "language": parts[-2],
        "version": parts[-1].rsplit(".", 1)[0] if "." in parts[-1] else parts[-1],
    }


def main():
    print(f"Listing gs://{BUCKET}/ ...")
    objects = list_bucket_objects(BUCKET)
    print(f"Found {len(objects)} objects")

    # Group by (title, language, version, categories) -> format URLs
    texts = defaultdict(lambda: {"formats": {}})
    special = []

    for obj in objects:
        name = obj.get("name", "")
        if name.endswith("/"):
            continue

        rel = name
        url = GCS_PUBLIC.format(bucket=BUCKET, name=name)
        size = int(obj.get("size", 0))

        parsed = parse_text_path(rel)
        if parsed and parsed["categories"]:
            key = (parsed["title"], parsed["language"], parsed["version"], tuple(parsed["categories"]))
            texts[key]["formats"][parsed["format"]] = url
            texts[key]["size"] = texts[key].get("size", 0) + size
        else:
            special.append({"path": rel, "url": url, "size": size})

    # Build flat books array
    books = []
    for (title, language, version, categories), data in sorted(texts.items()):
        entry = {
            "title": title,
            "language": language,
            "versionTitle": version,
            "categories": list(categories),
        }
        for fmt in ["json", "txt", "cltk-full", "cltk-flat"]:
            if fmt in data["formats"]:
                entry[fmt.replace("-", "_") + "_url"] = data["formats"][fmt]
        books.append(entry)

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket": f"gs://{BUCKET}",
        "base_url": f"https://storage.googleapis.com/{BUCKET}",
        "total_texts": len(books),
        "special_files": special,
        "books": books,
    }

    with open("books.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=1, ensure_ascii=False)

    print(f"Wrote books.json: {len(books)} texts, {len(special)} special files")


if __name__ == "__main__":
    main()
