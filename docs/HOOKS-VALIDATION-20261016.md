# Hook implementation validation — 2026-10-16

Baseline: 248d44f92f89bf358ee916335d46b585b6751a5d. Scope: this independent local wiki repo.

## Implemented and enabled

Git pre-commit and pre-merge-commit handlers installed in this clone using local
`core.hooksPath=.githooks`. Status reports installed=true and active=true. Existing custom hooks
were absent; no global settings were modified. Reinstall/status/uninstall are documented in
[HOOKS.md](HOOKS.md). Real Git commit tests exercise the installed hooks without bypass flags.

The hook validates the staged snapshot, including an alternate index for partial commits.
Raw bytes/log events are checked against HEAD and all recorded merge parents. No staged script
is executed. Dirty/unstaged/untracked/ignored user files are preserved. Warnings are advisory.
Automatic merge commits pause safely before parent metadata is available; a subsequent git commit
validates the prepared merge. A three-parent test verifies incoming raw deletion is rejected.

## Codex configuration and handler tests

`.codex/hooks.json` defines SessionStart, UserPromptSubmit and Stop. The handler supplies workflow
context, suggests candidate paths without source-body injection, and requests at most one
follow-up for changed invalid wiki or learning review on a dirty project. It never reads transcripts,
saves prompt/chat text, auto-ingests shared knowledge, publishes or changes a project pin.
The consumer template routes to an explicitly attached knowledge/shared submodule.

Bundled native CLI was found under ChatGPT.app: version 0.162.0-alpha.17.2, feature hooks stable true.
This confirms local feature availability only. **Native discovery/trust/end-to-end model activation
has not been run.** The current session cwd is the parent task directory. Start/open the wiki repo
as a local Codex project and review/trust its three definitions in /hooks. Trust is not bypassed.
Local command hooks are not supported with cloud orchestration according to the linked official docs.

## Tests and independent review

Full suite: 118 tests passed; [test output](evidence/hooks-tests-20261016.txt).
New coverage: 26 Git-hook tests and 20 lifecycle tests, plus existing 72 tests.
[Process smoke and enabled Git status](evidence/hooks-smoke-20261016.json).
Lifecycle tests directly feed synthetic events and execute configured shell commands; they are
not native host activation tests. No external model API or remote publication was invoked.

Independent review found and confirmed fixes for unborn HEAD detection and consumer projects
with an unrelated root wiki directory. Review also checked event output schema, bounded Stop
continuation, subdirectories, private/transcript isolation and source/log history checks.
A test-fixture-only failure in an octopus merge test was corrected before the final passing run.

## Limits

Native Codex hook trust remains a user-controlled activation step. Existing sessions may need
reopening with the correct project root. New clones require local Git-hook installation.
Stop observes current dirty state; tasks that committed every change do not get a learning
follow-up. Successful wiki validation uses a UI advisory, not a forced model continuation.
A changed turn can add one ordinary model pass. Failures outside task scope should be reported,
not repaired automatically. No guarantee that a model will obey a workflow hint.

This does not register /wiki, install a SKILL.md, configure Claude lifecycle hooks, attach a real
project, or prove semantic truth/rights/secrecy. Local Git hooks can be bypassed, and working-tree
hook code must remain trusted. See HOOKS.md and prior deep review for retained limits.
