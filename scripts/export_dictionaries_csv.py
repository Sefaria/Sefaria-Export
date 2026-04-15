#!/usr/bin/env python3
"""
Export Sefaria dictionary/lexicon data as CSV.

Uses Sefaria's public /api/words/ endpoint to crawl dictionary entries
(Jastrow, BDB, Klein, etc.) and export them as structured CSV files.

Dictionary entries in Sefaria use a DictionaryNode schema with linked-list
navigation (next_hw/prev_hw pointers), which this script follows to enumerate
every entry in a given lexicon.

Usage:
    # Export Jastrow Dictionary
    python scripts/export_dictionaries_csv.py --lexicon "Jastrow Dictionary"

    # Export all supported dictionaries
    python scripts/export_dictionaries_csv.py --all

    # Export with custom delay (be kind to the API)
    python scripts/export_dictionaries_csv.py --lexicon "BDB Dictionary" --delay 0.3

    # Resume an interrupted export
    python scripts/export_dictionaries_csv.py --lexicon "Jastrow Dictionary" --resume

    # Quick test: export first 20 entries only
    python scripts/export_dictionaries_csv.py --lexicon "Jastrow Dictionary" --limit 20
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse

import requests

SEFARIA_API = "https://www.sefaria.org/api"

# Map of lexicon name -> index title used in /api/index/{title}
SUPPORTED_LEXICONS = {
    "Jastrow Dictionary": {
        "index_title": "Jastrow",
        "description": "Aramaic/Hebrew dictionary for Talmud, midrash, and Targumim",
    },
    "BDB Dictionary": {
        "index_title": "BDB",
        "description": "Brown-Driver-Briggs Hebrew and English Lexicon (Biblical Hebrew)",
    },
    "BDB Aramaic Dictionary": {
        "index_title": "BDB",
        "description": "Brown-Driver-Briggs Biblical Aramaic entries",
    },
    "BDB Augmented Strong": {
        "index_title": None,  # No index; entries found via /api/words/
        "description": "BDB entries linked to Strong's concordance numbers",
    },
    "Klein Dictionary": {
        "index_title": "Klein Dictionary",
        "description": "Klein's Comprehensive Etymological Dictionary of the Hebrew Language",
    },
}

CSV_COLUMNS = [
    "headword",
    "headword_id",
    "transliteration",
    "pronunciation",
    "morphology",
    "definition",
    "senses_json",
    "alt_headwords",
    "plural_form",
    "strong_number",
    "language_code",
    "cross_refs",
    "source_lexicon",
    "prev_headword",
    "next_headword",
]


def strip_html(text):
    """Remove HTML tags from a string, preserving text content."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", str(text))
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def flatten_senses(senses, depth=0):
    """Recursively flatten a nested senses structure into a single definition string."""
    parts = []
    for i, sense in enumerate(senses, 1):
        defn = sense.get("definition", "")
        if defn:
            clean = strip_html(defn)
            prefix = f"{'  ' * depth}{i}." if depth > 0 or len(senses) > 1 else ""
            parts.append(f"{prefix} {clean}".strip())
        # Recurse into sub-senses
        sub = sense.get("senses", [])
        if sub:
            parts.append(flatten_senses(sub, depth + 1))
    return " | ".join(filter(None, parts))


def entry_to_row(entry):
    """Convert a single API entry dict to a flat CSV row dict."""
    content = entry.get("content", {})
    senses = content.get("senses", [])

    return {
        "headword": entry.get("headword", ""),
        "headword_id": entry.get("rid", ""),
        "transliteration": entry.get("transliteration", ""),
        "pronunciation": entry.get("pronunciation", ""),
        "morphology": content.get("morphology", ""),
        "definition": flatten_senses(senses),
        "senses_json": json.dumps(senses, ensure_ascii=False) if senses else "",
        "alt_headwords": "; ".join(entry.get("alt_headwords", []) or []),
        "plural_form": "; ".join(entry.get("plural_form", []) or []),
        "strong_number": entry.get("strong_number", ""),
        "language_code": entry.get("language_code", ""),
        "cross_refs": "; ".join(entry.get("refs", []) or []),
        "source_lexicon": entry.get("parent_lexicon", ""),
        "prev_headword": entry.get("prev_hw", ""),
        "next_headword": entry.get("next_hw", ""),
    }


def fetch_index(index_title):
    """Fetch the index schema for a dictionary to get headword starting points."""
    url = f"{SEFARIA_API}/index/{urllib.parse.quote(index_title)}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()


def fetch_word_entries(headword, lexicon_name):
    """Fetch all dictionary entries for a headword, filtered to the target lexicon."""
    url = f"{SEFARIA_API}/words/{urllib.parse.quote(headword)}"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list):
        return [e for e in data if e.get("parent_lexicon") == lexicon_name]
    return []


def get_starting_headwords(index_title):
    """Extract the headwordMap from a dictionary index to get starting points per letter."""
    index_data = fetch_index(index_title)
    schema = index_data.get("schema", {})
    nodes = schema.get("nodes", [])

    for node in nodes:
        if node.get("nodeType") == "DictionaryNode":
            return node.get("headwordMap", [])

    return []


def save_checkpoint(checkpoint_path, headword, count):
    """Save progress checkpoint for resume capability."""
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump({"last_headword": headword, "count": count}, f, ensure_ascii=False)


def load_checkpoint(checkpoint_path):
    """Load a previously saved checkpoint."""
    if not os.path.exists(checkpoint_path):
        return None
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        return json.load(f)


def export_lexicon(lexicon_name, output_dir, delay=0.2, resume=False, limit=None):
    """
    Export a single lexicon to CSV by crawling its entries via the API.

    The strategy:
    1. Get the headwordMap from the index (list of [letter, first_headword] pairs)
    2. For each starting headword, call /api/words/{headword}
    3. Filter to entries from the target lexicon
    4. Follow next_hw to the next entry
    5. Stop when next_hw is empty or we've hit the limit
    """
    config = SUPPORTED_LEXICONS.get(lexicon_name)
    if not config:
        print(f"Error: Unknown lexicon '{lexicon_name}'")
        print(f"Supported: {', '.join(SUPPORTED_LEXICONS.keys())}")
        return False

    index_title = config["index_title"]
    if not index_title:
        print(f"Error: '{lexicon_name}' doesn't have a standalone index.")
        print("  This lexicon's entries appear alongside other dictionaries")
        print("  and must be exported via a lexicon that has an index (e.g., BDB).")
        return False

    os.makedirs(output_dir, exist_ok=True)

    # Sanitize filename
    safe_name = re.sub(r"[^\w\-]", "_", lexicon_name)
    csv_path = os.path.join(output_dir, f"{safe_name}.csv")
    checkpoint_path = os.path.join(output_dir, f".{safe_name}.checkpoint")

    # Get starting headwords from the index
    print(f"Fetching index for '{index_title}'...")
    headword_map = get_starting_headwords(index_title)
    if not headword_map:
        print(f"Error: Could not find headwordMap in index for '{index_title}'")
        return False

    print(f"Found {len(headword_map)} letter sections")

    # Handle resume
    resume_from = None
    start_count = 0
    file_mode = "w"
    write_header = True

    if resume:
        checkpoint = load_checkpoint(checkpoint_path)
        if checkpoint:
            resume_from = checkpoint["last_headword"]
            start_count = checkpoint["count"]
            file_mode = "a"
            write_header = False
            print(f"Resuming from '{resume_from}' (entry #{start_count})")
        else:
            print("No checkpoint found, starting from the beginning")

    # Build the full starting-headword reference from the map
    # headwordMap entries look like: ["א", "Jastrow, א"]
    # We need to extract the actual headword reference (after the comma)
    starting_refs = {}
    for letter, ref in headword_map:
        # ref is like "Jastrow, א" - we need just the headword part
        if ", " in ref:
            hw = ref.split(", ", 1)[1]
        else:
            hw = ref
        starting_refs[letter] = hw

    # Open CSV file
    with open(csv_path, file_mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()

        count = start_count
        skipping = resume_from is not None
        current_hw = None
        errors = 0
        max_errors = 10  # Abort after too many consecutive errors

        # Start from first letter and crawl
        first_hw = list(starting_refs.values())[0]
        current_hw = first_hw

        if resume_from:
            current_hw = resume_from
            skipping = False  # We already have the resume point

        print(f"\nExporting '{lexicon_name}' to {csv_path}")
        print(f"Starting from headword: '{current_hw}'")
        print(f"Delay between requests: {delay}s")
        if limit:
            print(f"Limit: {limit} entries")
        print()

        consecutive_errors = 0

        while current_hw:
            if limit and (count - start_count) >= limit:
                print(f"\nReached limit of {limit} entries")
                break

            try:
                entries = fetch_word_entries(current_hw, lexicon_name)
                consecutive_errors = 0
            except requests.exceptions.RequestException as e:
                consecutive_errors += 1
                errors += 1
                print(f"  ⚠ Error fetching '{current_hw}': {e}")
                if consecutive_errors >= max_errors:
                    print(f"\n✗ Aborting after {max_errors} consecutive errors")
                    save_checkpoint(checkpoint_path, current_hw, count)
                    return False
                time.sleep(delay * 2)  # Back off on errors
                continue

            if not entries:
                # Word exists but no entries for this lexicon — try next_hw from
                # a different lexicon's entry if available
                try:
                    all_entries = requests.get(
                        f"{SEFARIA_API}/words/{urllib.parse.quote(current_hw)}"
                    ).json()
                    if isinstance(all_entries, list):
                        # Find any entry with a next_hw
                        for e in all_entries:
                            if e.get("next_hw"):
                                current_hw = e["next_hw"]
                                break
                        else:
                            current_hw = None
                    else:
                        current_hw = None
                except Exception:
                    current_hw = None
                time.sleep(delay)
                continue

            # Process all entries for this headword from the target lexicon
            next_hw = None
            for entry in entries:
                row = entry_to_row(entry)
                writer.writerow(row)
                count += 1
                next_hw = entry.get("next_hw")

                # Progress indicator
                if count % 100 == 0:
                    save_checkpoint(checkpoint_path, current_hw, count)
                    print(f"  [{count}] {row['headword']}")
                elif count % 10 == 0:
                    sys.stdout.write(".")
                    sys.stdout.flush()

            current_hw = next_hw
            time.sleep(delay)

    # Cleanup checkpoint on successful completion
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)

    print(f"\n\n✓ Exported {count - start_count} entries to {csv_path}")
    print(f"  Total entries: {count}")
    if errors:
        print(f"  Errors encountered: {errors}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Export Sefaria dictionary data as CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported lexicons:
  "Jastrow Dictionary"     - Aramaic/Hebrew for Talmud study (~13,000 entries)
  "BDB Dictionary"         - Biblical Hebrew lexicon (~8,700 entries)
  "BDB Aramaic Dictionary" - Biblical Aramaic entries
  "Klein Dictionary"       - Modern Hebrew etymological dictionary (~30,000 entries)

Examples:
  %(prog)s --lexicon "Jastrow Dictionary"
  %(prog)s --lexicon "BDB Dictionary" --delay 0.3
  %(prog)s --all --output ./dictionaries/
  %(prog)s --lexicon "Jastrow Dictionary" --resume
  %(prog)s --lexicon "Jastrow Dictionary" --limit 50
        """,
    )
    parser.add_argument(
        "--lexicon",
        help='Lexicon to export (e.g., "Jastrow Dictionary")',
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export all supported dictionaries",
    )
    parser.add_argument(
        "--output",
        default="./dictionaries",
        help="Output directory for CSV files (default: ./dictionaries)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds between API requests (default: 0.2, be kind to the API)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint if available",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of entries to export (for testing)",
    )

    args = parser.parse_args()

    if not args.lexicon and not args.all:
        parser.error("Specify --lexicon or --all")

    lexicons_to_export = []
    if args.all:
        # Export all lexicons that have an index
        lexicons_to_export = [
            name
            for name, config in SUPPORTED_LEXICONS.items()
            if config["index_title"] is not None
        ]
    else:
        if args.lexicon not in SUPPORTED_LEXICONS:
            parser.error(
                f"Unknown lexicon '{args.lexicon}'. "
                f"Supported: {', '.join(SUPPORTED_LEXICONS.keys())}"
            )
        lexicons_to_export = [args.lexicon]

    print("Sefaria Dictionary CSV Exporter")
    print("=" * 40)
    print(f"Output directory: {args.output}")
    print(f"Lexicons to export: {len(lexicons_to_export)}")
    print()

    results = {}
    for lexicon in lexicons_to_export:
        print(f"\n{'─' * 40}")
        print(f"Exporting: {lexicon}")
        print(f"  {SUPPORTED_LEXICONS[lexicon]['description']}")
        print(f"{'─' * 40}")

        success = export_lexicon(
            lexicon_name=lexicon,
            output_dir=args.output,
            delay=args.delay,
            resume=args.resume,
            limit=args.limit,
        )
        results[lexicon] = success

    # Summary
    print(f"\n{'=' * 40}")
    print("Summary")
    print(f"{'=' * 40}")
    for lexicon, success in results.items():
        status = "✓" if success else "✗"
        print(f"  {status} {lexicon}")

    all_ok = all(results.values())
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
