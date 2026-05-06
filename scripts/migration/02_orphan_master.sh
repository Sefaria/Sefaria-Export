#!/usr/bin/env bash
# Phase 2 of sc-43976: replace master of Sefaria-Export with a single
# orphan commit containing the current working tree, then force-push.
#
# DESTRUCTIVE. Run only after 01_create_archive.sh has succeeded and the
# archive repo on GitHub is verified and marked read-only.

set -euo pipefail

SOURCE_URL="${SOURCE_URL:-git@github.com:Sefaria/Sefaria-Export.git}"
ARCHIVE_URL="${ARCHIVE_URL:-https://github.com/Sefaria/Sefaria-Export-Archive}"
WORKDIR="${WORKDIR:-$(mktemp -d -t sefaria-export-slim-XXXX)}"

echo "==> Source (will be force-pushed): $SOURCE_URL"
echo "==> Archive (already populated):   $ARCHIVE_URL"
echo "==> Workdir: $WORKDIR"
echo
echo "This will REPLACE the master branch of Sefaria-Export with a single"
echo "orphan commit. All existing commit hashes on the remote master will"
echo "become unreachable from Sefaria-Export (they remain in the archive)."
echo
read -r -p "Type 'i understand' to continue: " ans
[[ "$ans" == "i understand" ]] || { echo "aborted"; exit 1; }

cd "$WORKDIR"
echo "==> Fresh clone of source (full, not shallow)..."
git clone "$SOURCE_URL" Sefaria-Export
cd Sefaria-Export

PRE_SHA="$(git rev-parse master)"
echo "==> Current master SHA: $PRE_SHA"

echo "==> Creating orphan branch from current tree..."
git checkout --orphan fresh-master
git add -A
git commit -m "Reset history; full archive at Sefaria/Sefaria-Export-Archive

Pre-migration master was $PRE_SHA.
The complete commit graph through that SHA is preserved in the archive
repo. This commit contains the working tree exactly as of that SHA.

See docs/superpowers/specs/2026-05-06-archive-git-history-design.md for
context, and scripts/migration/README.md for recovery."

echo "==> Replacing master with the orphan branch..."
git branch -D master
git branch -m fresh-master master

echo "==> Sanity check: tree of new master must equal tree of $PRE_SHA"
NEW_TREE="$(git rev-parse master^{tree})"
OLD_TREE="$(git rev-parse "$PRE_SHA^{tree}" 2>/dev/null || echo MISSING)"
if [[ "$NEW_TREE" != "$OLD_TREE" ]]; then
  echo "!! Tree mismatch: new=$NEW_TREE old=$OLD_TREE"
  echo "!! ABORT — do not push. Investigate."
  exit 2
fi
echo "==> Tree match OK ($NEW_TREE)"

echo
echo "==> About to: git push --force-with-lease origin master"
read -r -p "Type 'push' to proceed: " ans
[[ "$ans" == "push" ]] || { echo "aborted before push"; exit 1; }

git push --force-with-lease origin master

echo
echo "==> Done. Verify:"
echo "    git clone https://github.com/Sefaria/Sefaria-Export.git /tmp/check && du -sh /tmp/check/.git"
echo "==> Recovery (if needed) is documented in scripts/migration/README.md"
