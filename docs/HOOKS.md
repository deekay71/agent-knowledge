# Automatic hooks — local implementation, 2026-10-16

Two independent layers are provided: Git commit validation and Codex lifecycle workflow.
They do not automatically ingest sources, archive chat, mark knowledge verified, fetch, push,
change a pin or publish. The Git hook is enabled per clone. Codex requires its own trust step.

## Git hooks

```sh
python3 scripts/git_hooks.py install
python3 scripts/git_hooks.py status
python3 scripts/git_hooks.py check
python3 scripts/git_hooks.py uninstall
```

Use `--root /absolute/wiki` BEFORE the subcommand when invoking from elsewhere. Install sets
only this repository's `core.hooksPath` to `.githooks`; it does not edit global Git config.
It refuses existing/inherited custom hook configuration and active default hooks rather than
replace them. Uninstall restores the prior absence of local configuration and preserves files.
Linked worktrees share repository-local Git configuration; each must contain the committed
hook scripts. New clones need their own install. Use status to diagnose runtime files/config.

`pre-commit` automatically validates the **staged snapshot**, including Git's alternate index
for partial commits. Unstaged files cannot hide a staged error, and unstaged edits are preserved.
The validator uses the trusted working-checkout Python code; staged scripts are never executed.
Source bytes and log prefix are compared to HEAD, and incoming events/raw to every recorded
merge parent. New knowledge writes require an attached contrib/ branch. Errors block commit;
warnings are visible but do not prove semantic truth or sharing rights.

Git invokes pre-merge-commit before it writes MERGE_HEAD in this tested Git version. Therefore
an automatic merge commit is stopped safely if parent metadata is unavailable. Finish the staged
merge with `git commit`; its pre-commit hook can then validate every recorded parent. Prefer:

```sh
git merge --no-commit --no-ff contrib/topic
# Resolve each conflict, preserve both log streams, regenerate index, then stage resolved files.
git commit
```

No hook reset/clean/stash is performed. Git hooks are a local guard, not branch protection: Git
options/config can bypass them. Keep the same checks in eventual CI and review staged hook-code
changes. Do not delete old raw/log history to make the check pass.

## Codex lifecycle hooks

`.codex/hooks.json` registers the following **command hooks** for this wiki repo:

| Event | Automatic behavior |
|---|---|
| SessionStart | Supplies a concise policy/navigation reminder, also after resume/compact |
| UserPromptSubmit | Suggests up to five candidate page paths; exact versions must come from task/project context |
| Stop | Checks changed wiki against HEAD; asks for one repair/review pass when invalid. For other repository changes, asks once whether reusable learning should be proposed locally |

`stop_hook_active` prevents repeated continuation. Clean repositories need no follow-up, including tasks that already committed every change.
For valid wiki changes, Stop reports structural success as a UI advisory; this message alone
does not force another model pass. It reminds about semantic review.
The Stop continuation may consume one ordinary additional agent pass per changed turn; no separate
LLM API is called. Unrelated pre-existing changes must not be repaired or ingested by that pass.

The handler is `scripts/agent_hooks.py`; it reads one JSON event from stdin and returns JSON.
It never opens transcript_path or persists the prompt. Candidate paths are data, not instructions;
raw bodies/claims are not injected as developer instructions. Invalid metadata/path layout gives
advisory feedback. This does not replace source-level review or selectively reading relevant pages.

Current [official Codex documentation](https://learn.chatgpt.com/docs/hooks) supports project
`.codex/hooks.json`, these lifecycle events and command handlers. Project configuration must be
trusted, and every new/changed hook definition requires review/trust before the host runs it.
In the native Codex CLI, use **`/hooks`** to inspect/trust/disable definitions. `/hooks` belongs to
Codex itself; this repo has not registered a `/wiki` slash command. No trust-bypass flag is used.
Cloud orchestration does not run local command hooks; use a supported local Codex session.

Open/start Codex with **agent-knowledge as the project/cwd**, not its parent task directory, then
review/trust the three definitions. This task's cwd is the parent directory, so creating this file
alone does not prove the current chat loaded it. There is no automatic global installation.

Bundled local CLI verified: `0.162.0-alpha.17.2`, `features list` reports `hooks stable true`.
Handler tests and the configured shell command were executed, including paths with spaces and
subdirectories. Native host discovery/trust and end-to-end model activation remain unverified;
do not describe them as live until the host hook panel/event stream shows successful runs.

## Consuming projects and Claude

For an explicitly selected consuming project, merge the entries in
[templates/codex-project-hooks.json](../templates/codex-project-hooks.json) into its existing
`.codex/hooks.json` rather than overwrite other hooks. The template routes to
`knowledge/shared/scripts/agent_hooks.py`. Initialize the pinned submodule first and review/trust
that project's definitions. No real project was modified during this task.

This implementation registers Codex hooks. CLAUDE.md still points to the shared policy, but no
Claude lifecycle config or installable LLM Wiki SKILL.md has been created. Skill-based discovery
and Claude hooks would be separate, explicitly tested integrations.
