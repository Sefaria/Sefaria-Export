#!/usr/bin/env python3
"""
Download texts from Sefaria using books.json as an index.

Usage:
    # Download all Talmud texts as JSON
    python download_from_books_json.py --category Talmud

    # Download all English Mishnah texts
    python download_from_books_json.py --category Mishnah --language English

    # Download a specific title
    python download_from_books_json.py --title "Genesis"

    # Download all texts in TXT format
    python download_from_books_json.py --format txt

    # Just list what's available (no download)
    python download_from_books_json.py --category Tanakh --list
"""
import argparse
import json
import os
import requests

BOOKS_JSON_URL = "https://raw.githubusercontent.com/Sefaria/Sefaria-Export/master/books.json"


def fetch_books():
    print("Fetching books.json ...")
    resp = requests.get(BOOKS_JSON_URL)
    resp.raise_for_status()
    return resp.json()


def filter_books(books, category=None, title=None, language=None):
    results = books
    if category:
        results = [b for b in results if category in b.get("categories", [])]
    if title:
        results = [b for b in results if b["title"] == title]
    if language:
        results = [b for b in results if b["language"] == language]
    return results


def download_file(url, output_dir):
    # Derive local path from URL
    # URL: https://storage.googleapis.com/sefaria-export/json/Tanakh/Torah/Genesis/English/merged.json
    # Local: output_dir/Tanakh/Torah/Genesis/English/merged.json
    path_part = url.split("/sefaria-export/")[1]  # json/Tanakh/Torah/...
    parts = path_part.split("/", 1)                # skip format prefix
    if len(parts) < 2:
        return
    local_path = os.path.join(output_dir, parts[1])
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    resp = requests.get(url)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(resp.content)
    return local_path


def main():
    parser = argparse.ArgumentParser(description="Download Sefaria texts using books.json")
    parser.add_argument("--category", help="Filter by category (e.g., Talmud, Tanakh, Mishnah)")
    parser.add_argument("--title", help="Filter by exact title (e.g., Genesis)")
    parser.add_argument("--language", help="Filter by language (English, Hebrew)")
    parser.add_argument("--format", default="json", choices=["json", "txt", "cltk_full", "cltk_flat"],
                        help="Which format to download (default: json)")
    parser.add_argument("--output", default="./downloads", help="Output directory (default: ./downloads)")
    parser.add_argument("--list", action="store_true", help="Just list matching texts, don't download")
    args = parser.parse_args()

    data = fetch_books()
    books = filter_books(data["books"], args.category, args.title, args.language)

    if not books:
        print("No texts match your filters.")
        return

    url_key = args.format + "_url"

    if args.list:
        print(f"\n{len(books)} texts found:\n")
        for b in books:
            cats = " > ".join(b["categories"])
            print(f"  {b['title']:40s} {b['language']:8s} {cats}")
        return

    print(f"\nDownloading {len(books)} texts ({args.format} format) to {args.output}/ ...\n")
    downloaded = 0
    for b in books:
        url = b.get(url_key)
        if not url:
            continue
        path = download_file(url, args.output)
        if path:
            downloaded += 1
            print(f"  [{downloaded}/{len(books)}] {b['title']} ({b['language']})")

    print(f"\nDone. {downloaded} files saved to {args.output}/")


if __name__ == "__main__":
    main()
