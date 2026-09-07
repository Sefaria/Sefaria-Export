# Sefaria-Export

Public dataset of all [Sefaria](https://www.sefaria.org) texts, hosted on Google Cloud Storage.

This repository is a lightweight index and set of tools for accessing the Sefaria text corpus. The actual text data (~26GB, ~85K files) lives in a public GCS bucket and can be downloaded without authentication.

## Cloning

This repository holds only its current state, so a normal clone is small (~25 MB):

```bash
git clone https://github.com/Sefaria/Sefaria-Export.git
```

Its git history previously accumulated monthly snapshots of `books.json`, which made a
clone ~14 GB. In September 2026 that history was moved to a separate archive repo.

**You almost certainly don't need the history.** The current index (`books.json`) and
tooling are here, and all text data lives in the GCS bucket described below.

If you *do* need historical snapshots, the complete pre-reset commit graph is preserved
read-only at
[**Sefaria/Sefaria-Export-Archive**](https://github.com/Sefaria/Sefaria-Export-Archive).

If you cloned this repo before the reset, `git pull` will report *"refusing to merge
unrelated histories"* — re-clone instead.

## Quick Start

### Browse what's available

```bash
# List top-level formats and directories
./examples/browse_bucket.sh

# Drill into a specific category
./examples/browse_bucket.sh json/Talmud
```

### Download a single text

```bash
curl -O "https://storage.googleapis.com/sefaria-export/json/Tanakh/Torah/Genesis/English/merged.json"
```

### Download an entire category

```bash
# Using the helper script
./examples/download_category.sh Talmud          # all Talmud in JSON
./examples/download_category.sh Mishnah txt     # all Mishnah in TXT

# Or directly with gcloud/gsutil
gcloud storage cp -r "gs://sefaria-export/json/Talmud/" ./talmud/
gsutil -m cp -r "gs://sefaria-export/json/Talmud/" ./talmud/
```

### Download everything

```bash
gcloud storage cp -r "gs://sefaria-export/" ./sefaria-data/
```

### Use books.json to filter and download programmatically

```python
import requests

books = requests.get(
    "https://raw.githubusercontent.com/Sefaria/Sefaria-Export/master/books.json"
).json()

# Find all Talmud texts
for book in books["books"]:
    if "Talmud" in book["categories"]:
        print(book["title"], book.get("json_url"))
```

Or use the ready-made script:

```bash
# Download all English Mishnah texts as JSON
python examples/download_from_books_json.py --category Mishnah --language English

# Download a specific title
python examples/download_from_books_json.py --title "Genesis"

# List what's available without downloading
python examples/download_from_books_json.py --category Tanakh --list
```

## Bucket Structure

The GCS bucket is organized hierarchically by format, category, title, language, and version:

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

### Example paths

```
json/Tanakh/Torah/Genesis/English/merged.json
json/Talmud/Bavli/Seder Moed/Shabbat/Hebrew/merged.json
txt/Mishnah/Seder Zeraim/Mishnah Berakhot/English/merged.txt
schemas/Genesis.json
links/links0.csv
```

### Formats

| Format | Description |
|--------|-------------|
| `json/` | Structured JSON with text content, verse-level arrays |
| `txt/` | Plain text, one file per version |
| `cltk-full/` | JSON formatted for the [Classical Language Toolkit](http://cltk.org/) |
| `cltk-flat/` | Flattened CLTK format |
| `schemas/` | Schema/structure metadata for each text |
| `links/` | CSV files of all intertextual connections |

### Merged files

Each text directory includes a `merged` file (e.g., `merged.json`, `merged.txt`). This file combines the maximal content available from all versions, using Sefaria's merging logic. When a single complete version exists, the merged file is a copy of it. Use merged files when you want the most complete text available.

## books.json

[`books.json`](books.json) is an index of every text in the bucket. Each entry contains:

```json
{
  "title": "Genesis",
  "language": "English",
  "versionTitle": "merged",
  "categories": ["Tanakh", "Torah"],
  "json_url": "https://storage.googleapis.com/sefaria-export/json/Tanakh/Torah/Genesis/English/merged.json",
  "txt_url": "https://storage.googleapis.com/sefaria-export/txt/Tanakh/Torah/Genesis/English/merged.txt",
  "cltk_full_url": "...",
  "cltk_flat_url": "..."
}
```

This file is regenerated monthly (2nd of each month, day after the GCS export) by a [GitHub Action](.github/workflows/generate-books-json.yml). It can also be triggered manually from the Actions tab.

## Repository Contents

| Path | Description |
|------|-------------|
| `books.json` | Index of all texts with metadata and download URLs |
| `scripts/generate_books_json.py` | Generates books.json from the GCS bucket listing |
| `examples/download_from_books_json.py` | Filter and download texts using books.json |
| `examples/download_category.sh` | Download all texts in a category via gcloud |
| `examples/browse_bucket.sh` | Browse available categories and texts |
| `.github/workflows/generate-books-json.yml` | Monthly CI to regenerate books.json (also supports manual trigger) |


## Related Projects

- [Sefaria-Project](https://github.com/Sefaria/Sefaria-Project) - Sefaria's main application source code
- [Sefaria API](https://developers.sefaria.org) - REST API for accessing Sefaria data programmatically

## License

See [LICENSE.md](LICENSE.md).
