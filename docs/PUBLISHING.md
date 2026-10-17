# Publishing this repository

The user approved **GitHub `deekay71/agent-knowledge`, public** on 2026-10-17 UTC.
The publication branch starts at a tested, sanitized MVP snapshot. Earlier development commits
remain on the local `contrib/mvp` branch and are not part of the intended public push. Push only
the selected `main` branch, never `--all` or `--mirror`. Continue future contributions from the
published `main` lineage using fresh `contrib/...` branches/worktrees.

Local implementation, tests and commits do not publish anything. Confirm the host, owner,
repository name and private/public visibility before creating a remote. The proposed name is
`agent-knowledge`; it is not an authorization to select visibility. No credentials belong in chat,
this repository, export files or command arguments.

Before publication, inspect tracked files and reachable commit history, run tests, history-aware
lint and `export_vault.py --check`, then review the committed result. Keep the original handoff
context, sandbox projects, personal notes and local caches outside this repository. Raw sources
are included in the repository and vault; all readers can access them and Git history.

The local development history contains synthetic fixtures and validation records. A read-only audit found
no recognizable credentials or private project payload, but older test captures contain local
workspace and temporary paths. The latest copies redact those machine paths; previous commits
retain them. This is not a formal secret-scanning certificate. A new root snapshot for the public
branch preserves the tested tree without publishing those earlier development commits; the local
development branch is retained. Demonstration histories remain reproducible through scripts/demo.py.

When the destination and visibility are approved and `gh` is authenticated as the intended owner:

```sh
gh api user --jq .login
git status --short
python3 -m unittest discover -s tests -v
python3 scripts/wiki.py lint --base HEAD
python3 scripts/export_vault.py --check
```

Check that the requested new repository does not already exist before creating it. Create the
empty remote with the approved visibility and add it as `origin`; never overwrite an existing
remote or reuse a populated repository without reviewing it. Push the tested commit to `main`
with a normal non-force push, set the remote default branch to `main`, and verify the remote SHA
and visibility. The local `contrib/mvp` branch may remain the authoring branch.

No branch protection, collaborator invitations, paid usage, real-project submodule installation,
automatic sync or application plugins are included in this publication step. Future project
integration follows [SUBMODULES.md](SUBMODULES.md) after choosing a real consuming project.

GitHub connector access and local Git/CLI authentication are separate capabilities. If the
connector cannot create repositories and `gh` is not authenticated, complete local preparation
and report that blocker. The user can sign in with `gh auth login` or provide an authorized
empty remote and a supported write path; do not extract tokens from other applications.
