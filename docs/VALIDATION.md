# Local validation — 2026-10-15

This is the initial MVP record. Later results: [deep review](REVIEW-20261015.md),
[hooks](HOOKS-VALIDATION-20261016.md), and [portable vault](VIEWING-VALIDATION-20261017.md).

## Implemented
Independent repository; Markdown sources and linked concepts/lessons; shared agent policy;
JSON schema, workflow templates, source-aware exact-version retrieval, deterministic index,
append-only event recording, structural/history lint, safe local worktree and pin commands.
No external dependencies, model calls, network fetch in CLI, remote publication or real project changes.

## Tested
Environment: Python 3.14.8, Apple Git 2.50.1, macOS.
`python3 -m unittest discover -s tests -v`: **29 passed**, see [output](evidence/tests.txt).
`python3 scripts/wiki.py lint`: zero errors/warnings. Initial uncommitted repo has no history
baseline; historical checks were exercised in committed disposable repositories.
`python3 scripts/demo.py --output ../demo-final`: passed; see [result](evidence/demo.json).
Demo directories are outside the deliverable repo and remain inspectable in the task workspace.

Real Git/submodule results:
- A = cc989f21050bba030cc73e976c6d6c5ca4dcaf4b (v2)
- B = 65568d44c568ed418650ccd695bba943d39eed77 (v1)
- A upgrade, rollback and restore did not change B.
- Raw v1 SHA-256 remained ae754a1cd453de960f6054bc1562d6f87dee4fccfd846928701efff54d2a28d0.
- Query v1 cites v1; v2 cites v2; unknown versions return nothing; inference stays labeled.
- Added v2 source, updated existing synthesis/index/log; open contradiction detected then
  explicitly reconciled by version. Fixture review transition is scripted, never verified.
- Broken metadata/links/index, orphan pages, unapproved unreferenced raw, immutable raw changes,
  log rewrites, mismatched evidence versions, stale and contradiction cases covered.
- Dirty/detached guards, absent commit and uninitialized submodule rejection preserve work.
- Two real worktrees produce a merge conflict; test preserves both log streams, completes a
  two-parent merge, and rejects removal of incoming events.
- Root adapters checked structurally against the common policy.

Independent read-only agent review found unreferenced raw validation and malformed contradiction
handling gaps. Both corrected with regression tests. Two-parent log validation also corrected:
first-parent byte prefix plus ordered preservation of incoming events, with raw checks on both.

## Limits and proposed follow-up
No autonomous Codex/Claude session activation test or real LLM synthesis benchmark was run.
These are deterministic fixtures and real Git integration tests, not a model-quality evaluation.
Lint cannot prove semantics, detect every contradiction or secret, or establish legal permissions.
Metadata claims need review. Inline local file links are checked; external availability/anchors are not.
No enforced server branch protection or automatic hooks. Commands assume one writer per checkout;
OS-level races and adversarial external mutation are outside this MVP. Baselines must be trusted.
Read-only submodule query is supported; writes use separate contribution branches/worktrees.
Publication CI, real Unity knowledge and real project integration remain proposed.

## Blocked pending user choices
Remote platform/name/owner/visibility, authorized readers, reviewer/merger, first consuming project
and shareable source scope. No local implementation blocker remains. No remote was created/pushed.
