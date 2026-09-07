# Sefaria-Export

Public dataset of all Sefaria texts, hosted on Google Cloud Storage.

## Architecture

- **Data lives in GCS**: `gs://sefaria-export/` — ~26GB, ~85K files, updated monthly
- **This repo** holds `books.json` — a single index file with metadata and download URLs for every text
- **History lives elsewhere**: this repo keeps current state only (clone ~25 MB). The full
  pre-September-2026 commit history is archived read-only at
  [Sefaria/Sefaria-Export-Archive](https://github.com/Sefaria/Sefaria-Export-Archive).
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

## Files

| File | Purpose |
|------|---------|
| `books.json` | Index of all texts with metadata and GCS download URLs |
| `scripts/generate_books_json.py` | Generates books.json from GCS bucket (runs in CI) |
| `examples/` | Example download scripts for developers |
| `.github/workflows/generate-books-json.yml` | Monthly CI to regenerate books.json (also supports manual trigger) |
