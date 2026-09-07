#!/usr/bin/env bash
# Phase 1 of sc-43976: mirror Sefaria-Export into Sefaria-Export-Archive.
# Non-destructive to the source repo.
#
# Prereq: an empty Sefaria/Sefaria-Export-Archive repo exists on GitHub.
# Prereq: git-lfs is installed (`brew install git-lfs && git lfs install`) --
#   Sefaria-Export has one historical Git LFS object (links/links.csv @
#   c8b01ae0, ~106 MB) and a mirror push alone does NOT copy LFS
#   objects, only the pointer blobs. Skipping LFS here would leave the
#   archive with a dangling pointer and no way to recover that object.
#
# WHY NOT `git push --mirror`? Verified in a real run that it FAILS for this
# repo, for two distinct reasons -- do not "simplify" this script back to a
# single `git push --mirror` without re-reading both:
#
#   1. A `--mirror` clone of a GitHub-hosted repo pulls in the read-only
#      `refs/pull/*` namespace (21 such refs on this repo). GitHub rejects
#      any push to `refs/pull/*`, and `--mirror` tries to push every ref it
#      has, so the whole push is refused.
#   2. Even excluding `refs/pull/*`, this repo's ~14 GB of history in one
#      HTTPS push exceeds GitHub's ~2 GB per-push limit:
#        error: RPC failed; HTTP 500 curl 22 The requested URL returned error: 500
#        send-pack: unexpected disconnect while reading sideband packet
#        fatal: the remote end hung up unexpectedly
#      SSH does not have this per-push ceiling and is preferred when
#      available (see README's Prerequisites), but HTTPS must still work
#      because SSH isn't always configured on every maintainer's machine.
#
# The fix: push `refs/heads/*` and `refs/tags/*` explicitly (never
# `refs/pull/*`), and push `master` incrementally in small chunks of commits
# (oldest first) so no single push exceeds the size limit. A chunk that
# still fails (one did, in a real run, on a single oversized commit) is
# retried commit-by-commit rather than aborting the whole migration.
#
# This script targets bash 3.2 (macOS's shipped bash) on purpose: no
# `mapfile`/`readarray`, no associative arrays, no `${var,,}`/`${var^^}`.

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
  echo "!! 'git clone --mirror' + ref push will NOT copy."
  echo "!! Install it and retry:"
  echo "!!     brew install git-lfs && git lfs install"
  exit 1
fi
echo "==> git-lfs OK: $(git lfs version)"

echo "==> Source:  $SOURCE_URL"
echo "==> Archive: $ARCHIVE_URL"
echo "==> Workdir: $WORKDIR"
echo
read -r -p "Proceed with mirror clone + incremental push? [y/N] " ans
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

echo "==> Configuring remote for incremental push to archive..."
git remote set-url --push origin "$ARCHIVE_URL"
# A `--mirror` clone sets remote.origin.mirror=true, which forces every
# subsequent push to behave like `--mirror` (and fail with "--mirror can't
# be combined with refspecs") unless this is cleared first.
git config --unset remote.origin.mirror 2>/dev/null || true
git config http.postBuffer 524288000

STEP="${STEP:-5}"

echo "==> Checking archive's current master tip (for resuming a prior run)..."
ARCHIVE_MASTER_SHA="$(git ls-remote "$ARCHIVE_URL" refs/heads/master 2>/dev/null | cut -f1 || true)"
if [[ -n "$ARCHIVE_MASTER_SHA" ]] && git cat-file -e "${ARCHIVE_MASTER_SHA}^{commit}" 2>/dev/null; then
  echo "==> Archive already has master at $ARCHIVE_MASTER_SHA -- resuming from there."
  REV_RANGE="${ARCHIVE_MASTER_SHA}..master"
else
  echo "==> Archive has no usable master yet -- pushing full history."
  REV_RANGE="master"
fi

# Bash 3.2 has no `mapfile`/`readarray`. Build the ordered (oldest-first)
# commit list with a plain read loop into an indexed array instead.
COMMITS_FILE="$WORKDIR/commits_to_push.txt"
git rev-list --reverse "$REV_RANGE" > "$COMMITS_FILE"
commits=()
while IFS= read -r line; do
  [[ -n "$line" ]] && commits+=("$line")
done < "$COMMITS_FILE"
TOTAL="${#commits[@]}"

if [[ "$TOTAL" -eq 0 ]]; then
  echo "==> Archive master is already up to date with source master. Nothing to push."
else
  WIDTH="${#TOTAL}"
  echo "==> Pushing $TOTAL commit(s) to archive master in chunks of $STEP"
  echo "    (a chunk that fails is automatically retried commit-by-commit)..."

  i=0
  while [[ $i -lt $TOTAL ]]; do
    end=$((i + STEP - 1))
    if [[ $end -ge $TOTAL ]]; then
      end=$((TOTAL - 1))
    fi
    chunk_tip="${commits[$end]}"
    chunk_tip_short="${chunk_tip:0:10}"
    if git push "$ARCHIVE_URL" "+${chunk_tip}:refs/heads/master" \
        >"$WORKDIR/push.log" 2>&1; then
      printf "[%${WIDTH}d/%${WIDTH}d] through %s ... ok\n" \
        "$((end + 1))" "$TOTAL" "$chunk_tip_short"
    else
      echo "!! chunk push (commits $((i + 1))-$((end + 1))) failed at $chunk_tip_short;" \
        "falling back to commit-by-commit for this chunk:"
      cat "$WORKDIR/push.log" >&2
      j=$i
      while [[ $j -le $end ]]; do
        sha="${commits[$j]}"
        short="${sha:0:10}"
        if git push "$ARCHIVE_URL" "+${sha}:refs/heads/master" \
            >"$WORKDIR/push.log" 2>&1; then
          printf "[%${WIDTH}d/%${WIDTH}d] through %s ... ok (retry)\n" \
            "$((j + 1))" "$TOTAL" "$short"
        else
          echo "!! ABORT: push failed even commit-by-commit at $short" \
            "(commit $((j + 1))/$TOTAL)."
          cat "$WORKDIR/push.log" >&2
          exit 1
        fi
        j=$((j + 1))
      done
    fi
    i=$((end + 1))
  done
fi

echo "==> Pushing final master tip explicitly..."
git push "$ARCHIVE_URL" "+master:refs/heads/master"

echo "==> Pushing remaining branches (refs/heads/*, excluding master)..."
HEADS_FILE="$WORKDIR/heads.txt"
git for-each-ref --format='%(refname)' refs/heads/ > "$HEADS_FILE"
while IFS= read -r ref; do
  [[ -n "$ref" ]] || continue
  name="${ref#refs/heads/}"
  [[ "$name" == "master" ]] && continue
  echo "    pushing branch $name"
  git push "$ARCHIVE_URL" "+${ref}:${ref}"
done < "$HEADS_FILE"

echo "==> Pushing tags (refs/tags/*)..."
TAGS_FILE="$WORKDIR/tags.txt"
git for-each-ref --format='%(refname)' refs/tags/ > "$TAGS_FILE"
while IFS= read -r ref; do
  [[ -n "$ref" ]] || continue
  name="${ref#refs/tags/}"
  echo "    pushing tag $name"
  git push "$ARCHIVE_URL" "+${ref}:${ref}"
done < "$TAGS_FILE"

# `refs/pull/*` is intentionally never pushed above: it is read-only on
# GitHub, and a mirror push (or any attempt to push it) is rejected.

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
