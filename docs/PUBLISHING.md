# Publication record and future updates

[deekay71/agent-knowledge](https://github.com/deekay71/agent-knowledge) was created and pushed as
**public**, default branch **main**, after explicit owner/name/visibility approval. GitHub API
verification on 2026-10-17 UTC confirmed commit
`67e8bfb22a3281092c0e4bded0a3b702b279b486`, only main on the remote, and zero Actions runs/checks.
No CI workflow, branch protection, collaborator invitation or real-project integration was installed.
This is a recorded publication result, not a promise that later remote state is unchanged.

The public branch starts at a sanitized, tested root snapshot. Earlier development commits remain
on the original local `contrib/mvp` branch and were not pushed; that branch is not a base for public
updates. Its old validation captures contain machine paths. The public snapshot retains normalized
captures and the same tested implementation tree without those earlier commits. A read-only audit
found no recognizable credentials, private project payload or handoff context in the public snapshot;
that audit is not a universal secret-scanning certificate. Demo histories remain reproducible through
scripts/demo.py.

## Updating the existing public repository

The viewer release uses `contrib/local-graph-viewer`, starting from approved MVP
`5b31849749ddde53601d3dab359112707860b50e`. On 2026-10-18 the user additionally approved
publishing P1 `302c7c66cd318c31a4121aee6f306400c04ff3ca`, P2
`4e439737bd3fb83ed4a594654bea1af899dbdaf2` and scoped release fixes to that same branch.
The permitted operation is a normal non-force push; main must remain unchanged. This
does not authorize a new phase, branch-protection changes or updates to consuming projects.
See the [release checklist and evidence](VIEWER-RELEASE-20261018.md).

Start new contrib/ branches or worktrees from the accepted public main lineage. Review canonical
changes and their generated vault together. Use history-aware lint against the actual pre-change
baseline, applicable tests and staged hook validation; see [README](../README.md) and [HOOKS](HOOKS.md).
A docs-only change still needs link/command checks and staged validation, not invented model tests.

Push only the reviewed branch/commit within the user's authorized scope. Never use `--all` or
`--mirror`: local development branches may contain history that was deliberately kept private.
Use normal non-force pushes, inspect unexpected remote changes instead of overwriting them, and
verify the remote SHA after publication. A local commit or an earlier approval to create the repo
is not permission to publish every future change. Do not recreate the existing repo or change its
visibility, auth, sharing settings or branch protections as part of an unrelated documentation edit.

For a real consuming project, publish the accepted wiki commit first and verify it can be fetched;
only then bump the project's gitlink. No project update follows automatically. See
[SUBMODULES.md](SUBMODULES.md).

## Review scope before sharing

All readers of this public repo can read included raw sources and public history. Keep handoff
context, personal notes, customer/project-private content, tokens and local caches outside it.
Folders and exported vaults are not permission boundaries. Inspect files and reachable history;
removing a sensitive file from the latest tree does not remove earlier copies. Preserve local work
when preparing a separate publication snapshot; do not silently rewrite another working tree.

GitHub connector access, browser login and local Git/CLI authentication are separate. If a later
publish task lacks the required access, report that specific blocker. Do not extract tokens from
other apps, put credentials in chat/command arguments, or change accounts to bypass it. The wiki
scripts themselves perform no authentication or remote publication.
