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

# The one known Git LFS object in this repo's history: links/links.csv as of
# commit c8b01ae01480348c188e846a71fe260697882fc9. See the archive-git-history
# design doc under docs/superpowers/specs/ for context.
readonly LFS_OID="baa9ea43d9ccadd1b6340d77c317f2a92ef00be62c2a34a12ea19b9627e7e15f"
readonly LFS_SIZE="105951940"

# Derive the LFS batch API endpoint for a repo, whether given as an SSH URL
# (git@github.com:Org/Repo.git) or an HTTPS URL (https://github.com/Org/Repo.git).
lfs_batch_url() {
  local url="$1" https
  if [[ "$url" == git@*:* ]]; then
    local host_and_path="${url#git@}"
    local host="${host_and_path%%:*}"
    local path="${host_and_path#*:}"
    https="https://${host}/${path}"
  else
    https="$url"
  fi
  [[ "$https" == *.git ]] || https="${https}.git"
  echo "${https}/info/lfs/objects/batch"
}

# Probe an LFS batch endpoint for a downloadable copy of $LFS_OID. Public
# repos need no auth for this. Returns 0 and prints nothing on success;
# returns 1 and prints the raw response on failure.
probe_lfs_object() {
  local batch_url="$1" response
  response="$(curl -sS -X POST "$batch_url" \
    -H "Accept: application/vnd.git-lfs+json" \
    -H "Content-Type: application/vnd.git-lfs+json" \
    -d "{\"operation\":\"download\",\"transfers\":[\"basic\"],\"objects\":[{\"oid\":\"${LFS_OID}\",\"size\":${LFS_SIZE}}]}")"
  if echo "$response" | grep -q '"download"' && ! echo "$response" | grep -q '"error"'; then
    return 0
  fi
  echo "$response" >&2
  return 1
}

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

echo "==> Verifying archive contains pre-migration-master tag..."
git ls-remote --tags "$ARCHIVE_URL" "refs/tags/pre-migration-master" 2>/dev/null \
  | grep -q 'refs/tags/pre-migration-master$' \
  || { echo "!! ABORT: pre-migration-master tag not found in $ARCHIVE_URL."; \
       echo "!! Run 01_create_archive.sh first and verify it completed."; \
       exit 1; }
echo "==> Archive tag present. Recovery path is intact."

echo "==> Verifying LFS object $LFS_OID is retrievable from the archive..."
ARCHIVE_LFS_BATCH_URL="$(lfs_batch_url "$ARCHIVE_URL")"
echo "    probing: $ARCHIVE_LFS_BATCH_URL"
if ! probe_lfs_object "$ARCHIVE_LFS_BATCH_URL"; then
  echo "!! ABORT: LFS object $LFS_OID is NOT retrievable from the archive."
  echo "!! Phase 1 (01_create_archive.sh) did not finish migrating LFS"
  echo "!! objects -- the mirror push alone copies LFS pointer blobs but not"
  echo "!! the objects themselves. Proceeding now would force-push over the"
  echo "!! only live copy of this ~106 MB object and lose it permanently."
  echo "!! Re-run 01_create_archive.sh to completion (including its LFS"
  echo "!! fetch/push/verify steps) before running this script."
  exit 1
fi
echo "==> LFS object confirmed retrievable from archive. Safe to proceed."

cd "$WORKDIR"
echo "==> Fresh clone of source (full, not shallow)..."
git clone "$SOURCE_URL" Sefaria-Export
cd Sefaria-Export

PRE_SHA="$(git rev-parse master)"
echo "==> Current master SHA: $PRE_SHA"

echo "==> Auditing remote refs other than master..."
EXTRA_REFS=$(git ls-remote --heads --tags origin | awk '{print $2}' \
  | grep -vE '^refs/(heads/master|tags/pre-migration-master)$' || true)
if [[ -n "$EXTRA_REFS" ]]; then
  echo "==> Remote has these non-master refs (will be deleted from origin to actually slim it):"
  echo "$EXTRA_REFS" | sed 's/^/    /'
  read -r -p "Delete these refs from origin after the master force-push? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || \
    { echo "!! ABORT: refs left in place would defeat the size goal. Resolve manually first."; exit 1; }
  DELETE_EXTRA_REFS=1
else
  echo "==> No non-master refs on origin. Good."
  DELETE_EXTRA_REFS=0
fi

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

if [[ "$DELETE_EXTRA_REFS" == "1" ]]; then
  echo "==> Deleting non-master refs from origin (history is preserved in archive)..."
  while IFS= read -r ref; do
    [[ -z "$ref" ]] && continue
    short="${ref#refs/heads/}"; short="${short#refs/tags/}"
    if [[ "$ref" == refs/heads/* ]]; then
      git push origin --delete "$short" || echo "!! failed to delete branch $short (continuing)"
    elif [[ "$ref" == refs/tags/* ]]; then
      git push origin ":refs/tags/$short" || echo "!! failed to delete tag $short (continuing)"
    fi
  done <<< "$EXTRA_REFS"
fi

echo
echo "==> Done. Verify:"
echo "    git clone https://github.com/Sefaria/Sefaria-Export.git /tmp/check && du -sh /tmp/check/.git"
echo "==> Recovery (if needed) is documented in scripts/migration/README.md"
