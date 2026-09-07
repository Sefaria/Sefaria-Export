#!/usr/bin/env bash
# Phase 1 of sc-43976: mirror Sefaria-Export into Sefaria-Export-Archive.
# Non-destructive to the source repo.
#
# Prereq: an empty Sefaria/Sefaria-Export-Archive repo exists on GitHub.
# Prereq: git-lfs is installed (`brew install git-lfs && git lfs install`) --
#   Sefaria-Export has one historical Git LFS object (links/links.csv @
#   c8b01ae0, ~106 MB) and `git push --mirror` alone does NOT copy LFS
#   objects, only the pointer blobs. Skipping LFS here would leave the
#   archive with a dangling pointer and no way to recover that object.

set -euo pipefail

SOURCE_URL="${SOURCE_URL:-https://github.com/Sefaria/Sefaria-Export.git}"
ARCHIVE_URL="${ARCHIVE_URL:-git@github.com:Sefaria/Sefaria-Export-Archive.git}"
WORKDIR="${WORKDIR:-$(mktemp -d -t sefaria-export-archive-XXXX)}"

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

echo "==> Checking for git-lfs..."
if ! git lfs version >/dev/null 2>&1; then
  echo "!! ABORT: git-lfs is not installed or not on PATH."
  echo "!! Sefaria-Export has a historical Git LFS object that a plain"
  echo "!! 'git clone --mirror' + 'git push --mirror' will NOT copy."
  echo "!! Install it and retry:"
  echo "!!     brew install git-lfs && git lfs install"
  exit 1
fi
echo "==> git-lfs OK: $(git lfs version)"

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

echo "==> Fetching all LFS objects from source (origin still points at"
echo "    $SOURCE_URL for fetch at this point; includes the historical"
echo "    links/links.csv object referenced from commit c8b01ae0)..."
git lfs fetch --all

echo "==> Pushing mirror to archive remote..."
git remote set-url --push origin "$ARCHIVE_URL"
git push --mirror

echo "==> Pushing LFS objects to archive remote (origin's push URL now"
echo "    points at $ARCHIVE_URL, so this lands the LFS objects there too)..."
git lfs push --all origin

echo "==> Verifying LFS object $LFS_OID is retrievable from the archive..."
ARCHIVE_LFS_BATCH_URL="$(lfs_batch_url "$ARCHIVE_URL")"
echo "    probing: $ARCHIVE_LFS_BATCH_URL"
if ! probe_lfs_object "$ARCHIVE_LFS_BATCH_URL"; then
  echo "!! ABORT: LFS object $LFS_OID is NOT retrievable from the archive."
  echo "!! Do not proceed to 02_orphan_master.sh -- the archive would not"
  echo "!! actually preserve this object. Re-run 'git lfs push --all origin'"
  echo "!! from $WORKDIR/Sefaria-Export.git and re-verify before continuing."
  exit 1
fi
echo "==> LFS object confirmed retrievable from archive."

echo
echo "==> Done. Verify the archive on GitHub:"
echo "    https://github.com/Sefaria/Sefaria-Export-Archive"
echo "==> Pre-migration SHA recorded at: $WORKDIR/PRE_MIGRATION_SHA"
echo "==> Next: enable 'Archive this repository' in archive repo settings,"
echo "    then run 02_orphan_master.sh."
