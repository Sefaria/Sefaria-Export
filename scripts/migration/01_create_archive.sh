#!/usr/bin/env bash
# Phase 1 of sc-43976: mirror Sefaria-Export into Sefaria-Export-Archive.
# Non-destructive to the source repo.
#
# Prereq: an empty Sefaria/Sefaria-Export-Archive repo exists on GitHub.

set -euo pipefail

SOURCE_URL="${SOURCE_URL:-https://github.com/Sefaria/Sefaria-Export.git}"
ARCHIVE_URL="${ARCHIVE_URL:-git@github.com:Sefaria/Sefaria-Export-Archive.git}"
WORKDIR="${WORKDIR:-$(mktemp -d -t sefaria-export-archive-XXXX)}"

echo "==> Source:  $SOURCE_URL"
echo "==> Archive: $ARCHIVE_URL"
echo "==> Workdir: $WORKDIR"
echo
read -r -p "Proceed with mirror clone + push? [y/N] " ans
[[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "aborted"; exit 1; }

cd "$WORKDIR"
echo "==> Cloning mirror (this is the slow ~10 GB step)..."
git clone --mirror "$SOURCE_URL" Sefaria-Export.git

cd Sefaria-Export.git

PRE_SHA="$(git rev-parse master)"
echo "==> Pre-migration master SHA: $PRE_SHA"
echo "$PRE_SHA" > "$WORKDIR/PRE_MIGRATION_SHA"

echo "==> Tagging pre-migration tip"
git tag -f pre-migration-master "$PRE_SHA"

echo "==> Pushing mirror to archive remote..."
git remote set-url --push origin "$ARCHIVE_URL"
git push --mirror

echo
echo "==> Done. Verify the archive on GitHub:"
echo "    https://github.com/Sefaria/Sefaria-Export-Archive"
echo "==> Pre-migration SHA recorded at: $WORKDIR/PRE_MIGRATION_SHA"
echo "==> Next: enable 'Archive this repository' in archive repo settings,"
echo "    then run 02_orphan_master.sh."
