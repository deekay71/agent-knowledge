# Agent Knowledge — local LLM Wiki MVP

Independent shared knowledge repository. All initial pages are **synthetic fixtures**, not Unity
or production guidance. An agent synthesizes sources into linked concepts; Python provides
retrieval, navigation, structural lint and Git safety checks. No external service or dependency.
Requires Python 3.9+ and Git. Start with [policy](docs/POLICY.md), [schema](docs/SCHEMA.md),
[architecture](docs/ADR-001.md), [integration](docs/SUBMODULES.md), [CLI inventory](docs/CLI.md), [automatic hooks](docs/HOOKS.md), and [wiki index](wiki/index.md).

**Obsidian / Markdown view:** open the committed [vault/](vault/Home.md) folder as an
Obsidian vault, open `Home.md`, then **Graph view**. Notes and sources are connected by
standard Markdown links; no community plugin is needed. See [viewing guide](docs/VIEWING.md)
for other readers, refresh commands, and limitations. The vault is a generated reading view;
edit canonical knowledge through the contribution workflow. Native Obsidian GUI has not been
tested here. Keep personal notes outside `vault/`; `.obsidian/` preferences stay local.

```sh
python3 scripts/wiki.py query queue --version FixtureQueue/1
python3 scripts/wiki.py lint --base HEAD
python3 scripts/export_vault.py --check
python3 -m unittest discover -s tests -v
python3 scripts/demo.py --output /tmp/unique-wiki-demo
```
Demo output path must not already exist. It creates only disposable local repositories and no
network remotes; its submodules refer to the local synthetic wiki. Test copies do not alter this repo.

On a contribution branch after editing: `python3 scripts/wiki.py index`,
`python3 scripts/wiki.py record ingest 'Summary of source and synthesis change'`,
then `python3 scripts/wiki.py lint --base ACCEPTED_SHA --record`,
`python3 scripts/export_vault.py --refresh`, and review the diff.
Search requires an exact version; unsupported versions return no claims instead of guesses.
Read raw sources to validate returned citations. Queries return evidence/inference labels and structural-only validation warnings. They refuse
invalid metadata, source boundaries, log format and index drift before returning authored claims.

Layout: raw/ originals; wiki/ synthesized concepts and lessons; templates/ workflow forms;
docs/ policy, schema and ADR; scripts/ standard-library CLI and demo; tests/ automated checks.
Index is reproducible navigation. Log is append-only relative to the chosen baseline.
No full-text cache is needed at this scale; future caches belong in ignored .cache/.

AGENTS.md and CLAUDE.md point to one common policy. Optional Git hooks and Codex lifecycle hooks are implemented; see docs/HOOKS.md for per-clone
installation and host trust. There is no repository SKILL.md or registered /wiki slash command.
Knowledge ingestion and semantic review remain deliberate authoring workflows.
Demo/static tests check adapter contents; autonomous Codex/Claude behavior is a separate evaluation.
