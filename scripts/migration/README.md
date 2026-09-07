# Sefaria-Export history-split migration

Runbooks for [sc-43976](https://app.shortcut.com/sefaria/story/43976) — moving the
~10 GB git history out of `Sefaria/Sefaria-Export` into a separate archive repo.

**These scripts are run once, by a maintainer, by hand.** They are not invoked by CI.
Read the design at `docs/superpowers/specs/2026-05-06-archive-git-history-design.md`
before running anything here.

## Prerequisites

- Push access to `Sefaria/Sefaria-Export`.
- Push access to a *new, empty* `Sefaria/Sefaria-Export-Archive` repo on GitHub.
- `git-lfs` installed (`brew install git-lfs && git lfs install`). The repo has
  one historical Git LFS object (`links/links.csv`, ~106 MB); a plain mirror
  clone/push copies the LFS pointer but not the object itself.
- **SSH access to GitHub is preferred over HTTPS for Phase 1.** HTTPS pushes
  are capped at roughly 2 GB per push; this repo's ~14 GB of history requires
  many chunked pushes over HTTPS, which works but is slower. If SSH is set up
  on the maintainer's machine, use an SSH `ARCHIVE_URL`
  (`git@github.com:Sefaria/Sefaria-Export-Archive.git`) — it has no per-push
  size ceiling and the migration completes faster.
- All open PRs against `Sefaria-Export` resolved or PR authors notified.
- Branch protection on `master` temporarily relaxed (or admin override available).
- The monthly `generate-books-json` workflow is paused or in a quiet window — a
  push to master while Phase 2 is running will trip `--force-with-lease` and
  abort the migration partway. Re-enable after Phase 2 completes.
- A scratch directory with ~25 GB free disk (accounting for the ~10 GB mirror,
  a working clone, and the LFS object cache — the historical LFS object adds
  ~106 MB on its own, but budget generously).

## Order of operations

1. `01_create_archive.sh` — mirror current repo into the archive repo. Non-destructive
   to the source. Run this first; verify the archive looks right before continuing.
2. `02_orphan_master.sh` — replace `master` of `Sefaria-Export` with a single orphan
   commit containing the current tree. **Destructive.** Force-pushes. Prompts before
   doing it.

After Phase 2, follow Phase 3 of the design doc (README/CLAUDE.md updates as a normal
PR) and Phase 4 (announcement).

### Why not `git push --mirror`?

An earlier version of `01_create_archive.sh` used `git push --mirror` for Phase 1.
It was run once against the real repos and **failed** for two distinct reasons:

1. A `--mirror` clone of a GitHub repo pulls in the read-only `refs/pull/*`
   namespace (this repo has 21 such refs). GitHub rejects pushes to
   `refs/pull/*`, and `--mirror` tries to push every ref it has, so the
   whole push is refused.
2. Even excluding `refs/pull/*`, this repo's ~14 GB of history in one HTTPS
   push exceeds GitHub's ~2 GB per-push limit (`HTTP 500` / `unexpected
   disconnect while reading sideband packet`).

The script now pushes `refs/heads/*` and `refs/tags/*` explicitly, with
`master` pushed incrementally in small commit chunks (falling back to
commit-by-commit on a chunk that fails). `refs/pull/*` is intentionally
never touched.

`02_orphan_master.sh`'s pre-flight probes the archive's Git LFS batch API before
doing anything destructive. If the design doc's "Archive this repository" (read-only)
step already ran on `Sefaria-Export-Archive` and this probe then fails, don't treat
it as a false alarm just because the repo is archived — confirm manually first
(`git clone --mirror` the archive and run `git lfs fetch --all`) before assuming
the gate is wrong rather than the LFS migration being incomplete.

## Resuming a failed Phase 1

Phase 1 pushes `master` incrementally in commit chunks, then the remaining
`refs/heads/*` and `refs/tags/*`. The script is resumable: on startup it reads
the archive's current `master` tip via `git ls-remote` and only pushes commits
past that point, so re-running `01_create_archive.sh` after a failure re-pushes
only what is missing rather than starting the ~14 GB transfer over.

To skip the re-clone too, point the script at the existing workdir:

```bash
WORKDIR=/path/to/previous/run ./01_create_archive.sh
```

Note that `refs/pull/*` refs are intentionally not mirrored — GitHub's
`refs/pull/*` namespace is read-only and cannot be pushed, so the archive will
not carry PR refs. This is expected, not a sign of an incomplete migration.

## Recovery

If anything goes wrong after Phase 2:

```bash
# The pre-migration tip is preserved as the tag pre-migration-master in the archive.
git clone --mirror git@github.com:Sefaria/Sefaria-Export-Archive.git
cd Sefaria-Export-Archive.git
git push --force git@github.com:Sefaria/Sefaria-Export.git refs/tags/pre-migration-master:refs/heads/master
```

This restores the ref, but **not the Git LFS objects** — a mirror push moves
pointer blobs, not the LFS objects themselves. Also restore LFS content back
onto the target repo:

```bash
git lfs fetch --all
git lfs push --all git@github.com:Sefaria/Sefaria-Export.git
```

This restores `Sefaria-Export` to its pre-migration state.
