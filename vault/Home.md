---
title: "Agent Knowledge"
generated: true
note_type: "navigation"
---

# Agent Knowledge

A portable reading view of the shared wiki. Current starter content is synthetic fixtures, not production guidance.

Open this folder as an Obsidian vault, then open **Graph view**. Nodes are notes; lines are internal links.

## Browse

- [Wiki index](wiki/index.md)
- [Operation log](wiki/log.md)

- [fixture-v1](raw/fixture-v1.md) — source
- [Fixture queue capacity](wiki/concepts/queue.md) — wiki
- [Fixture version lesson](wiki/lessons/versioning.md) — wiki

## Reading and maintenance

Check exact versions and evidence/inference/unknown labels. A graph connection is not a claim of correctness. Open contradictions remain visible in their notes.

This is a generated view, with no bidirectional sync. Edit canonical raw/wiki files through the repository contribution workflow. Never edit an archived raw source; add a new version. Refresh using `python3 scripts/export_vault.py --refresh` from the repository root. Local edits here block refresh and must be preserved separately first.

Obsidian settings in `.obsidian/` remain local. No plugins, network service or account is required by the exporter. Other Markdown readers can follow relative links; graph/properties support depends on the app.

For a focused graph, filter out `Home`, `wiki/index` and `wiki/log`. Native graph edges are untyped; `graph.json` retains relationship types for other tools.
