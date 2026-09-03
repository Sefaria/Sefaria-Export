#!/usr/bin/env python3
"""
Quick example: export a few dictionary entries from Sefaria as CSV.

This is a simplified version of scripts/export_dictionaries_csv.py meant
to demonstrate the approach. For full exports with resume support, use
the main script.

Usage:
    # Export first 10 Jastrow entries
    python examples/export_dictionary_example.py

    # Export first 20 BDB entries
    python examples/export_dictionary_example.py --lexicon "BDB Dictionary" --limit 20

    # Print entries to stdout instead of writing CSV
    python examples/export_dictionary_example.py --stdout
"""
import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.parse

import requests

SEFARIA_API = "https://www.sefaria.org/api"


def strip_html(text):
    """Remove HTML tags from text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(text))).strip()


def flatten_senses(senses):
    """Flatten nested senses into a single string."""
    parts = []
    for sense in senses:
        defn = sense.get("definition", "")
        if defn:
            parts.append(strip_html(defn))
        for sub in sense.get("senses", []):
            d = sub.get("definition", "")
            if d:
                parts.append(f"  → {strip_html(d)}")
    return " | ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Quick dictionary export example")
    parser.add_argument("--lexicon", default="Jastrow Dictionary",
                        help='Lexicon name (default: "Jastrow Dictionary")')
    parser.add_argument("--index", default=None,
                        help='Index title (auto-detected from lexicon)')
    parser.add_argument("--limit", type=int, default=10,
                        help="Number of entries to export (default: 10)")
    parser.add_argument("--stdout", action="store_true",
                        help="Print to stdout instead of CSV file")
    parser.add_argument("--output", default=None,
                        help="Output CSV file (default: {lexicon}_sample.csv)")
    args = parser.parse_args()

    # Auto-detect index title
    index_map = {
        "Jastrow Dictionary": "Jastrow",
        "BDB Dictionary": "BDB",
        "BDB Aramaic Dictionary": "BDB",
        "Klein Dictionary": "Klein Dictionary",
    }
    index_title = args.index or index_map.get(args.lexicon)
    if not index_title:
        print(f"Error: Unknown lexicon '{args.lexicon}'. Specify --index.")
        sys.exit(1)

    # Step 1: Get starting headword from the index
    print(f"Fetching index for '{index_title}'...")
    resp = requests.get(f"{SEFARIA_API}/index/{urllib.parse.quote(index_title)}")
    resp.raise_for_status()
    index_data = resp.json()

    # Find the DictionaryNode and its headwordMap
    headword_map = None
    for node in index_data.get("schema", {}).get("nodes", []):
        if node.get("nodeType") == "DictionaryNode":
            headword_map = node.get("headwordMap", [])
            break

    if not headword_map:
        print("Error: Could not find headwordMap in index")
        sys.exit(1)

    # Get the first headword (after the "Dict, " prefix)
    first_ref = headword_map[0][1]  # e.g., "Jastrow, א"
    current_hw = first_ref.split(", ", 1)[1] if ", " in first_ref else first_ref

    # Step 2: Crawl entries
    print(f"Crawling '{args.lexicon}' starting from '{current_hw}'...\n")

    entries = []
    while current_hw and len(entries) < args.limit:
        resp = requests.get(f"{SEFARIA_API}/words/{urllib.parse.quote(current_hw)}")
        resp.raise_for_status()
        data = resp.json()

        # Filter to target lexicon
        matches = [e for e in data if e.get("parent_lexicon") == args.lexicon]

        next_hw = None
        for entry in matches:
            senses = entry.get("content", {}).get("senses", [])
            row = {
                "headword": entry.get("headword", ""),
                "definition": flatten_senses(senses),
                "morphology": entry.get("content", {}).get("morphology", ""),
                "transliteration": entry.get("transliteration", ""),
                "rid": entry.get("rid", ""),
            }
            entries.append(row)
            next_hw = entry.get("next_hw")
            print(f"  [{len(entries)}] {row['headword']}: {row['definition'][:80]}...")

        current_hw = next_hw
        time.sleep(0.2)  # Be kind to the API

    # Step 3: Output
    if args.stdout:
        print(f"\n{'='*60}")
        for e in entries:
            print(f"\n{e['headword']} ({e['morphology']})")
            print(f"  {e['definition']}")
    else:
        output_file = args.output or f"{re.sub(r'[^w-]', '_', args.lexicon)}_sample.csv"
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["headword", "rid", "transliteration",
                                                    "morphology", "definition"])
            writer.writeheader()
            writer.writerows(entries)
        print(f"\n✓ Wrote {len(entries)} entries to {output_file}")


if __name__ == "__main__":
    main()
