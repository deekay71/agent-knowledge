# Integration, contributions and rollback

Only after target project and remote are approved, in a clean project:
```sh
git submodule add APPROVED_URL knowledge/shared
git -C knowledge/shared checkout --detach ACCEPTED_FULL_SHA
mkdir -p knowledge/project knowledge/inbox
# Add the project adapter template to existing root instructions; do not overwrite them.
git add .gitmodules knowledge/shared
git commit -m 'Pin shared knowledge'
```
Fresh checkout: `git clone --recurse-submodules PROJECT_URL` or
`git submodule update --init --recursive`. CI needs authorized credentials for both repos,
recursive checkout, access to the pinned commit and adequate history for baseline lint.
Never run `update --remote` automatically. Local file transport is enabled only per command
inside the synthetic demo, never globally.

To update or rollback, obtain the reviewed commit with an explicitly authorized fetch, then:
```sh
python3 /path/to/wiki/scripts/wiki.py --root /path/to/project pin FULL_SHA
git diff --submodule=log
git add knowledge/shared
git commit -m 'Update shared knowledge pin'
```
The pin command rejects dirty project/submodule, uninitialized submodules, missing SHA and
detached superproject, in-progress Git operations, and ignored-file overwrite collisions.
It does not recurse into nested submodules. Missing history is never fetched automatically. It deliberately leaves a gitlink diff for review. Rollback is the same
operation using a known old SHA; it does not delete history. CLI never performs network access.

For contribution, use a separate writable wiki clone (not the project submodule). A clean
main or detached source checkout may create a new contribution worktree; run `wiki.py --root CLONE worktree NEW_PATH contrib/TOPIC`.
Read POLICY.md, ingest and review there. Commit wiki first, review/merge, push the accepted
wiki commit only when publication is authorized, verify consumers can fetch it, then bump project.
For the local sandbox, commits need only exist in the local source repository.

Concurrent work: use independent worktrees and sequential integration; if conflicts occur,
follow POLICY.md reconciliation and test against both parents. Commit IDs isolate projects,
not filesystem permissions. Scripts cannot protect against an independent process racing edits;
CLI mutations fail when an exclusive per-checkout wiki-write.lock exists. Coordinate editors
and external Git separately; the lock cannot protect against tools that ignore it.

## Publication plan (not executed)
Confirm platform, owner, official name, private/public, authorized readers, reviewer/merger,
first target project and permitted document scope. Review full history for confidential material.
Create remote only after those decisions, add URL, push reviewed branch, configure review/CI
with owner consent, test recursive clone with intended account, then attach the real project.
