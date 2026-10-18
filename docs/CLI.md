# CLI, skill and trigger inventory — updated 2026-10-18

Hook additions: `python3 scripts/git_hooks.py [--root ROOT] {check,install,status,uninstall}` (`check` also supports `--merge` for the pre-merge hook);
`python3 scripts/agent_hooks.py` receives lifecycle JSON on stdin. See [HOOKS.md](HOOKS.md).
The original six wiki.py subcommands below remain unchanged.

Portable reading view: `python3 scripts/export_vault.py [--root ROOT] [--output PATH] [--check | --refresh]`.
Initial export requires a new destination (default `ROOT/vault`). Check is read-only; refresh
updates only an unchanged managed export. See [viewing guide](VIEWING.md). When a vault is
tracked, Git hooks also validate its staged projection against staged canonical inputs.

Local canonical viewer: `python3 scripts/viewer.py [--root ROOT] [--port PORT] [--check]`.
Default port 8765; bind is fixed to `127.0.0.1`. Port 0 selects an available port; use the printed
URL. `--check` prints a snapshot summary and structural diagnostic counts without starting HTTP or exporting files.
There is no `--export` or host override. It reads canonical raw/wiki (excluding wiki/log.md),
not the generated vault. See [viewer guide](VIEWER.md) for filters, provenance and resource limits.
Its help and starter `--check` have been run; browser/security/performance validation is separate.
Grouping, saved layouts, opt-in refresh, revision comparison and confirmed JSON/PNG download
are browser controls, not new CLI subcommands. Comparison uses the same loopback server's
read-only `/api/compare?base=FULL_SHA&target=FULL_SHA`; both revisions must be in local HEAD
ancestry and pass the confined history/snapshot checks. Browser exports do not write canonical
files or update the portable vault. See the guide for scope and limits.

This inventory is derived from actual argparse help and subprocess smoke tests, not proposed commands.
See [captured help](evidence/review-help.txt), [smoke results](evidence/review-smoke.json) and
[deep review](REVIEW-20261015.md). Run from the independent agent-knowledge repository:

```sh
python3 scripts/wiki.py --help
```

Global syntax: `python3 scripts/wiki.py [--root ROOT] COMMAND ...`.
`--root` must appear BEFORE COMMAND. Default root is the repository containing scripts/wiki.py,
not the shell's current directory. Use an explicit project root for pin. Python 3.14.8 and Git 2.50.1
were tested; no third-party Python packages are required.

| Existing command | Exact arguments | Example | Validation |
|---|---|---|---|
| lint | `[--base BASE] [--merge-parent MERGE_PARENT] [--record]` | `python3 scripts/wiki.py lint --base HEAD` | Help, subprocess smoke, structural/history/merge regressions |
| index | none | `python3 scripts/wiki.py index` | Help, smoke, rename repair and failure rollback tests |
| query | `term --version VERSION [--record]` | `python3 scripts/wiki.py query queue --version FixtureQueue/1` | Help, smoke, exact version/source/private-path tests |
| record | `{ingest,review,maintain,query} detail` | `python3 scripts/wiki.py record ingest 'Added an authorized source and updated the concept'` | Help, smoke, Unicode/invalid log/lock tests |
| worktree | `path branch` | `python3 scripts/wiki.py worktree /absolute/new/wiki-contrib contrib/topic` | Help, smoke and real Git from main/detached/dirty sources |
| pin | `sha` | `python3 scripts/wiki.py --root /absolute/project pin FULL_LOCAL_COMMIT_SHA` | Help, real submodule upgrade/rollback/safety smoke tests |

Additional valid examples:
```sh
python3 scripts/wiki.py lint --base ACCEPTED_SHA --record
python3 scripts/wiki.py lint --base FIRST_PARENT --merge-parent SECOND_PARENT
python3 scripts/wiki.py query queue --version FixtureQueue/1 --record
python3 scripts/wiki.py record review 'Reviewed both sources; migration inference remains unresolved'
python3 scripts/wiki.py record maintain 'Reviewed stale page and retained unresolved evidence'
python3 scripts/wiki.py record query 'Persisted synthesis with explicit citations'
```

`record` only appends an event: it does not perform ingest, semantic review or maintenance.
wiki.py has no standalone `ingest`, `review`, `maintain`, `search`, `update`, `rollback`, `publish`,
`init` or `install` command. Search is query. Upgrade and rollback both use pin with a full local
commit SHA. Source ingestion/synthesis is an authoring workflow documented in POLICY.md.
`index` generates navigation and records an index event. `lint --record` records the result even
if structural checks fail; its exit code remains nonzero. Read-only lint/query do not change files.

Knowledge writes (index, record, query/lint with --record) require an attached `contrib/...`
branch, an initialized Git root and a valid log. They deliberately permit an authoring dirty tree.
Worktree requires a clean source, a new external destination without symlink components and a
new contrib/ branch; clean main/detached sources are supported. Pin requires a clean attached
superproject and clean initialized submodule. It rejects ignored-file overwrite collisions,
missing/abbreviated/non-commit SHAs and leaves only the gitlink diff for manual review/commit.
All wiki.py mutations use a cooperative per-checkout lock. They do not fetch, commit or push.
The separate exporter uses a per-output lock; demo.py deliberately creates local fixture commits.

Exit status: 0 success (lint warnings do not fail); 1 lint errors; 2 usage/safety/operational error.
No-baseline lint warns that history was not checked. Query returns at most five matching pages
in path order with scoped claims, citations, warnings and a structural-only validation label.
Query first runs structural checks of this small wiki; it is not ranked/vector search or an LLM.
An empty result is not proof that knowledge does not exist. No automatic inference saving occurs.

## Other executable entrypoints

`python3 scripts/viewer_demo.py --output NEW_DIRECTORY [--topics N] [--date YYYY-MM-DD]`
creates a separate synthetic canonical wiki for the viewer. Topics default to 8, range 1–200;
the optional date defaults to today in UTC and must not be in the future. Output must be new,
its parent must exist, and no destination path component may be a symlink. No Git initialization,
commits, network or model calls occur. Eight topics yield 49 viewer nodes and 227 explicit typed
edges. Example: `python3 scripts/viewer_demo.py --output ../viewer-demo --topics 8`.
Its help has been run; generated fixture counts are not performance guarantees.

Viewer `--check` returns 0 for an eligible snapshot with at most warnings/info, 1 when
the snapshot has error diagnostics such as missing declared sources, and 2 on fatal
validation, usage or operational errors. The demo generator returns 0 on success and 2 on error.
The HTTP viewer exits normally with Ctrl+C. It does not modify canonical files, the log, Git
state or the portable vault. The demo generator writes only its newly created destination.

`python3 scripts/demo.py --output NEW_DIRECTORY` is a separate demo CLI. Help and a full execution
were tested. It creates real local disposable repositories/submodules and commits synthetic fixtures.
Output directory must not already exist. Example: `python3 scripts/demo.py --output /tmp/wiki-demo-new`.
`scripts/fixtures.py` is an imported fixture helper, not a CLI (no parser or __main__ entrypoint).
`python3 -m unittest discover -s tests -v` runs the test suite.

## Skills, slash commands and auto-trigger

| Artifact | Exists in this repository? | Actual effect |
|---|---|---|
| SKILL.md for LLM Wiki | No | No installable/discoverable LLM Wiki skill is delivered or globally installed |
| Registered slash command | No | No /wiki, /ingest or other slash command is registered |
| AGENTS.md | Yes | Thin textual pointer to docs/POLICY.md for an agent that reads root instructions |
| CLAUDE.md | Yes | Same pointer; not an executable command registration |
| templates/project-adapter.md | Yes | Text to add deliberately to a consuming project's existing instructions |
| Git pre-commit / pre-merge-commit | Yes | Per-clone install; validates staged content automatically |
| Codex lifecycle hooks | Yes | .codex/hooks.json; project and hook trust required before host execution |
| Daemon / MCP / scheduled ingest | No | No background ingest |

The configured hooks can invoke checks/workflow automatically after installation/trust. Authoring
and semantic review remain deliberate actions; no autonomous shared ingest occurs. Whether a particular
host automatically loads AGENTS.md/CLAUDE.md is host behavior, not a tested activation guarantee.
Static adapter and handler integration tests passed; native Codex lifecycle activation after trust
and Claude task activation have not been tested.
The environment's resolving-merge-conflicts skill used in the earlier implementation is an external
session tool, not an LLM Wiki skill installed by this repo.

Proposed next step only: author a repository-local LLM Wiki SKILL.md referencing this single policy,
with scoped ingest/query/maintain triggers, then separately test host discovery and actual agent
behavior. No global skill installation or slash registration was requested or performed.
