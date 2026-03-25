#!/usr/bin/env bash
# Download all texts in a category from the Sefaria GCS bucket.
#
# Usage:
#   ./download_category.sh Talmud                  # all Talmud in JSON
#   ./download_category.sh Talmud txt              # all Talmud in TXT
#   ./download_category.sh "Mishneh Torah" json    # Mishneh Torah in JSON
#   ./download_category.sh Tanakh/Torah json       # just Torah subsection
#
# The bucket is hierarchical — you can download at any level:
#   Talmud/                    → everything
#   Talmud/Bavli/              → just Bavli
#   Talmud/Bavli/Seder Moed/  → just Seder Moed

set -euo pipefail

CATEGORY="${1:?Usage: $0 <category> [format]}"
FORMAT="${2:-json}"
BUCKET="sefaria-export"

echo "Downloading ${FORMAT}/${CATEGORY}/ from gs://${BUCKET} ..."

# gcloud storage supports downloading entire "folders" from GCS
gcloud storage cp -r \
  "gs://${BUCKET}/${FORMAT}/${CATEGORY}/" \
  "./${CATEGORY}/"

echo "Done. Files saved to ./${CATEGORY}/"
