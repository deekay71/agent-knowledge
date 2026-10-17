# Portable vault validation — 2026-10-17 UTC

## Implemented

`scripts/export_vault.py` creates a deterministic Markdown reading vault with YAML properties,
source links, evidence/inference/unknown labels, version scope, contradiction records and
supersession links. `Home.md` provides navigation; `graph.json` preserves relationship types;
the manifest hashes inputs and generated output. The starter vault has **6 Markdown notes**
plus graph JSON and manifest. All starter knowledge remains synthetic fixtures.

Check is read-only. Refresh refuses edited/unrecognized output and file/directory shape changes,
preserves local `.obsidian/` preferences, and rolls back ordinary write failures. Canonical
raw/wiki bytes are not changed by export. The installed Git hook validates the staged vault
against staged canonical inputs using trusted live validator code. Source fixtures now use UTC
dates to match lint and avoid local-midnight failures.

## Tested

- `python3 -m unittest discover -s tests -v`: **154 tests passed** in 48.785 seconds;
  [captured output](evidence/vault-tests.txt). This includes 24 exporter tests and 12 new
  staged-vault integration tests, plus all earlier wiki, Git and agent-handler regressions.
- `python3 scripts/export_vault.py --check`: passes; [result](evidence/vault-check.json).
  Input digest: `4f57f85415e52a56b2fec309b38dfc259577a90dfaae1da9c17b0f1f0f58d106`.
- Canonical `lint --base HEAD`: no errors or warnings; history checked.
- Ruby Psych independently parsed standard YAML front matter in all six Markdown notes;
  [result](evidence/vault-yaml.txt). No Python package dependency was introduced.
- Real Git commits reject stale staged views, accept rebuilt/staged views, honor alternate
  indexes, and preserve unstaged content. Malicious staged exporter code stays inert.
- `scripts/demo.py` ran again with real local repositories and submodules. A and B retain
  different commits and different vaults; updating/rolling back A does not update B.
  [Full result](evidence/vault-demo.json):
  - A / v2: `08e600e290265689017640a509035368911db18a`
  - B / v1: `e85b0bcedd2074fea97250622438097d58f2cfed`
  - Raw v1 remained byte-identical, SHA-256
    `5187ff91b913a7a8a392abf4b3edb91ee2038f61bba6755eca27a383bb1c40e2`.
  - A's view includes capacity 16 and labeled migration inference; B retains v1 capacity 8.
  - Review/evidence records are included as Markdown notes; canonical contradiction handling
    and project-local separation remain covered.

Independent read-only review found and verified fixes for a reserved Home filename collision,
refresh rollback across file/directory transitions, entity text escaping, code examples being
treated as graph links, and an unclosed fence hiding generated claims. Regression tests cover
these cases. The initial 153-test run was superseded by the 154-test run above after adding the
unclosed-fence regression. All source editing finished before the final suite.

## Limits and publication

No Obsidian GUI, Logseq GUI or other native reader was launched or evaluated. The output uses
standard YAML and relative Markdown links; actual graph/rendering support depends on the app.
Inline Markdown links are supported; full CommonMark, arbitrary attachments, reference links,
wikilinks and every HTML/code-container form are not a general-purpose parser contract.
The exporter fails rather than making a portable copy with unsupported local targets.
The public fixture vault is small by design, not a production knowledge corpus.

No autonomous LLM synthesis or native Codex hook activation evaluation was performed. Handler
tests and static adapters are distinct from host lifecycle activation. Export does not run
Obsidian plugins, configure sync, grant access, ingest chats or promote claims to verified.

The user selected `deekay71/agent-knowledge` public. Publication uses a new root snapshot of
the tested tree; the earlier local development branch remains intact. Older development
captures contain machine paths, so only the sanitized publication branch is intended for push.
Current copies of review-help.txt and review-smoke.json redact those path strings; their
recorded commands/results otherwise retain the earlier evidence. See [publication plan](PUBLISHING.md).
Remote creation and push must be confirmed by actual command/API results, not inferred from this report.
