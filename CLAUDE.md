# Sefaria-Export

Public dataset of all Sefaria texts, hosted on Google Cloud Storage.

## Architecture

- **Data lives in GCS**: `gs://sefaria-export/` — ~26GB, ~85K files, updated monthly
- **This repo** holds `books.json` — a single index file with metadata and download URLs for every text
- **GitHub Action** regenerates `books.json` monthly (2nd of each month, day after the text-export CronJob) from the GCS bucket listing (no auth needed — bucket is public). Can also be triggered manually via workflow_dispatch.

## Bucket structure

The GCS bucket is hierarchical, organized by format, category, title, language, and version:

```
gs://sefaria-export/
  json/{categories}/{title}/{language}/{versionTitle}.json
  txt/{categories}/{title}/{language}/{versionTitle}.txt
  cltk-full/{categories}/{title}/{language}/{versionTitle}.json
  cltk-flat/{categories}/{title}/{language}/{versionTitle}.json
  schemas/{title}.json
  links/links0.csv ... links12.csv
  table_of_contents.json
```

Example paths:
```
json/Tanakh/Torah/Genesis/English/merged.json
json/Talmud/Bavli/Seder Moed/Shabbat/Hebrew/merged.json
txt/Mishnah/Seder Zeraim/Mishnah Berakhot/English/merged.txt
```

## How to download data

All data is public. No authentication needed.

### Single file
```bash
curl -O "https://storage.googleapis.com/sefaria-export/json/Tanakh/Torah/Genesis/English/merged.json"
```

### Entire folder (e.g., all of Talmud in JSON)
```bash
# Using gcloud CLI
gcloud storage cp -r "gs://sefaria-export/json/Talmud/" ./talmud/

# Using gsutil
gsutil -m cp -r "gs://sefaria-export/json/Talmud/" ./talmud/
```

### Everything
```bash
gcloud storage cp -r "gs://sefaria-export/" ./sefaria-data/
```

### Using books.json
```python
import requests
books = requests.get("https://raw.githubusercontent.com/Sefaria/Sefaria-Export/master/books.json").json()
for book in books["books"]:
    if "Talmud" in book["categories"]:
        print(book["title"], book.get("json_url"))
```

## Example scripts

See `examples/` for ready-to-use download scripts:
- `download_category.sh` — download all texts in a category (e.g., Talmud, Mishnah)
- `download_from_books_json.py` — filter and download using books.json
- `browse_bucket.sh` — list available categories and texts in the bucket
- `export_dictionary_example.py` — export a sample of dictionary entries to CSV
- `dictionary-explorer/` — browser-based dictionary explorer and CSV exporter

## Dictionary export

Dictionaries (Jastrow, BDB, Klein) use a `DictionaryNode` schema and are NOT in the standard GCS text export. Use the dedicated tools:

```bash
# CLI: export Jastrow as CSV
python scripts/export_dictionaries_csv.py --lexicon "Jastrow Dictionary" --limit 50

# Browser: open the interactive explorer
open examples/dictionary-explorer/index.html
```

The script crawls `/api/words/{headword}` using `next_hw` linked-list pointers. Rate-limited (200ms default). Supports `--resume` for long crawls.

## Files

| File | Purpose |
|------|---------|
| `books.json` | Index of all texts with metadata and GCS download URLs |
| `scripts/generate_books_json.py` | Generates books.json from GCS bucket (runs in CI) |
| `scripts/export_dictionaries_csv.py` | Export dictionary/lexicon data as CSV via Sefaria API |
| `examples/` | Example download scripts for developers |
| `examples/dictionary-explorer/` | Browser-based dictionary explorer and CSV exporter |
| `tests/test_export_dictionaries_csv.py` | Tests for the dictionary export script |
| `.github/workflows/generate-books-json.yml` | Monthly CI to regenerate books.json (also supports manual trigger) |
