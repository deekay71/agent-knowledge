#!/usr/bin/env python3
"""Reproducible real Git/submodule integration demo, no network or LLM calls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import fixtures
import export_vault
import wiki


def commit(root, message):
    wiki.git(root, 'add', '.')
    wiki.git(root, '-c', 'user.name=Local Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', message)
    return wiki.git(root, 'rev-parse', 'HEAD')


def run(out):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shared = out/'wiki'
    shared.mkdir()
    wiki.git(shared, 'init', '-b', 'contrib/demo')
    fixtures.seed(shared, 1)
    assert not wiki.lint(shared)['errors']
    raw_hash = hashlib.sha256((shared/'raw/fixture-v1.md').read_bytes()).hexdigest()
    export_vault.export(shared, shared/'vault')
    first = commit(shared, 'Fixture v1 synthesis')
    projects = []
    for name in ('A', 'B'):
        project = out/name; project.mkdir()
        wiki.git(project, 'init', '-b', 'demo')
        wiki.git(project, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(shared), 'knowledge/shared')
        (project/'knowledge/project').mkdir()
        (project/'knowledge/project/context.md').write_text('Private fixture project contract: local only.\n')
        (project/'knowledge/inbox').mkdir()
        (project/'knowledge/inbox/proposal.md').write_text('Draft, not automatically imported.\n')
        shutil.copy(Path(__file__).resolve().parents[1]/'templates/project-adapter.md', project/'AGENTS.md')
        shutil.copy(project/'AGENTS.md', project/'CLAUDE.md')
        commit(project, 'Pin v1 and add explicit knowledge adapters')
        projects.append(project)
    fixtures.seed(shared, 2)
    open_result = wiki.lint(shared, first)
    assert not open_result['errors'] and any('OPEN CONTRADICTION' in w for w in open_result['warnings'])
    page = shared/'wiki/concepts/queue.md'
    m, body = wiki.read_page(page)
    (shared/'docs').mkdir()
    (shared/'docs/fixture-review.md').write_text('# Fixture review\nScripted review transition only, not independent LLM validation.\nBoth synthetic sources describe distinct versions. Retain 8 for v1 and 16 for v2.\nMigration inference remains inference; production behavior is unknown.\n')
    m.update(status='reviewed', review_record='docs/fixture-review.md')
    m['contradictions'][0].update(status='resolved', resolution='Different explicit versions; preserve both claims. No assertion about cross-version migration.')
    fixtures.write(page, m, body)
    wiki.record(shared, 'review', 'Scripted fixture review: version-scoped reconciliation; no verified status')
    (shared/'wiki/index.md').write_text(wiki.index_text(shared))
    assert not wiki.lint(shared, first)['errors']
    export_vault.export(shared, shared/'vault', refresh=True)
    second = commit(shared, 'Fixture v2 reconciliation and preserved history')
    a, b = projects
    wiki.git(a/'knowledge/shared', '-c', 'protocol.file.allow=always', 'fetch', 'origin')
    wiki.pin(a, second)
    commit(a, 'Update A only to v2')
    assert wiki.git(b/'knowledge/shared', 'rev-parse', 'HEAD') == first
    assert hashlib.sha256((shared/'raw/fixture-v1.md').read_bytes()).hexdigest() == raw_hash
    assert not (shared/'knowledge/project/context.md').exists()
    v1 = wiki.query(b/'knowledge/shared', 'queue', 'FixtureQueue/1')
    v2 = wiki.query(a/'knowledge/shared', 'queue', 'FixtureQueue/2')
    assert v1[0]['claims'][0]['sources'] == ['raw/fixture-v1.md']
    assert v2[0]['claims'][0]['sources'] == ['raw/fixture-v2.md']
    assert not wiki.query(b/'knowledge/shared', 'queue', 'FixtureQueue/2')
    for project in projects:
        checkout = project/'knowledge/shared'
        export_vault.check(checkout, checkout/'vault')
    a_view = (a/'knowledge/shared/vault/wiki/concepts/queue.md').read_text()
    b_view = (b/'knowledge/shared/vault/wiki/concepts/queue.md').read_text()
    assert 'Synthetic queue capacity is 16.' in a_view
    assert 'Synthetic queue capacity is 16.' not in b_view
    assert '**inference**' in a_view
    wiki.pin(a, first); commit(a, 'Rollback A to v1')
    wiki.pin(a, second); commit(a, 'Restore A to v2')
    result = dict(wiki_v1=first, wiki_v2=second, A=wiki.git(a/'knowledge/shared','rev-parse','HEAD'), B=wiki.git(b/'knowledge/shared','rev-parse','HEAD'), raw_v1_sha256=raw_hash, open_contradiction_detected=True, rollback_tested=True, project_local_stayed_local=True, query_v1=v1, query_v2=v2, history_lint=wiki.lint(shared, first), evaluation='Scripted fixtures and real Git; no autonomous LLM evaluation')
    result['vault_snapshot_checked'] = True
    result['vault_A'] = export_vault.check(a/'knowledge/shared', a/'knowledge/shared/vault')
    result['vault_B'] = export_vault.check(b/'knowledge/shared', b/'knowledge/shared/vault')
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True, type=Path)
    print(json.dumps(run(p.parse_args().output), indent=2))
