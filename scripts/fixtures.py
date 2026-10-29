"""Synthetic evidence only; not Unity guidance and not an LLM evaluation."""
import datetime as dt
import json
from pathlib import Path
import wiki


def write(p, metadata, body):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('---json\n' + json.dumps(metadata, indent=2) + '\n---\n' + body)


def seed(root, revision=1):
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    source = f'raw/fixture-v{revision}.md'
    write(root/source, dict(origin=f'synthetic:queue-spec-v{revision}', collected_at=today, scope='shared', version=f'FixtureQueue/{revision}', permission='synthetic-fixture'), f'# Synthetic queue spec v{revision}\nFixture only. Queue capacity is {8 if revision == 1 else 16}.\n')
    sources = ['raw/fixture-v1.md'] + ([source] if revision == 2 else [])
    versions = [f'FixtureQueue/{i}' for i in range(1, revision+1)]
    # Only v2 adds the migration inference; the summary must not claim it before then.
    summary = 'Synthetic version-scoped queue capacity.' if revision == 1 else 'Synthetic version-scoped capacity and migration lesson.'
    m = dict(id='queue-capacity', title='Fixture queue capacity', summary=summary, scope='shared', tags=['fixture', 'queue'], status='draft', sources=sources, updated_at=today, applies_to=versions, fixture=True, claims=[dict(kind='evidence', text=f'Synthetic queue capacity is {8 if i == 1 else 16}.', sources=[f'raw/fixture-v{i}.md'], applies_to=[f'FixtureQueue/{i}']) for i in range(1, revision+1)])
    if revision == 2:
        m['contradictions'] = [dict(status='open', sources=sources, resolution='8 vs 16: scope by explicit version; migration equivalence remains unreviewed.')]
        m['claims'].append(dict(kind='inference', text='Consumers may need capacity migration checks; this is an inference, not source evidence.', sources=sources, applies_to=versions))
    write(root/'wiki/concepts/queue.md', m, '# Fixture queue capacity\nSynthetic fixture, not production knowledge.\n\n' + '\n'.join(f'- [Source v{i}](../../raw/fixture-v{i}.md): capacity {8 if i == 1 else 16} for FixtureQueue/{i}.' for i in range(1, revision+1)) + '\n\nSee [version lesson](../lessons/versioning.md).\n')
    write(root/'wiki/lessons/versioning.md', dict(id='version-lesson', title='Fixture version lesson', summary='Preserve version boundaries when synthesizing.', scope='shared', tags=['fixture'], status='draft', sources=['raw/fixture-v1.md'], updated_at=today, applies_to=['FixtureQueue/1'], fixture=True, claims=[dict(kind='inference', text='Keep explicit version boundaries in answers.', sources=['raw/fixture-v1.md'], applies_to=['FixtureQueue/1'])]), '# Fixture version lesson\nInference from this fixture only. See [capacity concept](../concepts/queue.md).\n')
    if not (root/'wiki/log.md').exists(): (root/'wiki/log.md').write_text('# Wiki log\n')
    wiki.record(root, 'ingest', f'Synthetic v{revision}: source and existing concept synthesis updated; review pending')
    (root/'wiki/index.md').write_text(wiki.index_text(root))
