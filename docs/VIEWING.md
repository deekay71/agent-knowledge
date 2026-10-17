# View the wiki in Obsidian or a Markdown reader

The portable vault is a generated reading view. Canonical knowledge remains in the repository's
`wiki/` and `raw/` directories with `---json` metadata. Edit those sources through the contribution
workflow, not the exported notes. There is no bidirectional sync.

## Generate and open

From the repository root:

```sh
python3 scripts/export_vault.py --check
```

The default output is `vault/`, a small committed derived view. In Obsidian, choose **Open folder
as vault**, select this repository's `vault` folder, and open `Home.md`. Use **Graph view** to
explore linked notes. No community plugin is required or installed by the exporter.
If `vault/` is absent, run `python3 scripts/export_vault.py` first. An existing vault must be
checked or explicitly refreshed; initial export never overwrites it.

To create a separate copy, choose a new output directory:

```sh
python3 scripts/export_vault.py --output /tmp/agent-knowledge-reading
python3 scripts/export_vault.py --output /tmp/agent-knowledge-reading --check
```

Open that directory as the vault. A copy is a snapshot; it does not track later source changes
until explicitly refreshed. Ordinary Markdown readers can open `Home.md` and follow relative
links, but support for properties, navigation and graphs varies. Compatibility with every
application is not guaranteed.

## What the view contains

- `Home.md` provides navigation into the exported wiki.
- `wiki/` and `raw/` retain their relative paths. Exported raw files are presentation copies;
  the original archived bytes remain in canonical `raw/`.
- Metadata is presented as standard YAML front matter with simple properties. Nested claims
  and contradictions become readable sections with source links, preserving evidence,
  inference, unknown, version scope and contradiction status.
- `supersedes` and `superseded_by` relationships become actual Markdown links.
- `graph.json` carries typed metadata relationships and SHA-256 provenance for inspection by
  tools. Obsidian's native graph shows note links, not the relationship types in this JSON file.
- Explicitly referenced Markdown review/verification records are included. Arbitrary attachments
  and links outside the exported notes are rejected instead of producing a broken portable copy.
  The supported link syntax is inline Markdown file links, HTTP(S), mailto and same-note anchors;
  reference-style links and wikilink syntax are outside this MVP's graph extraction contract.
  Code examples are preserved as literal text, with no graph edges. Close all fenced code
  blocks before export so they cannot hide generated claims and evidence links.

For a graph focused on knowledge, optionally exclude `Home.md`, `wiki/index.md` and
`wiki/log.md` using the Graph view filters. Navigation hubs otherwise connect many notes and
can dominate the picture. A graph edge shows a link; it does not certify a claim or settle a
contradiction. A content hash identifies bytes; it does not establish source truth or approval.

## Refresh safely

After updating canonical content on a `contrib/...` branch, regenerate the canonical index,
record the change in the log, and run history-aware lint with the accepted baseline before
refreshing the view. Follow [the shared policy](POLICY.md) for review and source permissions.

```sh
python3 scripts/wiki.py index
python3 scripts/wiki.py record ingest 'Describe source and synthesis changes'
python3 scripts/wiki.py lint --base ACCEPTED_FULL_SHA
python3 scripts/export_vault.py --refresh
python3 scripts/export_vault.py --check
```

Replace `ACCEPTED_FULL_SHA` with the actual accepted baseline commit. Use `--output PATH`
with both export commands when refreshing a separate copy. Review the resulting diff and
commit the default derived view with its source changes. In a pinned submodule, read its
committed vault; make contributions in a separate writable clone/worktree.

`--check` is read-only: it compares the current input fingerprint and generated files to detect
stale or changed output. It does not refresh anything. `--refresh` replaces only unchanged
managed output and refuses locally edited generated files or unknown files outside `.obsidian/`.
If refresh refuses, preserve your notes separately and reconcile useful edits into canonical
sources through review before retrying. Do not discard edits simply to make refresh pass.
File-to-directory shape changes require a new output directory. Refresh preflights all files
and rolls back ordinary write failures; it is not a power-loss transaction or an editor lock.
Coordinate with other writers and retry if source files change during export.

Installed Git hooks validate the staged vault against the staged source snapshot. After
editing knowledge, refresh and stage both canonical files and `vault/` before committing.
The hook reports drift instead of silently regenerating or staging files.

Obsidian preferences under `.obsidian/` are left untouched and ignored by the managed export.
Keep personal notes outside the generated tree. Export and refresh do not configure Obsidian
Sync, publish a vault, or grant access. Sharing an exported vault shares the included raw sources
too; export is not a redaction or permission boundary.

## Validation limits and references

File generation, provenance checks and local CLI tests are distinct from an actual app evaluation.
No Obsidian GUI session has been tested for this feature; static validity does not prove visual
rendering or native graph behavior in an installed version.

Official references: [links](https://obsidian.md/help/links),
[properties](https://obsidian.md/help/properties), and
[Graph view](https://obsidian.md/help/plugins/graph).
