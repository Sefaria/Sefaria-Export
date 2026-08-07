# Sefaria-Export history-split migration

Runbooks for [sc-43976](https://app.shortcut.com/sefaria/story/43976) — moving the
~10 GB git history out of `Sefaria/Sefaria-Export` into a separate archive repo.

**These scripts are run once, by a maintainer, by hand.** They are not invoked by CI.
Read the design at `docs/superpowers/specs/2026-05-06-archive-git-history-design.md`
before running anything here.

## Prerequisites

- Push access to `Sefaria/Sefaria-Export`.
- Push access to a *new, empty* `Sefaria/Sefaria-Export-Archive` repo on GitHub.
- All open PRs against `Sefaria-Export` resolved or PR authors notified.
- Branch protection on `master` temporarily relaxed (or admin override available).
- The monthly `generate-books-json` workflow is paused or in a quiet window — a
  push to master while Phase 2 is running will trip `--force-with-lease` and
  abort the migration partway. Re-enable after Phase 2 completes.
- A scratch directory with ~25 GB free disk.

## Order of operations

1. `01_create_archive.sh` — mirror current repo into the archive repo. Non-destructive
   to the source. Run this first; verify the archive looks right before continuing.
2. `02_orphan_master.sh` — replace `master` of `Sefaria-Export` with a single orphan
   commit containing the current tree. **Destructive.** Force-pushes. Prompts before
   doing it.

After Phase 2, follow Phase 3 of the design doc (README/CLAUDE.md updates as a normal
PR) and Phase 4 (announcement).

## Resuming a failed Phase 1

Phase 1's `git push --mirror` is the single 10 GB transfer; if it drops mid-way,
re-running `01_create_archive.sh` from scratch re-clones from the source. To skip
the re-clone, point the script at the existing workdir:

```bash
WORKDIR=/path/to/previous/run ./01_create_archive.sh
```

Or, manually from inside the existing `Sefaria-Export.git/` mirror:

```bash
git push --mirror   # remote was already set by the previous run
```

## Recovery

If anything goes wrong after Phase 2:

```bash
# The pre-migration tip is preserved as the tag pre-migration-master in the archive.
git clone --mirror git@github.com:Sefaria/Sefaria-Export-Archive.git
cd Sefaria-Export-Archive.git
git push --force git@github.com:Sefaria/Sefaria-Export.git refs/tags/pre-migration-master:refs/heads/master
```

This restores `Sefaria-Export` to its pre-migration state.
