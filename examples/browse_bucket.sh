#!/usr/bin/env bash
# Browse the Sefaria GCS bucket to see what's available.
# No authentication needed — the bucket is public.
#
# Usage:
#   ./browse_bucket.sh                        # list top-level formats
#   ./browse_bucket.sh json                   # list categories in JSON format
#   ./browse_bucket.sh json/Talmud            # list subcategories
#   ./browse_bucket.sh json/Talmud/Bavli      # keep drilling down
#   ./browse_bucket.sh schemas                # list schema files

set -euo pipefail

BUCKET="sefaria-export"
PREFIX="${1:-}"

if [ -z "$PREFIX" ]; then
  echo "Top-level contents of gs://${BUCKET}/"
  echo "======================================="
  echo ""
fi

# Use the public GCS XML API to list "directories" at this level
# delimiter=/ gives us folder-like listing without listing every nested object
curl -s "https://storage.googleapis.com/${BUCKET}?prefix=${PREFIX}${PREFIX:+/}&delimiter=/" \
  | grep -oP '(?<=<Prefix>)[^<]+' \
  | sort

# Also show files at this level (not in subdirectories)
curl -s "https://storage.googleapis.com/${BUCKET}?prefix=${PREFIX}${PREFIX:+/}&delimiter=/" \
  | grep -oP '(?<=<Key>)[^<]+' \
  | sort
